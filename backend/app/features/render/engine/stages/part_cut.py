"""Per-part CUT stage — post-WAITING / pre-RENDERING block.

Sprint 6.D-2.3 — extracted verbatim from stages/part_renderer.py
(lines 182-349 of the pre-2.3 file). No logic changes; pure relocation.

run_cut_stage() runs once per part during process_one_part, immediately
after the JobPartStage.WAITING upsert and before the prepare_part_assets
call (which is itself Sprint 6.D-2.2's extracted module).

Block responsibilities (in order):
  1. Per-part timing-metric counters (cut_ms, first_frame_scan_ms).
  2. detect_silence_trim_offset on the source path. Skipped if the
     resulting trim would leave < 3.0 s of clip. Emits
     `silence_trim_applied` event when applied.
  3. detect_bad_first_frame visual scan. When trim is feasible
     (clip still ≥ 3.0 s after combined offset), sets
     force_accurate_cut=True and emits `first_frame_shift_applied`.
  4. TimelineMap + BaseClipManifest construction (timeline manifest
     pre-cut snapshot — written to disk).
  6. JobPartStage.CUTTING upsert (Sacred Contract #5 — frozen
     state-machine transition, line 328 of original).
  7. cut_video() call when not resuming a valid cached raw clip;
     emits `accurate_cut_forced` when force_accurate_cut is True.
  8. Manifest cut_path write (post-cut snapshot).

Returns CutStageResult with 9 fields the downstream RENDER block
in process_one_part needs:
    trim_offset, effective_start, effective_end, force_accurate_cut,
    visual_trim, part_timeline, part_manifest, cut_ms, first_frame_scan_ms.

The caller (process_one_part) aliases each returned field back to its
original local-variable name so the rest of the function is byte-for-byte
unchanged.

Sacred Contracts honored:
  - #5 Frozen part-stage: JobPartStage.CUTTING via enum reference only.
       Grep confirms no string literal "CUTTING" introduced.
  - #6 _emit_render_event signature: 3 call sites preserved verbatim
       (silence_trim_applied, first_frame_shift_applied,
       accurate_cut_forced) with identical kwargs.
  - #7 Sole DB writer: upsert_job_part(JobPartStage.CUTTING, ...) at
       line 328 of original routes through app.services.db unchanged.

Logger note (same pattern as 6.D-2.1 / 6.D-2.2):
  `logger = logging.getLogger("app.render")` preserved verbatim so
  existing log routing resolves identically.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.stage import JobPartStage
from app.domain.manifests import BaseClipManifest
from app.domain.timeline import TimelineMap
from app.features.render.engine.pipeline.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _get_effective_playback_speed,
)
from app.features.render.engine.stages.part_render_plan_resolvers import _resolve_pacing_speed_delta
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.db.jobs_repo import upsert_job_part
from app.features.render.engine.stages.manifest_writer import write_manifest
from app.features.render.engine.encoder.clip_ops import (
    cut_video,
    detect_bad_first_frame,
    detect_silence_trim_offset,
)

# Preserve original logger name (same pattern as 6.D-2.1 / 6.D-2.2).
logger = logging.getLogger("app.render")



@dataclass
class CutStageResult:
    """Bundle of values produced by run_cut_stage — caller aliases each
    field back to its original local-variable name so the rest of
    process_one_part is byte-for-byte unchanged."""
    trim_offset: float
    effective_start: float
    effective_end: float
    force_accurate_cut: bool
    visual_trim: float
    part_timeline: TimelineMap
    part_manifest: BaseClipManifest
    cut_ms: int
    first_frame_scan_ms: int


def run_cut_stage(
    ctx: PartRenderContext,
    idx: int,
    seg: dict,
    raw_part: Path,
    part_name: str,
    final_part: Path,
) -> CutStageResult:
    """Execute the CUT stage of one part. See module docstring for the
    8-step responsibility breakdown.

    Raises whatever cut_video() raises on cut failure — the caller's
    outer try/except (in process_one_part) classifies the failure.
    """
    _trim_offset = 0.0
    _cut_ms = _first_frame_scan_ms = 0

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

    _pacing_delta_cut, _platform_delta_cut = _resolve_pacing_speed_delta(ctx, idx, ctx.target_platform)
    _part_platform_delta = _pacing_delta_cut + _platform_delta_cut
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
        payload_speed=float(ctx.payload.playback_speed or 1.0),
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
        ai_mode=None,
        ai_selected=False,
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

    return CutStageResult(
        trim_offset=_trim_offset,
        effective_start=_effective_start,
        effective_end=_effective_end,
        force_accurate_cut=_force_accurate_cut,
        visual_trim=_visual_trim,
        part_timeline=_part_timeline,
        part_manifest=_part_manifest,
        cut_ms=_cut_ms,
        first_frame_scan_ms=_first_frame_scan_ms,
    )

