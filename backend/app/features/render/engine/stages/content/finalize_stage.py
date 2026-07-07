"""
finalize_stage.py — QA gate + thumbnail + part-repoint + terminal result_json /
DONE for a Content render (CM-6 extract). Sacred Contracts #8 (never bypass QA),
#1 (result_json carries output_rank_score / is_best_output / is_best_clip), #4
(stage DONE), MED-1 (partial success → completed_with_errors). Byte-for-byte the
former inline block; raises RuntimeError on QA failure.
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

logger = logging.getLogger("app.render.content")


def finalize_content(ctx, plan, payload, *, output_dir, output_stem, final_out, assembly,
                     scene_clips, scenes_dir, total_parts, failed_parts, visual_fallbacks,
                     visual_provider, budget, scene_providers):
    """Validate + finalize the assembled video: QA gate, thumbnail, repoint scene
    parts, clean intermediates, write the terminal result_json + DONE row. Raises
    RuntimeError when QA fails (Sacred Contract #8)."""
    job_id = ctx.job_id
    effective_channel = ctx.effective_channel

    # 6. QA gate (Sacred Contract #8 — never bypassed) ---------------------
    _exp = float(assembly.get("expected_duration") or 0.0)
    _qa = _validate_render_output(
        final_out, expected_duration=(_exp if _exp > 0 else None), expect_audio=True,
    )
    if not _qa["ok"]:
        raise RuntimeError(f"Content: output failed QA: {_qa.get('error')}")
    _final_dur = float(_qa["metadata"].get("duration") or 0.0)

    # E2: best-effort poster thumbnail from the finished video (~1/3 in).
    # Never fails the render (Sacred Contract #3 spirit).
    _thumb_path = ""
    if os.getenv("CONTENT_THUMBNAIL", "1") == "1":
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
                _job_log(effective_channel, job_id, f"Content: thumbnail → {_thumb.name}")
        except Exception as _th_exc:
            logger.warning("content: thumbnail failed (non-fatal): %s", _th_exc)

    # Repoint scene part rows at the final video BEFORE deleting the scene
    # intermediates, so every per-part surface keeps a live output link.
    try:
        from app.db.jobs_repo import update_part_output_path
        for i in range(1, total_parts + 1):
            update_part_output_path(job_id, i, str(final_out))
    except Exception as exc:
        logger.warning("content: part repoint failed (non-fatal): %s", exc)
    try:
        shutil.rmtree(scenes_dir, ignore_errors=True)
    except Exception:
        pass

    # 7. Terminal result_json + DONE (Sacred Contract #1 keys on output) ---
    _entry = {
        "part_no": 1, "path": str(final_out), "output_file": str(final_out),
        "output_path": str(final_out), "title": (plan.topic or output_stem),
        "clip_name": output_stem, "ai_title": (plan.topic or ""),
        "start_sec": 0.0, "end_sec": _final_dur, "duration": _final_dur,
        "viral_score": 100.0,
        # Sacred Contract #1 keys — present on EVERY output.
        "output_rank_score": 100.0, "is_best_output": True, "is_best_clip": True,
    }
    _result = {
        "outputs": [_entry],
        "render_format": "content",
        "content_plan": plan.to_json(),
        "content_topic": plan.topic,
        "content_tone": plan.tone,
        "content_audience": plan.audience,
        "output_ranking": [dict(_entry, output_rank=1)],
        "best_clip": _entry,
        "successful_outputs_count": 1,
        "failed_outputs_count": len(failed_parts),
        "failed_parts": [int(f["part_no"]) for f in failed_parts],
        "visual_provider": visual_provider,
        "thumbnail_path": _thumb_path,   # E2
        "visual_fallback_scenes": visual_fallbacks,
        "selected_segments_count": total_parts,
        "is_partial_success": bool(failed_parts),
        "ai_director": {"enabled": True, "mode": "content"},
        # CU-8/9: which visual provider each scene used + estimated paid cost.
        "ai_cost": {
            "estimated": round(budget.spent, 3),
            "budget_cap": budget.cap,
            "by_provider": {
                _p: sum(1 for _v in scene_providers.values() if _v == _p)
                for _p in sorted(set(scene_providers.values()))
            },
        },
    }
    # MED-1: a partial success (some scenes failed but ≥1 delivered) reports
    # "completed_with_errors" so the UI/history flag it — matching the clips /
    # recap convention. Job STAGE stays DONE (Sacred Contract #4).
    _terminal_status = "completed_with_errors" if failed_parts else "completed"
    upsert_job(
        job_id, "render", effective_channel, _terminal_status, payload.model_dump(), _result,
        stage=JobStage.DONE, progress_percent=100,
        message=(
            f"Content complete: {len(scene_clips)}/{total_parts} scenes, {_final_dur:.0f}s"
            + (f" ({len(failed_parts)} failed)" if failed_parts else "")
        ),
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id, event="render.complete",
        level="INFO", message="Content render complete", step="render.complete",
        context={
            "duration_sec": _final_dur, "scenes": total_parts,
            "rendered": len(scene_clips), "failed": len(failed_parts),
        },
    )
    _job_log(
        effective_channel, job_id,
        f"Content DONE: {len(scene_clips)}/{total_parts} scenes ({_final_dur:.0f}s)",
    )
