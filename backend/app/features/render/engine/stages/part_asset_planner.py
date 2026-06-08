"""Per-part asset planner — Layer 7 of the render pipeline.

Sprint 6.D-2.2 — extracted verbatim from stages/part_renderer.py
(lines 107-716 of the pre-2.2 file). No logic changes; pure relocation.

`prepare_part_assets(ctx, idx, seg, srt_part, ass_part,
translated_srt_part, _effective_start, _part_manifest, part_name,
final_part, raw_part)` runs once per part during process_one_part.
It produces a PartAssets bundle + 4 extra meta values for the
downstream renderer.

Layer 7 responsibilities (in order):
  1. Per-part Whisper transcription (subtitle_transcription_adapters)
     or resume-cache hit when the SRT already exists.
  2. Optional intelligent re-segmentation for readability.
  3. Optional per-language translation via translate_srt_file with
     per-block failure tracking (ctx.sub_translate_* lists).
  4. Subtitle edits + market-viral hook text injection +
     market line-break + hook subtitle format pass.
  5. Effective subtitle-style resolution (variant > creator >
     platform > DNA > content-type default).
  6. Subtitle emphasis pass (preset_id + market + language).
  7. Optional CTA block append.
  8. ASS file generation (srt_to_ass_karaoke OR srt_to_ass_bounce
     depending on _effective_subtitle_style).
  9. Hook overlay text-layer prepend (when hook_overlay_enabled
     and slot budget MAX_TEXT_LAYERS not exhausted).
  10. PartAssets construction + return.

Returns:
  (PartAssets, _srt_count, _srt_meta, _hook_subtitle_formatted,
   _subtitle_ass_ms)

Public re-export contract:
  Re-exported from stages/part_renderer.py so the existing internal
  caller (process_one_part) keeps using `prepare_part_assets(...)`
  via the bare reference. No external module imports
  prepare_part_assets directly — only process_one_part does.

Sacred Contracts touched:
  - #5 Frozen part-stage names: uses JobPartStage.TRANSCRIBING via
       enum reference at line 138 of the original. No string literal
       replacement; renames blocked at the type level.
  - #6 _emit_render_event signature: 20+ call sites preserved
       verbatim with identical kwargs.
  - #7 Sole DB writer: upsert_job_part(...) route through
       app.services.db unchanged.

LOC budget note (Sprint 6.D-3.6b pattern):
  ~610 LOC single commit — 2Ã— the Â§7 advisory cap of 300. The
  function is a single internally-cohesive Layer-7 sequence with
  30+ mutable state vars flowing across all sections; no clean
  interior seam exists. Cohesion preferred over the LOC guideline.

Logger note (same pattern as 6.D-2.1 / motion_crop extractions):
  `logger = logging.getLogger("app.render")` preserved verbatim so
  existing log routing still resolves to the correct logger name.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Tuple

from app.core.stage import JobPartStage
from app.features.render.engine.pipeline.part_assets import PartAssets
from app.features.render.engine.pipeline.pipeline_cache import (
    _ass_cache_get,
    _ass_cache_key,
    _ass_cache_put,
)
from app.features.render.engine.pipeline.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _select_cta_text,
)
from app.features.render.engine.pipeline.pipeline_subtitle_utils import (
    _append_cta_block_to_srt,
    _apply_subtitle_edits_to_srt,
    _aspect_play_res_y,
    _read_srt_meta,
)
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.db.jobs_repo import upsert_job_part
from app.features.render.engine.stages.manifest_writer import write_manifest
from app.features.render.engine.subtitle.generator.ass import srt_to_ass_bounce, srt_to_ass_karaoke
from app.features.render.engine.subtitle.generator.srt import parse_srt_blocks, write_srt_blocks
from app.features.render.engine.subtitle.processing.readability import (
    resegment_srt_for_readability,
    subtitle_emphasis_pass,
)
from app.features.render.engine.subtitle.processing.text_transforms import (
    apply_hook_subtitle_format,
    apply_market_hook_text_to_srt,
    apply_market_line_break_to_srt,
    resolve_hook_overlay_text,
)
from app.features.render.engine.subtitle.transcription.adapters import transcribe_with_adapter
from app.features.render.engine.overlay.text_overlay import MAX_TEXT_LAYERS
from app.features.render.engine.subtitle.translation_service import translate_srt_file

# Preserve original logger name (Sprint 6.D-2.1 pattern) — used by the
# original code in stages/part_renderer.py and by downstream filters.
logger = logging.getLogger("app.render")


# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
# Sprint 4.E — RenderPlan.subtitle_policy consume helpers.
#
# When ctx.render_plan is None (flag OFF, no AI emission), both
# resolvers fall through to the caller's fallback — Sacred Contract
# #2 (default behaviour identical baseline). When ctx.render_plan is
# set, per-field merge applies: empty fields stay at fallback (the
# "empty = inherit" semantic documented at render_plan.py SubtitlePolicy);
# set fields override. Invalid style values soft-fall back per Sacred
# Contract #3.
#
# Sprint 4.E scope: style + market. emphasis_pass is now wired below —
# gate is active only when render_plan is present; legacy path (None)
# always runs emphasis so baseline behaviour is unchanged.
# line_break_rule removed: no valid value vocabulary was defined in the
# prompt and apply_market_line_break_to_srt doesn't expose a rule-string
# override — keeping a dead field wastes AI tokens with no effect.
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

# Allowed subtitle style strings the planner will accept from a
# RenderPlan. Superset of the SubtitlePolicy vocabulary
# (viral/clean/story/gaming) plus the registered preset_ids already
# wired into subtitle_engine. Anything outside the set soft-falls
# back to the legacy 5-tier resolution.
# Strategic-8 — Audit 2026-06-08 refactor. The 5 RenderPlan resolvers +
# 3 supporting constants moved to stages/part_render_plan_resolvers.py.
# Pure re-import keeps the bare reference style at the call sites inside
# prepare_part_assets and preserves the existing source-level test
# guards (which grep this file's text for the resolver call patterns).
from app.features.render.engine.stages.part_render_plan_resolvers import (  # noqa: E402
    _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES,
    _resolve_subtitle_style_from_plan,
    _resolve_market_from_plan,
    _SUBTITLE_EMPHASIS_MULTIPLIERS,
    _apply_subtitle_emphasis,
    _resolve_cta_audio_from_plan,
    _ALLOWED_CTA_TYPES_FROM_PLAN,
    _resolve_cta_type_from_plan,
)

def prepare_part_assets(
    ctx: PartRenderContext,
    idx,
    seg,
    srt_part,
    ass_part,
    translated_srt_part,
    _effective_start,
    _part_manifest,
    part_name,
    final_part,
    raw_part,
):
    # Layer 7: Overlay Asset Prep — subtitle slicing, ASS conversion, hook formatting,
    # text-layer assembly. Returns PartAssets + raw timing/meta for Layer 8 callers.
    _sub_target_lang = getattr(ctx.payload, "subtitle_target_language", "en")
    _srt_count = 0
    _hook_subtitle_formatted = False
    _srt_meta: dict = {}
    _subtitle_ass_ms = 0
    _effective_subtitle_style = ""

    # Strategic-1c — Audit 2026-06-08 closure (UP26 subtitle_emphasis).
    # Resolve the effective subtitle font size ONCE by applying the
    # operator's emphasis multiplier (subtle 0.85× / balanced 1.0× /
    # aggressive 1.20×) to payload.sub_font_size. Used by the ASS
    # cache key, both ASS writers, the log line, and the report dict.
    # None / "balanced" / unknown emphasis is a byte-for-byte
    # no-op vs pre-Strategic-1c.
    _raw_sub_font_size = int(getattr(ctx.payload, "sub_font_size", 0) or 0)
    _emphasis = getattr(ctx.payload, "subtitle_emphasis", None)
    _effective_sub_font_size = _apply_subtitle_emphasis(_raw_sub_font_size, _emphasis)

    subtitle_selected_by_rule = ctx.subtitle_enabled_by_idx.get(idx, False)
    part_subtitle_enabled = subtitle_selected_by_rule
    if part_subtitle_enabled and not raw_part.exists():
        part_subtitle_enabled = False
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} subtitle skipped: raw clip not available for transcription", kind="warning")
    if ctx.payload.add_subtitle and not part_subtitle_enabled and not subtitle_selected_by_rule:
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} subtitle skipped (viral={float(seg.get('viral_score', 0) or 0):.3f} < cutoff={ctx.subtitle_cutoff})")

    if part_subtitle_enabled:
        upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.TRANSCRIBING, 35, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Preparing subtitle")
        needs_srt = not (ctx.payload.resume_from_last and srt_part.exists() and srt_part.stat().st_size > 0)
        needs_ass = not (ctx.payload.resume_from_last and ass_part.exists() and ass_part.stat().st_size > 0)
        _srt_source_is_fresh = needs_srt
        if needs_srt:
            _t_part_transcribe = time.perf_counter()
            _part_trans_engine = getattr(ctx.payload, "subtitle_transcription_engine", "default")
            # Sprint 6 P1 N.2 (H3 quality fix from Whisper defer audit):
            # default the per-part Whisper model to whatever the source-level
            # Whisper resolved to (ctx.tuned["whisper_model"]), so users on
            # quality/best profiles don't silently get per-part subtitles
            # capped at "small" while their source-level SRT is "large-v3".
            # Explicit SUBTITLE_PER_PART_MODEL env var still wins so anyone
            # who relied on the old "small" default can pin it back. Final
            # defensive fallback to "small" if the tuned dict is missing
            # the key for any reason.
            _part_trans_model = os.getenv(
                "SUBTITLE_PER_PART_MODEL",
                ctx.tuned.get("whisper_model", "small"),
            )
            try:
                transcribe_with_adapter(
                    str(raw_part),
                    str(srt_part),
                    engine=_part_trans_engine,
                    model_name=_part_trans_model,
                    retry_count=0,
                    highlight_per_word=bool(getattr(ctx.payload, "highlight_per_word", False)),
                    logger=logger,
                )
            except Exception as _part_trans_exc:
                logger.warning("per_part_transcription_failed part=%d: %s", idx, _part_trans_exc)
                _job_log(ctx.effective_channel, ctx.job_id,
                         f"per_part_transcription_failed part_no={idx}: {_part_trans_exc}", kind="warning")
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="subtitle_transcription_failed",
                    level="WARNING",
                    message=f"Subtitle skipped for part {idx}: per-part transcription failed",
                    step="subtitle.transcribe_part",
                    context={"part_no": idx, "error": str(_part_trans_exc)},
                )
                needs_srt = False
                needs_ass = False
                _srt_source_is_fresh = False
            _part_trans_ms = int((time.perf_counter() - _t_part_transcribe) * 1000)
            _srt_meta = _read_srt_meta(str(srt_part)) if srt_part.exists() and srt_part.stat().st_size > 0 else {}
            _srt_count = _srt_meta.get("subtitle_count", 0)
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"subtitle_part_transcribed part_no={idx} model={_part_trans_model} "
                f"engine={_part_trans_engine} elapsed_ms={_part_trans_ms} count={_srt_count}"
                + (
                    f" first={_srt_meta['first_start']:.3f}->{_srt_meta['first_end']:.3f}s"
                    f" last={_srt_meta['last_start']:.3f}->{_srt_meta['last_end']:.3f}s"
                    if _srt_count > 0 else " (no speech)"
                ),
                kind="debug" if _srt_count > 0 else "warning",
            )
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="subtitle_part_sync",
                level="INFO" if _srt_count > 0 else "WARNING",
                message=f"Subtitle transcribed for part {idx}: {_srt_count} entries",
                step="subtitle.transcribe_part",
                context={
                    "part_no": idx,
                    "part_start": seg["start"],
                    "part_end": seg["end"],
                    "subtitle_count": _srt_count,
                    "first_sub_start": _srt_meta.get("first_start"),
                    "first_sub_end": _srt_meta.get("first_end"),
                    "last_sub_start": _srt_meta.get("last_start"),
                    "last_sub_end": _srt_meta.get("last_end"),
                    "part_srt_path": str(srt_part),
                    "model": _part_trans_model,
                    "engine": _part_trans_engine,
                    "elapsed_ms": _part_trans_ms,
                    "resume_cache_hit_srt": False,
                    "resume_cache_hit_ass": not needs_ass,
                },
            )
        else:
            if srt_part.exists() and srt_part.stat().st_size > 0:
                _srt_meta = _read_srt_meta(str(srt_part))
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"subtitle_resume_cache_hit part_no={idx} "
                f"srt_exists={srt_part.exists()} "
                f"ass_exists={ass_part.exists()} "
                f"last_sub_end={_srt_meta.get('last_end')!r}",
                kind="debug",
            )
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="subtitle_part_sync",
                level="INFO",
                message=f"Subtitle resume cache hit for part {idx}: {_srt_meta.get('subtitle_count', 0)} entries",
                step="subtitle.slice",
                context={
                    "part_no": idx,
                    "part_start": seg["start"],
                    "part_end": seg["end"],
                    "part_srt_path": str(srt_part),
                    "resume_cache_hit_srt": True,
                    "resume_cache_hit_ass": not needs_ass,
                    "subtitle_count": _srt_meta.get("subtitle_count", 0),
                    "last_sub_end": _srt_meta.get("last_end"),
                },
            )
        _part_manifest.srt_path = str(srt_part)
        write_manifest(ctx.work_dir, _part_manifest)
        if _srt_source_is_fresh and srt_part.exists() and not getattr(ctx.payload, "highlight_per_word", False):
            try:
                _intel_out = resegment_srt_for_readability(str(srt_part))
                if _intel_out > 0:
                    needs_ass = True
            except Exception as _intel_exc:
                logger.warning("subtitle_intel_resegment_failed part=%d: %s", idx, _intel_exc)

        _ass_srt_source = srt_part
        if getattr(ctx.payload, "subtitle_translate_enabled", False) and srt_part.exists() and srt_part.stat().st_size > 0:
            _needs_translated = not (ctx.payload.resume_from_last and translated_srt_part.exists() and translated_srt_part.stat().st_size > 0)
            if _needs_translated:
                ctx.sub_translate_attempts.append(idx)
                if ctx.cancel_registry.is_cancelled(ctx.job_id):
                    raise ctx.cancel_registry.JobCancelledError()
                try:
                    _job_log(ctx.effective_channel, ctx.job_id, f"subtitle_translate_started part_no={idx} target={_sub_target_lang}", kind="debug")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="subtitle_translate_started",
                        level="INFO",
                        message=f"Translating subtitle (part {idx})",
                        step="subtitle.translate",
                        context={"part_no": idx, "target": _sub_target_lang},
                    )
                    _, _block_failures = translate_srt_file(str(srt_part), str(translated_srt_part), target_language=_sub_target_lang)
                    for _bfi in _block_failures:
                        _job_log(ctx.effective_channel, ctx.job_id, f"subtitle_translate_block_failed part_no={idx} block={_bfi} target={_sub_target_lang}", kind="warning")
                    if _block_failures:
                        ctx.sub_translate_partial.append(idx)
                        _job_log(
                            ctx.effective_channel, ctx.job_id,
                            f"Translation partially failed for {_sub_target_lang} export — "
                            f"{len(_block_failures)} subtitle block(s) could not be translated. "
                            f"Original text preserved for those blocks.",
                            kind="warning",
                        )
                    else:
                        ctx.sub_translate_clean.append(idx)
                    _job_log(ctx.effective_channel, ctx.job_id, f"subtitle_translate_completed part_no={idx} output={translated_srt_part}")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="subtitle_translate_completed",
                        level="INFO",
                        message=f"Subtitle translated (part {idx})",
                        step="subtitle.translate",
                        context={"part_no": idx, "output": str(translated_srt_part), "block_failures": len(_block_failures)},
                    )
                    needs_ass = True
                except Exception as _trans_exc:
                    ctx.sub_translate_failed_parts.append(idx)
                    _job_log(ctx.effective_channel, ctx.job_id, f"subtitle_translate_failed part_no={idx}: {_trans_exc}", kind="warning")
                    _job_log(
                        ctx.effective_channel, ctx.job_id,
                        f"Translation failed for {_sub_target_lang} export (part {idx}). "
                        f"Subtitles will use original language.",
                        kind="warning",
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="subtitle_translate_failed",
                        level="WARNING",
                        message=f"Subtitle translation failed (part {idx}): {_trans_exc}",
                        step="subtitle.translate",
                        context={"part_no": idx},
                    )
            if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0:
                _ass_srt_source = translated_srt_part
                if _needs_translated:
                    _srt_source_is_fresh = True
        _sub_edits = getattr(ctx.payload, 'subtitle_edits', None)
        if _srt_source_is_fresh and _sub_edits and _ass_srt_source.exists():
            try:
                _apply_subtitle_edits_to_srt(str(_ass_srt_source), _sub_edits)
            except Exception as _se_exc:
                logger.warning("subtitle_edits: skipped due to error: %s", _se_exc)
        if _srt_source_is_fresh and ctx.hook_apply_enabled and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
            try:
                _hook_apply_meta = apply_market_hook_text_to_srt(
                    str(_ass_srt_source),
                    ctx.hook_applied_text,
                    max_hook_blocks=1,
                    max_hook_seconds=5.0,
                )
                _hook_affected = int(_hook_apply_meta.get("affected_count") or 0)
                if _hook_apply_meta.get("applied"):
                    needs_ass = True
                _job_log(
                    ctx.effective_channel,
                    ctx.job_id,
                    "market_viral_hook_apply "
                    f"part_no={idx} market={ctx.mv_market} "
                    f"hook_apply_enabled={ctx.hook_apply_enabled} "
                    f"hook_score={ctx.hook_score} "
                    f"subtitle_blocks_affected={_hook_affected} "
                    f"original_hook_text={_hook_apply_meta.get('original_hook_text', '')!r} "
                    f"applied_hook_text={_hook_apply_meta.get('applied_hook_text', '')!r}",
                )
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="market_viral_hook_applied",
                    level="INFO",
                    message=f"Market Viral hook applied to {_hook_affected} subtitle block(s) (part {idx})",
                    step="subtitle.market_hook",
                    context={
                        "part_no": idx,
                        "market": ctx.mv_market,
                        "hook_apply_enabled": ctx.hook_apply_enabled,
                        "hook_score": ctx.hook_score,
                        "subtitle_blocks_affected": _hook_affected,
                        "original_hook_text": _hook_apply_meta.get("original_hook_text", ""),
                        "applied_hook_text": _hook_apply_meta.get("applied_hook_text", ""),
                    },
                )
            except Exception as _hook_exc:
                logger.warning("market_viral_hook_apply: skipped due to error: %s", _hook_exc)
        elif ctx.hook_apply_enabled:
            _job_log(
                ctx.effective_channel,
                ctx.job_id,
                "market_viral_hook_apply "
                f"part_no={idx} market={ctx.mv_market} "
                f"hook_apply_enabled={ctx.hook_apply_enabled} "
                f"hook_score={ctx.hook_score} "
                "subtitle_blocks_affected=0 "
                "original_hook_text='' "
                f"applied_hook_text={ctx.hook_applied_text!r}",
                kind="warning",
            )
        if _srt_source_is_fresh and ctx.mv_cfg and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
            try:
                apply_market_line_break_to_srt(str(_ass_srt_source), ctx.mv_cfg)
                needs_ass = True
            except Exception:
                pass
        if _srt_source_is_fresh and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
            try:
                _hook_orig_len = _ass_srt_source.stat().st_size
                _hook_blocks = apply_hook_subtitle_format(str(_ass_srt_source))
                if _hook_blocks > 0:
                    needs_ass = True
                    _hook_subtitle_formatted = True
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="subtitle_hook_format_applied",
                        level="INFO",
                        message=f"Hook subtitle impact applied: {_hook_blocks} blocks (part {idx})",
                        step="subtitle.hook_format",
                        context={
                            "part_no": idx,
                            "original_length": _hook_orig_len,
                            "new_length": _ass_srt_source.stat().st_size,
                            "lines_count": _hook_blocks,
                        },
                    )
            except Exception as _hfmt_exc:
                logger.warning("apply_hook_subtitle_format: skipped part %d due to error: %s", idx, _hfmt_exc)
        _CONTENT_TYPE_SUB_DEFAULTS: dict[str, str] = {
            "interview":  "clean",
            "commentary": "viral",
            "vlog":       "story",
            "tutorial":   "clean",
            "montage":    "gaming",
        }
        _raw_sub_style = (
            str(seg.get("variant_subtitle_style") or seg.get("ai_subtitle_style") or "").strip()
            or (ctx.payload.subtitle_style or "").strip()
        )
        _platform_sub_bias = (
            _PLATFORM_PROFILES.get(ctx.target_platform, {})
            .get("sub_bias", {})
            .get(str(seg.get("content_type_hint") or "vlog"), "")
        ) if not _raw_sub_style else ""
        _dna_sub_bias_val = (
            {"interview": "clean", "commentary": "story", "vlog": "story",
             "tutorial": "clean", "montage": "gaming"}.get(
                str(seg.get("content_type_hint") or "vlog"), "")
        ) if (not _raw_sub_style and not _platform_sub_bias and ctx.dna_clean_visual) else ""
        if ctx.dna_clean_visual and not _dna_sub_bias_val:
            _sub_suppress_reason = (
                "variant"  if str(seg.get("variant_subtitle_style") or "").strip() else
                "creator"  if (ctx.payload.subtitle_style or "").strip() else
                "platform" if _platform_sub_bias else "n/a"
            )
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"dna_sub_suppressed: reason={_sub_suppress_reason} part={idx}",
                kind="debug",
            )
        # Sprint 4.E — legacy 5-tier resolution remains the source of
        # truth when ctx.render_plan is None. When the plan IS set we
        # let the resolver override per F.1/F.2 decisions.
        _legacy_subtitle_style = (
            _raw_sub_style
            or _platform_sub_bias
            or _dna_sub_bias_val
            or _CONTENT_TYPE_SUB_DEFAULTS.get(
                seg.get("content_type_hint", "vlog"), "tiktok_bounce_v1"
            )
        )
        _effective_subtitle_style, _subtitle_style_source = _resolve_subtitle_style_from_plan(
            ctx, _legacy_subtitle_style, idx
        )

        if _srt_source_is_fresh and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
            try:
                _emph_blocks = parse_srt_blocks(str(_ass_srt_source))
                if _emph_blocks:
                    _ai_emph_override = (
                        ctx.ai_subtitle_emphasis_config.emphasis_style
                        if (
                            ctx.ai_subtitle_emphasis_config is not None
                            and ctx.ai_subtitle_emphasis_config.applied
                        )
                        else None
                    )
                    # Sprint 4.E — RenderPlan.subtitle_policy.market
                    # overrides ctx.mv_market at this functional call
                    # site only. Log fields (L319/L335/L350) keep
                    # ctx.mv_market so upstream identity is preserved.
                    _market_for_emphasis = _resolve_market_from_plan(ctx) or ctx.mv_market
                    # Honour RenderPlan.subtitle_policy.emphasis_pass when
                    # a plan is present. Legacy path (render_plan is None)
                    # always runs emphasis so baseline behaviour is unchanged.
                    _run_emphasis = (
                        ctx.render_plan is None
                        or ctx.render_plan.subtitle_policy.emphasis_pass
                    )
                    if _run_emphasis:
                        subtitle_emphasis_pass(
                            _emph_blocks,
                            preset_id=_effective_subtitle_style,
                            market=_market_for_emphasis,
                            language=_sub_target_lang,
                            emphasis_level_override=_ai_emph_override,
                        )
                        write_srt_blocks(_emph_blocks, str(_ass_srt_source))
                        needs_ass = True
                        _job_log(
                            ctx.effective_channel, ctx.job_id,
                            f"subtitle_emphasis_applied part={idx} "
                            f"style={_effective_subtitle_style} market={ctx.mv_market} "
                            f"lang={_sub_target_lang} blocks={len(_emph_blocks)}"
                            + (f" ai_emph_override={_ai_emph_override}" if _ai_emph_override else ""),
                            kind="info",
                        )
                    else:
                        _job_log(
                            ctx.effective_channel, ctx.job_id,
                            f"subtitle_emphasis_skipped part={idx} reason=render_plan_disabled "
                            f"style={_effective_subtitle_style}",
                            kind="debug",
                        )
                else:
                    _job_log(
                        ctx.effective_channel, ctx.job_id,
                        f"subtitle_emphasis_skipped part={idx} reason=empty_blocks "
                        f"style={_effective_subtitle_style}",
                        kind="debug",
                    )
            except Exception:
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"subtitle_emphasis_error part={idx} style={_effective_subtitle_style} "
                    f"market={ctx.mv_market} — emphasis pass skipped, render continues",
                    kind="warning",
                )

        _cta_enabled = bool(getattr(ctx.payload, "cta_enabled", False))
        if _cta_enabled and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
            try:
                _cta_type    = str(getattr(ctx.payload, "cta_type", "auto") or "auto").strip().lower()
                _ct_hint     = str(seg.get("content_type_hint") or "vlog")
                _cta_vt      = str(seg.get("variant_type") or "")
                # Strategic-3 — Audit 2026-06-08 closure. Capture AI's
                # CTA-type hint from RenderPlan.overlays[kind=cta].type.
                # Used below when the operator's _cta_type is "auto"
                # AND the AI didn't supply an exact text via
                # cta_audio. Pre-Strategic-3 the overlays[kind=cta]
                # entry was silently dropped at render_pipeline.py
                # :679-684 — Batch A Phase 6.2 finding.
                _plan_cta_type = _resolve_cta_type_from_plan(ctx)
                # Option B: AI-specified exact CTA text overrides library lookup.
                _plan_cta_audio = _resolve_cta_audio_from_plan(ctx)
                if _plan_cta_audio:
                    _cta_text = _plan_cta_audio
                else:
                    # Strategic-3: AI's overlays[kind=cta].type biases
                    # _cta_type BEFORE the hook_type bias. The
                    # priority order is now:
                    #   1. Operator-explicit _cta_type (non-"auto").
                    #   2. AI's overlays[kind=cta].type (NEW).
                    #   3. Hook-type bias derived from seg["hook_type"].
                    #   4. Library default ("auto" → content-type fallback).
                    if _cta_type == "auto" and _plan_cta_type and _plan_cta_type != "auto":
                        _cta_type = _plan_cta_type
                    # Option C: AI hook_type biases auto cta_type before library lookup.
                    _hook_type_hint = str(seg.get("hook_type") or "").strip().lower()
                    if _cta_type == "auto" and _hook_type_hint:
                        _cta_type = {
                            "question": "comment",
                            "humor":    "comment",
                            "reveal":   "follow",
                            "contrast": "follow",
                            "emotion":  "follow",
                        }.get(_hook_type_hint, _cta_type)
                    _cta_text = _select_cta_text(_ct_hint, ctx.target_platform, _cta_type, _cta_vt)
                _last_sub_end = float(_srt_meta.get("last_end") or 0)
                _eff_speed    = float(
                    seg.get("variant_playback_speed")
                    or getattr(ctx.payload, "playback_speed", 1.07)
                    or 1.07
                )
                _raw_dur  = float(seg.get("duration") or 0)
                _eff_dur  = max(5.0, _raw_dur / _eff_speed) - 0.5
                if _cta_text and _append_cta_block_to_srt(
                    str(_ass_srt_source), _cta_text, _last_sub_end, _eff_dur
                ):
                    needs_ass = True
                    seg["cta_applied"] = True
                    seg["cta_text"]    = _cta_text
                    _emit_render_event(
                        channel_code=ctx.effective_channel, job_id=ctx.job_id,
                        event="cta_appended", level="INFO",
                        message=f"CTA appended: part {idx} text={_cta_text!r}",
                        step="render.cta",
                        context={
                            "part_no":        idx,
                            "cta_text":       _cta_text,
                            "cta_type":       _cta_type,
                            "content_type":   _ct_hint,
                            "target_platform": ctx.target_platform,
                            "last_sub_end":   _last_sub_end,
                        },
                    )
                    _job_log(
                        ctx.effective_channel, ctx.job_id,
                        f"cta_appended part_no={idx} text={_cta_text!r} "
                        f"type={_cta_type} platform={ctx.target_platform} ct={_ct_hint}",
                    )
            except Exception as _cta_exc:
                logger.warning("cta_append_failed part=%d: %s", idx, _cta_exc)

        # Sprint 7.3 — default cache-hit state for the subtitle_style_applied
        # event context (additive key, Sacred Contract #6 compliant).
        _ass_cache_hit = False
        if needs_ass:
            _play_res_y = _aspect_play_res_y(ctx.payload.aspect_ratio)
            _margin_v = getattr(ctx.payload, "sub_margin_v", 180)
            if not ctx.payload.motion_aware_crop and seg.get("content_type_hint") in ("interview", "commentary"):
                _margin_v += 40
            _t_sub = time.perf_counter()

            # Sprint 7.3 — content-addressable ASS cache. Compute a SHA-256
            # key from the 13 inputs that determine the ASS body and try a
            # cache hit before the writer call. Cache hits skip both the
            # 5-20 ms srt_to_ass_* generation and the file write — the
            # cached file is shutil.copy2'd to ass_part so the existing
            # downstream contract (ass_part as a file path consumed by
            # base_clip_renderer/overlay_compositor/motion_crop) is preserved.
            # See docs/review/SPRINT_7_3_ASS_CONTENT_CACHE_2026-06-05.md.
            _ass_writer = "karaoke" if _effective_subtitle_style == "pro_karaoke" else "bounce"
            _ass_cache_k = _ass_cache_key(
                srt_path=_ass_srt_source,
                writer=_ass_writer,
                style=_effective_subtitle_style or "",
                scale_y=int(ctx.payload.frame_scale_y or 0),
                font_name=getattr(ctx.payload, "sub_font", "Bungee") or "Bungee",
                font_size=_effective_sub_font_size,
                margin_v=int(_margin_v),
                play_res_y=int(_play_res_y),
                play_res_x=1080,
                x_percent=float(getattr(ctx.payload, "sub_x_percent", 50.0) or 50.0),
                highlight_per_word=bool(getattr(ctx.payload, "highlight_per_word", False)),
                base_color=str(getattr(ctx.payload, "sub_color", "") or "")
                    if _ass_writer == "karaoke" else "",
                highlight_color=str(getattr(ctx.payload, "sub_highlight", "") or "")
                    if _ass_writer == "karaoke" else "",
                outline_size=int(getattr(ctx.payload, "sub_outline", 0) or 0)
                    if _ass_writer == "karaoke" else 0,
            )
            _ass_cache_path = _ass_cache_get(_ass_cache_k) if _ass_cache_k else None
            if _ass_cache_path is not None:
                try:
                    shutil.copy2(str(_ass_cache_path), str(ass_part))
                    _ass_cache_hit = True
                except Exception as _ass_copy_exc:
                    # Copy failure: fall through to generation path. Cache
                    # acts purely as a best-effort optimisation, never the
                    # critical path.
                    logger.debug(
                        "ass_cache_copy_failed part=%d key=%s err=%s — falling through to generation",
                        idx, (_ass_cache_k[:8] if _ass_cache_k else "?"), _ass_copy_exc,
                    )

            if not _ass_cache_hit:
                if _effective_subtitle_style == "pro_karaoke":
                    from app.features.render.engine.subtitle.generator.ass import _hex_to_ass
                    srt_to_ass_karaoke(
                        str(_ass_srt_source), str(ass_part),
                        scale_y=ctx.payload.frame_scale_y,
                        font_size=_effective_sub_font_size or 46,
                        font_name=getattr(ctx.payload, "sub_font", "Bungee"),
                        margin_v=_margin_v,
                        play_res_y=_play_res_y,
                        base_color=_hex_to_ass(getattr(ctx.payload, "sub_color", "#FFFFFF")),
                        highlight_color=_hex_to_ass(getattr(ctx.payload, "sub_highlight", "#FFFF00")),
                        outline_size=getattr(ctx.payload, "sub_outline", 3),
                        x_percent=getattr(ctx.payload, "sub_x_percent", 50.0),
                    )
                else:
                    srt_to_ass_bounce(
                        str(_ass_srt_source),
                        str(ass_part),
                        subtitle_style=_effective_subtitle_style,
                        scale_y=ctx.payload.frame_scale_y,
                        highlight_per_word=ctx.payload.highlight_per_word,
                        font_name=getattr(ctx.payload, "sub_font", "Bungee"),
                        margin_v=_margin_v,
                        play_res_y=_play_res_y,
                        x_percent=getattr(ctx.payload, "sub_x_percent", 50.0),
                        font_size=_effective_sub_font_size,
                    )
                # Sprint 7.3 — after a successful generation, put the
                # produced ASS into the cache for future re-renders.
                if _ass_cache_k:
                    _ass_cache_put(_ass_cache_k, ass_part)

            _subtitle_ass_ms = int((time.perf_counter() - _t_sub) * 1000)
            logger.info(
                "subtitle_ass_ms=%d part=%d style=%s content_type=%s ass_cache_hit=%s",
                _subtitle_ass_ms, idx, _effective_subtitle_style,
                seg.get("content_type_hint", ""), _ass_cache_hit,
            )
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"ass_content_cache part_no={idx} hit={_ass_cache_hit} "
                f"key={(_ass_cache_k[:8] if _ass_cache_k else 'disabled')} "
                f"elapsed_ms={_subtitle_ass_ms} writer={_ass_writer} "
                f"style={_effective_subtitle_style}",
                kind="debug",
            )
            _dbg_first_line = ""
            _dbg_first_ts: float = -1.0
            try:
                _dbg_blocks = parse_srt_blocks(str(_ass_srt_source))
                if _dbg_blocks:
                    _dbg_first_line = _dbg_blocks[0]["text"][:80]
                    _dbg_first_ts = round(_dbg_blocks[0]["start"], 3)
            except Exception:
                pass
            _dbg_source_offset = round(_effective_start + _dbg_first_ts - seg["start"], 3) if _dbg_first_ts >= 0 else None
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"subtitle_file_chain part={idx} "
                f"srt={srt_part.name} srt_size={srt_part.stat().st_size if srt_part.exists() else 0} "
                f"ass={ass_part.name} ass_size={ass_part.stat().st_size if ass_part.exists() else 0} "
                f"source_fresh={_srt_source_is_fresh} needs_srt={needs_srt} needs_ass={needs_ass} "
                f"first_ts={_dbg_first_ts}s first_line={_dbg_first_line!r} "
                f"effective_start={_effective_start:.3f}s rebase_origin={seg['start']:.3f}s "
                f"source_offset={_dbg_source_offset}s",
                kind="debug",
            )
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"Part {idx} subtitle: style={_effective_subtitle_style} "
                f"(payload={ctx.payload.subtitle_style or 'auto'}) "
                f"font_size={_effective_sub_font_size} "
                f"raw_font_size={_raw_sub_font_size} "
                f"emphasis={_emphasis or 'balanced'} "
                f"margin_v={_margin_v} x_pct={getattr(ctx.payload, 'sub_x_percent', 50.0):.1f} "
                f"play_res_y={_play_res_y} aspect={ctx.payload.aspect_ratio}",
                kind="info",
            )
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="subtitle_style_applied",
                level="INFO",
                message=f"Subtitle style applied for part {idx}: {_effective_subtitle_style}",
                step="render.subtitle",
                context={
                    "part_no": idx,
                    "subtitle_style": _effective_subtitle_style,
                    # Sprint 4.E — when a plan overrides the legacy
                    # 5-tier value we surface `"render_plan"` (or the
                    # `"fallback_invalid_style"` recovery tag) so
                    # operators can attribute the decision. Pre-4.E
                    # values "auto" / "explicit" stay valid when the
                    # plan does not override.
                    "subtitle_style_source": (
                        _subtitle_style_source
                        if _subtitle_style_source != "fallback"
                        else ("auto" if not _raw_sub_style else "explicit")
                    ),
                    "content_type_hint": seg.get("content_type_hint", ""),
                    "font_size": _effective_sub_font_size,
                    "raw_font_size": _raw_sub_font_size,
                    "subtitle_emphasis": (str(_emphasis).lower() if _emphasis else "balanced"),
                    "margin_v": _margin_v,
                    "play_res_y": _play_res_y,
                    "aspect_ratio": ctx.payload.aspect_ratio,
                    # Sprint 7.3 — additive only. Sibling to existing
                    # resume_cache_hit_srt / resume_cache_hit_ass keys in
                    # subtitle_part_sync. False on generation, True on
                    # content-cache hit. Sacred Contract #6 compliant
                    # (event signature unchanged; only context dict grows).
                    "ass_cache_hit": _ass_cache_hit,
                },
            )
            _part_manifest.ass_path = str(ass_part)
            write_manifest(ctx.work_dir, _part_manifest)
    else:
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} subtitle disabled", kind="debug")

    _hook_overlay_applied_for_part = False
    _part_text_layers = list(ctx.normalized_text_layers)
    _part_text_layers_overlay = list(ctx.normalized_text_layers)
    if ctx.hook_overlay_enabled and len(_part_text_layers) < MAX_TEXT_LAYERS:
        _hook_srt_path = str(srt_part) if srt_part.exists() and srt_part.stat().st_size > 0 else None
        # Strategic-2 — Audit 2026-06-08 closure. The LLM's per-clip
        # ``RenderPlan.clips[i].title`` (surfaced into ``seg["ai_title"]``
        # by ``_scored_from_render_plan`` at render_pipeline.py:267) now
        # serves as the hook-overlay text source when the operator has
        # not set an explicit ``hook_applied_text``. Pre-Strategic-2
        # this field was display-only (visible in the parts API but
        # never rendered into the video). resolve_hook_overlay_text
        # implements the priority: explicit > ai_title > SRT-first-block.
        _ai_title = str(seg.get("ai_title") or "").strip()
        _hook_text, _hook_source = resolve_hook_overlay_text(
            ctx.hook_applied_text if ctx.hook_applied_text else None,
            _hook_srt_path,
            ai_title=_ai_title or None,
        )
        if _hook_text:
            _hook_overlay_applied_for_part = True
            _hook_spd = max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.07)))
            _hook_end_t = round(min(2.5, 1.5 * _hook_spd), 3)
            _part_text_layers = [
                {
                    "id": f"hook_overlay_{idx}",
                    "text": _hook_text,
                    "font_family": "Bungee",
                    "font_size": 52,
                    "color": "#FFFFFF",
                    "position": "top-center",
                    "x_percent": 50.0,
                    "y_percent": 26.0,
                    "alignment": "center",
                    "bold": False,
                    "outline": {"enabled": True, "thickness": 4},
                    "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
                    "background": {"enabled": True, "color": "#000000CC", "padding": 18},
                    "start_time": 0.0,
                    "end_time": _hook_end_t,
                    "order": -1,
                }
            ] + _part_text_layers
            _part_text_layers_overlay = [
                {
                    "id": f"hook_overlay_{idx}",
                    "text": _hook_text,
                    "font_family": "Bungee",
                    "font_size": 52,
                    "color": "#FFFFFF",
                    "position": "top-center",
                    "x_percent": 50.0,
                    "y_percent": 26.0,
                    "alignment": "center",
                    "bold": False,
                    "outline": {"enabled": True, "thickness": 4},
                    "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
                    "background": {"enabled": True, "color": "#000000CC", "padding": 18},
                    "start_time": 0.0,
                    "end_time": _hook_end_t,
                    "order": -1,
                }
            ] + _part_text_layers_overlay
            logger.info(
                "hook_overlay_selected part=%d text=%r source=%s end_t=%.3f",
                idx, _hook_text, _hook_source, _hook_end_t,
            )
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="hook_overlay_applied",
                level="INFO",
                message=f"Hook overlay applied for part {idx}: {_hook_text!r}",
                step="render.hook_overlay",
                context={
                    "part_no": idx,
                    "hook_text": _hook_text,
                    "source": _hook_source,
                    "end_time": _hook_end_t,
                    "hook_overlay_duration": _hook_end_t,
                },
            )
            _job_log(ctx.effective_channel, ctx.job_id,
                f"hook_overlay_applied part={idx} text={_hook_text!r} source={_hook_source} "
                f"end_t={_hook_end_t:.3f}s")
        else:
            logger.info("hook_overlay_skipped_reason part=%d reason=%s", idx, _hook_source)
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="hook_overlay_skipped",
                level="INFO",
                message=f"Hook overlay skipped for part {idx}: {_hook_source}",
                step="render.hook_overlay",
                context={"part_no": idx, "reason": _hook_source},
            )

    _pa = PartAssets(
        subtitle_enabled=part_subtitle_enabled,
        srt_path=str(srt_part) if part_subtitle_enabled and srt_part.exists() else None,
        ass_path=str(ass_part) if part_subtitle_enabled and ass_part.exists() else None,
        subtitle_count=_srt_count,
        hook_subtitle_formatted=_hook_subtitle_formatted,
        hook_overlay_applied=_hook_overlay_applied_for_part,
        text_layers=list(_part_text_layers),
        text_layers_overlay=list(_part_text_layers_overlay),
        subtitle_style=_effective_subtitle_style,
    )
    logger.info(
        "part_assets part=%d subtitle=%s srt_count=%d "
        "hook_format=%s hook_overlay=%s text_layers=%d",
        idx, _pa.subtitle_enabled, _pa.subtitle_count,
        _pa.hook_subtitle_formatted, _pa.hook_overlay_applied,
        len(_pa.text_layers),
    )
    return _pa, _srt_count, _srt_meta, _hook_subtitle_formatted, _subtitle_ass_ms

