"""
story_pipeline.py — fully separate orchestrator for render_format="story".

Story-to-Video: Chapter → AI Story Director (P1 understanding + P2 storyboard) →
per-shot narration (cast voice) + consistent AI image → one assembled video. Kept
ENTIRELY separate from run_render_pipeline (clips), run_recap and run_content so
those paths are never touched. Dispatched from routers/_common.process_render:

    elif render_format == "story":
        run_story(...)

Story has NO source footage — it composes each SHOT by COMPOSITION over shared
engine blocks (mirrors run_content): setup_render_pipeline · prepare_output_dir ·
generate_story_plan (Story Director) · apply_voice_cast · story_image (gpt-image-1)·
content_scene_render (Content's shot compositor, Shot duck-types as scene) ·
content_assembler.concat_with_transitions (2-tier) · qa_pipeline (Sacred #8) ·
upsert_job(DONE) with the Sacred Contract #1 result_json keys.

Contract mirrors run_content so process_render's cancel / failure / metrics /
close_thread_conn wrapper applies unchanged: same signature, raises
JobCancelledError on cancel, raises on failure, writes a terminal DB row on success.

Sacred Contracts: #1 (result_json aliases) #2 (gated by render_format) #3 (AI
returns None → job fails cleanly, never raises mid-render) #4 (frozen job stages)
#5 (per-shot part status frozen) #6 (_emit_render_event untouched) #7 (DB via repo
helpers) #8 (single concatenated output passes qa_pipeline before DONE).
"""
from __future__ import annotations

import logging
from typing import Callable

from app.core.config import TEMP_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.db.connection import close_thread_conn
from app.db.jobs_repo import (
    get_story_plan,
    update_story_plan,
    update_job_progress,
    upsert_job,
    upsert_job_part,
)
from app.jobs import cancel as cancel_registry
from app.domain.story_plan import StoryPlan
from app.features.render.ai.llm import generate_story_plan
from app.features.render.ai.llm.story_voice_cast import apply_voice_cast
from app.features.render.engine.encoder.ffmpeg_helpers import resolve_target_dimensions
from app.features.render.engine.visual.decision import BudgetTracker
from app.features.render.engine.pipeline.pipeline_setup import (
    prepare_output_dir,
    setup_render_pipeline,
)
from app.features.render.engine.pipeline.render_events import (
    _emit_render_event,
    _job_log,
    _resolve_job_log_dir,
    register_job_log_dir,
    unregister_job_log_dir,
)
from app.features.render.engine.stages.story.context import StoryRenderContext, safe_filename
from app.features.render.engine.stages.story.shot_stage import render_one_shot
from app.features.render.engine.stages.story.assembly_stage import assemble_shots
from app.features.render.engine.stages.story.finalize_stage import finalize_story

logger = logging.getLogger("app.render.story")

_SAMPLE_RATE = 48000


def _build_transitions(ordered: list) -> list:
    """2-tier transitions aligned to the DELIVERED clips: a CUT within a scene, the
    scene's own transition (fade) BETWEEN scenes. ``ordered`` is a list of
    ``(clip, scene_idx, shot, scene)`` in render order. Returns len-1 transitions.
    Pure + never raises."""
    transitions: list = []
    for i in range(len(ordered) - 1):
        _clip, si_cur, shot_cur, scene_cur = ordered[i]
        _clip2, si_next, _s2, _sc2 = ordered[i + 1]
        if si_cur == si_next:
            transitions.append((getattr(shot_cur, "transition_out", "") or "cut"))
        else:
            transitions.append((getattr(scene_cur, "transition_out", "") or "fade"))
    return transitions


