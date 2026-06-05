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
  4. AI timing-mutation deltas (tighten_setup / shorten_outro) when
     payload.ai_timing_mutation_enabled AND ctx.ai_edit_plan has
     applied_mutations. Each delta is bounded so the clip stays
     ≥ payload.min_part_sec after trim.
  5. TimelineMap + BaseClipManifest construction (timeline manifest
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
from app.orchestration.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _get_effective_playback_speed,
)
from app.orchestration.render_events import _emit_render_event, _job_log
from app.orchestration.stages.part_render_context import PartRenderContext
from app.services.db import upsert_job_part
from app.services.manifest_writer import write_manifest
from app.services.render_engine import (
    cut_video,
    detect_bad_first_frame,
    detect_silence_trim_offset,
)

# Preserve original logger name (same pattern as 6.D-2.1 / 6.D-2.2).
logger = logging.getLogger("app.render")

# Sprint 6 O-4 Commit 1 — feature-flag mirror reads.
# Same pattern as part_renderer.py / part_render_setup.py /
# part_render_encode.py / render_pipeline.py (four-site read drift-
# prevention). No drift possible — every site reads the same env vars
# deterministically at import time.
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
# Sprint 7.2 (2026-06-05): FEATURE_BASE_CLIP_VALIDATION_ARTIFACT removed —
# see render_pipeline.py for the closure rationale.


def _should_skip_raw_part_write(
    *,
    part_subtitle_enabled: bool,
    feature_base_clip_first: bool,
    feature_overlay_after_base_clip: bool,
) -> bool:
    """Sprint 6 audit O-4 predicate — Commit 1 (telemetry-only).

    Returns True when ``raw_part`` has zero downstream readers and
    ``cut_video`` could be fused into the final render encode. Three
    consumer sites today:

      C1  per-part Whisper at part_asset_planner.py:209
      C2  render_base_clip at part_render_encode.py (post Sprint 6 P0 HIGH gate)
      C3  render_part_smart at part_render_encode.py

    C1 is gated by ``part_subtitle_enabled``. C2 is gated by the same
    boolean ``_base_clip_consumer_active`` introduced in Sprint 6 P0
    HIGH. C3 is the only consumer the fuse would replace — its argv
    would change from ``-i raw_part`` to ``-ss start -t duration -i source``.

    The predicate is pure (no I/O, no side effects) so the truth-table
    test in tests/test_raw_part_skip_predicate.py can exercise it
    without constructing a PartRenderContext.

    Sprint 6 audit O-4 Commit 1 ships this predicate AS TELEMETRY ONLY.
    No skip is wired yet — ``run_cut_stage`` still calls ``cut_video``
    on every part. A future sprint commit will gate the actual skip on
    a feature flag (``FEATURE_RAW_PART_SKIP=0`` default) after manual
    visual review on 3-5 sample renders per SPRINT_PLAN risk register
    line 302.
    """
    base_clip_will_render = feature_base_clip_first and feature_overlay_after_base_clip
    return (not part_subtitle_enabled) and (not base_clip_will_render)


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

    # Sprint 6 audit O-4 Commit 1 — telemetry-only predicate evaluation.
    # Logs which parts WOULD be eligible to skip the raw_part write if the
    # actual fuse were enabled. No behavior change today. The data shows
    # up at debug level so production logs stay quiet by default; turn on
    # render debug logging to see the per-part predicate state.
    _part_subtitle_enabled = ctx.subtitle_enabled_by_idx.get(idx, False)
    if _should_skip_raw_part_write(
        part_subtitle_enabled=_part_subtitle_enabled,
        feature_base_clip_first=_FEATURE_BASE_CLIP_FIRST,
        feature_overlay_after_base_clip=_FEATURE_OVERLAY_AFTER_BASE_CLIP,
    ):
        _job_log(
            ctx.effective_channel,
            ctx.job_id,
            f"raw_part_skip_eligible part={idx} predicate=true "
            f"subtitle_enabled=False base_clip_consumer=False",
            kind="debug",
        )

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
