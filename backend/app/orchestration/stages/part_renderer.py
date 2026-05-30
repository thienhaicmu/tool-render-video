"""
Per-part render logic extracted from run_render_pipeline() inner closures (Phase A-3).
PartRenderContext carries all closure-captured state.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import TEMP_DIR
from app.core.stage import JobPartStage
from app.domain.manifests import BaseClipManifest
from app.domain.timeline import TimelineMap
from app.orchestration.asset_pipeline import (
    _maybe_append_asset_outro,
    _maybe_apply_asset_logo,
    _maybe_prepend_asset_intro,
    _maybe_prepend_remotion_hook_intro,
)
from app.orchestration.audio_pipeline import _maybe_cleanup_narration_audio
from app.orchestration.camera_strategy import CameraStrategy
from app.orchestration.part_assets import PartAssets
from app.orchestration.part_plan import PartExecutionPlan
from app.orchestration.pipeline_cache import _render_cache_key
from app.orchestration.pipeline_config import extract_text_from_srt
from app.orchestration.pipeline_subtitle_utils import (
    _append_cta_block_to_srt,
    _apply_subtitle_edits_to_srt,
    _aspect_play_res_y,
    _read_srt_meta,
)
from app.orchestration.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _get_effective_playback_speed,
    _select_cover_frame_time,
    _select_cta_text,
)
from app.orchestration.pipeline_ranking import resolve_combined_score_weights
from app.orchestration.qa_pipeline import (
    _assess_output_quality,
    _assess_render_quality_intelligence,
    _resume_output_valid,
    _validate_render_output,
)
from app.orchestration.render_events import (
    _emit_render_event,
    _job_log,
    _render_progress_timer,
    _safe_unlink,
)
from app.orchestration.render_output import RenderOutputResult
from app.services.audio_mix_service import mix_narration_audio
from app.services.db import upsert_job_part
from app.services.manifest_writer import manifest_path as _manifest_path
from app.services.manifest_writer import write_manifest
from app.services.render_engine import (
    apply_micro_pacing,
    composite_overlays_on_base_clip,
    content_type_crf_delta as _crf_delta_for_content_type,
    cut_video,
    detect_bad_first_frame,
    detect_silence_trim_offset,
    extract_thumbnail_frame,
    render_base_clip,
    render_part_smart,
    set_thread_cancel_event,
)
from app.services.subtitle_engine import (
    apply_hook_subtitle_format,
    apply_market_hook_text_to_srt,
    apply_market_line_break_to_srt,
    parse_srt_blocks,
    resegment_srt_for_readability,
    resolve_hook_overlay_text,
    slice_srt_to_output_timeline,
    slice_srt_to_text,
    srt_to_ass_bounce,
    srt_to_ass_karaoke,
    subtitle_emphasis_pass,
    write_srt_blocks,
)
from app.services.subtitle_transcription_adapters import transcribe_with_adapter
from app.services.text_overlay import MAX_TEXT_LAYERS
from app.services.translation_service import translate_srt_file
from app.services.tts_service import generate_narration_audio

logger = logging.getLogger("app.render")

_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"


@dataclass
class PartRenderContext:
    # Job identity
    job_id: str
    effective_channel: str
    total_parts: int
    retry_count: int
    # I/O paths
    work_dir: Path
    output_dir: Path
    source_path: Path
    source: dict
    output_stem: str
    # Payload
    payload: Any
    # Resume
    existing_parts: dict
    # AI state
    ai_edit_plan: Any
    vis_intensity_hint: Any
    # Platform/render config
    target_platform: str
    tuned: dict
    ffmpeg_threads: int
    # Cancel
    cancel_registry: Any
    # Motion
    src_stat_for_motion: Any
    # Subtitle
    full_srt: Path
    full_srt_available: bool
    subtitle_enabled_by_idx: dict
    subtitle_cutoff: float
    # Voice
    voice_audio_path: Any
    # Market/hook
    mv_market: str
    mv_cfg: dict
    hook_apply_enabled: bool
    hook_applied_text: str
    hook_score: Any
    hook_overlay_enabled: bool
    # AI subtitle
    dna_clean_visual: bool
    ai_subtitle_emphasis_config: Any
    # Text layers
    normalized_text_layers: Any
    # Mutable shared lists (passed by reference — same list object as outer scope)
    voice_part_tts_attempts: list = field(default_factory=list)
    voice_mix_ok: list = field(default_factory=list)
    sub_translate_attempts: list = field(default_factory=list)
    sub_translate_partial: list = field(default_factory=list)
    sub_translate_clean: list = field(default_factory=list)
    sub_translate_failed_parts: list = field(default_factory=list)
    recovery_notes: list = field(default_factory=list)


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

    subtitle_selected_by_rule = ctx.subtitle_enabled_by_idx.get(idx, False)
    part_subtitle_enabled = subtitle_selected_by_rule
    if part_subtitle_enabled and not raw_part.exists():
        part_subtitle_enabled = False
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} subtitle skipped: raw clip not available for transcription", kind="warning")
    if ctx.payload.add_subtitle and not part_subtitle_enabled and not subtitle_selected_by_rule:
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} subtitle skipped (viral={int(seg.get('viral_score', 0))} < cutoff={int(ctx.subtitle_cutoff)})")

    if part_subtitle_enabled:
        upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.TRANSCRIBING, 35, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Preparing subtitle")
        needs_srt = not (ctx.payload.resume_from_last and srt_part.exists() and srt_part.stat().st_size > 0)
        needs_ass = not (ctx.payload.resume_from_last and ass_part.exists() and ass_part.stat().st_size > 0)
        _srt_source_is_fresh = needs_srt
        if needs_srt:
            _t_part_transcribe = time.perf_counter()
            _part_trans_engine = getattr(ctx.payload, "subtitle_transcription_engine", "default")
            _part_trans_model = os.getenv("SUBTITLE_PER_PART_MODEL", "small")
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
            str(seg.get("variant_subtitle_style") or "").strip()
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
        _effective_subtitle_style = (
            _raw_sub_style
            or _platform_sub_bias
            or _dna_sub_bias_val
            or _CONTENT_TYPE_SUB_DEFAULTS.get(
                seg.get("content_type_hint", "vlog"), "tiktok_bounce_v1"
            )
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
                    subtitle_emphasis_pass(
                        _emph_blocks,
                        preset_id=_effective_subtitle_style,
                        market=ctx.mv_market,
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
                _cta_text    = _select_cta_text(_ct_hint, ctx.target_platform, _cta_type, _cta_vt)
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

        if needs_ass:
            _play_res_y = _aspect_play_res_y(ctx.payload.aspect_ratio)
            _margin_v = getattr(ctx.payload, "sub_margin_v", 180)
            if not ctx.payload.motion_aware_crop and seg.get("content_type_hint") in ("interview", "commentary"):
                _margin_v += 40
            _t_sub = time.perf_counter()
            if _effective_subtitle_style == "pro_karaoke":
                from app.services.subtitle_engine import _hex_to_ass
                srt_to_ass_karaoke(
                    str(_ass_srt_source), str(ass_part),
                    scale_y=ctx.payload.frame_scale_y,
                    font_size=getattr(ctx.payload, "sub_font_size", 46),
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
                    font_size=getattr(ctx.payload, "sub_font_size", 0),
                )
            _subtitle_ass_ms = int((time.perf_counter() - _t_sub) * 1000)
            logger.info(
                "subtitle_ass_ms=%d part=%d style=%s content_type=%s",
                _subtitle_ass_ms, idx, _effective_subtitle_style,
                seg.get("content_type_hint", ""),
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
                f"font_size={getattr(ctx.payload, 'sub_font_size', 0)} "
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
                    "subtitle_style_source": "auto" if not _raw_sub_style else "explicit",
                    "content_type_hint": seg.get("content_type_hint", ""),
                    "font_size": getattr(ctx.payload, "sub_font_size", 0),
                    "margin_v": _margin_v,
                    "play_res_y": _play_res_y,
                    "aspect_ratio": ctx.payload.aspect_ratio,
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
        _hook_text, _hook_source = resolve_hook_overlay_text(
            ctx.hook_applied_text if ctx.hook_applied_text else None,
            _hook_srt_path,
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
                    "end_time": 1.5,
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


def process_one_part(ctx: PartRenderContext, idx: int, seg: dict):
    raw_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_raw.mp4"
    srt_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}.srt"
    ass_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}.ass"
    _variant_type = str(seg.get("variant_type") or "")
    if _variant_type:
        final_part = ctx.output_dir / f"{ctx.output_stem}_{_variant_type}.mp4"
        part_name  = f"{ctx.output_stem}_{_variant_type}.mp4"
    else:
        final_part = ctx.output_dir / f"{ctx.output_stem}_part_{idx:03d}.mp4"
        part_name  = f"{ctx.output_stem}_part_{idx:03d}.mp4"
    _sub_target_lang = getattr(ctx.payload, "subtitle_target_language", "en")
    translated_srt_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}.{_sub_target_lang}.srt"
    _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx}/{ctx.total_parts} start", kind="debug")
    import os as _os2
    if _os2.getenv("RENDER_DEBUG_LOG", "0") == "1":
        try:
            import json as _json2
            _meta_path = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_meta.json"
            _meta_data = {
                "part": idx,
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "duration": float(seg.get("duration", 0)),
                "viral_score": float(seg.get("viral_score", 0)),
                "motion_score": float(seg.get("motion_score", 0)),
                "hook_score": float(seg.get("hook_score", 0)),
                "content_type": seg.get("content_type_hint", ""),
                "variant": seg.get("variant_type", ""),
                "files": {
                    "raw": str(raw_part),
                    "srt": str(srt_part),
                    "ass": str(ass_part),
                    "output": str(final_part),
                },
            }
            _meta_path.write_text(_json2.dumps(_meta_data, indent=2), encoding="utf-8")
            logger.debug("debug_artifact segment_meta=%s", _meta_path)
        except Exception as _meta_exc:
            logger.debug("debug_artifact segment_meta_failed part=%d: %s", idx, _meta_exc)

    if ctx.cancel_registry.is_cancelled(ctx.job_id):
        raise ctx.cancel_registry.JobCancelledError()
    _cancel_ev = ctx.cancel_registry.get_event(ctx.job_id)
    if _cancel_ev is not None:
        set_thread_cancel_event(_cancel_ev)

    _existing_part_info = ctx.existing_parts.get(idx, {})
    if (
        ctx.payload.resume_from_last
        and ((_existing_part_info.get("status") or "").lower() == "done")
        and final_part.exists()
        and final_part.stat().st_size > 0
        and _resume_output_valid(final_part)
    ):
        upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Skipped (already rendered)")
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} skipped: final output already exists", kind="debug")
        return {"idx": idx, "output": str(final_part), "row": None, "skipped": True}

    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.WAITING, 5, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), "", "Waiting for worker")

    _trim_offset = 0.0
    _t_part_start = time.perf_counter()
    _cut_ms = _first_frame_scan_ms = 0
    _subtitle_ass_ms = 0
    _render_ms = _micro_pacing_ms = _quality_validation_ms = 0

    try:
        _trim_offset = detect_silence_trim_offset(str(ctx.source_path), seg["start"], seg["end"])
    except Exception:
        _trim_offset = 0.0
    if _trim_offset > 0 and (seg["end"] - seg["start"] - _trim_offset) < 3.0:
        _trim_offset = 0.0
    if _trim_offset > 0:
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="silence_trim_applied",
            level="INFO",
            message=f"Silence trim: {_trim_offset:.3f}s removed from part {idx} start",
            step="render.silence_trim",
            context={
                "part_no": idx,
                "trim_offset_sec": _trim_offset,
                "original_start": seg["start"],
                "effective_start": seg["start"] + _trim_offset,
            },
        )
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} silence trim: {_trim_offset:.3f}s offset applied")
    _effective_start = seg["start"] + _trim_offset

    _visual_trim = 0.0
    _force_accurate_cut = False
    try:
        logger.info("first_frame_scan_started part_no=%d effective_start=%.3f", idx, _effective_start)
        _t_ff = time.perf_counter()
        _visual_trim = detect_bad_first_frame(str(ctx.source_path), _effective_start, seg["end"])
        _first_frame_scan_ms = int((time.perf_counter() - _t_ff) * 1000)
        logger.info("first_frame_scan_ms=%d part=%d shift=%.3f", _first_frame_scan_ms, idx, _visual_trim)
    except Exception:
        _visual_trim = 0.0
    if _visual_trim > 0:
        _candidate_total = _trim_offset + _visual_trim
        if (seg["end"] - seg["start"] - _candidate_total) >= 3.0:
            _trim_offset = _candidate_total
            _effective_start = seg["start"] + _trim_offset
            _force_accurate_cut = True
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="first_frame_shift_applied",
                level="INFO",
                message=f"Bad first frame detected: shifted part {idx} start by {_visual_trim:.3f}s",
                step="render.first_frame_scan",
                context={
                    "part_no": idx,
                    "visual_trim_sec": _visual_trim,
                    "total_trim_sec": _trim_offset,
                    "effective_start": _effective_start,
                    "force_accurate_cut": True,
                },
            )
            _job_log(ctx.effective_channel, ctx.job_id,
                f"first_frame_shift_applied part={idx} visual_trim={_visual_trim:.3f}s "
                f"total_trim={_trim_offset:.3f}s effective_start={_effective_start:.3f}s accurate_cut=True")

    _effective_end = seg['end']
    if (
        getattr(ctx.payload, 'ai_timing_mutation_enabled', False)
        and ctx.ai_edit_plan is not None
        and ctx.ai_edit_plan.timing_apply.get('applied_mutations')
    ):
        _mutations = ctx.ai_edit_plan.timing_apply['applied_mutations']
        _min_sec = float(getattr(ctx.payload, 'min_part_sec', 15) or 15)

        _ai_setup_delta = sum(
            float(m.get('delta_sec', 0.0))
            for m in _mutations
            if (
                m.get('mutation_type') == 'tighten_setup'
                and m.get('safe') is True
                and seg['start'] <= float(m.get('start_sec', -1)) <= seg['start'] + 5.0
            )
        )
        if _ai_setup_delta > 0:
            _ai_setup_delta = min(_ai_setup_delta, max(0.0, _effective_end - _effective_start - _min_sec))
        if _ai_setup_delta > 0:
            _trim_offset += _ai_setup_delta
            _effective_start = seg['start'] + _trim_offset

        _ai_outro_delta = sum(
            float(m.get('delta_sec', 0.0))
            for m in _mutations
            if (
                m.get('mutation_type') == 'shorten_outro'
                and m.get('safe') is True
                and seg['end'] - 5.0 <= float(m.get('end_sec', -1)) <= seg['end']
            )
        )
        if _ai_outro_delta > 0:
            _ai_outro_delta = min(_ai_outro_delta, max(0.0, _effective_end - _effective_start - _min_sec))
        if _ai_outro_delta > 0:
            _effective_end -= _ai_outro_delta

    _part_platform_delta = float(
        _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)
    )
    _part_timeline = TimelineMap(
        source_start=float(_effective_start),
        source_end=float(_effective_end),
        effective_speed=_get_effective_playback_speed(ctx.payload, ctx.target_platform),
        trim_offset=float(_trim_offset),
    )
    _part_manifest = BaseClipManifest(
        job_id=ctx.job_id,
        part_no=idx,
        source_path=str(ctx.source_path),
        source_start=float(_effective_start),
        source_end=float(_effective_end),
        payload_speed=float(ctx.payload.playback_speed or 1.07),
        platform=ctx.target_platform,
        platform_delta=_part_platform_delta,
        effective_speed=_part_timeline.effective_speed,
        variant_type=seg.get("variant_type"),
        variant_speed=(
            float(seg["variant_playback_speed"])
            if seg.get("variant_playback_speed") is not None else None
        ),
        silence_trim_offset=float(_trim_offset - _visual_trim)
            if _visual_trim > 0 else float(_trim_offset),
        visual_trim_offset=float(_visual_trim),
        timeline=_part_timeline,
        ai_enabled=bool(getattr(ctx.payload, "ai_director_enabled", False)),
        ai_mode=getattr(ctx.ai_edit_plan, "mode", None) if ctx.ai_edit_plan is not None else None,
        ai_selected=(
            any(
                min(seg["end"], clip.end) - max(seg["start"], clip.start)
                >= 0.5 * min(seg["end"] - seg["start"], clip.end - clip.start)
                for clip in ctx.ai_edit_plan.selected_segments
            )
            if ctx.ai_edit_plan is not None and ctx.ai_edit_plan.selected_segments
            else False
        ),
        ai_speed_hint=None,
    )
    write_manifest(ctx.work_dir, _part_manifest)

    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.CUTTING, 10, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Cutting raw part")
    if not (ctx.payload.resume_from_last and raw_part.exists() and raw_part.stat().st_size > 0):
        _t_cut = time.perf_counter()
        cut_video(str(ctx.source_path), str(raw_part), _effective_start, _effective_end,
                  retry_count=ctx.retry_count, force_accurate_cut=_force_accurate_cut)
        _cut_ms = int((time.perf_counter() - _t_cut) * 1000)
        logger.info("cut_video_ms=%d part=%d", _cut_ms, idx)
        if _force_accurate_cut:
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="accurate_cut_forced",
                level="INFO",
                message=f"Accurate re-encode cut used for part {idx} (bad first frame shift)",
                step="render.cut",
                context={"part_no": idx, "effective_start": _effective_start},
            )
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} cut done", kind="debug")
    else:
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} cut skipped (raw exists)", kind="debug")
    _part_manifest.cut_path = str(raw_part)
    write_manifest(ctx.work_dir, _part_manifest)

    (_part_assets, _srt_count, _srt_meta,
     _hook_subtitle_formatted, _subtitle_ass_ms) = prepare_part_assets(
        ctx, idx, seg, srt_part, ass_part, translated_srt_part,
        _effective_start, _part_manifest, part_name, final_part,
        raw_part,
    )
    part_subtitle_enabled = _part_assets.subtitle_enabled
    _part_text_layers = list(_part_assets.text_layers)
    _part_text_layers_overlay = list(_part_assets.text_layers_overlay)
    _effective_subtitle_style = _part_assets.subtitle_style
    _hook_overlay_applied_for_part = _part_assets.hook_overlay_applied
    overlay_title = (ctx.payload.title_overlay_text or "").strip() or ctx.source["title"]
    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.RENDERING, 70, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Rendering final video")

    _vf_ct = seg.get("content_type_hint", "vlog")
    _vf_crf_delta = _crf_delta_for_content_type(_vf_ct)
    _part_video_crf = max(11, min(28, ctx.tuned["video_crf"] + _vf_crf_delta))
    _vf_bitrate_profile = (
        "high" if _vf_ct == "montage" else
        "low" if _vf_ct in ("interview", "tutorial") else "standard"
    )
    _vf_subtitle_bump = not ctx.payload.motion_aware_crop and _vf_ct in ("interview", "commentary")
    logger.info(
        "visual_finish_applied part=%d content_type=%s crf=%d(delta=%+d) "
        "bitrate_profile=%s subtitle_safety_bump=%s",
        idx, _vf_ct, _part_video_crf, _vf_crf_delta,
        _vf_bitrate_profile, _vf_subtitle_bump,
    )

    _encode_stop = threading.Event()
    _encode_timer = threading.Thread(
        target=_render_progress_timer,
        args=(
            _encode_stop, ctx.job_id, idx, part_name, seg,
            str(final_part),
            time.monotonic(),
            max(float(seg.get("duration") or 0), 1.0),
            ctx.effective_channel,
        ),
        daemon=True,
        name=f"progress-timer-{ctx.job_id[:8]}-p{idx}",
    )
    _encode_timer.start()
    _t_encode = time.perf_counter()
    _t_render = time.perf_counter()
    _motion_ck = None
    _motion_crop_fallback: list = []
    if ctx.payload.motion_aware_crop and ctx.src_stat_for_motion is not None:
        try:
            _motion_ck = _render_cache_key(
                str(ctx.source_path),
                ctx.src_stat_for_motion.st_mtime,
                ctx.src_stat_for_motion.st_size,
                round(_effective_start, 3),
                round(float(seg["end"]), 3),
                str(ctx.payload.aspect_ratio),
                float(ctx.payload.frame_scale_x),
                float(ctx.payload.frame_scale_y),
                str(getattr(ctx.payload, "reframe_mode", "subject")),
                str(seg.get("content_type_hint", "vlog")),
            )
        except Exception:
            _motion_ck = None
    _part_plan = PartExecutionPlan(
        part_no=idx,
        source_start=float(seg["start"]),
        source_end=float(seg["end"]),
        effective_start=_effective_start,
        trim_offset_sec=_trim_offset,
        visual_trim_sec=_visual_trim,
        force_accurate_cut=_force_accurate_cut,
        subtitle_enabled=part_subtitle_enabled,
        motion_aware_crop=bool(ctx.payload.motion_aware_crop),
        reframe_mode=str(getattr(ctx.payload, "reframe_mode", "subject")),
        frame_scale_x=int(ctx.payload.frame_scale_x),
        frame_scale_y=int(ctx.payload.frame_scale_y),
        content_type=_vf_ct,
        video_crf=_part_video_crf,
        bitrate_profile=_vf_bitrate_profile,
        voice_enabled=bool(getattr(ctx.payload, "voice_enabled", False)),
        voice_source=str(getattr(ctx.payload, "voice_source", "none")),
        playback_speed=float(
            max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.07)
                   + _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)))
        ),
    )
    logger.info(
        "part_execution_plan part=%d trim=%.3f+%.3f accurate_cut=%s "
        "subtitle=%s crop=%s reframe=%s voice=%s speed=%.3f crf=%d",
        _part_plan.part_no, _part_plan.trim_offset_sec, _part_plan.visual_trim_sec,
        _part_plan.force_accurate_cut, _part_plan.subtitle_enabled,
        _part_plan.motion_aware_crop, _part_plan.reframe_mode,
        _part_plan.voice_enabled, _part_plan.playback_speed, _part_plan.video_crf,
    )
    _camera_strategy = CameraStrategy(
        aspect_ratio=ctx.payload.aspect_ratio,
        frame_scale_x=int(ctx.payload.frame_scale_x),
        frame_scale_y=int(ctx.payload.frame_scale_y),
        motion_aware_crop=bool(ctx.payload.motion_aware_crop),
        reframe_mode=str(getattr(ctx.payload, "reframe_mode", "subject")),
        content_type=_vf_ct,
    )
    logger.info(
        "camera_strategy part=%d mode=%s crop=%s reframe=%s aspect=%s scale=%dx%d",
        idx, _camera_strategy.camera_mode, _camera_strategy.motion_aware_crop,
        _camera_strategy.reframe_mode, _camera_strategy.aspect_ratio,
        _camera_strategy.frame_scale_x, _camera_strategy.frame_scale_y,
    )
    if _FEATURE_OVERLAY_AFTER_BASE_CLIP and not _FEATURE_BASE_CLIP_FIRST:
        logger.warning(
            "overlay_flag_ignored job_id=%s part=%d: "
            "FEATURE_OVERLAY_AFTER_BASE_CLIP=1 requires FEATURE_BASE_CLIP_FIRST=1 "
            "— using render_part_smart() for final output",
            ctx.job_id, idx,
        )

    if _FEATURE_BASE_CLIP_FIRST:
        _base_clip_out = ctx.work_dir / f"part_{idx}" / "base_clip.mp4"
        try:
            _base_clip_out.parent.mkdir(parents=True, exist_ok=True)
            _bc_bgm_path = str(getattr(ctx.payload, "reup_bgm_path", None) or "").strip()
            _bc_bgm_ok = (
                getattr(ctx.payload, "reup_bgm_enable", False)
                and _bc_bgm_path
                and Path(_bc_bgm_path).is_file()
            )
            _bc_meta = render_base_clip(
                input_path=str(raw_part),
                output_path=str(_base_clip_out),
                timeline=_part_timeline,
                aspect_ratio=ctx.payload.aspect_ratio,
                scale_x=ctx.payload.frame_scale_x,
                scale_y=ctx.payload.frame_scale_y,
                motion_aware_crop=ctx.payload.motion_aware_crop,
                reframe_mode=getattr(ctx.payload, "reframe_mode", "subject"),
                effect_preset=ctx.payload.effect_preset,
                transition_sec=ctx.tuned["transition_sec"],
                video_codec=ctx.payload.video_codec,
                video_crf=_part_video_crf,
                video_preset=ctx.tuned["video_preset"],
                audio_bitrate=ctx.payload.audio_bitrate,
                retry_count=ctx.retry_count,
                encoder_mode=ctx.payload.encoder_mode,
                output_fps=ctx.payload.output_fps,
                loudnorm_enabled=getattr(ctx.payload, "loudnorm_enabled", False),
                ffmpeg_threads=ctx.ffmpeg_threads,
                content_type=seg.get("content_type_hint", "vlog"),
                _motion_cache_key=_motion_ck,
                reup_bgm_enable=getattr(ctx.payload, "reup_bgm_enable", False),
                reup_bgm_path=getattr(ctx.payload, "reup_bgm_path", None),
                reup_bgm_gain=getattr(ctx.payload, "reup_bgm_gain", 0.18),
                visual_intensity_hint=ctx.vis_intensity_hint,
            )
            _part_manifest.base_clip_path = str(_base_clip_out)
            _part_manifest.base_clip_duration = _bc_meta.get("duration")
            _part_manifest.base_clip_fps = _bc_meta.get("fps")
            _part_manifest.base_clip_width = _bc_meta.get("width")
            _part_manifest.base_clip_height = _bc_meta.get("height")
            _part_manifest.base_clip_has_audio = _bc_meta.get("has_audio")
            _part_manifest.base_clip_created_at = _bc_meta.get("created_at")
            _part_manifest.base_clip_bgm_applied = bool(_bc_bgm_ok)
            write_manifest(ctx.work_dir, _part_manifest)
            logger.info(
                "base_clip_rendered part=%d path=%s duration=%.3fs",
                idx, _base_clip_out, _bc_meta.get("duration", 0.0),
            )
        except Exception as _bc_err:
            logger.warning(
                "base_clip_render_failed part=%d err=%s — render_part_smart continues",
                idx, _bc_err,
            )

    _overlay_composite_succeeded = False
    if (
        _FEATURE_BASE_CLIP_FIRST
        and _FEATURE_OVERLAY_AFTER_BASE_CLIP
        and _part_manifest.base_clip_path is not None
    ):
        _overlay_dir = Path(_part_manifest.base_clip_path).parent
        _overlay_srt = _overlay_dir / "subtitle_output_timeline.srt"
        _overlay_ass = _overlay_dir / "subtitle_output_timeline.ass"
        try:
            _overlay_ass_path: "str | None" = None
            if part_subtitle_enabled and ctx.full_srt_available and ctx.full_srt.exists():
                _ot_meta = slice_srt_to_output_timeline(
                    source_srt_path=str(ctx.full_srt),
                    output_srt_path=str(_overlay_srt),
                    source_start=_part_timeline.source_start,
                    source_end=_part_timeline.source_end,
                    timeline=_part_timeline,
                )
                if _ot_meta.get("subtitle_count", 0) > 0:
                    _overlay_play_res_y = _aspect_play_res_y(ctx.payload.aspect_ratio)
                    _overlay_margin_v = getattr(ctx.payload, "sub_margin_v", 180)
                    if (
                        not ctx.payload.motion_aware_crop
                        and seg.get("content_type_hint") in ("interview", "commentary")
                    ):
                        _overlay_margin_v += 40
                    srt_to_ass_bounce(
                        str(_overlay_srt),
                        str(_overlay_ass),
                        subtitle_style=_effective_subtitle_style,
                        scale_y=ctx.payload.frame_scale_y,
                        font_name=getattr(ctx.payload, "sub_font", "Bungee"),
                        font_size=getattr(ctx.payload, "sub_font_size", 0),
                        margin_v=_overlay_margin_v,
                        play_res_y=_overlay_play_res_y,
                        play_res_x=1080,
                        x_percent=getattr(ctx.payload, "sub_x_percent", 50.0),
                        highlight_per_word=getattr(ctx.payload, "highlight_per_word", True),
                    )
                    _overlay_ass_path = str(_overlay_ass)
                    _part_manifest.overlay_srt_path = str(_overlay_srt)
                    _part_manifest.overlay_ass_path = str(_overlay_ass)

            _oc_meta = composite_overlays_on_base_clip(
                base_clip_path=_part_manifest.base_clip_path,
                output_path=str(final_part),
                timeline=_part_timeline,
                subtitle_ass=_overlay_ass_path,
                text_layers=_part_text_layers_overlay if _part_text_layers_overlay else None,
                title_text=overlay_title if ctx.payload.add_title_overlay else None,
                video_codec=ctx.payload.video_codec,
                video_crf=_part_video_crf,
                video_preset=ctx.tuned["video_preset"],
                audio_bitrate=ctx.payload.audio_bitrate,
                retry_count=ctx.retry_count,
                encoder_mode=ctx.payload.encoder_mode,
                ffmpeg_threads=ctx.ffmpeg_threads,
            )
            _part_manifest.overlay_rendered_path = str(final_part)
            _part_manifest.rendered_path = str(final_part)
            _part_manifest.overlay_text_layers_applied = len(_part_text_layers_overlay or [])
            write_manifest(ctx.work_dir, _part_manifest)
            logger.info(
                "overlay_composite_succeeded part=%d path=%s subtitle=%s",
                idx, final_part, _overlay_ass_path is not None,
            )
            _overlay_composite_succeeded = True
        except Exception as _oc_err:
            logger.warning(
                "overlay_composite_failed job_id=%s part=%d base_clip=%s err=%s "
                "— falling back to render_part_smart",
                ctx.job_id, idx, _part_manifest.base_clip_path, _oc_err,
            )

    try:
        if not _overlay_composite_succeeded:
            render_part_smart(
                str(raw_part), str(final_part), str(ass_part) if part_subtitle_enabled else None, overlay_title if ctx.payload.add_title_overlay else "",
                ctx.payload.aspect_ratio, ctx.payload.frame_scale_x, ctx.payload.frame_scale_y,
                ctx.payload.motion_aware_crop,
                reframe_mode=ctx.payload.reframe_mode,
                add_subtitle=part_subtitle_enabled,
                add_title_overlay=ctx.payload.add_title_overlay,
                effect_preset=ctx.payload.effect_preset,
                transition_sec=ctx.tuned["transition_sec"],
                video_codec=ctx.payload.video_codec,
                video_crf=_part_video_crf,
                video_preset=ctx.tuned["video_preset"],
                audio_bitrate=ctx.payload.audio_bitrate,
                retry_count=ctx.retry_count,
                encoder_mode=ctx.payload.encoder_mode,
                output_fps=ctx.payload.output_fps,
                reup_mode=ctx.payload.reup_mode,
                reup_overlay_enable=ctx.payload.reup_overlay_enable,
                reup_overlay_opacity=ctx.payload.reup_overlay_opacity,
                reup_bgm_enable=ctx.payload.reup_bgm_enable,
                reup_bgm_path=ctx.payload.reup_bgm_path,
                reup_bgm_gain=ctx.payload.reup_bgm_gain,
                playback_speed=float(
                    seg.get("variant_playback_speed")
                    or max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.07)
                           + _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)))
                ),
                text_layers=_part_text_layers,
                loudnorm_enabled=getattr(ctx.payload, "loudnorm_enabled", False),
                ffmpeg_threads=ctx.ffmpeg_threads,
                content_type=seg.get("content_type_hint", "vlog"),
                _motion_cache_key=_motion_ck,
                _fallback_flag=_motion_crop_fallback,
                visual_intensity_hint=ctx.vis_intensity_hint,
            )
    finally:
        _encode_stop.set()
        _encode_timer.join(timeout=5.0)
    _render_ms = int((time.perf_counter() - _t_render) * 1000)
    logger.info("render_part_ms=%d part=%d codec=%s crop=%s",
                _render_ms, idx, ctx.payload.video_codec, ctx.payload.motion_aware_crop)
    _part_manifest.rendered_path = str(final_part)
    write_manifest(ctx.work_dir, _part_manifest)
    if _motion_ck:
        _job_log(ctx.effective_channel, ctx.job_id, f"rerender_fast_path part={idx} motion_cache_key={_motion_ck[:8]} render_ms={_render_ms}")
    if _motion_crop_fallback:
        ctx.recovery_notes.append("Motion crop unavailable — used standard crop")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="recovery_success",
            level="WARNING",
            message=f"Recovery: motion crop failed for part {idx}, standard crop used",
            step="render.motion_crop",
            context={
                "recovery_strategy": "fallback_standard_crop",
                "part_no": idx,
                "reason": _motion_crop_fallback[0],
            },
        )
    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="visual_finish_applied",
        level="INFO",
        message=f"Visual finish: part {idx} content_type={_vf_ct} crf={_part_video_crf}({_vf_crf_delta:+d}) bitrate={_vf_bitrate_profile}",
        step="render.visual_finish",
        context={
            "part_no": idx,
            "content_type": _vf_ct,
            "visual_finish_score": min(100, max(0, 50 + (_part_video_crf - ctx.tuned["video_crf"]) * -5)),
            "clarity_level": "enhanced" if _vf_ct in ("tutorial", "interview") else (
                "reduced" if _vf_ct == "montage" else "standard"
            ),
            "compression_risk": "low" if _vf_ct in ("interview", "tutorial") else (
                "high" if _vf_ct == "montage" else "medium"
            ),
            "subtitle_visibility": "adjusted" if _vf_subtitle_bump else "standard",
            "crf_applied": _part_video_crf,
            "crf_delta": _vf_crf_delta,
            "bitrate_profile": _vf_bitrate_profile,
        },
    )
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

    _micro_pacing_applied = False
    _micro_pacing_trim_sec = 0.0
    if ctx.cancel_registry.is_cancelled(ctx.job_id):
        raise ctx.cancel_registry.JobCancelledError()
    if final_part.exists() and final_part.stat().st_size > 0:
        _paced_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_paced.mp4"
        _t_mp = time.perf_counter()
        try:
            _seg_content_type = seg.get("content_type_hint", "vlog")
            _pacing = apply_micro_pacing(
                str(final_part), str(_paced_part),
                content_type=_seg_content_type,
            )
            _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
            if _pacing["applied"] and _paced_part.exists() and _paced_part.stat().st_size > 0:
                os.replace(str(_paced_part), str(final_part))
                _micro_pacing_applied = True
                _micro_pacing_trim_sec = max(0.0, float(_pacing.get("total_trim_ms") or 0) / 1000.0)
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"Part {idx} micro pacing: {_pacing['segments_trimmed']} segments, "
                    f"{_pacing['total_trim_ms']}ms trimmed, "
                    f"content_type={_seg_content_type}",
                )
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="micro_pacing_applied",
                    level="INFO",
                    message=(
                        f"Micro pacing applied: {_pacing['segments_trimmed']} segments, "
                        f"{_pacing['total_trim_ms']}ms removed"
                    ),
                    step="render.micro_pacing",
                    context={
                        "part_no": idx,
                        "segments_trimmed": _pacing["segments_trimmed"],
                        "total_trim_ms": _pacing["total_trim_ms"],
                        "method": _pacing["method"],
                        "content_type": _seg_content_type,
                    },
                )
            else:
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="micro_pacing_skipped",
                    level="INFO",
                    message="Micro pacing skipped: no qualifying silence segments",
                    step="render.micro_pacing",
                    context={"part_no": idx},
                )
        except subprocess.TimeoutExpired:
            _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"micro_pacing_timeout part_no={idx} elapsed_ms={_micro_pacing_ms} — skipped, original kept",
                kind="warning",
            )
        except Exception as _pace_exc:
            _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"micro_pacing_failed part_no={idx}: {_pace_exc}",
                kind="warning",
            )
        finally:
            _safe_unlink(_paced_part)
        logger.info("micro_pacing_ms=%d part=%d applied=%s", _micro_pacing_ms, idx, _micro_pacing_applied)

    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="p4_output_opening_optimized",
        level="INFO",
        message=(
            f"P4 opening: part {idx} trim={_trim_offset:.3f}s "
            f"hook={_hook_subtitle_formatted} pacing={_micro_pacing_applied}"
        ),
        step="render.p4_opening",
        context={
            "part_no": idx,
            "original_start": seg["start"],
            "effective_start": _effective_start,
            "trim_offset": _trim_offset,
            "original_duration": seg["end"] - seg["start"],
            "effective_duration": seg["end"] - _effective_start,
            "subtitle_count": _srt_count,
            "hook_subtitle_formatted": _hook_subtitle_formatted,
            "micro_pacing_applied": _micro_pacing_applied,
            "micro_pacing_trim_sec": _micro_pacing_trim_sec,
        },
    )

    _encode_ms = int((time.perf_counter() - _t_encode) * 1000)
    _total_part_ms = int((time.perf_counter() - _t_part_start) * 1000)
    _effective_duration = max(0.0, float(seg["end"]) - float(_effective_start))
    _render_speed = _get_effective_playback_speed(ctx.payload, ctx.target_platform)
    _remotion_intro_sec = _maybe_prepend_remotion_hook_intro(
        final_part,
        ctx.payload,
        effective_channel=ctx.effective_channel,
        job_id=ctx.job_id,
        part_no=idx,
        content_type=str(seg.get("content_type_hint") or "vlog"),
        hook_text=ctx.hook_applied_text or None,
        source_title=str(ctx.source.get("title") or ""),
    )
    _maybe_prepend_asset_intro(final_part, ctx.payload,
        effective_channel=ctx.effective_channel, job_id=ctx.job_id, part_no=idx)
    _maybe_append_asset_outro(final_part, ctx.payload,
        effective_channel=ctx.effective_channel, job_id=ctx.job_id, part_no=idx)
    _maybe_apply_asset_logo(final_part, ctx.payload,
        effective_channel=ctx.effective_channel, job_id=ctx.job_id, part_no=idx)
    _expected_final_duration = max(
        0.0,
        (_effective_duration / _render_speed) - _micro_pacing_trim_sec + _remotion_intro_sec,
    )
    _speed_ratio = round(_expected_final_duration * 1000 / max(_encode_ms, 1), 2)
    _job_log(
        ctx.effective_channel, ctx.job_id,
        f"playback_speed_resolution part={idx} "
        f"payload_speed={float(ctx.payload.playback_speed or 1.0):.4f} "
        f"platform_delta={_PLATFORM_PROFILES.get(ctx.target_platform, {}).get('speed_delta', 0.0):.4f} "
        f"effective_speed={_render_speed:.4f} "
        f"target_platform={ctx.target_platform} "
        f"source_duration={_part_timeline.source_duration:.3f}s "
        f"output_duration={_part_timeline.output_duration:.3f}s "
        f"effective_duration={_effective_duration:.3f}s "
        f"expected_duration={_expected_final_duration:.3f}s "
        f"manifest={_manifest_path(ctx.work_dir, idx)}",
        kind="debug",
    )
    logger.info(
        "total_part_render_ms=%d part=%d "
        "cut_ms=%d first_frame_ms=%d subtitle_ass_ms=%d "
        "render_ms=%d pacing_ms=%d quality_ms=%d",
        _total_part_ms, idx,
        _cut_ms, _first_frame_scan_ms, _subtitle_ass_ms,
        _render_ms, _micro_pacing_ms, _quality_validation_ms,
    )
    if ctx.normalized_text_layers:
        _job_log(
            ctx.effective_channel,
            ctx.job_id,
            f"Applied {len(ctx.normalized_text_layers)} text layer(s) on part {idx}/{ctx.total_parts}",
            kind="debug",
        )
    _job_log(
        ctx.effective_channel, ctx.job_id,
        f"Part {idx}/{ctx.total_parts} done: encode_ms={_encode_ms} "
        f"expected_final_duration={_expected_final_duration:.2f}s speed_ratio={_speed_ratio}x "
        f"(>1 = faster than realtime)",
        kind="info",
    )

    try:
        _mv_text = ""
        if srt_part.exists() and srt_part.stat().st_size > 0:
            _mv_text = extract_text_from_srt(str(srt_part))
        _mv_dur = float(seg.get("duration") or 0) or None
        _mv_result = _mv_score_part(_mv_text, _mv_dur, ctx.mv_market)
        seg["mv_viral_score"]   = _mv_result.get("viral_score",  0)
        seg["mv_viral_tier"]    = _mv_result.get("viral_tier",   "weak")
        seg["mv_viral_market"]  = _mv_result.get("viral_market", ctx.mv_market)
        seg["mv_viral_reasons"] = _mv_result.get("reasons",      [])
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="market_viral_scored",
            level="INFO",
            message=(
                f"Part {idx} market viral: {seg['mv_viral_score']} "
                f"{seg['mv_viral_tier']} ({seg['mv_viral_market']})"
            ),
            step="render.market_viral",
            context={
                "part_no":              idx,
                "market_viral_score":   seg["mv_viral_score"],
                "market_viral_tier":    seg["mv_viral_tier"],
                "market_viral_market":  seg["mv_viral_market"],
                "market_viral_reasons": seg["mv_viral_reasons"][:2],
            },
        )
    except Exception:
        pass

    try:
        _cs_enabled  = bool(getattr(ctx.payload, "combined_scoring_enabled", False))
        _cs_adaptive = bool(getattr(ctx.payload, "adaptive_scoring_enabled", False))
        _cs_viral    = float(seg.get("viral_score", 0) or 0)
        _cs_mv_raw   = seg.get("mv_viral_score")
        _cs_mv       = float(_cs_mv_raw) if _cs_mv_raw is not None else _cs_viral
        _cs_hook_raw = (seg.get("hook_text_score") or seg.get("hook_timing_score") or
                        seg.get("hook_opening_score") or seg.get("hook_score"))
        _cs_hook     = float(_cs_hook_raw or 0)
        _cs_dur      = float(seg.get("duration") or 0) or None

        _cs_weights = resolve_combined_score_weights(
            target_market=ctx.mv_market,
            has_market_score=(_cs_mv_raw is not None),
            has_hook_score=(_cs_hook_raw is not None and float(_cs_hook_raw) > 0),
            duration=_cs_dur,
            adaptive_enabled=_cs_adaptive,
        )
        seg["combined_weights"] = _cs_weights

        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="adaptive_score_weights_resolved",
            level="INFO",
            message=f"Part {idx} weights v={_cs_weights['viral_weight']} m={_cs_weights['market_weight']} h={_cs_weights['hook_weight']} reason={_cs_weights['reason']}",
            step="render.combined_score",
            context={
                "part_no":                  idx,
                "adaptive_scoring_enabled": _cs_adaptive,
                "target_market":            ctx.mv_market,
                "duration":                 _cs_dur,
                "viral_weight":             _cs_weights["viral_weight"],
                "market_weight":            _cs_weights["market_weight"],
                "hook_weight":              _cs_weights["hook_weight"],
                "reason":                   _cs_weights["reason"],
            },
        )

        _cs_raw = (
            _cs_viral * _cs_weights["viral_weight"] +
            _cs_mv    * _cs_weights["market_weight"] +
            _cs_hook  * _cs_weights["hook_weight"]
        )
        seg["combined_score"] = round(max(0.0, min(100.0, _cs_raw)), 1)
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="combined_score_computed",
            level="INFO",
            message=f"Part {idx} combined_score={seg['combined_score']}",
            step="render.combined_score",
            context={
                "part_no":                  idx,
                "viral_score":              _cs_viral,
                "market_viral_score":       _cs_mv,
                "hook_score_component":     _cs_hook,
                "combined_score":           seg["combined_score"],
                "combined_scoring_enabled": _cs_enabled,
                "viral_weight":             _cs_weights["viral_weight"],
                "market_weight":            _cs_weights["market_weight"],
                "hook_weight":              _cs_weights["hook_weight"],
            },
        )
    except Exception:
        pass

    _render_output = RenderOutputResult(
        output_path=str(final_part),
        render_ms=_render_ms,
        codec=str(ctx.payload.video_codec),
        crop_fallback=bool(_motion_crop_fallback),
        overlay_composite_used=bool(
            int(os.environ.get("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0"))
            and int(os.environ.get("FEATURE_BASE_CLIP_FIRST", "0"))
        ),
    )
    logger.info(
        "render_output part=%d codec=%s render_ms=%d crop_fallback=%s overlay=%s",
        idx, _render_output.codec, _render_output.render_ms,
        _render_output.crop_fallback, _render_output.overlay_composite_used,
    )

    _expect_audio: bool | None = None
    if getattr(ctx.payload, "voice_enabled", False):
        _expect_audio = True
    elif (getattr(ctx.payload, "reup_bgm_enable", False)
          and bool(str(getattr(ctx.payload, "reup_bgm_path", None) or "").strip())):
        _expect_audio = True
    _qa = _validate_render_output(
        final_part,
        expected_duration=_expected_final_duration if _expected_final_duration > 0 else None,
        expect_audio=_expect_audio,
    )
    _actual_final_duration = float((_qa.get("metadata") or {}).get("duration") or 0.0)
    _job_log(
        ctx.effective_channel,
        ctx.job_id,
        f"Part {idx} duration validation: expected_final_duration={_expected_final_duration:.3f}s "
        f"actual_final_duration={_actual_final_duration:.3f}s "
        f"effective_start={float(_effective_start):.3f}s segment_end={float(seg['end']):.3f}s "
        f"playback_speed={_render_speed:.4f}",
        kind="debug",
    )
    if not _qa["ok"]:
        _qa_code = str(_qa.get("code") or "RN001")
        _job_log(ctx.effective_channel, ctx.job_id,
                 f"Part {idx} output_validation_failed: {_qa['error']} | "
                 f"code={_qa_code} output={final_part} meta={_qa['metadata']}", kind="error")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_validation_failed",
            level="ERROR",
            message=f"Part {idx} output validation failed: {_qa['error']}",
            step="render.output.validate",
            error_code=_qa_code,
            context={
                "part_no": idx,
                "output_file": str(final_part),
                "validation_code": _qa_code,
                **_qa["metadata"],
            },
        )
        raise RuntimeError(f"output_validation_failed[{_qa_code}]: {_qa['error']}")
    if _qa["warnings"]:
        _job_log(ctx.effective_channel, ctx.job_id,
                 f"Part {idx} output_validation_warning: {'; '.join(_qa['warnings'])} | "
                 f"meta={_qa['metadata']}", kind="warning")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_validation_warning",
            level="WARNING",
            message=f"Part {idx} output validation passed with warnings: {'; '.join(_qa['warnings'])}",
            step="render.output.validate",
            context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
        )
    else:
        _job_log(ctx.effective_channel, ctx.job_id,
                 f"Part {idx} output_validation_passed: "
                 f"dur={_qa['metadata']['duration']:.2f}s "
                 f"size={_qa['metadata']['size_bytes']} "
                 f"has_video={_qa['metadata']['has_video']} "
                 f"has_audio={_qa['metadata']['has_audio']}")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_validation_passed",
            level="INFO",
            message=f"Part {idx} output validation passed",
            step="render.output.validate",
            context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
        )

    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="output_quality_validation_started",
        level="INFO",
        message=f"Part {idx} quality validation started",
        step="render.output.quality",
        context={"part_no": idx, "output_file": str(final_part)},
    )
    _t_qq = time.perf_counter()
    _qq = _assess_output_quality(
        final_part,
        ctx.output_dir,
        expect_subtitle=part_subtitle_enabled,
        subtitle_file=ass_part if part_subtitle_enabled else None,
        expect_hook=ctx.hook_overlay_enabled,
        hook_applied=_hook_overlay_applied_for_part,
    )
    _quality_validation_ms = int((time.perf_counter() - _t_qq) * 1000)
    logger.info("quality_validation_ms=%d part=%d penalty=%d",
                _quality_validation_ms, idx, int(_qq["score_penalty"]))
    _quality_penalty = int(_qq["score_penalty"])
    seg["quality_penalty"] = _quality_penalty
    if _qq["warnings"] or not _qq["passed"]:
        _qq_level = "ERROR" if not _qq["passed"] else "WARNING"
        _qq_evt = "output_quality_validation_failed" if not _qq["passed"] else "output_quality_validation_warning"
        for _qw in _qq["warnings"]:
            _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} quality_warning: {_qw}", kind="warning")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event=_qq_evt,
            level=_qq_level,
            message=f"Part {idx} quality validation: {len(_qq['warnings'])} warning(s)",
            step="render.output.quality",
            context={
                "part_no": idx,
                "output_file": str(final_part),
                "warnings": _qq["warnings"],
                "hard_failures": _qq["hard_failures"],
                "checks": _qq["checks"],
                "score_penalty": _quality_penalty,
            },
        )
    else:
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_quality_validation_passed",
            level="INFO",
            message=f"Part {idx} quality validation passed",
            step="render.output.quality",
            context={"part_no": idx, "output_file": str(final_part), "checks": _qq["checks"]},
        )
    if _quality_penalty > 0:
        _job_log(
            ctx.effective_channel, ctx.job_id,
            f"Part {idx} quality_score_penalty: -{_quality_penalty} checks={_qq['checks']}",
            kind="warning",
        )
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_quality_score_penalty_applied",
            level="WARNING",
            message=f"Part {idx} quality penalty applied: -{_quality_penalty} points",
            step="render.output.quality",
            context={
                "part_no": idx,
                "score_penalty": _quality_penalty,
                "checks": _qq["checks"],
                "warnings": _qq["warnings"],
            },
        )
    if _quality_penalty > 20:
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="render.quality_penalty_high",
            level="WARNING",
            message=f"Part {idx} quality penalty high: -{_quality_penalty} points",
            step="render.output.quality",
            context={
                "part_no": idx,
                "warnings": _qq["warnings"],
                "score_penalty": _quality_penalty,
            },
        )

    try:
        _qi_srt = ass_part if part_subtitle_enabled and ass_part and ass_part.suffix == ".srt" else None
        _qi_srt_path: Path | None = None
        if srt_path is not None and Path(str(srt_path)).exists():  # noqa: F821 — preserved bug: srt_path is undefined, caught by except below
            _qi_srt_path = Path(str(srt_path))
        elif _qi_srt is not None and Path(str(_qi_srt)).exists():
            _qi_srt_path = Path(str(_qi_srt))
        _qi_manifest: Path | None = None
        try:
            from app.ai.tracing import _DEFAULT_LOG_DIR as _ai_log_dir
            _qi_ai_trace = _ai_log_dir / f"{ctx.job_id}_ai_trace.jsonl"
            _qi_ai_trace = _qi_ai_trace if _qi_ai_trace.exists() else None
        except Exception:
            _qi_ai_trace = None
        _assess_render_quality_intelligence(
            video_path=final_part,
            part_no=idx,
            job_id=ctx.job_id,
            srt_path=_qi_srt_path,
            manifest_path=_qi_manifest,
            ai_trace_path=_qi_ai_trace,
        )
    except Exception:
        pass

    try:
        _clip_dur = max(1.0, float(seg.get("duration") or 0))
        _cover_hint_ratio: float | None = None
        try:
            if ctx.ai_edit_plan is not None:
                _plan_hint = (ctx.ai_edit_plan.clip_cover_hints or {}).get(idx - 1) or {}
                _raw_ratio = _plan_hint.get("preferred_offset_ratio")
                if _raw_ratio is not None:
                    _cover_hint_ratio = float(_raw_ratio)
        except Exception:
            pass
        _cover_offset, _cover_reason = _select_cover_frame_time(
            clip_duration=_clip_dur,
            hook_score=float(seg.get("hook_score") or 0),
            srt_meta=_srt_meta,
            target_platform=ctx.target_platform,
            variant_type=str(seg.get("variant_type") or ""),
            cover_hint_ratio=_cover_hint_ratio,
        )
        _cover_quality_reasons: list = []
        _cover_bytes = None
        if os.getenv("S4_THUMBNAIL_QUALITY_ENABLED") == "1":
            try:
                from app.services.thumbnail_quality import select_best_thumbnail
                _t_thumb = time.perf_counter()
                _cover_bytes, _cover_offset, _cover_quality_reasons = select_best_thumbnail(
                    str(final_part), _cover_offset, _clip_dur, width=640
                )
                _thumb_ms = int((time.perf_counter() - _t_thumb) * 1000)
                logger.debug("s4_thumbnail_select_ms part=%d ms=%d offset=%.3f", idx, _thumb_ms, _cover_offset)
            except Exception as _s43_exc:
                logger.debug("s4_thumbnail_quality_failed part=%d: %s", idx, _s43_exc)
        if not _cover_bytes:
            _cover_bytes = extract_thumbnail_frame(str(final_part), _cover_offset, width=640)
        if _cover_bytes:
            _cover_stem = (
                f"{ctx.output_stem}_{_variant_type}_cover" if _variant_type
                else f"{ctx.output_stem}_part_{idx:03d}_cover"
            )
            _cover_path = ctx.output_dir / f"{_cover_stem}.jpg"
            _cover_path.write_bytes(_cover_bytes)
            seg["cover_file"] = str(_cover_path)
            seg["cover_frame_offset"] = _cover_offset
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="cover_frame_selected",
                level="INFO",
                message=f"Smart cover: part {idx} offset={_cover_offset:.3f}s",
                step="render.cover",
                context={
                    "part_no":        idx,
                    "cover_file":     str(_cover_path),
                    "frame_offset":   _cover_offset,
                    "cover_reason":   _cover_reason,
                    "target_platform": ctx.target_platform,
                    "variant_type":   str(seg.get("variant_type") or ""),
                    "thumbnail_quality_reason": _cover_quality_reasons,
                },
            )
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"cover_frame_selected part_no={idx} offset={_cover_offset:.3f}s "
                f"platform={ctx.target_platform} reason={_cover_reason!r}",
            )
    except Exception as _cov_exc:
        logger.warning("cover_frame_extraction_failed part=%d: %s", idx, _cov_exc)
    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Completed")
    row = [ctx.job_id, ctx.effective_channel, ctx.source["title"], idx, seg["start"], seg["end"], seg["duration"], seg["viral_score"], seg["priority_rank"], str(final_part)]
    if ctx.payload.cleanup_temp_files:
        _safe_unlink(raw_part)
        _safe_unlink(srt_part)
        _safe_unlink(ass_part)
    return {"idx": idx, "output": str(final_part), "row": row, "skipped": False}