def _resolve_story_plan(payload, *, job_id, resume_mode, chapter, language, art_style,
                        aspect_ratio, reading_pace, series_id, chapter_no) -> StoryPlan:
    """Resolve the StoryPlan to render: approved override → persisted (resume) →
    fresh AI plan. Raises RuntimeError when no usable plan is available."""
    # 1. Approved/edited plan from the Storyboard review (skips the AI call).
    override = (getattr(payload, "story_plan_override", "") or "").strip()
    if override:
        plan = StoryPlan.from_json(override)
        if plan is not None and plan.scene_count() > 0:
            logger.info("story: using approved story_plan_override (%d scenes)", plan.scene_count())
            return plan

    # 2. Resume: prefer the persisted plan so scene/shot indices match disk.
    if resume_mode:
        persisted = get_story_plan(job_id)
        if persisted:
            plan = StoryPlan.from_json(persisted)
            if plan is not None and plan.scene_count() > 0:
                logger.info("story: resume — using persisted story_plan_json (%d scenes)", plan.scene_count())
                return plan

    # 3. Fresh AI plan (P1 understanding + P2 storyboard).
    provider = (getattr(payload, "ai_provider", "") or "").strip().lower()
    try:
        from app.core import config as _cfg
        provider = provider or getattr(_cfg, "AI_PROVIDER_DEFAULT", "openai") or "openai"
    except Exception:
        provider = provider or "openai"
    api_key = ""
    resolve_key = None
    try:
        from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
        api_key, _ = _resolve_api_key(payload, provider)
        resolve_key = lambda _p: _resolve_api_key(payload, _p)[0]  # noqa: E731
    except Exception:
        api_key, resolve_key = "", None
    plan = generate_story_plan(
        provider=provider, chapter_text=chapter, language=language, tone="",
        art_style=art_style, series_id=series_id, chapter_no=chapter_no,
        aspect_ratio=aspect_ratio, reading_pace=reading_pace,
        api_key=api_key, model=(getattr(payload, "llm_model", None) or None),
        resolve_key=resolve_key,
    )
    if plan is None or plan.scene_count() == 0:
        raise RuntimeError("Story: AI Story Director returned no usable plan")
    return plan


