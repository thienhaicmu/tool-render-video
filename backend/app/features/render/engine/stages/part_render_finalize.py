"""Per-part finalize stage — Layer 8→9 boundary.

Sprint 6.D-2.5c — extracted verbatim from stages/part_renderer.py
(lines 298-728 of the post-2.5b file). No logic changes; pure relocation.

âš ï¸  CRITICAL TIER per docs/SPRINT_6D_PLAN.md Â§10 and CLAUDE.md
   Blast Radius. This module contains the Sacred Contract #8
   (qa_pipeline never bypassed) surface — `_validate_render_output`
   and `_assess_output_quality` calls must remain verbatim with
   their original kwargs.

run_part_finalize() runs once per part during process_one_part,
immediately after the voice/audio-mix block (Sprint 6.D-2.5b's
run_part_voice_mix) and before the DONE block (Sprint 6.D-2.5d's
run_part_done).

Block responsibilities (in order):
  1. Micro-pacing pass via apply_micro_pacing() — trims silence within
     the rendered clip and atomically swaps the file. Emits
     micro_pacing_applied or micro_pacing_skipped (or logs
     micro_pacing_timeout / micro_pacing_failed warnings on error).
  2. p4_output_opening_optimized emit with trim/hook/pacing context.
  3. Asset intro/outro/logo orchestration:
       - _maybe_prepend_remotion_hook_intro (returns intro_sec for
         duration math)
       - _maybe_prepend_asset_intro, _maybe_append_asset_outro,
         _maybe_apply_asset_logo
  4. Duration math: _expected_final_duration + _speed_ratio +
     playback_speed_resolution debug log + total_part_render_ms log +
     per-part-done info log with encode_ms/expected/speed_ratio.
  5. Market viral scoring (_mv_score_part) — wrapped in try/except
     (see "Known-bug preservation" below).
  6. Combined score computation (viral Ã— market Ã— hook weighted).
  7. RenderOutputResult construction — Layer 8→9 boundary dataclass
     per docs/RENDER_PIPELINE.md.
  8. Sacred Contract #8 surface — `_validate_render_output`:
       - Computes expect_audio flag from voice_enabled / reup_bgm_enable.
       - Calls _validate_render_output(final_part, expected_duration,
         expect_audio).
       - On NOT _qa["ok"]: raises RuntimeError(output_validation_failed
         [code]) — propagates up to the caller's outer try/except in
         pipeline_render_loop (the per-part worker catches it and
         records the failure in result_json[failed_parts]).
       - On warnings: emits output_validation_warning.
       - On clean pass: emits output_validation_passed.
  9. Sacred Contract #8 surface — `_assess_output_quality`:
       - Quality assessment (non-blocking, score_penalty only).
       - Emits output_quality_validation_started + _passed/_warning/_failed.
       - Sets seg["quality_penalty"] for downstream ranking.
       - Emits output_quality_score_penalty_applied when penalty > 0.
       - Emits render.quality_penalty_high when penalty > 20.

Returns:
  None. All state mutations are by-reference (seg dict, final_part
  on disk, ctx fields). No new dataclass return — keeps the helper
  surface narrow.

Sacred Contracts honored:
  - #6 _emit_render_event signature: 11 call sites preserved verbatim
       (micro_pacing_applied, micro_pacing_skipped, p4_output_opening_optimized,
       market_viral_scored, adaptive_score_weights_resolved,
       combined_score_computed, output_validation_failed,
       output_validation_warning, output_validation_passed,
       output_quality_validation_{started, passed, warning, failed},
       output_quality_score_penalty_applied, render.quality_penalty_high).
       Each preserves identical kwargs (channel_code, job_id, event,
       level, message, step, context, +error_code on validation_failed,
       +exception/traceback_text not used here).
  - #7 Sole DB writer: 0 upsert_job_part calls in this block.
  - #8 qa_pipeline NEVER bypassed:
       * _validate_render_output called with kwargs preserved verbatim
         (expected_duration, expect_audio).
       * Raise on `not _qa["ok"]` preserved exactly — no fallback
         path that catches the validation exception.
       * _assess_output_quality called with kwargs preserved verbatim
         (expect_subtitle, subtitle_file, expect_hook, hook_applied).
       * No threshold values lowered.
       * No exception path that returns success.

Bug fix history (Track C C2, 2026-06-03):
  Phase A-1..A-4 refactor on 2026-05-28 (commit 765616d) extracted
  process_one_part to stages/part_renderer.py but FORGOT to copy
  the `from app.services.viral_scoring import score_part_for_market
  as _mv_score_part` line. The call site below kept working
  syntactically but raised a silent NameError caught by the
  surrounding try/except — making market_viral_scored emit a no-op
  for 6 days. Sprint 6.D-2.5c preserved the bug verbatim during the
  finalize extraction. Track C bug fix C2 restores the missing
  import on 2026-06-03. See ledger entry
  AUDIT_2026-06-02_followup_6.md for full timeline + impact
  assessment.

Cycle risk: NONE.
  Verified before extraction: run_part_finalize does not call any
  function in stages/part_renderer. The module imports come from leaf
  packages only (asset_pipeline, pipeline_config, pipeline_ranking,
  pipeline_segment_selection, qa_pipeline, render_events, render_output,
  part_render_context, part_render_setup, part_render_encode,
  domain.timeline, services.manifest_writer, services.render_engine).

LOC budget note:
  ~431 LOC moved — 43% over the Â§7 advisory cap of 300. Justified by:
  (a) cohesion — Layer 8→9 boundary is one logical sequence;
  (b) Sacred Contract #8 concentration — splitting would create
      artificial seams through the qa_pipeline validation surface;
  (c) plan Â§11 changelog entry 3 explicitly approved this scope.

Logger note (same pattern as 6.D-2.1 through 2.5d):
  `logger = logging.getLogger("app.render")` preserved verbatim.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

from app.domain.timeline import TimelineMap
from app.features.render.engine.pipeline.asset_pipeline import (
    _maybe_append_asset_outro,
    _maybe_apply_asset_logo,
    _maybe_prepend_asset_intro,
    _maybe_prepend_remotion_hook_intro,
)
from app.features.render.engine.pipeline.pipeline_config import extract_text_from_srt
from app.features.render.engine.pipeline.pipeline_ranking import resolve_combined_score_weights
from app.features.render.engine.pipeline.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _get_effective_playback_speed,
)
from app.features.render.engine.pipeline.qa_pipeline import (
    _assess_output_quality,
    _validate_render_output,
)
from app.features.render.engine.pipeline.render_events import (
    _emit_render_event,
    _job_log,
    _safe_unlink,
)
from app.features.render.engine.pipeline.render_output import RenderOutputResult
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.features.render.engine.stages.part_render_encode import RenderEncodeResult
from app.features.render.engine.stages.part_render_setup import RenderPreflightResult
from app.features.render.engine.stages.manifest_writer import manifest_path as _manifest_path
from app.features.render.engine.encoder.clip_ops import apply_micro_pacing
# Track C bug fix C2 (2026-06-03): restore the missing import that the
# Phase A-1..A-4 refactor on 2026-05-28 (commit 765616d) lost when it
# extracted process_one_part into stages/part_renderer.py. The call
# site at line ~361 below has been raising a silent NameError caught
# by try/except for 6 days, making market_viral_scored a no-op.
# See docs/review/AUDIT_2026-06-02_followup_6.md for the timeline +
# impact assessment.
from app.features.render.engine.stages.viral_scoring import score_part_for_market as _mv_score_part

# Preserve original logger name (same pattern as 6.D-2.1 through 2.5d).
logger = logging.getLogger("app.render")


def run_part_finalize(
    ctx: PartRenderContext,
    idx: int,
    seg: dict,
    srt_part: Path,
    ass_part: Path,
    final_part: Path,
    part_subtitle_enabled: bool,
    hook_overlay_applied_for_part: bool,
    hook_subtitle_formatted: bool,
    srt_count: int,
    trim_offset: float,
    effective_start: float,
    part_timeline: TimelineMap,
    t_part_start: float,
    cut_ms: int,
    first_frame_scan_ms: int,
    subtitle_ass_ms: int,
    preflight: RenderPreflightResult,
    encode: RenderEncodeResult,
) -> None:
    """Execute the per-part finalize block. See module docstring for the
    9-step responsibility breakdown.

    Raises:
        RuntimeError: when Sacred Contract #8 `_validate_render_output`
        returns ok=False. The caller (process_one_part) does NOT catch
        this — it propagates up to pipeline_render_loop.run_render_loop's
        per-part try/except, which records the failure in the per-part
        failed_parts list. This is the load-bearing failure path.
    """
    # Aliases preserve the original local variable names so the block
    # body below is byte-for-byte identical to the pre-2.5c code.
    _trim_offset = trim_offset
    _effective_start = effective_start
    _part_timeline = part_timeline
    _t_part_start = t_part_start
    _cut_ms = cut_ms
    _first_frame_scan_ms = first_frame_scan_ms
    _subtitle_ass_ms = subtitle_ass_ms
    _hook_subtitle_formatted = hook_subtitle_formatted
    _srt_count = srt_count
    _hook_overlay_applied_for_part = hook_overlay_applied_for_part
    _t_encode = preflight.t_encode
    _render_ms = encode.render_ms
    _motion_crop_fallback = preflight.motion_crop_fallback
    _quality_validation_ms = 0  # set below in step 9; declared early for the total_part log

    _micro_pacing_applied = False
    _micro_pacing_trim_sec = 0.0
    _micro_pacing_ms = 0
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
        overlay_composite_used=False,
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

