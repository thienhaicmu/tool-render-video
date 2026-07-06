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
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
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
from app.features.render.ai.llm import select_content_plan
from app.features.render.engine.encoder.ffmpeg_helpers import resolve_target_dimensions
from app.features.render.engine.pipeline.pipeline_setup import (
    prepare_output_dir,
    setup_render_pipeline,
)
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
from app.features.render.engine.pipeline.render_events import (
    _emit_render_event,
    _job_log,
    _resolve_job_log_dir,
    register_job_log_dir,
    unregister_job_log_dir,
)
from app.features.render.engine.stages.recap_assembler import concat_clips
from app.features.render.engine.stages.content_scene_render import (
    render_content_scene,
    synthesize_scene_narration,
)
from app.features.render.engine.visual import SceneVisualRequest, resolve_scene_visual
from app.features.render.engine.visual.decision import BudgetTracker, decide_provider

logger = logging.getLogger("app.render.content")

_SAMPLE_RATE = 48000
_FS_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _stable_seed(key: str) -> int:
    """CU-11 — a stable 31-bit seed from a key (character id / style) so the same
    subject reproduces a consistent look across scenes. 0 for an empty key."""
    key = (key or "").strip().lower()
    if not key:
        return 0
    import hashlib
    return int(hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:8], 16) & 0x7FFFFFFF


