"""Per-part DONE stage — quality intelligence + cover frame + terminal upsert.

Sprint 6.D-2.5d — extracted verbatim from stages/part_renderer.py
(lines 939-1037 of the post-2.5a file). No logic changes; pure relocation.

run_part_done() is the FINAL block of process_one_part. It runs after
Sprint 6.D-2.5c's validation phase (run_part_finalize) and is
responsible for the terminal JobPartStage.DONE transition + the
return dict that the per-part worker hands back to the orchestrator.

Block responsibilities (in order):
  1. _assess_render_quality_intelligence — wraps qa_pipeline's AI quality
     evaluator. Result is silently dropped (any exception caught by the
     outer try/except). Sacred Contract #3 holds: AI module returns None
     on failure — no propagation.
  2. Cover frame selection + extraction:
       - _select_cover_frame_time() chooses an offset using ai_edit_plan
         hints when available.
       - Optional S4 thumbnail quality selection when
         S4_THUMBNAIL_QUALITY_ENABLED=1.
       - extract_thumbnail_frame() falls back when S4 fails or returns nothing.
       - cover_frame_selected emit when bytes were extracted.
       - Outer try/except logs cover_frame_extraction_failed on any error
         and continues — never blocks the part completion.
  3. JobPartStage.DONE upsert (Sacred Contract #5 — frozen terminal
     transition with progress=100).
  4. Row construction for /api/jobs result_json[outputs] table.
  5. Optional cleanup of raw_part / srt_part / ass_part when
     payload.cleanup_temp_files is True.
  6. Return dict: {idx, output, row, skipped: False}.

Returns:
  dict with the same shape process_one_part already returned to its
  ThreadPoolExecutor caller in pipeline_render_loop.run_render_loop:
    {"idx": idx, "output": str(final_part), "row": row, "skipped": False}

Sacred Contracts honored:
  - #3 AI return-None contract: _assess_render_quality_intelligence
       lives in qa_pipeline (an orchestration module, not under
       backend/app/ai/**). It already catches all exceptions and
       returns None — and this caller wraps it in an additional
       try/except: pass for belt-and-suspenders safety.
  - #5 Frozen part-stage names: JobPartStage.DONE via enum reference
       only. Grep-confirmed no string literal "DONE" introduced.
  - #6 _emit_render_event signature: 1 call site preserved verbatim
       (cover_frame_selected) with identical kwargs.
  - #7 Sole DB writer: 1 upsert_job_part(JobPartStage.DONE, ...) call
       routes through app.services.db unchanged.

Bug fix history (Track C C1, 2026-06-03):
  The pre-extraction code at the original line 942 referenced `srt_path`
  which was never defined (typo for `srt_part`). NameError was caught
  by the surrounding try/except, making _assess_render_quality_intelligence
  effectively a silent no-op for ALL renders. Sprint 6.D-2.5d preserved
  the typo verbatim per the no-while-I-am-here convention. Track C bug
  fix C1 corrected the typo on 2026-06-03 — the function now actually
  runs when SRT is available. See ledger entry
  AUDIT_2026-06-02_followup_5.md for full impact assessment.

Logger note (same pattern as 6.D-2.1 through 2.5a):
  `logger = logging.getLogger("app.render")` preserved verbatim.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from app.core.stage import JobPartStage
from app.features.render.engine.pipeline.pipeline_segment_selection import _select_cover_frame_time
from app.features.render.engine.pipeline.qa_pipeline import _assess_render_quality_intelligence
from app.features.render.engine.pipeline.render_events import (
    _emit_render_event,
    _job_log,
    _safe_unlink,
)
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.db.jobs_repo import upsert_job_part
from app.features.render.engine.encoder.ffmpeg_helpers import extract_thumbnail_frame

# Preserve original logger name (same pattern as 6.D-2.1 through 2.5a).
logger = logging.getLogger("app.render")


def run_part_done(
    ctx: PartRenderContext,
    idx: int,
    seg: dict,
    raw_part: Path,
    srt_part: Path,
    ass_part: Path,
    final_part: Path,
    part_name: str,
    srt_meta: dict,
    variant_type: str,
    part_subtitle_enabled: bool,
) -> dict:
    """Execute the per-part DONE block. See module docstring for the
    6-step responsibility breakdown.

    Returns the dict process_one_part hands back to its caller in
    pipeline_render_loop.run_render_loop.
    """
    # Aliases preserve the original local variable names so the block
    # body below is byte-for-byte identical to the pre-2.5d code.
    _srt_meta = srt_meta
    _variant_type = variant_type

    try:
        _qi_srt = ass_part if part_subtitle_enabled and ass_part and ass_part.suffix == ".srt" else None
        _qi_srt_path: Path | None = None
        # Track C bug fix C1 (2026-06-03): the original code referenced
        # `srt_path` here (undefined NameError caught by surrounding try/except),
        # which made _assess_render_quality_intelligence a silent no-op.
        # Restored to use `srt_part` — the function parameter holding the
        # per-part SRT file path — which is the most likely original intent.
        # See docs/review/AUDIT_2026-06-02_followup_5.md for the full impact
        # assessment.
        if srt_part is not None and Path(str(srt_part)).exists():
            _qi_srt_path = Path(str(srt_part))
        elif _qi_srt is not None and Path(str(_qi_srt)).exists():
            _qi_srt_path = Path(str(_qi_srt))
        _qi_manifest: Path | None = None
        try:
            from app.features.render.ai.tracing import _DEFAULT_LOG_DIR as _ai_log_dir
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
            if _cover_hint_ratio is None:
                _raw_ratio = seg.get("cover_hint_ratio")
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
                from app.features.render.engine.thumbnail.thumbnail_quality import select_best_thumbnail
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
    row = [ctx.job_id, ctx.effective_channel, ctx.source["title"], idx, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("priority_rank", idx), str(final_part)]
    if ctx.payload.cleanup_temp_files:
        _safe_unlink(raw_part)
        _safe_unlink(srt_part)
        _safe_unlink(ass_part)
    return {"idx": idx, "output": str(final_part), "row": row, "skipped": False}

