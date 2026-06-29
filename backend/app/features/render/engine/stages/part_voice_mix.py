"""Per-part voice TTS + audio mix stage.

Sprint 6.D-2.5b — extracted verbatim from stages/part_renderer.py
(lines 283-513 of the post-2.5d file). No logic changes; pure relocation.

run_part_voice_mix() runs once per part during process_one_part,
immediately after the FFmpeg encode core (Sprint 6.D-2.5a's
run_render_encode) and before the finalize stage (Sprint 6.D-2.5c).

Block responsibilities (in order):
  1. SUBTITLE-source TTS path: when voice_enabled AND voice_source ==
     "subtitle" AND no manual voice already set. Resolves narration
     text from per-part SRT or full SRT in-memory slice. Calls
     generate_narration_audio(); on failure emits voice_failed with
     error_code=VOICE001 and continues (Sacred Contract #3-style:
     TTS is optional).
  2. TRANSLATED_SUBTITLE-source TTS path: when voice_source ==
     "translated_subtitle". Uses translated_srt_part first, falls
     back to original srt_part, then full SRT slice. Emits
     voice_translated_subtitle_tts_started/completed events.
     Falls back to the original-language SRT if translated SRT
     is missing (warns VOICE_TRANSLATED_SUBTITLE_MISSING).
  3. Audio MIX: if any voice path was resolved (manual ctx.voice_audio_path
     or per-part subtitle path), invokes mix_narration_audio(...) to
     burn the narration onto final_part. Uses os.replace(mixed_part,
     final_part) for atomic file swap. On failure cleans up the temp
     mixed file via _safe_unlink and emits voice_failed.

State mutations (by-reference pattern):
  - ctx.voice_part_tts_attempts.append(idx) — at TTS attempt sites.
  - ctx.voice_mix_ok.append(idx) — on successful mix completion.
  - part_manifest.narration_path = ... + write_manifest() — when
    a voice path is present.
  - final_part on disk: replaced by mix_narration_audio output.

Returns:
  None. The function operates entirely by side effect through ctx
  mutable lists, part_manifest field writes, and final_part replacement.

Sacred Contracts honored:
  - #3 AI return-None contract: TTS lives in app.services.audio.tts
       (not under backend/app/ai/**, so #3 doesn't apply cardinally),
       but the spirit holds: failures are caught locally, voice_failed
       events emitted with error_code=VOICE001, render continues.
  - #6 _emit_render_event signature: 8 call sites preserved verbatim
       (voice_tts_started, voice_tts_completed, voice_translated_subtitle_tts_started,
       voice_translated_subtitle_tts_completed, voice_failed [×3 instances],
       voice_subtitle_source_missing, voice_mix_started, voice_mix_completed)
       — total 9 emit events when counting both VOICE001 paths.
  - #7 Sole DB writer: 0 upsert_job_part calls.

VOICE001 error code preservation:
  All three voice-failure paths (subtitle TTS, translated_subtitle TTS,
  mix) emit voice_failed events with `context.error_code = "VOICE001"`.
  Per docs/RENDER_PIPELINE.md "What must not break: voice", "VOICE001
  error events must remain useful". The error code is preserved
  verbatim in this commit.

Cycle risk: NONE.
  Verified before extraction: run_part_voice_mix does not call any
  function in stages/part_renderer. The 12 module-level imports come
  from leaf packages (core.config, domain.manifests, audio_pipeline,
  pipeline_config, pipeline_segment_selection, render_events,
  part_render_context, services.audio_mix_service, services.manifest_writer,
  services.subtitle_engine, services.tts_service).

Logger note (same pattern as 6.D-2.1 through 2.5d):
  `logger = logging.getLogger("app.render")` preserved verbatim.
"""
from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path

from app.core.config import TEMP_DIR, _pick_bgm_file
from app.domain.manifests import BaseClipManifest
from app.features.render.engine.pipeline.audio_cleanup import _maybe_cleanup_narration_audio
from app.features.render.engine.pipeline.pipeline_config import extract_text_from_srt
from app.features.render.engine.pipeline.pipeline_segment_selection import _get_effective_playback_speed
from app.features.render.engine.pipeline.render_events import (
    _emit_render_event,
    _job_log,
    _safe_unlink,
)
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.features.render.engine.audio.mixer import mix_narration_audio, mix_with_bgm
from app.features.render.engine.stages.manifest_writer import write_manifest
from app.features.render.engine.subtitle.generator.srt import slice_srt_to_text, parse_srt_blocks
from app.features.render.engine.audio.tts import generate_narration_audio, clean_spoken_text
from app.features.render.engine.audio.timed_narration import synthesize_timed_narration
from app.features.render.engine.stages.part_reaction_freeze import (
    apply_reaction_freezes,
    plan_freeze_points,
    _probe_duration_s as _probe_part_duration,
)
from app.features.render.ai.llm.rewrite import rewrite_subtitle as _llm_rewrite_subtitle
from app.features.render.ai.llm.rewrite_prompts import format_segments_for_prompt
from app.features.render.engine.pipeline.llm_stage import _resolve_api_key as _resolve_llm_api_key