def _safe_filename(name: str, max_len: int = 120) -> str:
    """Make an AI-authored title/topic safe to use as a filename stem. Strips
    illegal chars, collapses whitespace, trims trailing dots/spaces (Windows),
    caps length. Returns '' if nothing usable survives. Never raises."""
    try:
        s = _FS_ILLEGAL_RE.sub(" ", str(name or ""))
        s = re.sub(r"\s+", " ", s).strip().strip(".").strip()
        if len(s) > max_len:
            s = s[:max_len].rsplit(" ", 1)[0].strip() or s[:max_len].strip()
        return s
    except Exception:
        return ""


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

        # 3. Content Plan — either an APPROVED plan from the Review step
        #    (content_plan_override), or freshly generated by the AI Director.
        _set_stage(JobStage.ANALYZING, 15, "Preparing content plan")
        from app.domain.content_plan import ContentPlan
        plan = None
        _override_raw = (getattr(payload, "content_plan_override", "") or "").strip()
        if _override_raw:
            # CS-A: render FROM the user-approved/edited plan — skip the AI call.
            plan = ContentPlan.from_json(_override_raw)
            if plan is not None and plan.scene_count() > 0:
                _job_log(effective_channel, job_id,
                         f"Content: using approved plan ({plan.scene_count()} scene(s)) — AI planning skipped")
            else:
                # Defensive: a malformed override falls back to AI planning rather
                # than failing the job (Sacred Contract #3 spirit).
                logger.warning("content: content_plan_override unusable — falling back to AI planning")
                plan = None
        if plan is None:
            from app.core import config as _cfg
            from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
            provider = (getattr(payload, "ai_provider", "") or "").strip().lower() \
                or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
            api_key, _ = _resolve_api_key(payload, provider)
            plan = select_content_plan(
                provider=provider, script=script,
                target_duration_sec=float(getattr(payload, "target_duration", 90) or 90),
                target_language=language, tone=(getattr(payload, "rewrite_tone", "") or ""),
                api_key=api_key, model=getattr(payload, "llm_model", None),
                # LOW-1: resolve the right key per provider on cross-provider fallback.
                resolve_key=lambda _prov: _resolve_api_key(payload, _prov)[0],
            )
        if plan is None or plan.scene_count() == 0:
            raise RuntimeError("Content: no usable content plan")

        # Content per-scene narration refine (opt-in, CONTENT_REFINE_NARRATION=1
        # — default OFF because it costs +1 LLM call). A focused second pass
        # re-authors the whole scene set's narration so voice-over flows
        # scene→scene and each scene's length matches its planned seconds.
        # Best-effort: any failure keeps the original narration (Sacred #3 spirit).
        # Runs BEFORE the duration fit so the fit measures the final narration.
        if os.getenv("CONTENT_REFINE_NARRATION", "0") == "1":
            try:
                from app.features.render.ai.llm import select_content_narration
                from app.core import config as _cfg2
                from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
                _prov = (getattr(payload, "ai_provider", "") or "").strip().lower() \
                    or getattr(_cfg2, "AI_PROVIDER_DEFAULT", "gemini")
                _key, _ = _resolve_api_key(payload, _prov)
                _scene_payload = [
                    {
                        "index": i, "role": (s.role or ""),
                        "seconds": float(getattr(s, "est_duration_sec", 0.0) or 0.0),
                        "narration": (s.narration or ""),
                    }
                    for i, s in enumerate(plan.scenes)
                ]
                _refined = select_content_narration(
                    provider=_prov, scenes=_scene_payload,
                    topic=(plan.topic or ""), tone=(plan.tone or getattr(payload, "rewrite_tone", "") or ""),
                    target_language=language, api_key=_key,
                    model=getattr(payload, "llm_model", None),
                )
                if _refined:
                    _n_refined = 0
                    for i, s in enumerate(plan.scenes):
                        _txt = _refined.get(i)
                        if _txt and _txt.strip():
                            s.narration = _txt.strip()
                            _n_refined += 1
                    if _n_refined:
                        _job_log(effective_channel, job_id,
                                 f"Content: narration refined ({_n_refined} scene(s))")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="content.narration.refined", level="INFO",
                            message=f"Per-scene narration refined ({_n_refined} scene(s))",
                            step="render.content", context={"scenes_refined": _n_refined},
                        )
            except Exception as _refine_exc:
                logger.warning("content: narration refine failed (non-fatal): %s", _refine_exc)

        # Deterministic duration fit (mirrors recap's trim_to_duration_band in
        # spirit): the AI's est_duration_sec often drifts from the requested
        # target. Uniformly scale reading_speed (clamped) so the video lands near
        # target WITHOUT dropping any narrative scene. Non-destructive, never
        # raises, env kill-switch CONTENT_FIT_DURATION (default ON). Runs BEFORE
        # persist + part seeding so narration/TTS use the fitted speeds.
        if os.getenv("CONTENT_FIT_DURATION", "1") == "1":
            try:
                _target = float(getattr(payload, "target_duration", 0) or 0)
                _fit = plan.fit_to_target_duration(_target)
                if _fit.get("changed"):
                    _job_log(
                        effective_channel, job_id,
                        f"Content: fitted to target — {_fit['before_sec']:.0f}s → "
                        f"{_fit['after_sec']:.0f}s (target {_fit['target_sec']:.0f}s, "
                        f"speed ×{_fit.get('applied_scale')}, {_fit['scaled_scenes']} scene(s))",
                    )
                    _emit_render_event(
                        channel_code=effective_channel, job_id=job_id,
                        event="content.timing.fit", level="INFO",
                        message=(
                            f"Content fitted to target: {_fit['before_sec']:.0f}s → "
                            f"{_fit['after_sec']:.0f}s"
                        ),
                        step="render.content", context=_fit,
                    )
            except Exception as _fit_exc:
                logger.warning("content: duration fit failed (non-fatal): %s", _fit_exc)

        # Deterministic narration/timing audit (diagnostic only — mirrors recap's
        # coverage check). Flags scenes whose narration is too long ("overloaded"
        # → TTS rushes/overflows) or too short ("sparse" → silence) for their
        # planned duration. Never blocks the render; emits a WS event + logs a
        # warning so a weak plan is visible. Runs on the FITTED plan.
        try:
            _audit = plan.narration_audit()
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="content.narration.audit",
                level=("WARNING" if _audit.get("weak") else "INFO"),
                message=(
                    f"Narration audit: {_audit['overloaded']} overloaded, "
                    f"{_audit['sparse']} sparse of {_audit['rated']} rated scene(s)"
                    + (" — weak plan" if _audit.get("weak") else "")
                ),
                step="render.content", context=_audit,
            )
            if _audit.get("weak"):
                _job_log(
                    effective_channel, job_id,
                    f"content_narration_weak overloaded={_audit['overloaded']} "
                    f"sparse={_audit['sparse']}/{_audit['rated']} — narration/timing mismatch",
                    kind="warning",
                )
        except Exception as _audit_exc:
            logger.warning("content: narration audit failed (non-fatal): %s", _audit_exc)

        update_content_plan(job_id, plan.to_json())

        scenes = plan.scenes
        total_parts = len(scenes)
        _output_stem = (
            _safe_filename(getattr(payload, "title_overlay_text", "") or plan.topic or "")
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

        # CU-8/9: decide the cheapest-sufficient visual provider per scene UP FRONT
        # (budget applied deterministically in scene order) so the parallel loop
        # just executes. Uses est_duration_sec (no TTS needed). Only downgrades a
        # paid choice — never costs more than the user's provider selection.
        # P4.1: per-render budget cap from the payload wins; fall back to the env
        # CONTENT_AI_BUDGET. 0 (either source) = unlimited.
        _budget = BudgetTracker(
            float(getattr(payload, "content_ai_budget", 0.0) or 0.0)
            or float(os.getenv("CONTENT_AI_BUDGET", "0") or 0)
        )
        _scene_providers: dict[int, str] = {}
        for _si, _s in enumerate(scenes, start=1):
            _scene_providers[_si] = decide_provider(
                _s, visual_provider, _budget,
                float(getattr(_s, "est_duration_sec", 0.0) or 0.0),
            )

        try:
            _user_req = int(getattr(payload, "max_parallel_parts", 0) or 0)
        except Exception:
            _user_req = 0
        _cpu = os.cpu_count() or 4
        _cap = max(1, min(int(os.getenv("CONTENT_MAX_PARALLEL", "3") or 3), _cpu))
        max_workers = max(1, min(_user_req, _cpu)) if _user_req > 0 else _cap

        def _render_one_scene(i: int, scene) -> dict:
            """Compose one scene → {idx, clip|None, error|None}. Resumes from a
            valid existing scene clip. Raises JobCancelledError on cancel."""
            part_name = f"scene_{i:03d}"
            scene_out = str(scenes_dir / f"{part_name}.mp4")

            # Resume (disk-truth): reuse a scene clip that already passes QA
            # (retry keeps scenes_dir since it's only cleaned on success).
            if Path(scene_out).exists() and Path(scene_out).stat().st_size > 0:
                _rq = _validate_render_output(Path(scene_out), expect_audio=True)
                if _rq.get("ok"):
                    upsert_job_part(job_id, i, part_name, JobPartStage.DONE,
                                    progress_percent=100,
                                    duration=float(_rq["metadata"].get("duration") or 0.0),
                                    output_file=scene_out, message=(scene.role or ""))
                    return {"idx": i, "clip": scene_out, "error": None}

            if _cancel_cb():
                raise cancel_registry.JobCancelledError()
            upsert_job_part(job_id, i, part_name, JobPartStage.RENDERING,
                            progress_percent=20, message="synthesizing narration")

            narr = synthesize_scene_narration(
                scene=scene, job_id=job_id, language=language, gender=gender,
                voice_id=voice_id, tts_engine=tts_engine,
                out_path=str(scenes_dir / f"narr_{i:03d}.mp3"),
            )
            if narr is None:
                upsert_job_part(job_id, i, part_name, JobPartStage.FAILED,
                                progress_percent=0, message="TTS failed")
                _job_log(effective_channel, job_id,
                         f"Content scene {i} TTS failed — skipped", kind="warning")
                return {"idx": i, "clip": None, "error": "tts_failed"}
            audio_path, ndur = narr
            if _cancel_cb():
                raise cancel_registry.JobCancelledError()

            # Provider chosen by the CU-8 pre-pass (decision tree + budget). A
            # per-scene override still resolves via local with the user's asset.
            _s_source = (getattr(scene, "visual_source", "") or "").strip().lower()
            _s_ken_burns = bool(getattr(scene, "ken_burns", False))
            _prov = _scene_providers.get(i, visual_provider)
            if _s_source in ("color", "image", "video"):
                _kind, _value = _s_source, (getattr(scene, "visual_path", "") or "").strip()
            else:
                _kind, _value = bg_kind, bg_value

            # Stock search (Pexels/Pixabay) wants SHORT keywords, not a full
            # cinematic prompt — prefer the short visual_hint for stock; AI
            # generators (Imagen/DALL·E/Veo) want the rich visual_prompt.
            _visual_query = (
                (scene.visual_hint or scene.visual_prompt or "")
                if _prov == "stock"
                else (scene.visual_prompt or scene.visual_hint or "")
            )
            asset = resolve_scene_visual(
                SceneVisualRequest(
                    scene_index=i, kind=_kind, value=_value,
                    prompt=_visual_query,
                    negative_prompt=(getattr(scene, "negative_prompt", "") or ""),
                    style=(getattr(plan, "video_style", "") or ""),
                    # CU-11: seed by the scene's primary character (else the video
                    # style) so the same subject stays visually consistent.
                    # CU-11 + B1: stable seed by the scene's character, else the
                    # plan's video_style, else its topic — so even a character-less
                    # scene keeps a coherent look across the whole video (never 0).
                    seed=_stable_seed(
                        (getattr(scene, "characters", None) or [""])[0]
                        or (getattr(plan, "video_style", "") or "")
                        or (getattr(plan, "topic", "") or "")
                    ),
                    width=width, height=height, fps=fps, duration_sec=ndur,
                    work_dir=str(scenes_dir), cancel_check=_cancel_cb,
                    imagen_tier=(getattr(payload, "content_imagen_tier", "") or ""),
                ),
                provider=_prov,
            )
            if asset is None:
                upsert_job_part(job_id, i, part_name, JobPartStage.FAILED,
                                progress_percent=0, message="visual resolve failed")
                return {"idx": i, "clip": None, "error": "visual_failed"}
            # A requested online provider (stock / ai_image / ai_video) that yields
            # a 'local' asset SILENTLY fell back to the plain background (no key /
            # no access / API error / empty visual_prompt). Flag it so the user is
            # told WHY "AI images" produced only backgrounds instead of guessing.
            _fell_back = _prov != "local" and (asset.provider or "local") == "local"
            if _fell_back:
                upsert_job_part(job_id, i, part_name, JobPartStage.RENDERING,
                                progress_percent=55,
                                message=f"{_prov} unavailable — using background")
                _job_log(effective_channel, job_id,
                         f"Content scene {i}: visual provider '{_prov}' fell back to "
                         f"local background (no key / no access / error / empty prompt)",
                         kind="warning")
            if _cancel_cb():
                raise cancel_registry.JobCancelledError()

            # Subtitle style precedence (P1.1): the user's explicit UI pick is
            # authoritative. Only when the user leaves it on "auto" (or empty)
            # does the AI-chosen style apply — per-scene override first, else the
            # plan-level suggestion. Fixes the prior order where the AI plan style
            # silently overrode the user's dropdown choice.
            _user_pick = (getattr(payload, "subtitle_style", "") or "").strip()
            if _user_pick and _user_pick.lower() != "auto":
                _sub_style = _user_pick
            else:
                _sub_style = (
                    (getattr(scene, "subtitle_style", "") or "").strip()
                    or (getattr(plan, "subtitle_style", "") or "").strip()
                )
            # A3: AI-directed camera move (image backgrounds only). "pan" alternates
            # left/right by scene index for variety. Empty hint → build_background_clip
            # falls back to the default Ken Burns zoom. Gated by CONTENT_CAMERA_MOTION.
            _camera = ""
            if asset.kind == "image" and os.getenv("CONTENT_CAMERA_MOTION", "1") == "1":
                _ch = (getattr(scene, "camera_hint", "") or "").strip().lower()
                if _ch == "pan":
                    _ch = "pan_right" if (i % 2 == 0) else "pan_left"
                _camera = _ch
            ok = render_content_scene(
                scene=scene, background_kind=asset.kind, background_value=asset.value,
                narration_audio_path=audio_path, narration_dur=ndur,
                width=width, height=height, fps=fps, sample_rate=_SAMPLE_RATE,
                out_path=scene_out, work_dir=str(scenes_dir), subtitle_enabled=add_subtitle,
                subtitle_style=_sub_style, word_by_word=_word_by_word,
                camera=_camera,
                ken_burns=asset.kind == "image" and (
                    _s_ken_burns or asset.provider in ("stock", "ai_image", "ai_image_free")
                ),
            )
            if ok:
                upsert_job_part(job_id, i, part_name, JobPartStage.DONE,
                                progress_percent=100, duration=ndur,
                                output_file=scene_out, message=(scene.role or ""))
                return {"idx": i, "clip": scene_out, "error": None, "fallback": _fell_back}
            upsert_job_part(job_id, i, part_name, JobPartStage.FAILED,
                            progress_percent=0, message="scene render failed")
            return {"idx": i, "clip": None, "error": "render_failed"}

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
                _collect(_render_one_scene(i, scene))
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
                    _fut[_ex.submit(_render_one_scene, i, scene)] = i
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

        # 5. Assemble scenes → one video (reuse the recap assembler) -----------
        _set_stage(JobStage.WRITING_REPORT, 88, "Assembling final video")
        final_out = output_dir / f"{_output_stem}.mp4"
        _base = _output_stem
        _n = 2
        while final_out.exists():
            final_out = output_dir / f"{_base} ({_n}).mp4"
            _n += 1
        # A1: join scenes with crossfade transitions per the AI's transition_hint.
        # Content-only assembler (never touches the shared concat_clips). Any
        # failure / disabled → fall back to the plain concat (hard cut).
        _res = None
        if os.getenv("CONTENT_TRANSITIONS", "1") == "1" and len(scene_clips) >= 2:
            try:
                from app.features.render.engine.stages.content_assembler import concat_with_transitions
                _ordered = sorted(_results)
                # transition BEFORE each clip after the first = that scene's hint.
                _trans = [(getattr(scenes[idx - 1], "transition_hint", "") or "") for idx in _ordered[1:]]
                _res = concat_with_transitions(
                    scene_clips, str(final_out), transitions=_trans,
                    width=width, height=height, fps=fps,
                )
                if _res.get("ok"):
                    _job_log(effective_channel, job_id,
                             f"Content: assembled with transitions ({_res.get('method')})")
                else:
                    _res = None
            except Exception as _tx_exc:
                logger.warning("content: transition assembly failed (%s) — plain concat", _tx_exc)
                _res = None
        if not _res:
            _res = concat_clips(scene_clips, str(final_out), width=width, height=height, fps=fps)
        if not _res.get("ok"):
            raise RuntimeError("Content: assembly (concat) failed")

        # 5b. CS-F — mix background music (ducked under the narration) into the
        #     assembled video. Best-effort: a BGM failure keeps the non-BGM output
        #     (never fails the render). Runs BEFORE QA so the delivered file is
        #     validated with its final audio.
        _bgm = (getattr(payload, "content_bgm_path", "") or "").strip()
        # A2: no user BGM → auto-pick a track for the AI-planned mood from
        # BGM_DIR/{mood}/ (reuses the clips-path music library). Returns None when
        # the user hasn't added any music files → no BGM (unchanged behaviour).
        if not (_bgm and Path(_bgm).exists()) and os.getenv("CONTENT_AUTO_BGM", "1") == "1":
            try:
                from app.core.config import _pick_bgm_file
                _auto_bgm = _pick_bgm_file(getattr(plan, "bgm_mood", "") or "")
                if _auto_bgm:
                    _bgm = _auto_bgm
                    _job_log(effective_channel, job_id,
                             f"Content: auto BGM for mood '{plan.bgm_mood or 'default'}'")
            except Exception as _bgm_pick_exc:
                logger.warning("content: auto BGM pick failed (%s)", _bgm_pick_exc)
        if _bgm and Path(_bgm).exists():
            _bgm_tmp = str(final_out) + ".bgm.mp4"
            try:
                from app.features.render.engine.audio.mixer import mix_with_bgm
                mix_with_bgm(
                    video_path=str(final_out), bgm_path=_bgm,
                    output_path=_bgm_tmp, duck=True,
                )
                Path(_bgm_tmp).replace(final_out)
                _job_log(effective_channel, job_id, "Content: background music mixed (ducked)")
            except Exception as exc:
                logger.warning("content: BGM mix failed (non-fatal): %s", exc)
                try:
                    Path(_bgm_tmp).unlink(missing_ok=True)
                except Exception:
                    pass

        # 6. QA gate (Sacred Contract #8 — never bypassed) ---------------------
        _exp = float(_res.get("expected_duration") or 0.0)
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
            "output_path": str(final_out), "title": (plan.topic or _output_stem),
            "clip_name": _output_stem, "ai_title": (plan.topic or ""),
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
            "visual_fallback_scenes": _visual_fallbacks,
            "selected_segments_count": total_parts,
            "is_partial_success": bool(failed_parts),
            "ai_director": {"enabled": True, "mode": "content"},
            # CU-8/9: which visual provider each scene used + estimated paid cost.
            "ai_cost": {
                "estimated": round(_budget.spent, 3),
                "budget_cap": _budget.cap,
                "by_provider": {
                    _p: sum(1 for _v in _scene_providers.values() if _v == _p)
                    for _p in sorted(set(_scene_providers.values()))
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
    finally:
        try:
            unregister_job_log_dir(job_id)
        except Exception:
            pass
        try:
            close_thread_conn()
        except Exception:
            pass
