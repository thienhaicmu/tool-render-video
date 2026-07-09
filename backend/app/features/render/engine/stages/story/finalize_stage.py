"""
finalize_stage.py — QA gate + thumbnail + part-repoint + terminal result_json /
DONE for a Story render (P5). Mirrors Content's finalize_content:
Sacred Contract #8 (never bypass QA), #1 (result_json carries output_rank_score /
is_best_output / is_best_clip), #4 (stage DONE), partial-success →
completed_with_errors. Raises RuntimeError on QA failure.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from app.core.stage import JobStage
from app.db.jobs_repo import upsert_job
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log

logger = logging.getLogger("app.render.story")


def finalize_story(ctx, plan, payload, *, output_dir, output_stem, final_out, assembly,
                   shot_clips, shots_dir, total_parts, failed_parts, visual_fallbacks, budget):
    """Validate + finalize the assembled Story video. Raises RuntimeError when QA
    fails (Sacred Contract #8)."""
    job_id = ctx.job_id
    effective_channel = ctx.effective_channel

    # QA gate (Sacred Contract #8 — never bypassed).
    _exp = float(assembly.get("expected_duration") or 0.0)
    _qa = _validate_render_output(
        final_out, expected_duration=(_exp if _exp > 0 else None), expect_audio=True,
    )
    if not _qa["ok"]:
        raise RuntimeError(f"Story: output failed QA: {_qa.get('error')}")
    _final_dur = float(_qa["metadata"].get("duration") or 0.0)

    # Best-effort poster thumbnail (~1/3 in). Never fails the render.
    _thumb_path = ""
    if os.getenv("STORY_THUMBNAIL", "1") == "1":
        try:
            import subprocess
            from app.services.bin_paths import get_ffmpeg_bin
            _thumb = output_dir / f"{final_out.stem}.thumb.jpg"
            _tss = max(0.5, _final_dur / 3.0)
            subprocess.run(
                [get_ffmpeg_bin(), "-y", "-ss", f"{_tss:.2f}", "-i", str(final_out),
                 "-frames:v", "1", "-q:v", "3", str(_thumb)],
                capture_output=True, timeout=60,
            )
            if _thumb.exists() and _thumb.stat().st_size > 0:
                _thumb_path = str(_thumb)
        except Exception as _th_exc:
            logger.warning("story: thumbnail failed (non-fatal): %s", _th_exc)

    # Repoint shot part rows at the final video BEFORE deleting intermediates.
    try:
        from app.db.jobs_repo import update_part_output_path
        for i in range(1, total_parts + 1):
            update_part_output_path(job_id, i, str(final_out))
    except Exception as exc:
        logger.warning("story: part repoint failed (non-fatal): %s", exc)
    try:
        shutil.rmtree(shots_dir, ignore_errors=True)
    except Exception:
        pass

    # Terminal result_json + DONE (Sacred Contract #1 keys on output).
    _topic = (getattr(plan, "topic", "") or output_stem)
    _entry = {
        "part_no": 1, "path": str(final_out), "output_file": str(final_out),
        "output_path": str(final_out), "title": _topic,
        "clip_name": output_stem, "ai_title": (getattr(plan, "topic", "") or ""),
        "start_sec": 0.0, "end_sec": _final_dur, "duration": _final_dur,
        "viral_score": 100.0,
        # Sacred Contract #1 keys — present on EVERY output.
        "output_rank_score": 100.0, "is_best_output": True, "is_best_clip": True,
    }
    _result = {
        "outputs": [_entry],
        "render_format": "story",
        "story_topic": getattr(plan, "topic", ""),
        "story_series_id": getattr(plan, "series_id", ""),
        "story_chapter_no": getattr(plan, "chapter_no", 0),
        "output_ranking": [dict(_entry, output_rank=1)],
        "best_clip": _entry,
        "successful_outputs_count": 1,
        "failed_outputs_count": len(failed_parts),
        "failed_parts": [int(f["part_no"]) for f in failed_parts],
        "thumbnail_path": _thumb_path,
        "visual_fallback_shots": visual_fallbacks,
        "selected_segments_count": total_parts,
        "scene_count": plan.scene_count(),
        "shot_count": plan.shot_count(),
        "is_partial_success": bool(failed_parts),
        "ai_director": {"enabled": True, "mode": "story"},
        "ai_cost": {"estimated": round(getattr(budget, "spent", 0.0), 3),
                    "budget_cap": getattr(budget, "cap", 0.0)},
    }
    _terminal_status = "completed_with_errors" if failed_parts else "completed"
    upsert_job(
        job_id, "render", effective_channel, _terminal_status, payload.model_dump(), _result,
        stage=JobStage.DONE, progress_percent=100,
        message=(
            f"Story complete: {len(shot_clips)}/{total_parts} shots, {_final_dur:.0f}s"
            + (f" ({len(failed_parts)} failed)" if failed_parts else "")
        ),
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id, event="render.complete",
        level="INFO", message="Story render complete", step="render.complete",
        context={"duration_sec": _final_dur, "shots": total_parts,
                 "rendered": len(shot_clips), "failed": len(failed_parts)},
    )
    _job_log(effective_channel, job_id,
             f"Story DONE: {len(shot_clips)}/{total_parts} shots ({_final_dur:.0f}s)")


__all__ = ["finalize_story"]
