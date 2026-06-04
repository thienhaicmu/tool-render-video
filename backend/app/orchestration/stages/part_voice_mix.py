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
  - #3 AI return-None contract: TTS lives in app.services.tts_service
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

from app.core.config import TEMP_DIR
from app.domain.manifests import BaseClipManifest
from app.orchestration.audio_pipeline import _maybe_cleanup_narration_audio
from app.orchestration.pipeline_config import extract_text_from_srt
from app.orchestration.pipeline_segment_selection import _get_effective_playback_speed
from app.orchestration.render_events import (
    _emit_render_event,
    _job_log,
    _safe_unlink,
)
from app.orchestration.stages.part_render_context import PartRenderContext
from app.services.audio_mix_service import mix_narration_audio
from app.services.manifest_writer import write_manifest
from app.services.subtitle_engine import slice_srt_to_text
from app.services.tts_service import generate_narration_audio

# Preserve original logger name (same pattern as 6.D-2.1 through 2.5d).
logger = logging.getLogger("app.render")


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
    if (
        getattr(ctx.payload, "voice_enabled", False)
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
                        text=_part_narration_text,
                        language=ctx.payload.voice_language,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=getattr(ctx.payload, "tts_engine", "edge"),
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
        getattr(ctx.payload, "voice_enabled", False)
        and getattr(ctx.payload, "voice_source", "manual") == "translated_subtitle"
        and ctx.voice_audio_path is None
    ):
        _tgt_lang_voice = getattr(ctx.payload, "subtitle_target_language", "en")
        if not ctx.payload.voice_language.lower().startswith(_tgt_lang_voice.lower()):
            _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_LANGUAGE_TARGET_MISMATCH: voice_language={ctx.payload.voice_language} target={_tgt_lang_voice}", kind="warning")
        _voice_srt = translated_srt_part if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0 else None
        if _voice_srt is None:
            _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_TRANSLATED_SUBTITLE_MISSING: part {idx} translated SRT not found; falling back to original", kind="warning")
            _voice_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
        _voice_srt_inmem_text: str | None = None
        if _voice_srt is None and ctx.full_srt_available:
            try:
                _voice_srt_inmem_text = slice_srt_to_text(str(ctx.full_srt), seg["start"], seg["end"])
                _voice_srt = ctx.full_srt
                _job_log(ctx.effective_channel, ctx.job_id, f"voice.translated_srt_in_memory part_no={idx} (no temp file written)", kind="debug")
            except Exception:
                _voice_srt = None
        if _voice_srt:
            _part_narration_text = _voice_srt_inmem_text if _voice_srt_inmem_text is not None else extract_text_from_srt(str(_voice_srt))
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
                        text=_part_narration_text,
                        language=ctx.payload.voice_language,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=getattr(ctx.payload, "tts_engine", "edge"),
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
    _final_voice_path = ctx.voice_audio_path or _part_subtitle_voice_path
    if _final_voice_path:
        _part_manifest.narration_path = str(_final_voice_path)
        write_manifest(ctx.work_dir, _part_manifest)
        mixed_part = final_part.with_name(final_part.stem + ".voice_tmp.mp4")
        try:
            _job_log(ctx.effective_channel, ctx.job_id, f"Mixing AI narration into part {idx}/{ctx.total_parts}", kind="debug")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_mix_started",
                level="INFO",
                message="Mixing narration audio",
                step="voice.mix",
                context={"part_no": idx, "mix_mode": ctx.payload.voice_mix_mode},
            )
            mix_narration_audio(
                video_path=str(final_part),
                narration_audio_path=str(_final_voice_path),
                mix_mode=ctx.payload.voice_mix_mode,
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
