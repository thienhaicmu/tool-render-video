"""Render-pipeline finalize stage â€” success-path terminal block.

Sprint 6.D-1.5 â€” extracted verbatim from render_pipeline.py
(lines 1295â€“1455 of the pre-extraction file). No logic changes;
pure relocation. The block runs only after a successful render loop
and is responsible for:

  1. Auto Best Export (P5-2): copy top-N ranked outputs to <output_dir>/best/.
  2. Final status determination (completed vs completed_with_errors).
  3. result_json assembly + terminal upsert_job(JobStage.DONE).
  4. Opportunistic DB backup hook (Sprint 6.A).
  5. Final logging + render.ffmpeg.success / render.complete WS events.

Sacred Contracts honored (CLAUDE.md):
  - #1: keys output_rank_score / is_best_clip / is_best_output are set
        in the ranking stage upstream and copied through unchanged here.
  - #4: terminal job stage emitted is JobStage.DONE.
  - #6: _emit_render_event signature/shape unchanged.
  - #7: only DB writer is upsert_job (db/jobs_repo).
  - #8: qa_pipeline not bypassed â€” this block fires only after the
        success path already cleared qa_pipeline upstream.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.models.schemas import RenderRequest
from app.services.db import upsert_job
from app.core.stage import JobStage
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log


@dataclass
class FinalizeContext:
    """State bundle passed from run_render_pipeline into run_render_finalize.

    Every field corresponds to a local variable in run_render_pipeline at
    the moment finalize is entered. Field names mirror the originals with
    leading underscores dropped (e.g. _output_stem â†’ output_stem) so the
    dataclass surface reads naturally; the orchestrator binds each field
    explicitly when constructing the context.
    """
    job_id: str
    effective_channel: str
    payload: RenderRequest
    started_at: datetime
    output_dir: Path
    output_stem: str

    outputs: list
    failed_parts: list
    total_parts: int
    scored: list
    recovery_notes: list

    rank_entries: list
    rank_entries_ordered: list
    best_rank_entry: Optional[dict]
    partial_warning: str

    preset_name: str
    preset_id: str
    preset_label: str
    mv_parts: list

    voice_summary: Any
    subtitle_translate_summary: Any
    ai_influence_report: dict
    ai_beat_report: dict


def run_render_finalize(ctx: FinalizeContext) -> str:
    """Execute the success-path finalize block.

    Returns:
        _final_status string ("completed" or "completed_with_errors"),
        consumed by the caller's finally block to decide whether the
        preview session can be cleaned up.
    """
    job_id              = ctx.job_id
    effective_channel   = ctx.effective_channel
    payload             = ctx.payload
    started_at          = ctx.started_at
    output_dir          = ctx.output_dir
    _output_stem        = ctx.output_stem
    outputs             = ctx.outputs
    failed_parts        = ctx.failed_parts
    total_parts         = ctx.total_parts
    scored              = ctx.scored
    _recovery_notes     = ctx.recovery_notes
    _rank_entries       = ctx.rank_entries
    _rank_entries_ordered = ctx.rank_entries_ordered
    _best_rank_entry    = ctx.best_rank_entry
    _partial_warning    = ctx.partial_warning
    _preset_name        = ctx.preset_name
    _preset_id          = ctx.preset_id
    _preset_label       = ctx.preset_label
    _mv_parts           = ctx.mv_parts
    _voice_summary      = ctx.voice_summary
    _subtitle_translate_summary = ctx.subtitle_translate_summary
    _ai_influence_report = ctx.ai_influence_report
    _ai_beat_report     = ctx.ai_beat_report

    # â”€â”€ P5-2 Auto Best Export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _best_exports_list: list[dict] = []
    if getattr(payload, "auto_best_export_enabled", False):
        if _rank_entries:
            _abe_count = max(1, min(10, int(getattr(payload, "auto_best_export_count", 3) or 3)))
            _abe_top   = _rank_entries[:_abe_count]  # already sorted desc by score
            _best_dir  = output_dir / "best"
            try:
                _best_dir.mkdir(parents=True, exist_ok=True)
                for _abe in _abe_top:
                    _abe_src = Path(_abe["output_file"])
                    _abe_dst = _best_dir / f"{_output_stem}_rank_{_abe['output_rank']:02d}.mp4"
                    try:
                        shutil.copy2(str(_abe_src), str(_abe_dst))
                        _best_exports_list.append({
                            "rank":              _abe["output_rank"],
                            "part_no":           _abe["part_no"],
                            "source_file":       str(_abe_src),
                            "best_file":         str(_abe_dst),
                            "output_score":      _abe["output_score"],
                            "output_rank_score": _abe["output_rank_score"],
                            "ranking_reason":    _abe["ranking_reason"],
                        })
                    except Exception as _abe_copy_err:
                        _job_log(
                            effective_channel, job_id,
                            f"best_export copy failed part_{_abe['part_no']:03d}: {_abe_copy_err}",
                            kind="warning",
                        )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="best_export_completed",
                    level="INFO",
                    message=f"Best export: {len(_best_exports_list)}/{len(_abe_top)} files â†’ {_best_dir}",
                    step="render.best_export",
                    context={
                        "count":          len(_best_exports_list),
                        "best_dir":       str(_best_dir),
                        "exported_files": [e["best_file"] for e in _best_exports_list],
                    },
                )
            except Exception as _abe_err:
                _job_log(
                    effective_channel, job_id,
                    f"best_export_failed: {_abe_err}",
                    kind="warning",
                )
        else:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="best_export_skipped",
                level="INFO",
                message="Best export skipped: no ranked outputs available",
                step="render.best_export",
                context={"reason": "no_ranked_outputs"},
            )

    _is_partial_success = bool(failed_parts)
    _final_status = "completed_with_errors" if _is_partial_success else "completed"
    _final_message = (
        f"Render complete: {len(outputs)}/{total_parts} clips Ã‚Â· {len(failed_parts)} failed"
        if _is_partial_success else "Render completed"
    )
    if _recovery_notes:
        _final_message += " [" + "; ".join(_recovery_notes) + "]"

    # Phases 30, 45, 49A (AI output ranking, quality evaluation, UX metadata)
    # removed in Phase G. All consumed _ai_edit_plan which is None after E3.
    # Result payload keeps the keys with default empty values for consumer compat.
    _ai_output_ranking: dict = {"available": False, "mode": "recommendation_only"}
    _ai_render_quality: dict = {"available": False, "evaluation_mode": "evaluation_only"}
    _ai_ux_metadata: dict = {"available": False}

    _result_payload = {
        "outputs": outputs,
        "render_preset": _preset_name,
        "render_preset_id": _preset_id,
        "render_preset_label": _preset_label,
        "segments": scored,
        "market_viral_parts": _mv_parts,
        "output_ranking": _rank_entries_ordered,
        "output_ranking_warning": _partial_warning,
        "best_clip": _best_rank_entry,
        "best_exports": _best_exports_list,
        "voice_summary": _voice_summary,
        "subtitle_translate_summary": _subtitle_translate_summary,
        "failed_parts": [int(f["part_no"]) for f in failed_parts],
        "failed_parts_detail": failed_parts,
        "selected_segments_count": total_parts,
        "successful_outputs_count": len(outputs),
        "failed_outputs_count": len(failed_parts),
        "is_partial_success": _is_partial_success,
        "ai_director": {"enabled": False},
        "ai_render_influence": _ai_influence_report,
        "ai_beat_execution": _ai_beat_report,
        "story": {},
        "preset_evolution": {},
        "creator_style": {},
        "ai_output_ranking": _ai_output_ranking,
        "ai_render_quality_evaluation": _ai_render_quality,
        "ai_ux": _ai_ux_metadata,
        "recovery_notes": _recovery_notes,
    }
    upsert_job(
        job_id,
        "render",
        effective_channel,
        _final_status,
        payload.model_dump(),
        _result_payload,
        stage=JobStage.DONE,
        progress_percent=100,
        message=_final_message,
    )
    # AI Memory write (Phase 3) removed in Phase G â€” consumed _ai_edit_plan (None after E3).
    # Sprint 6.A: opportunistic db backup after a completed render. Wrapped
    # so any backup failure CANNOT propagate into the render pipeline.
    # Triggers every Nth job or after the configured time interval (see
    # app.services.db_backup). Sacred Contract 7 follow-up.
    try:
        from app.features.render.engine.pipeline.db_backup import maybe_snapshot_after_job
        maybe_snapshot_after_job()
    except Exception:
        pass

    _job_log(
        effective_channel,
        job_id,
        f"Render final summary: status={_final_status} "
        f"successful_outputs={len(outputs)} failed_outputs={len(failed_parts)} "
        f"selected_segments={total_parts}",
        kind="warning" if _is_partial_success else "info",
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.ffmpeg.success",
        level="WARNING" if _is_partial_success else "INFO",
        message="FFmpeg render completed with errors" if _is_partial_success else "FFmpeg render completed",
        step="render.ffmpeg",
        context={"outputs": len(outputs), "failed_outputs": len(failed_parts), "total_parts": total_parts},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.complete_with_errors" if _is_partial_success else "render.complete",
        level="WARNING" if _is_partial_success else "INFO",
        message=_final_message,
        step="render.complete",
        duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
        context={
            "outputs": len(outputs),
            "failed_outputs": len(failed_parts),
            "total_parts": total_parts,
            "is_partial_success": _is_partial_success,
            "voice_summary": _voice_summary,
            "subtitle_translate_summary": _subtitle_translate_summary,
        },
    )

    return _final_status