def run_story(
    job_id: str,
    payload,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
) -> None:
    """Orchestrate a Story-Mode render. Raises JobCancelledError on cancel and
    re-raises on failure (process_render writes the terminal failed row).
    ``load_session_fn`` / ``cleanup_session_fn`` are accepted for signature parity
    with run_content / run_recap (shared dispatch) but unused (no editor session)."""
    _setup = setup_render_pipeline(payload)
    effective_channel = _setup.effective_channel
    output_dir = _setup.output_dir
    prepare_output_dir(job_id, effective_channel, output_dir)
    register_job_log_dir(job_id, _resolve_job_log_dir(output_dir, effective_channel))
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    shots_dir = work_dir / "story_shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    current_stage = JobStage.STARTING

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage
        current_stage = stage
        update_job_progress(job_id, stage, max(0, min(99, int(progress))), message)
        _job_log(effective_channel, job_id, f"[STAGE] {stage} | {message}")
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id,
            event=STAGE_TO_EVENT.get(stage, "render.start"),
            level="INFO", message=message, step=str(stage),
            context={"progress_percent": progress, "render_format": "story"},
        )

    upsert_job(
        job_id, "render", effective_channel, "running", payload.model_dump(), {},
        stage=JobStage.STARTING, progress_percent=1, message="Initializing story render",
    )
    _job_log(effective_channel, job_id, "Story render started")

    try:
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()

        chapter = (getattr(payload, "content_script", "") or "").strip()
        if not chapter:
            raise RuntimeError("Story: empty content_script — nothing to render")

        width, height = resolve_target_dimensions(
            str(getattr(payload, "aspect_ratio", "9:16") or "9:16")
        )
        try:
            fps = float(getattr(payload, "output_fps", 0) or 0) or 30.0
        except Exception:
            fps = 30.0
        language = (getattr(payload, "voice_language", "") or "vi")
        gender = (getattr(payload, "voice_gender", "") or "female")
        add_subtitle = bool(getattr(payload, "add_subtitle", True))
        word_by_word = bool(getattr(payload, "highlight_per_word", False))
        art_style = (getattr(payload, "story_art_style", "") or "")
        reading_pace = (getattr(payload, "story_reading_pace", "") or "normal")
        series_id = (getattr(payload, "story_series_id", "") or "")
        chapter_no = int(getattr(payload, "story_chapter_no", 0) or 0)
        bg_kind = (getattr(payload, "content_background_kind", "") or "color")
        bg_value = (getattr(payload, "content_background_value", "") or "#101820")
        budget_cap = float(getattr(payload, "content_ai_budget", 0.0) or 0.0)

        _set_stage(JobStage.ANALYZING, 15, "Story Director: understanding + storyboard")
        plan = _resolve_story_plan(
            payload, job_id=job_id, resume_mode=resume_mode, chapter=chapter,
            language=language, art_style=art_style, aspect_ratio=str(getattr(payload, "aspect_ratio", "9:16") or "9:16"),
            reading_pace=reading_pace, series_id=series_id, chapter_no=chapter_no,
        )
        update_story_plan(job_id, plan.to_json())
        bible = plan.story_bible
        cast = apply_voice_cast(bible, language, narrator_gender=gender)

        # Flatten scenes → shots (each shot = one part row, Sacred Contract #5).
        flat: list[tuple] = []
        for si, scene in enumerate(plan.scenes):
            for shot in scene.shots:
                flat.append((si, scene, shot))
        total_parts = len(flat)
        if total_parts == 0:
            raise RuntimeError("Story: plan has no shot to render")

        _output_stem = (
            safe_filename(getattr(payload, "title_overlay_text", "") or plan.topic or "")
            or f"story_{job_id[:8]}"
        )
        _set_stage(JobStage.SEGMENT_BUILDING, 30,
                   f"Storyboard ready: {plan.scene_count()} scene(s), {total_parts} shot(s)")

        for pos, (si, scene, shot) in enumerate(flat, start=1):
            upsert_job_part(job_id, pos, f"shot_{pos:04d}", JobPartStage.QUEUED,
                            progress_percent=0, duration=float(shot.est_duration_sec or 0.0),
                            message=(shot.shot_type or ""))

        subtitle_pick = (getattr(payload, "subtitle_style", "") or "")
        try:
            from app.features.render.ai.vision.qa import is_enabled as _qa_enabled
            vision_qa = bool(_qa_enabled())
        except Exception:
            vision_qa = False
        ctx = StoryRenderContext(
            job_id=job_id, effective_channel=effective_channel, shots_dir=shots_dir,
            width=width, height=height, fps=fps, sample_rate=_SAMPLE_RATE,
            language=language, gender=gender, add_subtitle=add_subtitle,
            word_by_word=word_by_word, art_style=art_style, bg_kind=bg_kind,
            bg_value=bg_value, subtitle_pick=subtitle_pick, vision_qa=vision_qa,
            cancel_cb=lambda: cancel_registry.is_cancelled(job_id),
        )

        # ── Render shots — SERIAL (image gen is API-sequential; budget mutation
        # is single-threaded; parallelism is a P8 optimisation) ───────────────
        budget = BudgetTracker(budget_cap)
        results: dict[int, tuple] = {}   # part_no -> (clip, scene_idx, shot, scene)
        failed_parts: list[dict] = []
        visual_fallbacks: list[int] = []
        _set_stage(JobStage.RENDERING, 40, f"Rendering {total_parts} shot(s)")
        for pos, (si, scene, shot) in enumerate(flat, start=1):
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            r = render_one_shot(ctx, plan, bible, pos, scene, shot, cast, budget)
            if r.get("clip"):
                results[pos] = (r["clip"], si, shot, scene)
                if r.get("fallback"):
                    visual_fallbacks.append(pos)
            elif r.get("error"):
                failed_parts.append({"part_no": pos, "error": r["error"]})
            _set_stage(JobStage.RENDERING, 40 + int(45 * pos / max(1, total_parts)),
                       f"Rendered {pos}/{total_parts}")

        ordered = [results[p] for p in sorted(results)]
        shot_clips = [c[0] for c in ordered]
        if not shot_clips:
            raise RuntimeError("Story: no shot rendered successfully")

        # 2-tier transitions: cut WITHIN a scene, the scene's transition BETWEEN
        # scenes, aligned to the DELIVERED clips (skips failed shots).
        transitions = _build_transitions(ordered)

        if visual_fallbacks:
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="story.visual.fallback", level="WARNING",
                message=(f"{len(visual_fallbacks)}/{total_parts} shot(s): AI image "
                         f"unavailable — used the background. Check OPENAI_API_KEY / prompts."),
                step="render.story",
                context={"fallback_shots": visual_fallbacks, "total": total_parts},
            )

        final_out, _res = assemble_shots(
            ctx, plan, payload, output_dir=output_dir, output_stem=_output_stem,
            shot_clips=shot_clips, transitions=transitions, set_stage=_set_stage,
        )
        finalize_story(
            ctx, plan, payload, output_dir=output_dir, output_stem=_output_stem,
            final_out=final_out, assembly=_res, shot_clips=shot_clips, shots_dir=shots_dir,
            total_parts=total_parts, failed_parts=failed_parts,
            visual_fallbacks=visual_fallbacks, budget=budget,
        )
    finally:
        try:
            unregister_job_log_dir(job_id)
        except Exception:
            pass
        try:
            close_thread_conn()
        except Exception:
            pass


__all__ = ["run_story"]