# Preserve original logger name (same pattern as 6.D-2.1 through 2.5d).
logger = logging.getLogger("app.render")


# ── Sprint AI-WF: RenderPlan.audio_plan.voice_provider consume helper ────────
#
# When ctx.render_plan is None (LLM_EMIT_RENDER_PLAN OFF) or the field
# is empty, falls through to the caller's payload-derived fallback —
# Sacred Contract #2 (default behaviour identical to baseline). When set,
# overrides the tts_engine for both TTS call sites in run_part_voice_mix.
#
# P3 wired:
#   - audio_plan.voice_enabled: wired via _resolve_voice_enabled_from_plan
#   - audio_plan.voice_provider: wired via _resolve_voice_provider_from_plan
# Sprint 1 wired (resolver only):
#   - audio_plan.bgm_enabled: resolver wired; full BGM mixing deferred to
#     Sprint 2.3 — full BGM mixing now wired via _resolve_bgm_mood_from_plan +
#     _resolve_bgm_volume_from_plan and mix_with_bgm() at end of voice block.
# Deferred (future sprint):
#   - audio_plan.cta_audio      (requires audio-mixer changes — cross-file)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_voice_provider_from_plan(ctx: PartRenderContext, fallback: str) -> str:
    """Return the tts_engine to use for this part.

    Returns ``render_plan.audio_plan.voice_provider`` when set (non-empty),
    otherwise the caller's payload-derived fallback value.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return fallback
    plan_provider = (rp.audio_plan.voice_provider or "").strip()
    if not plan_provider:
        return fallback
    return plan_provider


def _resolve_voice_enabled_from_plan(ctx: PartRenderContext, fallback: bool) -> bool:
    """Return the effective voice_enabled flag for this part.

    User's explicit opt-in (payload.voice_enabled=True) is sacred: the LLM
    prompt defaults audio_plan.voice_enabled=false (it judges narration as
    "extremely rare" for short-form viral clips), so if the AI plan were
    allowed to override an opted-in user, the user's chosen TTS would be
    silently dropped. Precedence: user-True wins; otherwise the plan's
    explicit value (when set) wins; else fall back to user's choice.
    """
    if fallback is True:
        return True
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return fallback
    plan_enabled = rp.audio_plan.voice_enabled
    if plan_enabled is None:
        return fallback
    return bool(plan_enabled)


def _resolve_bgm_enabled_from_plan(ctx: PartRenderContext, fallback: bool) -> bool:
    """Return the effective bgm_enabled flag for this part.

    Same precedence rule as voice: user explicit True wins over AI's default.
    """
    if fallback is True:
        return True
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return fallback
    plan_enabled = rp.audio_plan.bgm_enabled
    if plan_enabled is None:
        return fallback
    return bool(plan_enabled)


def _resolve_bgm_mood_from_plan(ctx: PartRenderContext) -> str:
    """Return AI-directed BGM mood or '' (no preference).

    Empty string means no AI BGM preference — caller should not attempt BGM.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return ""
    return (getattr(rp.audio_plan, "bgm_mood", "") or "").strip().lower()


