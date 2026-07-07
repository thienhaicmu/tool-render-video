"""
scene_stage.py — render ONE Content-Mode scene end-to-end (CM-6 extract of
content_pipeline._render_one_scene). TTS → visual → subtitle → mux, with
disk-truth resume. Logic is byte-for-byte the former closure; the ~15
closure-captured locals are now ``ctx`` fields + the ``plan`` / ``scene_provider``
params. Returns ``{idx, clip|None, error|None, fallback?}``; raises
JobCancelledError on cancel.
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
from app.features.render.engine.stages.content.context import ContentRenderContext, stable_seed
from app.features.render.engine.visual import SceneVisualRequest, resolve_scene_visual

logger = logging.getLogger("app.render.content")


def render_one_scene(ctx: ContentRenderContext, plan, i: int, scene, scene_provider: str,
                     pre_audio=None, pre_word_srt=None) -> dict:
    """Compose one scene → {idx, clip|None, error|None}. Resumes from a valid
    existing scene clip. Raises JobCancelledError on cancel.

    W5-6: ``pre_audio`` (audio_path, dur) and ``pre_word_srt`` (0-based word SRT)
    come from the shared narration pre-pass — when present, this skips the
    per-scene TTS and per-scene Whisper transcription. Both default None → the
    original per-scene path (the fallback when the pre-pass didn't cover a scene)."""
    job_id = ctx.job_id
    effective_channel = ctx.effective_channel
    scenes_dir = ctx.scenes_dir
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

    if ctx.cancel_cb():
        raise cancel_registry.JobCancelledError()
    upsert_job_part(job_id, i, part_name, JobPartStage.RENDERING,
                    progress_percent=20, message="synthesizing narration")

    # W5-6: reuse the pre-pass narration when available, else synth per-scene.
    narr = pre_audio if pre_audio is not None else synthesize_scene_narration(
        scene=scene, job_id=job_id, language=ctx.language, gender=ctx.gender,
        voice_id=ctx.voice_id, tts_engine=ctx.tts_engine,
        out_path=str(scenes_dir / f"narr_{i:03d}.mp3"),
    )
    if narr is None:
        upsert_job_part(job_id, i, part_name, JobPartStage.FAILED,
                        progress_percent=0, message="TTS failed")
        _job_log(effective_channel, job_id,
                 f"Content scene {i} TTS failed — skipped", kind="warning")
        return {"idx": i, "clip": None, "error": "tts_failed"}
    audio_path, ndur = narr
    if ctx.cancel_cb():
        raise cancel_registry.JobCancelledError()

    # Provider chosen by the CU-8 pre-pass (decision tree + budget). A
    # per-scene override still resolves via local with the user's asset.
    _s_source = (getattr(scene, "visual_source", "") or "").strip().lower()
    _s_ken_burns = bool(getattr(scene, "ken_burns", False))
    _prov = scene_provider
    if _s_source in ("color", "image", "video"):
        _kind, _value = _s_source, (getattr(scene, "visual_path", "") or "").strip()
    else:
        _kind, _value = ctx.bg_kind, ctx.bg_value

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
            seed=stable_seed(
                (getattr(scene, "characters", None) or [""])[0]
                or (getattr(plan, "video_style", "") or "")
                or (getattr(plan, "topic", "") or "")
            ),
            width=ctx.width, height=ctx.height, fps=ctx.fps, duration_sec=ndur,
            work_dir=str(scenes_dir), cancel_check=ctx.cancel_cb,
            imagen_tier=ctx.imagen_tier,
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
    if ctx.cancel_cb():
        raise cancel_registry.JobCancelledError()

    # Subtitle style precedence (P1.1): the user's explicit UI pick is
    # authoritative. Only when the user leaves it on "auto" (or empty)
    # does the AI-chosen style apply — per-scene override first, else the
    # plan-level suggestion. Fixes the prior order where the AI plan style
    # silently overrode the user's dropdown choice.
    _user_pick = (ctx.subtitle_pick or "").strip()
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
        width=ctx.width, height=ctx.height, fps=ctx.fps, sample_rate=ctx.sample_rate,
        out_path=scene_out, work_dir=str(scenes_dir), subtitle_enabled=ctx.add_subtitle,
        subtitle_style=_sub_style, word_by_word=ctx.word_by_word, word_srt=pre_word_srt,
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
