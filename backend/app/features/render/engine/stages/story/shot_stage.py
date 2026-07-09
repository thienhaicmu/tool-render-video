"""
shot_stage.py — render ONE Story shot end-to-end (P5).

TTS (cast voice, language-routed engine) → AI image (gpt-image-1, tier + character
reference) → optional Vision QA → compose (background + Ken Burns + subtitle + mux).
Reuses Content's synthesize_scene_narration + render_content_scene verbatim (a Shot
duck-types as a "scene": same getattr fields). Returns
``{idx, clip|None, error|None, fallback?}``; raises JobCancelledError on cancel.

Sacred Contract #5: per-shot part status from the frozen set (QUEUED/RENDERING/
DONE/FAILED). Sacred Contract #3: AI helpers return None on failure → the shot
falls back to a plain background rather than aborting the render.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.stage import JobPartStage
from app.db.jobs_repo import upsert_job_part
from app.jobs import cancel as cancel_registry
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
from app.features.render.engine.pipeline.render_events import _job_log
from app.features.render.engine.stages.content_scene_render import (
    render_content_scene,
    synthesize_scene_narration,
)
from app.features.render.engine.visual.story_image import generate_shot_image
from app.features.render.engine.visual.story_decision import decide_shot_asset

logger = logging.getLogger("app.render.story")


def _story_qa_max_retry() -> int:
    """Max Vision-QA regenerations per shot (P8). Only consulted when Vision QA is
    on. Default 2. Never raises."""
    try:
        return max(0, int(os.getenv("STORY_QA_MAX_RETRY", "2") or 2))
    except (TypeError, ValueError):
        return 2


def render_one_shot(ctx, plan, bible, part_no: int, scene, shot, cast: dict, budget) -> dict:
    """Compose one shot → {idx, clip|None, error|None, fallback?}. Resumes from a
    valid existing shot clip. Raises JobCancelledError on cancel."""
    job_id = ctx.job_id
    effective_channel = ctx.effective_channel
    part_name = f"shot_{part_no:04d}"
    shot_out = str(ctx.shots_dir / f"{part_name}.mp4")

    # Resume (disk-truth): reuse a shot clip that already passes QA.
    if Path(shot_out).exists() and Path(shot_out).stat().st_size > 0:
        _rq = _validate_render_output(Path(shot_out), expect_audio=True)
        if _rq.get("ok"):
            upsert_job_part(job_id, part_no, part_name, JobPartStage.DONE,
                            progress_percent=100,
                            duration=float(_rq["metadata"].get("duration") or 0.0),
                            output_file=shot_out, message=(shot.shot_type or ""))
            return {"idx": part_no, "clip": shot_out, "error": None}

    if ctx.cancel_cb():
        raise cancel_registry.JobCancelledError()

    # ── 1/3 narration (TTS, cast voice) ──────────────────────────────────────
    upsert_job_part(job_id, part_no, part_name, JobPartStage.RENDERING,
                    progress_percent=15, message="synthesizing narration")
    entry = cast.get((shot.speaker or "").strip()) or cast.get("") or {}
    voice_id = entry.get("voice_id") or None
    engine = entry.get("engine") or "edge"
    gender = entry.get("gender") or ctx.gender
    narr = synthesize_scene_narration(
        scene=shot, job_id=job_id, language=ctx.language, gender=gender,
        voice_id=voice_id, tts_engine=engine,
        out_path=str(ctx.shots_dir / f"narr_{part_no:04d}.mp3"),
    )
    if narr is None:
        upsert_job_part(job_id, part_no, part_name, JobPartStage.FAILED,
                        progress_percent=0, message="TTS failed")
        _job_log(effective_channel, job_id, f"Story shot {part_no} TTS failed — skipped", kind="warning")
        return {"idx": part_no, "clip": None, "error": "tts_failed"}
    audio_path, ndur = narr
    if ctx.cancel_cb():
        raise cancel_registry.JobCancelledError()

    # ── 2/3 visual (asset decision → gpt-image-1 / local fallback) ───────────
    upsert_job_part(job_id, part_no, part_name, JobPartStage.RENDERING,
                    progress_percent=45, message="resolving visual")
    atype, tier = decide_shot_asset(shot, budget)
    try:
        shot.quality_tier = tier  # honour any budget downgrade at generation time
    except Exception:
        pass
    bg_kind, bg_value = ctx.bg_kind, ctx.bg_value
    fell_back = False
    _s_source = (getattr(shot, "visual_source", "") or "").strip().lower()

    if atype in ("local", "pin") and _s_source in ("color", "image", "video"):
        bg_kind, bg_value = _s_source, (getattr(shot, "visual_path", "") or "").strip()
    elif atype == "ai_image":
        # P8: Vision-QA regen loop. Generate → QA → on a clear reject, regenerate
        # a genuinely different take (variant), bounded by STORY_QA_MAX_RETRY. QA
        # is fail-open (Sacred #3): unavailable/error accepts. The last candidate
        # is kept as a fail-open fallback if every take is rejected.
        _img_out = str(ctx.shots_dir / f"img_{part_no:04d}.png")
        _attempts = 1 + (_story_qa_max_retry() if ctx.vision_qa else 0)
        img = None
        for _attempt in range(_attempts):
            cand = generate_shot_image(
                shot, bible, ctx.art_style, ctx.width, ctx.height,
                out_path=_img_out, variant=_attempt,
            )
            if not (cand and Path(cand).exists() and Path(cand).stat().st_size > 0):
                img = None
                break
            img = cand  # keep as fail-open fallback
            if not ctx.vision_qa:
                break
            try:
                from app.features.render.ai.vision.qa import qa_shot_image
                _qa = qa_shot_image(cand, shot, bible)
            except Exception:
                _qa = {"ok": True}
            if _qa.get("ok"):
                break
            _job_log(effective_channel, job_id,
                     f"Story shot {part_no}: vision QA reject (try {_attempt + 1}/{_attempts}) — "
                     f"{_qa.get('reason', '')[:60]}",
                     kind="warning")
        if img and Path(img).exists() and Path(img).stat().st_size > 0:
            bg_kind, bg_value = "image", img
        else:
            fell_back = True
            upsert_job_part(job_id, part_no, part_name, JobPartStage.RENDERING,
                            progress_percent=55, message="AI image unavailable — using background")

    if ctx.cancel_cb():
        raise cancel_registry.JobCancelledError()

    # Subtitle style: user's explicit pick wins; else per-shot, else plan.
    _user_pick = (ctx.subtitle_pick or "").strip()
    if _user_pick and _user_pick.lower() != "auto":
        _sub_style = _user_pick
    else:
        _sub_style = (getattr(shot, "subtitle_style", "") or "").strip() or (getattr(plan, "subtitle_style", "") or "").strip()

    # ── 3/3 compose (background + Ken Burns + subtitle + mux) ────────────────
    upsert_job_part(job_id, part_no, part_name, JobPartStage.RENDERING,
                    progress_percent=75, message="composing shot")
    ok = render_content_scene(
        scene=shot, background_kind=bg_kind, background_value=bg_value,
        narration_audio_path=audio_path, narration_dur=ndur,
        width=ctx.width, height=ctx.height, fps=ctx.fps, sample_rate=ctx.sample_rate,
        out_path=shot_out, work_dir=str(ctx.shots_dir), subtitle_enabled=ctx.add_subtitle,
        subtitle_style=_sub_style, word_by_word=ctx.word_by_word,
        camera=(getattr(shot, "camera", "") or ""),
        ken_burns=(bg_kind == "image"),
    )
    if ok:
        upsert_job_part(job_id, part_no, part_name, JobPartStage.DONE,
                        progress_percent=100, duration=ndur,
                        output_file=shot_out, message=(shot.shot_type or ""))
        return {"idx": part_no, "clip": shot_out, "error": None, "fallback": fell_back}
    upsert_job_part(job_id, part_no, part_name, JobPartStage.FAILED,
                    progress_percent=0, message="shot render failed")
    return {"idx": part_no, "clip": None, "error": "render_failed"}


__all__ = ["render_one_shot"]