def _resolve_bgm_volume_from_plan(ctx: PartRenderContext) -> float:
    """Return AI-directed BGM dB offset relative to vocal track.

    0.0 means "use platform default" (-18 dB). Positive values raise BGM,
    negative values lower it. Clamped to [-20, 6] to prevent extremes.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return 0.0
    raw = float(getattr(rp.audio_plan, "bgm_volume", 0.0) or 0.0)
    return max(-20.0, min(6.0, raw))


def run_part_voice_mix(
    ctx: PartRenderContext,
    idx: int,
    seg: dict,
    srt_part: Path,
    translated_srt_part: Path,
    final_part: Path,
    part_manifest: BaseClipManifest,
) -> None:
    """Execute the per-part voice TTS + audio mix block. See module
    docstring for the 3-step responsibility breakdown.

    Side-effect only: mutates ctx.voice_part_tts_attempts /
    voice_mix_ok lists, part_manifest.narration_path, and overwrites
    final_part with the mixed video.
    """
    # Alias preserves the original local variable name so the block
    # body below is byte-for-byte identical to the pre-2.5b code.
    _part_manifest = part_manifest

    _part_subtitle_voice_path = None
    # Reaction freeze-frame (Phase B): captured from the ai_rewrite segments so
    # the freeze post-pass at the end of this function can apply suspense holds.
    _reaction_segments: "list[dict] | None" = None
    _effective_voice_enabled = _resolve_voice_enabled_from_plan(
        ctx, getattr(ctx.payload, "voice_enabled", False)
    )
    _effective_bgm_enabled = _resolve_bgm_enabled_from_plan(
        ctx, getattr(ctx.payload, "bgm_enabled", False)
    )
    _bgm_mood = _resolve_bgm_mood_from_plan(ctx)
    _bgm_volume_offset = _resolve_bgm_volume_from_plan(ctx)
    _job_log(
        ctx.effective_channel,
        ctx.job_id,
        f"voice_mix.bgm_enabled={_effective_bgm_enabled} mood={_bgm_mood or 'none'} vol_offset={_bgm_volume_offset:+.1f}dB part_no={idx}",
        kind="debug",
    )
    if (
        _effective_voice_enabled
        and getattr(ctx.payload, "voice_source", "manual") == "subtitle"
        and ctx.voice_audio_path is None
    ):
        _part_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
        _part_srt_inmem_text: str | None = None
        if _part_srt is None and ctx.full_srt_available:
            try:
                _part_srt_inmem_text = slice_srt_to_text(str(ctx.full_srt), seg["start"], seg["end"])
                _part_srt = ctx.full_srt
                _job_log(ctx.effective_channel, ctx.job_id, f"voice.srt_in_memory part_no={idx} (no temp file written)", kind="debug")
            except Exception:
                _part_srt = None
        if _part_srt:
            _part_narration_text = _part_srt_inmem_text if _part_srt_inmem_text is not None else extract_text_from_srt(str(_part_srt))
            if _part_narration_text.strip():
                ctx.voice_part_tts_attempts.append(idx)
                _part_mp3 = str(TEMP_DIR / ctx.job_id / "voice" / f"part_{idx:03d}.mp3")
                if ctx.cancel_registry.is_cancelled(ctx.job_id):
                    raise ctx.cancel_registry.JobCancelledError()
                try:
                    _job_log(ctx.effective_channel, ctx.job_id, f"Generating AI narration for part {idx}/{ctx.total_parts} from subtitle", kind="debug")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_started",
                        level="INFO",
                        message=f"Generating AI voice from subtitle (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "language": ctx.payload.voice_language, "source": "subtitle"},
                    )
                    _part_subtitle_voice_path = generate_narration_audio(
                        text=clean_spoken_text(_part_narration_text, ctx.payload.voice_language),
                        language=ctx.payload.voice_language,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=_resolve_voice_provider_from_plan(
                            ctx, getattr(ctx.payload, "tts_engine", "edge")
                        ),
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_completed",
                        level="INFO",
                        message=f"AI voice from subtitle generated (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                    )
                    _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                        str(_part_subtitle_voice_path),
                        ctx.payload,
                        effective_channel=ctx.effective_channel,
                        job_id=ctx.job_id,
                        part_no=idx,
                        source="subtitle",
                    )
                except Exception as _part_tts_exc:
                    _part_subtitle_voice_path = None
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_part_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                    _job_log(ctx.effective_channel, ctx.job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"AI voice (subtitle, part {idx}) failed: {_part_tts_exc}",
                        step="voice.tts",
                        exception=_part_tts_exc,
                        traceback_text=traceback.format_exc(),
                        context={"part_no": idx, "error_code": "VOICE001"},
                    )
            else:
                _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} subtitle text empty; narration skipped", kind="warning")
        else:
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_subtitle_source_missing part_no={idx} source=subtitle; narration skipped", kind="warning")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_subtitle_source_missing",
                level="WARNING",
                message=f"Subtitle voice source missing for part {idx}; narration skipped",
                step="voice.tts",
                context={"part_no": idx, "source": "subtitle"},
            )
    elif (
        _effective_voice_enabled
        and getattr(ctx.payload, "voice_source", "manual") == "translated_subtitle"
        and ctx.voice_audio_path is None
    ):
        # P2 (2026-06-20): narration language is the VOICE language, decoupled
        # from the burned subtitle. Reuse the subtitle's translation only when
        # it is already in the voice's language; otherwise translate the
        # original part text to the voice language independently — so e.g. an
        # English on-screen subtitle can pair with a Japanese narration.
        _voice_target = (ctx.payload.voice_language.split("-")[0] or "en").lower()
        _sub_target = (getattr(ctx.payload, "subtitle_target_language", "") or "en").lower()
        _tgt_lang_voice = _voice_target  # event/context label (now the voice language)
        _part_narration_text = ""
        if _sub_target == _voice_target and translated_srt_part.exists() and translated_srt_part.stat().st_size > 0:
            # Subtitle was already translated to the voice language — reuse it.
            _part_narration_text = extract_text_from_srt(str(translated_srt_part))
        else:
            # Take the original-language part text and translate it to the
            # voice language ourselves (independent of the burned subtitle).
            if srt_part.exists() and srt_part.stat().st_size > 0:
                _orig_text = extract_text_from_srt(str(srt_part))
            elif ctx.full_srt_available:
                try:
                    _orig_text = slice_srt_to_text(str(ctx.full_srt), seg["start"], seg["end"])
                except Exception:
                    _orig_text = ""
            else:
                _orig_text = ""
            if _orig_text.strip():
                try:
                    from app.features.render.engine.subtitle.translation_service import translate_text
                    _part_narration_text = translate_text(_orig_text, target_language=_voice_target)
                except Exception as _self_tr_exc:
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice.self_translate_failed part_no={idx} target={_voice_target}: {_self_tr_exc} — speaking original text", kind="warning")
                    _part_narration_text = _orig_text
        _voice_srt = bool((_part_narration_text or "").strip())
        if _voice_srt:
            if _part_narration_text.strip():
                ctx.voice_part_tts_attempts.append(idx)
                _part_mp3 = str(TEMP_DIR / ctx.job_id / "voice" / f"part_{idx:03d}.mp3")
                try:
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_translated_subtitle_tts_started part_no={idx}", kind="debug")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_translated_subtitle_tts_started",
                        level="INFO",
                        message=f"Generating AI voice from translated subtitle (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "language": ctx.payload.voice_language, "target": _tgt_lang_voice},
                    )
                    _part_subtitle_voice_path = generate_narration_audio(
                        text=clean_spoken_text(_part_narration_text, ctx.payload.voice_language),
                        language=ctx.payload.voice_language,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=_resolve_voice_provider_from_plan(
                            ctx, getattr(ctx.payload, "tts_engine", "edge")
                        ),
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_translated_subtitle_tts_completed",
                        level="INFO",
                        message=f"AI voice from translated subtitle generated (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                    )
                    _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                        str(_part_subtitle_voice_path),
                        ctx.payload,
                        effective_channel=ctx.effective_channel,
                        job_id=ctx.job_id,
                        part_no=idx,
                        source="translated_subtitle",
                    )
                except Exception as _part_tts_exc:
                    _part_subtitle_voice_path = None
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_translated_subtitle_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                    _job_log(ctx.effective_channel, ctx.job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"AI voice (translated subtitle, part {idx}) failed: {_part_tts_exc}",
                        step="voice.tts",
                        exception=_part_tts_exc,
                        traceback_text=traceback.format_exc(),
                        context={"part_no": idx, "error_code": "VOICE001"},
                    )
            else:
                _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} translated subtitle text empty; narration skipped", kind="warning")
        else:
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_subtitle_source_missing part_no={idx} source=translated_subtitle; narration skipped", kind="warning")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_subtitle_source_missing",
                level="WARNING",
                message=f"Translated subtitle voice source missing for part {idx}; narration skipped",
                step="voice.tts",
                context={"part_no": idx, "source": "translated_subtitle"},
            )
    elif (
        _effective_voice_enabled
        and getattr(ctx.payload, "voice_source", "manual") == "ai_rewrite"
        and ctx.voice_audio_path is None
    ):
        # AI rewrite path (v2 — segmented, timestamp-aware).
        # 1. Parse srt_part into {start, end, text} blocks (relative to clip).
        # 2. Format as `[s - e] text` per line, pass to LLM.
        # 3. LLM returns list of {start, end, text} narration segments.
        # 4. synthesize_timed_narration sinhs TTS per segment, atempo-fits
        #    each to its slot, and concats with silence pads.
        # 5. On rewrite=None → fallback to v1 single-segment narration of
        #    the full original transcript (Sacred Contract #3).
        #
        # 2026-06-28 bugfix: previous code fell back to ctx.full_srt VERBATIM
        # when srt_part was missing — so every part received the WHOLE video
        # transcript and the LLM produced near-identical narration across
        # parts (user-reported symptom: "5 parts share same content"). Now
        # the fallback slices full_srt to the clip window IN MEMORY and
        # rebases timestamps to be clip-relative, matching what srt_part
        # would have looked like.
        _part_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
        _src_blocks: list[dict] = []
        _orig_text = ""
        if _part_srt:
            try:
                _src_blocks = parse_srt_blocks(str(_part_srt))
            except Exception as _parse_exc:
                logger.warning("voice.ai_rewrite: parse_srt_blocks failed: %s", _parse_exc)
                _src_blocks = []
            _orig_text = extract_text_from_srt(str(_part_srt))
        elif ctx.full_srt_available:
            try:
                from app.features.render.engine.subtitle.generator.srt import (
                    _parse_srt_blocks as _parse_full_blocks,
                )
                _full_blocks = _parse_full_blocks(str(ctx.full_srt))
                _seg_start = float(seg["start"])
                _seg_end = float(seg["end"])
                _src_blocks = []
                for _b in _full_blocks:
                    _ov_start = max(_seg_start, _b["start"])
                    _ov_end = min(_seg_end, _b["end"])
                    if _ov_end <= _ov_start:
                        continue
                    _src_blocks.append({
                        "start": _ov_start - _seg_start,
                        "end":   _ov_end - _seg_start,
                        "text":  _b["text"],
                    })
                _orig_text = " ".join(b["text"] for b in _src_blocks).strip()
                logger.info(
                    "voice.ai_rewrite: srt_part missing — using full_srt slice "
                    "[%.1fs - %.1fs] (%d blocks) for part %d",
                    _seg_start, _seg_end, len(_src_blocks), idx,
                )
                # Mark _part_srt non-None so the downstream `if _part_srt:`
                # branch enters with the in-memory blocks.
                _part_srt = ctx.full_srt
            except Exception as _slice_exc:
                logger.warning(
                    "voice.ai_rewrite: full_srt slice failed for part %d: %s",
                    idx, _slice_exc,
                )

        if _part_srt:
            if _src_blocks and _orig_text.strip():
                _clip_dur = max(1.0, float(seg["end"]) - float(seg["start"]))
                _srt_segmented = format_segments_for_prompt(_src_blocks)
                _provider = (getattr(ctx.payload, "ai_provider", "") or "gemini").strip().lower()
                _model = getattr(ctx.payload, "llm_model", None)
                _api_key, _api_key_src = _resolve_llm_api_key(ctx.payload, _provider)
                _tone = (getattr(ctx.payload, "rewrite_tone", "") or "").strip()
                _voice_lang = ctx.payload.voice_language
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"voice.ai_rewrite_started part_no={idx} provider={_provider} "
                    f"clip_dur={_clip_dur:.1f}s src_blocks={len(_src_blocks)}",
                    kind="debug",
                )
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="voice_ai_rewrite_started",
                    level="INFO",
                    message=f"AI rewriting narration (part {idx})",
                    step="voice.tts",
                    context={
                        "part_no": idx, "provider": _provider,
                        "clip_duration_sec": _clip_dur,
                        "src_blocks": len(_src_blocks),
                    },
                )
                _segments = _llm_rewrite_subtitle(
                    provider=_provider,
                    srt_segmented=_srt_segmented,
                    clip_duration_sec=_clip_dur,
                    target_language=_voice_lang,
                    tone=_tone,
                    api_key=_api_key,
                    model=_model,
                    # A2.1 + A2.2 (2026-06-28): forward clip context so the
                    # rewriter adapts style to content_type / hook_type /
                    # platform / position. All defaults are empty/0 so the
                    # prompt's CLIP CONTEXT block self-suppresses on absent
                    # fields (back-compat).
                    content_type=str(seg.get("content_type_hint", "") or ""),
                    hook_type=str(seg.get("hook_type", "") or ""),
                    clip_title=str(seg.get("ai_title", "") or ""),
                    target_platform=str(getattr(ctx.payload, "target_platform", "") or ""),
                    part_idx=idx,
                    total_parts=int(ctx.total_parts or 0),
                    # Reaction persona ("" = faithful rewrite | "reaction" =
                    # faceless reaction/storyteller). Default "" keeps prior
                    # behaviour byte-identical (Sacred Contract #2).
                    narration_mode=str(getattr(ctx.payload, "narration_mode", "") or ""),
                    # R3: per-scene DIRECTOR'S INTENT — recap scenes carry the
                    # plan's narration_intent + act context here so the narrator
                    # tells the story across scenes. Empty for clips (no change).
                    editorial_hint=str(seg.get("editorial_hint", "") or ""),
                )
                _used_fallback = False
                if not _segments:
                    # Rewrite returned None (LLM error / rate-limit / parse).
                    # 2026-07 BUGFIX: the old fallback spoke the ORIGINAL-language
                    # transcript with the TARGET voice — on a cross-language job
                    # (e.g. English source + Vietnamese voice) that is gibberish
                    # ("ra cái gì không hiểu"), and it also dropped the reaction
                    # structure. Safety net: translate the original to the voice
                    # language via Google Translate (NO API key, independent of
                    # the LLM that just failed); if translation is unavailable,
                    # SKIP narration for this part rather than emit wrong-language
                    # audio.
                    _vlang = (str(_voice_lang).split("-")[0] or "en").lower()
                    _fb_text = ""
                    try:
                        from app.features.render.engine.subtitle.translation_service import translate_text
                        _tr = translate_text(_orig_text.strip(), target_language=_vlang)
                        _fb_text = (_tr or "").strip()
                    except Exception as _tr_exc:
                        _job_log(
                            ctx.effective_channel, ctx.job_id,
                            f"voice.ai_rewrite_fallback translate failed part_no={idx} target={_vlang}: {_tr_exc}",
                            kind="warning",
                        )
                    if _fb_text:
                        _segments = [{"start": 0.0, "end": _clip_dur, "text": _fb_text}]
                        _used_fallback = True
                        _job_log(
                            ctx.effective_channel, ctx.job_id,
                            f"voice.ai_rewrite_fallback part_no={idx}: rewrite None → narrating TRANSLATED original (→{_vlang})",
                            kind="warning",
                        )
                    else:
                        # Cannot narrate safely (translate unavailable) → skip.
                        # Empty _segments → synth returns None → no narration mix.
                        _segments = []
                        _job_log(
                            ctx.effective_channel, ctx.job_id,
                            f"voice.ai_rewrite_fallback part_no={idx}: rewrite None + translate unavailable → SKIP narration (avoids wrong-language audio)",
                            kind="warning",
                        )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_ai_rewrite_fallback",
                        level="WARNING",
                        message=(
                            f"AI rewrite returned None — "
                            f"{'narrating translated original' if _used_fallback else 'narration skipped (no safe text)'} (part {idx})"
                        ),
                        step="voice.tts",
                        context={
                            "part_no": idx, "reason": "llm_returned_none",
                            "translated_fallback": _used_fallback,
                            "voice_language": _voice_lang,
                        },
                    )
                else:
                    # 2026-06-28: log per-part rewrite preview (first segment
                    # text, truncated) so operators can verify the LLM
                    # actually produced DIFFERENT content per clip. Earlier
                    # bug: the full_srt fallback gave every part the same
                    # whole-video transcript → identical narration across
                    # parts. With the slice fix this log proves the variance
                    # in production.
                    _first_seg_preview = (_segments[0].get("text", "")[:140] + "…") if _segments else ""
                    logger.info(
                        "voice.ai_rewrite: part %d returned %d segments — first preview: %r",
                        idx, len(_segments), _first_seg_preview,
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_ai_rewrite_completed",
                        level="INFO",
                        message=f"AI rewrite OK (part {idx}, {len(_segments)} segments)",
                        step="voice.tts",
                        context={
                            "part_no": idx,
                            "src_blocks": len(_src_blocks),
                            "out_segments": len(_segments),
                            "total_chars": sum(len(s["text"]) for s in _segments),
                            "first_segment_preview": _first_seg_preview,
                        },
                    )
                ctx.voice_part_tts_attempts.append(idx)
                if ctx.cancel_registry.is_cancelled(ctx.job_id):
                    raise ctx.cancel_registry.JobCancelledError()
                try:
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_started",
                        level="INFO",
                        message=f"Generating AI voice from rewrite (part {idx})",
                        step="voice.tts",
                        context={
                            "part_no": idx, "language": _voice_lang,
                            "source": "ai_rewrite",
                            "segments": len(_segments),
                            "fallback": _used_fallback,
                        },
                    )
                    # Capture for the freeze-frame post-pass (reaction mode).
                    _reaction_segments = _segments
                    _part_subtitle_voice_path = synthesize_timed_narration(
                        segments=_segments,
                        clip_duration_sec=_clip_dur,
                        voice_language=_voice_lang,
                        voice_gender=ctx.payload.voice_gender,
                        voice_rate=ctx.payload.voice_rate,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=_resolve_voice_provider_from_plan(
                            ctx, getattr(ctx.payload, "tts_engine", "edge")
                        ),
                        job_id=ctx.job_id,
                        part_idx=idx,
                    )
                    if not _part_subtitle_voice_path:
                        raise RuntimeError("synthesize_timed_narration returned None")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_completed",
                        level="INFO",
                        message=f"AI voice from rewrite generated (part {idx})",
                        step="voice.tts",
                        context={
                            "part_no": idx,
                            "audio_path": _part_subtitle_voice_path,
                            "segments": len(_segments),
                        },
                    )
                    _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                        str(_part_subtitle_voice_path),
                        ctx.payload,
                        effective_channel=ctx.effective_channel,
                        job_id=ctx.job_id,
                        part_no=idx,
                        source="ai_rewrite",
                    )
                except Exception as _part_tts_exc:
                    _part_subtitle_voice_path = None
                    _job_log(
                        ctx.effective_channel, ctx.job_id,
                        f"voice_ai_rewrite_tts_failed part_no={idx}: {_part_tts_exc}",
                        kind="error",
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"AI voice (ai_rewrite, part {idx}) failed: {_part_tts_exc}",
                        step="voice.tts",
                        exception=_part_tts_exc,
                        traceback_text=traceback.format_exc(),
                        context={"part_no": idx, "error_code": "VOICE001"},
                    )
            else:
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"VOICE_SUBTITLE_EMPTY: part {idx} source text empty; narration skipped",
                    kind="warning",
                )
        else:
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"voice_subtitle_source_missing part_no={idx} source=ai_rewrite; narration skipped",
                kind="warning",
            )
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_subtitle_source_missing",
                level="WARNING",
                message=f"AI rewrite source missing for part {idx}; narration skipped",
                step="voice.tts",
                context={"part_no": idx, "source": "ai_rewrite"},
            )
    _final_voice_path = ctx.voice_audio_path or _part_subtitle_voice_path
    if _final_voice_path:
        _part_manifest.narration_path = str(_final_voice_path)
        write_manifest(ctx.work_dir, _part_manifest)
        mixed_part = final_part.with_name(final_part.stem + ".voice_tmp.mp4")
        # Reaction narration is a commentary OVER the clip — the source must
        # stay audible underneath, ducked while the reactor speaks. So a
        # reaction job mixes with keep_original_low regardless of the payload's
        # voice_mix_mode default (replace_original would silence the source).
        _effective_mix_mode = ctx.payload.voice_mix_mode
        if str(getattr(ctx.payload, "narration_mode", "") or "").strip().lower() == "reaction":
            _effective_mix_mode = "keep_original_low"
        try:
            _job_log(ctx.effective_channel, ctx.job_id, f"Mixing AI narration into part {idx}/{ctx.total_parts}", kind="debug")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_mix_started",
                level="INFO",
                message="Mixing narration audio",
                step="voice.mix",
                context={"part_no": idx, "mix_mode": _effective_mix_mode},
            )
            mix_narration_audio(
                video_path=str(final_part),
                narration_audio_path=str(_final_voice_path),
                mix_mode=_effective_mix_mode,
                output_path=str(mixed_part),
                playback_speed=_get_effective_playback_speed(ctx.payload, ctx.target_platform),
            )
            os.replace(str(mixed_part), str(final_part))
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_mix_completed part_no={idx}/{ctx.total_parts}")
            ctx.voice_mix_ok.append(idx)
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_mix_completed",
                level="INFO",
                message="Voice narration completed",
                step="voice.mix",
                context={"part_no": idx, "output_file": str(final_part)},
            )
        except Exception as mix_exc:
            _safe_unlink(mixed_part)
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_mix_failed part_no={idx}: {mix_exc}", kind="error")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_failed",
                level="ERROR",
                message=f"voice_mix_failed part_no={idx}: {mix_exc}",
                step="voice.mix",
                context={"part_no": idx, "output_file": str(final_part), "error_code": "VOICE001"},
                exception=mix_exc,
                traceback_text=traceback.format_exc(),
            )

    # ── R3b: burn the spoken narration as captions (recap only) ─────────────
    # Recap shows the narrator's words on-screen. Burns AFTER the voice mix and
    # BEFORE the BGM/freeze passes so the freeze re-times the captions with the
    # video. Gated on render_format=="recap" (no new payload field; clips path
    # unaffected). Sacred Contract #3 spirit: failure leaves the clip uncaptioned.
    if (
        str(getattr(ctx.payload, "render_format", "clips") or "clips").strip().lower() == "recap"
        and _reaction_segments
        and final_part.exists()
    ):
        try:
            from app.features.render.engine.stages.recap_narration_subtitle import burn_narration_subtitle
            _sub_tmp = final_part.with_name(final_part.stem + ".narrsub_tmp.mp4")
            _speed = _get_effective_playback_speed(ctx.payload, ctx.target_platform)
            if burn_narration_subtitle(
                video_path=str(final_part),
                segments=_reaction_segments,
                out_path=str(_sub_tmp),
                speed=_speed,
                video_crf=int(getattr(ctx.payload, "video_crf", None) or 18),
            ):
                os.replace(str(_sub_tmp), str(final_part))
                _job_log(ctx.effective_channel, ctx.job_id, f"recap_narration_subtitle_burned part_no={idx}")
            else:
                _safe_unlink(_sub_tmp)
        except Exception as _nsub_exc:
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"recap_narration_subtitle_failed part_no={idx}: {_nsub_exc}; continuing without narration captions",
                kind="warning",
            )

    # Sprint 6 P0-3 (audit 2026-06-04 O-13): the raw per-part TTS MP3
    # (and any *.cleaned.mp3 variant emitted by _maybe_cleanup_narration_
    # audio) sit in TEMP_DIR/{job_id}/voice/ until the per-job prune.
    # By this point mix_narration_audio has already merged the audio
    # into final_part, so the intermediate files are dead weight. The
    # glob targets only files written by this part (part_{idx:03d}*.mp3)
    # — ctx.voice_audio_path (a manual user-supplied audio file) lives
    # under a different name and is never matched. Best-effort cleanup;
    # never raises.
    try:
        _voice_dir = TEMP_DIR / ctx.job_id / "voice"
        if _voice_dir.exists():
            for _artifact in _voice_dir.glob(f"part_{idx:03d}*.mp3"):
                _safe_unlink(_artifact)
    except Exception:
        pass

    # ── Sprint 2.3 — BGM mix ─────────────────────────────────────────────────
    # Mix background music under the final video when bgm_enabled AND the AI
    # specified a mood AND a matching file exists in BGM_DIR/{mood}/.
    # Sacred Contract #3 spirit: any failure here emits a warning and
    # continues — BGM is optional, never a render-blocker.
    if _effective_bgm_enabled and _bgm_mood:
        _bgm_file = _pick_bgm_file(_bgm_mood)
        if _bgm_file:
            _bgm_tmp = final_part.with_name(final_part.stem + ".bgm_tmp.mp4")
            try:
                _bgm_db = -18.0 + _bgm_volume_offset
                mix_with_bgm(
                    video_path=str(final_part),
                    bgm_path=_bgm_file,
                    output_path=str(_bgm_tmp),
                    bgm_db_gain=_bgm_db,
                )
                os.replace(str(_bgm_tmp), str(final_part))
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"bgm_mix_completed part_no={idx} mood={_bgm_mood} gain={_bgm_db:.1f}dB",
                )
            except Exception as _bgm_exc:
                _safe_unlink(_bgm_tmp)
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"bgm_mix_failed part_no={idx} mood={_bgm_mood} — {_bgm_exc}; continuing without BGM",
                    kind="warning",
                )
        else:
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"bgm_no_file part_no={idx} mood={_bgm_mood} — no audio files in BGM_DIR/{_bgm_mood}/; skipping BGM",
                kind="debug",
            )

    # ── Reaction freeze-frame post-pass (narration_mode="reaction", Phase B) ──
    # After the voice (+BGM) mix, insert the AI-marked suspense freeze-frames
    # (freeze_after) into the final clip. Re-times video + mixed audio together;
    # the added seconds are stashed on ``seg`` so the finalize/qa stage widens
    # its expected-duration window (Sacred Contract #8 stays valid — qa still
    # validates the delivered, extended output). Sacred Contract #3 spirit: any
    # failure leaves the clip untouched and the render continues.
    if (
        str(getattr(ctx.payload, "narration_mode", "") or "").strip().lower() == "reaction"
        and _reaction_segments
        and final_part.exists()
    ):
        try:
            _speed = _get_effective_playback_speed(ctx.payload, ctx.target_platform)
            _final_dur = _probe_part_duration(str(final_part))
            _freeze_pts = plan_freeze_points(
                _reaction_segments,
                render_speed=_speed,
                clip_final_duration=_final_dur,
            )
            if _freeze_pts:
                _freeze_tmp = final_part.with_name(final_part.stem + ".freeze_tmp.mp4")
                _fr = apply_reaction_freezes(
                    video_path=str(final_part),
                    output_path=str(_freeze_tmp),
                    freeze_points=_freeze_pts,
                    video_crf=int(getattr(ctx.payload, "video_crf", None) or 18),
                )
                if _fr.get("applied"):
                    os.replace(str(_freeze_tmp), str(final_part))
                    seg["reaction_freeze_added_sec"] = float(_fr.get("added_sec", 0.0))
                    _job_log(
                        ctx.effective_channel, ctx.job_id,
                        f"reaction_freeze_applied part_no={idx} points={_fr.get('points')} added={_fr.get('added_sec'):.2f}s",
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="reaction_freeze_applied",
                        level="INFO",
                        message=f"Reaction freeze-frames applied (part {idx}, +{_fr.get('added_sec'):.1f}s)",
                        step="voice.reaction_freeze",
                        context={"part_no": idx, "points": _fr.get("points"), "added_sec": _fr.get("added_sec")},
                    )
                else:
                    _safe_unlink(_freeze_tmp)
        except Exception as _frz_exc:
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"reaction_freeze_failed part_no={idx}: {_frz_exc}; continuing without freeze",
                kind="warning",
            )

