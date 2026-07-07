"""
content_pipeline.py — fully separate orchestrator for render_format="content".

Content Mode: Script → AI Content Director → per-scene narration + visual →
one assembled video. Kept ENTIRELY separate from run_render_pipeline (clips) and
run_recap so those paths are never touched. Dispatched from
routers/_common.process_render:

    if render_format == "content":
        run_content(...)

Content Mode has NO source footage, so it does NOT use the clips render loop
(process_one_part cuts from a source video). Instead it composes each scene by
COMPOSITION over the shared engine building blocks:

  setup_render_pipeline · prepare_output_dir ·
  ai.llm.select_content_plan (AI Content Director) ·
  engine.visual.resolve_scene_visual (Visual Generator provider seam — v1 'local')·
  content_scene_render.synthesize_scene_narration + render_content_scene ·
  recap_assembler.concat_clips (scenes → 1 video) ·
  qa_pipeline._validate_render_output (Sacred Contract #8) ·
  upsert_job(JobStage.DONE) with the Sacred Contract #1 result_json keys.

Contract mirrors run_recap / run_render_pipeline so process_render's cancel /
failure / metrics / close_thread_conn wrapper applies unchanged: same signature,
raises JobCancelledError on cancel, raises on failure, writes a terminal DB row
on the success path.

Sacred Contracts: #1 (result_json carries output_rank_score / is_best_output /
is_best_clip on every output); #2 (gated by render_format, default "clips"); #3
(AI never raises — select_content_plan returns None → job fails cleanly); #4
(job stages from the frozen set — ANALYZING/SEGMENT_BUILDING/RENDERING/
WRITING_REPORT/DONE); #5 (per-scene part status from the frozen set —
QUEUED/RENDERING/DONE/FAILED); #6 (_emit_render_event signature untouched); #7
(only DB writers are the shared repo helpers); #8 (the single concatenated
output passes qa_pipeline before DONE).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.core.config import TEMP_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.db.connection import close_thread_conn
from app.db.jobs_repo import (
    update_content_plan,
    update_job_progress,
    upsert_job,
    upsert_job_part,
)
from app.jobs import cancel as cancel_registry
from app.features.render.engine.stages.content.plan_stage import resolve_content_plan
from app.features.render.engine.encoder.ffmpeg_helpers import resolve_target_dimensions
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
from app.features.render.engine.stages.content.context import ContentRenderContext, safe_filename
from app.features.render.engine.stages.content.scene_stage import render_one_scene
from app.features.render.engine.stages.content.provider_stage import plan_scene_providers
from app.features.render.engine.stages.content.assembly_stage import assemble_scenes
from app.features.render.engine.stages.content.finalize_stage import finalize_content

logger = logging.getLogger("app.render.content")

_SAMPLE_RATE = 48000
# CM-6: _stable_seed / _safe_filename moved to stages/content/context.py (shared
# by scene_stage); safe_filename is imported above and used below.


def run_content(
    job_id: str,
    payload,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
) -> None:
    """Orchestrate a Content-Mode render. Raises JobCancelledError on cancel and
    re-raises on failure (process_render writes the terminal failed row).

    ``load_session_fn`` / ``cleanup_session_fn`` are accepted for signature parity
    with run_recap (the shared dispatch call site) but unused — Content Mode has
    no editor session / source prep."""
    _setup = setup_render_pipeline(payload)
    effective_channel = _setup.effective_channel
    output_dir = _setup.output_dir
    prepare_output_dir(job_id, effective_channel, output_dir)
    register_job_log_dir(job_id, _resolve_job_log_dir(output_dir, effective_channel))
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = work_dir / "content_scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
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
            context={"progress_percent": progress, "render_format": "content"},
        )

    upsert_job(
        job_id, "render", effective_channel, "running", payload.model_dump(), {},
        stage=JobStage.STARTING, progress_percent=1,
        message="Initializing content render",
    )
    _job_log(effective_channel, job_id, "Content render started")

    try:
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()

        # 1. Script -----------------------------------------------------------
        script = (getattr(payload, "content_script", "") or "").strip()
        if not script:
            raise RuntimeError("Content: empty content_script — nothing to render")

        # 2. Canvas + voice params (reuse the shared aspect→dimensions helper) --
        width, height = resolve_target_dimensions(
            str(getattr(payload, "aspect_ratio", "9:16") or "9:16")
        )
        try:
            fps = float(getattr(payload, "output_fps", 0) or 0) or 30.0
        except Exception:
            fps = 30.0
        language = (getattr(payload, "voice_language", "") or "vi-VN")
        gender = (getattr(payload, "voice_gender", "") or "female")
        voice_id = getattr(payload, "voice_id", None)
        tts_engine = (getattr(payload, "tts_engine", "") or "edge")
        add_subtitle = bool(getattr(payload, "add_subtitle", True))
        visual_provider = (getattr(payload, "content_visual_provider", "") or "local")
        bg_kind = (getattr(payload, "content_background_kind", "") or "color")
        bg_value = (getattr(payload, "content_background_value", "") or "#000000")

        # 3. Content Plan (resolve on resume / override / AI, then refine + fit
        #    + audit). Raises RuntimeError on no usable plan.
        plan = resolve_content_plan(
            payload, job_id=job_id, effective_channel=effective_channel,
            resume_mode=resume_mode, script=script, language=language,
            set_stage=_set_stage,
        )

        update_content_plan(job_id, plan.to_json())

        scenes = plan.scenes
        total_parts = len(scenes)
        _output_stem = (
            safe_filename(getattr(payload, "title_overlay_text", "") or plan.topic or "")
            or f"content_{job_id[:8]}"
        )

        _set_stage(JobStage.SEGMENT_BUILDING, 30, f"Content plan ready: {total_parts} scene(s)")
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="content.plan.ready",
            level="INFO",
            message=f"Content plan: topic={plan.topic!r}, {total_parts} scene(s)",
            step="render.content", context={
                "topic": plan.topic, "tone": plan.tone, "audience": plan.audience,
                "language": plan.language, "subtitle_style": plan.subtitle_style,
                "bgm_mood": plan.bgm_mood, "total_target_sec": plan.total_target_sec,
                "scenes": [
                    {
                        "n": i, "role": s.role, "emotion": s.emotion,
                        "reading_speed": s.reading_speed, "narration": s.narration,
                        "est_duration_sec": s.est_duration_sec, "visual_hint": s.visual_hint,
                    }
                    for i, s in enumerate(scenes, start=1)
                ],
            },
        )

        # Seed per-scene part rows (Sacred Contract #5 — QUEUED).
        for i, s in enumerate(scenes, start=1):
            upsert_job_part(
                job_id, i, f"scene_{i:03d}", JobPartStage.QUEUED,
                progress_percent=0, duration=float(s.est_duration_sec or 0.0),
                message=(s.role or ""),
            )

        # 4. Render scenes — PARALLEL (CU-2) with disk-truth resume ------------
        # Each worker composes one scene end-to-end (TTS → visual → subtitle →
        # mux). Whisper access is already lock-serialised inside transcribe_to_srt,
        # and word-by-word is opt-in (default off = no Whisper), so parallel
        # scenes are safe. Results are collected in THIS thread and ordered by
        # scene index for a correct concat. Per-scene status writes use each
        # worker's own thread-local DB connection.
        failed_parts: list[dict] = []
        _results: dict[int, str] = {}
        _visual_fallbacks: list[int] = []   # scenes where an online visual provider fell back to local

        # MED-2: cancel probe (Veo polls it; checked between sub-steps).
        def _cancel_cb() -> bool:
            return cancel_registry.is_cancelled(job_id)

        # MED-3: word-by-word opt-in via highlight_per_word (FE defaults it on).
        _word_by_word = bool(getattr(payload, "highlight_per_word", False))

        # CM-6: gather the render-invariant params into one context so the
        # per-scene stage takes `ctx` instead of ~15 closure-captured locals.
        ctx = ContentRenderContext(
            job_id=job_id, effective_channel=effective_channel, scenes_dir=scenes_dir,
            width=width, height=height, fps=fps, sample_rate=_SAMPLE_RATE,
            language=language, gender=gender, voice_id=voice_id, tts_engine=tts_engine,
            add_subtitle=add_subtitle, word_by_word=_word_by_word,
            visual_provider=visual_provider, bg_kind=bg_kind, bg_value=bg_value,
            imagen_tier=(getattr(payload, "content_imagen_tier", "") or ""),
            subtitle_pick=(getattr(payload, "subtitle_style", "") or ""),
            cancel_cb=_cancel_cb,
        )

        # CU-8/9: decide the cheapest-sufficient visual provider per scene UP FRONT
        # (deterministic, budget-bounded) + the parallel-render worker cap. Only
        # downgrades a paid choice — never costs more than the user's selection.
        _budget, _scene_providers, max_workers = plan_scene_providers(
            payload, scenes, visual_provider,
        )

        # W5-6: for the word-by-word subtitle path, synthesize all narrations and
        # transcribe the concatenation ONCE (word timings split back per scene) —
        # ~2.2× cheaper than a Whisper pass per scene. Best-effort: any scene not
        # covered falls back to the per-scene synth+transcribe in the render loop.
        _pre_audio: dict = {}
        _pre_word_srt: dict = {}
        if _word_by_word and add_subtitle:
            try:
                from app.features.render.engine.stages.content.narration_stage import (
                    prepare_narration_word_timings,
                )
                _pre_audio, _pre_word_srt = prepare_narration_word_timings(ctx, scenes)
            except Exception as _npexc:
                logger.warning("content: narration pre-pass errored (%s) — per-scene path", _npexc)
                _pre_audio, _pre_word_srt = {}, {}

        def _collect(r: dict) -> None:
            if r.get("clip"):
                _results[int(r["idx"])] = r["clip"]
                if r.get("fallback"):
                    _visual_fallbacks.append(int(r["idx"]))
            elif r.get("error"):
                failed_parts.append({"part_no": int(r["idx"]), "error": r["error"]})

        _done = 0
        if max_workers == 1:
            _set_stage(JobStage.RENDERING, 40, f"Rendering {total_parts} scene(s)")
            for i, scene in enumerate(scenes, start=1):
                if _cancel_cb():
                    raise cancel_registry.JobCancelledError()
                _collect(render_one_scene(ctx, plan, i, scene, _scene_providers.get(i, visual_provider),
                                          pre_audio=_pre_audio.get(i), pre_word_srt=_pre_word_srt.get(i)))
                _done += 1
                _set_stage(JobStage.RENDERING, 40 + int(45 * _done / max(1, total_parts)),
                           f"Rendered scene {_done}/{total_parts}")
        else:
            _set_stage(JobStage.RENDERING_PARALLEL, 40,
                       f"Rendering {total_parts} scene(s) ×{max_workers}")
            _fut: dict = {}
            with ThreadPoolExecutor(max_workers=max_workers) as _ex:
                for i, scene in enumerate(scenes, start=1):
                    if _cancel_cb():
                        break  # stop submitting; running futures self-check cancel
                    _fut[_ex.submit(render_one_scene, ctx, plan, i, scene,
                                    _scene_providers.get(i, visual_provider),
                                    _pre_audio.get(i), _pre_word_srt.get(i))] = i
                for _f in as_completed(_fut):
                    _i = _fut[_f]
                    try:
                        _collect(_f.result())
                    except cancel_registry.JobCancelledError:
                        raise
                    except Exception as _exc:
                        upsert_job_part(job_id, _i, f"scene_{_i:03d}", JobPartStage.FAILED,
                                        progress_percent=0, message="scene render error")
                        failed_parts.append({"part_no": _i, "error": f"exc: {_exc}"})
                    _done += 1
                    _set_stage(JobStage.RENDERING_PARALLEL,
                               40 + int(45 * _done / max(1, total_parts)),
                               f"Rendered {_done}/{total_parts}")
            if _cancel_cb():
                raise cancel_registry.JobCancelledError()

        # Ordered by scene index → correct concat order (Partial-success: proceed
        # as long as ≥1 scene rendered).
        scene_clips: list[str] = [_results[i] for i in sorted(_results)]
        if not scene_clips:
            raise RuntimeError("Content: no scene rendered successfully")

        # Tell the user WHY "AI images" produced only backgrounds — a requested
        # online visual provider that silently fell back to local on every scene
        # is almost always a missing API key / no Imagen access on the key /
        # a bad model id / empty visual prompts. Surfaced as a WS warning event
        # + result flag so it shows in the Activity Feed (not just the log).
        if _visual_fallbacks and visual_provider != "local":
            _n_fb = len(_visual_fallbacks)
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="content.visual.fallback", level="WARNING",
                message=(
                    f"{_n_fb}/{total_parts} scene(s): '{visual_provider}' visuals "
                    f"unavailable — used the background instead. Check the API key / "
                    f"model access (Imagen needs a billing-enabled Gemini key) or the "
                    f"scene visual prompts."
                ),
                step="render.content",
                context={"provider": visual_provider, "fallback_scenes": _visual_fallbacks,
                         "total": total_parts},
            )

        # 5. Assemble scenes → one video, then mix BGM (returns final_out + the
        #    concat result for the QA expected-duration).
        final_out, _res = assemble_scenes(
            ctx, plan, payload, output_dir=output_dir, output_stem=_output_stem,
            scene_clips=scene_clips, results=_results, scenes=scenes, set_stage=_set_stage,
        )

        finalize_content(
            ctx, plan, payload, output_dir=output_dir, output_stem=_output_stem,
            final_out=final_out, assembly=_res, scene_clips=scene_clips,
            scenes_dir=scenes_dir, total_parts=total_parts, failed_parts=failed_parts,
            visual_fallbacks=_visual_fallbacks, visual_provider=visual_provider,
            budget=_budget, scene_providers=_scene_providers,
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
