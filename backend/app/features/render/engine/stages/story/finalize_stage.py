"""
finalize_stage.py — Story v2 finalize (extracted from story_pipeline_v2.py, A0
refactor — behaviour unchanged).

QA gate (Sacred Contract #8) → thumbnail → part repoint → terminal result_json
(with the Sacred Contract #1 aliases: output_rank_score / is_best_output /
is_best_clip) → DONE. Raises RuntimeError on QA failure so process_render writes the
terminal failed row.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

from app.core.stage import JobStage
from app.db.jobs_repo import upsert_job
from app.features.render.ai.llm.story_prompts_v2 import SUPER_PROMPT_VERSION
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log

logger = logging.getLogger("app.render.story")


def _finalize_story_v2(job_id, effective_channel, payload, plan, *, output_dir, output_stem,
                       final_out, assembly, clips, shots_dir, total_parts,
                       failed_parts, visual_fallbacks, plan_meta=None):
    """QA gate + thumbnail + part repoint + terminal result_json / DONE. Raises
    RuntimeError on QA failure (Sacred Contract #8). Mirrors finalize_story for v2."""
    _exp = float(assembly.get("expected_duration") or 0.0)
    _qa = _validate_render_output(
        final_out, expected_duration=(_exp if _exp > 0 else None), expect_audio=True,
    )
    if not _qa["ok"]:
        raise RuntimeError(f"Story v2: output failed QA: {_qa.get('error')}")
    _final_dur = float(_qa["metadata"].get("duration") or 0.0)

    _thumb_path = ""
    if os.getenv("STORY_THUMBNAIL", "1") == "1":
        try:
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
            logger.warning("story v2: thumbnail failed (non-fatal): %s", _th_exc)

    try:
        from app.db.jobs_repo import update_part_output_path
        for i in range(1, total_parts + 1):
            update_part_output_path(job_id, i, str(final_out))
    except Exception as exc:
        logger.warning("story v2: part repoint failed (non-fatal): %s", exc)
    try:
        shutil.rmtree(shots_dir, ignore_errors=True)
    except Exception:
        pass

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
        "visual_fallback_visuals": visual_fallbacks,
        "selected_segments_count": total_parts,
        "image_count": plan.image_count(),
        "beat_count": plan.beat_count(),
        "total_sec": getattr(plan.render, "total_sec", 0.0),
        "is_partial_success": bool(failed_parts),
        "ai_director": {"enabled": True, "mode": "story_v2"},
        # Reproducibility (Phase 3): which prompt version + provider/model produced
        # this plan. Additive — never touches the Sacred Contract #1 keys above.
        "story_prompt_version": SUPER_PROMPT_VERSION,
        "story_provider": (plan_meta or {}).get("provider", ""),
        "story_llm_model": (plan_meta or {}).get("model", ""),
        "story_plan_source": (plan_meta or {}).get("plan_source", ""),
    }
    _terminal_status = "completed_with_errors" if failed_parts else "completed"
    upsert_job(
        job_id, "render", effective_channel, _terminal_status, payload.model_dump(), _result,
        stage=JobStage.DONE, progress_percent=100,
        message=(
            f"Story complete: {len(clips)}/{total_parts} cue(s), {_final_dur:.0f}s"
            + (f" ({len(failed_parts)} failed)" if failed_parts else "")
        ),
    )
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id, event="render.complete",
        level="INFO", message="Story render complete", step="render.complete",
        context={"duration_sec": _final_dur, "cues": total_parts,
                 "rendered": len(clips), "failed": len(failed_parts)},
    )
    _job_log(effective_channel, job_id,
             f"Story v2 DONE: {len(clips)}/{total_parts} cue(s) ({_final_dur:.0f}s)")


__all__ = ["_finalize_story_v2"]
