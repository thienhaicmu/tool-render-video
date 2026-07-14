"""
story_pipeline_v2.py — Story Mode v2 orchestrator (Super-Prompt + Cue Sheet, B7).

One flat, length-independent AI cost profile: 1 super plan call → N images (≤ceiling)
→ ~1 TTS per voice-run → a deterministic CUE SHEET → per-cue Ken Burns render →
assemble → QA → DONE. Replaces the v1 scene/shot pipeline as the dispatch target for
render_format="story" (routers/_common.process_render).

Flow (all engine blocks reused; nothing in the clips/recap/content paths is touched):
  setup_render_pipeline · prepare_output_dir · generate_story_plan_v2 (1 super call) ·
  apply_voice_cast_v2 · _generate_images (procedural SVG per Visual, offline $0) ·
  synthesize_timeline (per voice-run TTS → beat_audio) · StoryPlan.build_cues
  (deterministic) · beat_render.render_one_cue (per cue) · assemble_shots
  (content_assembler xfade) · qa_pipeline (Sacred #8) · upsert_job(DONE) with the
  Sacred Contract #1 result_json aliases.

Contract mirrors run_content/run_story so process_render's cancel / failure / metrics
/ close_thread_conn wrapper applies unchanged: same signature, raises
JobCancelledError on cancel, re-raises on failure, writes a terminal DB row on success.

Sacred Contracts: #1 (result_json aliases) #2 (gated by render_format) #3 (AI returns
None → job fails cleanly) #4 (frozen job stages) #5 (per-cue part status frozen) #6
(_emit_render_event untouched) #7 (DB via repo helpers) #8 (single output passes QA).
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from app.core.config import CACHE_DIR, TEMP_DIR
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
from app.domain.story_plan_v2 import StoryPlan, ASPECT_SIZE
from app.features.render.ai.llm import generate_story_plan_v2
from app.features.render.ai.llm.story_voice_cast import apply_voice_cast_v2
from app.features.render.engine.audio.story_narration import synthesize_timeline
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
from app.features.render.engine.stages.story.context import safe_filename
from app.features.render.engine.stages.story.assembly_stage import assemble_shots
from app.features.render.engine.stages.story.beat_render import render_one_cue
# A0 refactor: visual-asset generation, BGM mix + finalize live in sibling stage
# modules (behaviour unchanged). Imported here so run_story_v2's call sites are intact.
from app.features.render.engine.stages.story.visuals_stage import (
    _worker_count,
    _generate_images,
    _generate_overlay_masters,
)
from app.features.render.engine.stages.story.bgm_stage import (
    _delivered_transitions,
    _mix_scene_bgm,
)
from app.features.render.engine.stages.story.finalize_stage import _finalize_story_v2

logger = logging.getLogger("app.render.story")


def _subtitle_mode(payload) -> str:
    """Map the request flags → v2 subtitle_mode. Default hook_only; add_subtitle=False
    → off. (full-subtitle is not exposed on the wire yet — niche.)"""
    return "hook_only" if bool(getattr(payload, "add_subtitle", True)) else "off"


# FE story-genre → library genre_key GROUP (P2 catalog scope). The library genre folders
# are art-style buckets and one story spans several (a wuxia tale has codai emperors /
# scholars), so scope to a GROUP not a single key — shrinks the prompt without hiding
# valid picks. Unknown / "" → () → full catalog. Region is NOT scoped (no FE region field).
_GENRE_GROUP = {
    "kiem-hiep": ("wuxia", "codai"), "wuxia": ("wuxia", "codai"),
    "tien-hiep": ("wuxia", "fantasy", "codai"), "xianxia": ("wuxia", "fantasy", "codai"),
    "huyen-huyen": ("fantasy", "wuxia"), "fantasy": ("fantasy", "wuxia"),
    "ngon-tinh": ("ngontinh", "hiendai"), "ngontinh": ("ngontinh", "hiendai"),
    "do-thi": ("hiendai",), "hiendai": ("hiendai",),
    "khoa-huyen": ("fantasy", "hiendai"),
    "kinh-di": ("horror",), "horror": ("horror",),
    "codai": ("codai", "wuxia"),
}


def _genre_group(genre: str) -> tuple:
    """FE story-genre → a tuple of library genre_keys to scope the catalog. () = full."""
    return _GENRE_GROUP.get((genre or "").strip().lower(), ())


def _resolve_story_plan_v2(payload, *, job_id, resume_mode, source, chapter, idea,
                           duration_sec, genre, language, art_style, aspect, subtitle_mode,
                           has_base_video=False, base_video_dur=0.0) -> "tuple[StoryPlan, dict]":
    """Resolve the StoryPlan v2 to render: approved override → persisted (resume) →
    fresh super-plan call. Returns ``(plan, meta)`` where ``meta`` records how the
    plan was obtained (plan_source/provider/model) for result_json reproducibility.
    Raises RuntimeError when no usable plan is available."""
    override = (getattr(payload, "story_plan_override", "") or "").strip()
    # paste-JSON source (feature): the plan is HAND-AUTHORED and MUST render verbatim —
    # never silently fall back to an AI call (that would cost money + ignore the paste).
    _strict = (source or "").strip().lower() == "paste_json"
    if override:
        plan = StoryPlan.from_json(override)
        if plan is not None:
            # Scrub dangling refs + DROP any stale render state so a pasted/exported plan
            # can't reuse another job's cues/masters/asset paths. Generous ceiling so a
            # legit hand-authored visual set is not trimmed. Never raises.
            plan.normalize_for_render(max(15, plan.image_count()))
        if plan is not None and plan.schema_version == 2 and not plan.is_empty() and plan.image_count() > 0:
            logger.info("story v2: using story_plan_override (%d visuals, strict=%s)",
                        plan.image_count(), _strict)
            return plan, {"plan_source": "override", "provider": "", "model": ""}
        if _strict:
            raise RuntimeError(
                "paste_json: the pasted StoryPlan is invalid — it needs schema_version=2, "
                "at least 1 visual and 1 beat with text. Fix the JSON (AI planning is NOT "
                "used for this source).")
    elif _strict:
        raise RuntimeError("paste_json: story_plan_override is empty — paste a StoryPlan JSON to render.")

    if resume_mode:
        persisted = get_story_plan(job_id)
        if persisted:
            plan = StoryPlan.from_json(persisted)
            if plan is not None and plan.schema_version == 2 and not plan.is_empty() and plan.image_count() > 0:
                logger.info("story v2: resume — using persisted plan (%d visuals)", plan.image_count())
                return plan, {"plan_source": "resume", "provider": "", "model": ""}

    # Fresh super-plan. GPT-centric: provider from payload else STORY_AI_PROVIDER.
    provider = (getattr(payload, "ai_provider", "") or "").strip().lower()
    if not provider:
        provider = (os.getenv("STORY_AI_PROVIDER", "openai") or "openai").strip().lower()
    api_key, resolve_key = "", None
    try:
        from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
        api_key, _ = _resolve_api_key(payload, provider)
        # F-11: generic key belongs to the active provider only — a cross-provider
        # fallback resolves solely from its own per-provider/env key.
        resolve_key = lambda _p: _resolve_api_key(payload, _p, allow_generic=(_p == provider))[0]  # noqa: E731
    except Exception:
        api_key, resolve_key = "", None
    _sid = (getattr(payload, "story_series_id", "") or "")
    _cno = int(getattr(payload, "story_chapter_no", 0) or 0)
    # G1: ground a later series chapter on earlier ones (no-op when series_id empty).
    from app.features.render.engine.pipeline.story_series_memory import build_prior_context
    prior_context = build_prior_context(_sid, before_chapter=(_cno or None))
    # Library-pick: inject the asset-library catalog so the AI plan can CHOOSE assets by
    # slug. Default ON (STORY_LIBRARY_PICK=1) now that the library is large (569 assets)
    # + fuzzy matching is strong — this is the strongest matching signal. Set
    # STORY_LIBRARY_PICK=0 to opt out (e.g. shrink the prompt for a pure gpt-image run,
    # which ignores the picks). An empty library → catalog "" → prompt byte-identical.
    library_catalog = ""
    if os.getenv("STORY_LIBRARY_PICK", "1") == "1":
        try:
            from app.db import story_asset_repo
            library_catalog = story_asset_repo.build_library_catalog(genres=_genre_group(genre))
        except Exception:
            library_catalog = ""
    plan = generate_story_plan_v2(
        provider=provider, source=source, chapter=chapter, idea=idea,
        duration_sec=duration_sec, genre=genre, language=language, art_style=art_style,
        aspect_ratio=aspect, subtitle_mode=subtitle_mode,
        series_id=_sid, chapter_no=_cno, prior_context=prior_context,
        library_catalog=library_catalog,
        has_base_video=has_base_video, base_video_dur=base_video_dur,
        api_key=api_key, model=(getattr(payload, "llm_model", None) or None),
        resolve_key=resolve_key,
    )
    if plan is None or plan.is_empty() or plan.image_count() == 0:
        raise RuntimeError("Story v2: super plan returned no usable StoryPlan")
    if not (plan.language or "").strip():
        plan.language = language
    return plan, {
        "plan_source": "fresh", "provider": provider,
        "model": (getattr(payload, "llm_model", None) or ""),
    }


def run_story_v2(
    job_id: str,
    payload,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
) -> None:
    """Orchestrate a Story-Mode v2 render. Raises JobCancelledError on cancel and
    re-raises on failure (process_render writes the terminal failed row).
    load_session_fn / cleanup_session_fn accepted for dispatch parity (unused)."""
    _setup = setup_render_pipeline(payload)
    effective_channel = _setup.effective_channel
    output_dir = _setup.output_dir
    prepare_output_dir(job_id, effective_channel, output_dir)
    register_job_log_dir(job_id, _resolve_job_log_dir(output_dir, effective_channel))
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    shots_dir = work_dir / "story_v2"
    shots_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = work_dir / "story_v2_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
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
    _job_log(effective_channel, job_id, "Story v2 render started")

    try:
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()

        aspect = str(getattr(payload, "aspect_ratio", "16:9") or "16:9")
        width, height = resolve_target_dimensions(aspect)
        img_w, img_h = ASPECT_SIZE.get(aspect, ASPECT_SIZE["16:9"])
        try:
            fps = float(getattr(payload, "output_fps", 0) or 0) or 30.0
        except Exception:
            fps = 30.0
        language = (getattr(payload, "voice_language", "") or "vi")
        narrator_gender = (getattr(payload, "voice_gender", "") or "female")
        art_style = (getattr(payload, "story_art_style", "") or "")
        subtitle_mode = _subtitle_mode(payload)
        source = (getattr(payload, "story_source", "") or "paste") or "paste"
        chapter = (getattr(payload, "content_script", "") or "").strip()
        idea = (getattr(payload, "story_idea", "") or "").strip()
        duration_sec = int(getattr(payload, "story_duration_sec", 0) or 0)
        genre = (getattr(payload, "story_genre", "") or "")
        bg_value = (getattr(payload, "content_background_value", "") or "#101820")

        # A1: optional LOCAL base video the story is composited over. "" → image-based
        # (default). A missing/invalid path degrades to image-based (Sacred #3 spirit),
        # never aborts. Consumed as the cue base layer in a later phase (A2).
        base_video_path, base_video_dur, base_video_has_audio = "", 0.0, False
        _bvp = (getattr(payload, "story_base_video_path", "") or "").strip()
        if _bvp:
            try:
                _p = Path(_bvp).expanduser()
                if _p.exists() and _p.is_file():
                    from app.features.render.engine.pipeline.render_pipeline import _probe_video_duration
                    base_video_dur = float(_probe_video_duration(_p) or 0.0)
                    base_video_path = str(_p)
                    try:                                 # A4: does the base video carry audio?
                        from app.features.render.engine.audio.mixer import _has_audio_stream
                        base_video_has_audio = bool(_has_audio_stream(base_video_path))
                    except Exception:
                        base_video_has_audio = False
                    _job_log(effective_channel, job_id,
                             f"Story v2: base video ok ({base_video_dur:.1f}s, audio={base_video_has_audio}) — {_p.name}")
                else:
                    _job_log(effective_channel, job_id,
                             f"Story v2: base video not found, using image-based — {_bvp}")
            except Exception as _bv_exc:
                logger.warning("story v2: base video probe failed (non-fatal): %s", _bv_exc)

        if source == "idea":
            if not idea:
                raise RuntimeError("Story v2: source=idea but story_idea is empty")
        elif source == "paste_json":
            # paste-JSON renders from story_plan_override (no chapter/idea). The override's
            # presence + validity is enforced in _resolve_story_plan_v2 (strict) below.
            pass
        elif not chapter:
            raise RuntimeError("Story v2: empty content_script — nothing to render")

        # ── 1. Super plan (1 AI call) ───────────────────────────────────────
        _set_stage(JobStage.ANALYZING, 12, "Story Director: super plan (1 call)")
        plan, plan_meta = _resolve_story_plan_v2(
            payload, job_id=job_id, resume_mode=resume_mode, source=source, chapter=chapter,
            idea=idea, duration_sec=duration_sec, genre=genre, language=language,
            art_style=art_style, aspect=aspect, subtitle_mode=subtitle_mode,
            has_base_video=bool(base_video_path), base_video_dur=base_video_dur,
        )
        # Phase 3 (lean contract): the AI emits only the creative per-beat fields; derive
        # the mechanical style labels (motion / transition / bgm placement / speaking-
        # character overlay anchor) deterministically HERE — before overlay-master gen and
        # cue build both read them. Fill-only, so a plan that DID carry them (P2 / legacy /
        # approved override) is unchanged. Never raises.
        plan.derive_beat_styling()

        # PASTE-JSON only: a setting may carry a hand-authored scene_spec (declarative
        # drawing). Render + BANK it into the library as a background asset (user-named
        # slug), then point setting.asset at it → the existing library/_bg_layer flow
        # renders it unchanged. Isolated: no scene_spec (or other sources) → untouched.
        if source == "paste_json":
            try:
                from app.features.render.engine.visual.svg_scene_spec import bank_scene_spec
                for _s in plan.settings:
                    _spec = getattr(_s, "scene_spec", None)
                    if isinstance(_spec, dict) and _spec:
                        _slug = (str(_spec.get("slug") or "").strip()) or _s.asset or _s.id
                        _banked = bank_scene_spec(_spec, region=plan.region, genre=plan.genre_key,
                                                  slug=_slug, name=_s.name)
                        if _banked:
                            _s.asset = _banked
            except Exception as _spec_exc:
                logger.warning("story v2: scene_spec banking skipped (non-fatal): %s", _spec_exc)

        update_story_plan(job_id, plan.to_json())

        # P3: soft semantic lint (non-mutating) — surface weak-plan signals in the
        # monitor without gating the render. Best-effort; never raises.
        try:
            from app.features.render.ai.llm.story_director_v2 import lint_story_plan
            _lint = lint_story_plan(plan)
            if _lint:
                _job_log(effective_channel, job_id,
                         "Story v2 plan lint: " + "; ".join(_lint))
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id, event="story.plan.lint",
                    level="INFO",
                    message=f"{len(_lint)} plan quality note(s) — see log",
                    step="render.story", context={"warnings": _lint},
                )
        except Exception:
            pass

        # G1: ensure the series row exists BEFORE any character / reference-sheet
        # upsert (FK parent) — a first chapter would otherwise silently fail to pin
        # its reference sheets. No-op when story_series_id is empty (one-off chapter).
        _series_id = (getattr(payload, "story_series_id", "") or "").strip()
        if _series_id:
            try:
                from app.db import story_repo as _story_repo
                _story_repo.upsert_series(_series_id, language=language, art_style=art_style)
            except Exception:
                pass

        # ── 2. Voice cast (AI-decided; fills render.voices) ─────────────────
        # Cast from plan.language — the plan is the source of truth for the render's
        # language (esp. a pasted plan whose language may differ from the request's
        # voice_language). Casting from the request language mis-picked the TTS engine:
        # a JA plan submitted with the default VI config resolved to Gemini (VI's engine)
        # and synthesized Japanese on a PAID engine. plan.language is always set (line 188).
        apply_voice_cast_v2(plan, plan.language or language, narrator_gender=narrator_gender)

        # ── 3. Images (≤ceiling; per Visual) ────────────────────────────────
        _set_stage(JobStage.SEGMENT_BUILDING, 30,
                   f"Storyboard: {plan.image_count()} image(s), {plan.beat_count()} beat(s)")
        # Persistent visuals dir (under CACHE_DIR — survives the shots_dir cleanup
        # so the live-monitor thumbnail endpoint keeps serving after DONE; reclaimed
        # by the periodic cache prune).
        visuals_dir = CACHE_DIR / "story_visuals" / job_id
        visuals_dir.mkdir(parents=True, exist_ok=True)
        # Story Mode is SVG-only (the schema validator coerces any stored legacy value →
        # "svg"); this local is kept for the guard + call-site parity below.
        image_provider = (getattr(payload, "story_image_provider", "svg") or "svg").strip().lower()
        if image_provider != "svg":
            image_provider = "svg"
        # SVG foundation guard: when the SVG art path is active the resvg-py rasteriser
        # is the SOLE source of key-visuals AND character overlays. If it's unavailable
        # every visual would silently degrade to a solid background with no characters —
        # a near-blank video delivered as success. Fail fast with a clear, actionable
        # error instead. Only the image path is guarded here; a base video supplies its
        # own imagery from the video frames (its overlay masters are guarded separately).
        _svg_active = image_provider == "svg" or os.getenv("STORY_SVG_GEN", "0") == "1"
        if _svg_active and not base_video_path:
            from app.features.render.engine.visual import svg_raster
            if not svg_raster.available():
                raise RuntimeError(
                    "Story SVG rendering needs the 'resvg-py' package, which is not "
                    "installed — the video would have no artwork or characters. Install "
                    "it (pip install resvg-py) and retry."
                )
        visual_fallbacks = []
        # When a base video is the visual layer the key-visual images are NEVER used
        # (render_one_cue draws from the video) — skip composing them. The character
        # overlay masters are generated in 3b below.
        if base_video_path:
            _job_log(effective_channel, job_id,
                     "Story v2: base video present — skipping key-visual image gen (unused)")
        else:
            # Procedural SVG key-visuals (offline, $0). With the overlay default ON they are
            # composed BACKGROUND-ONLY; the speaking character is composited per-beat below.
            visual_fallbacks = _generate_images(
                plan, visuals_dir, art_style, img_w, img_h,
                job_id=job_id, effective_channel=effective_channel, provider=image_provider,
            )
            if visual_fallbacks:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.visual.fallback", level="WARNING",
                    message=(f"{len(visual_fallbacks)}/{plan.image_count()} image(s) unavailable — "
                             f"used a solid background. Check resvg-py / the visual prompts."),
                    step="render.story",
                    context={"fallback_visuals": visual_fallbacks, "total": plan.image_count()},
                )
            # N4 — per-(speaker, emotion, pose) overlay masters. Key-visuals were composed
            # BACKGROUND-ONLY, so these masters are what the cue render overlays (default ON,
            # opt out STORY_CHAR_OVERLAY=0). Best-effort.
            if os.getenv("STORY_CHAR_OVERLAY", "1") != "0":
                _generate_overlay_masters(plan, visuals_dir, job_id=job_id,
                                          effective_channel=effective_channel)

        # ── 3b. Character overlay masters (per emotion/pose) — when a base video is the
        #        base layer, the SPEAKING CHARACTER is composited over the VIDEO. The video
        #        is the background (no SVG background is ever drawn over it), so only the
        #        transparent character masters are generated here — one per (speaker,
        #        emotion, pose), matching the image path so a base-video story shows the
        #        same per-beat expressions. Best-effort; a no-op with STORY_CHAR_OVERLAY=0
        #        or no speaking beats. resvg-absent simply yields no overlay (the video
        #        still plays), so this path is not hard-gated on the rasteriser.
        if base_video_path and os.getenv("STORY_CHAR_OVERLAY", "1") != "0":
            _generate_overlay_masters(plan, visuals_dir, job_id=job_id,
                                      effective_channel=effective_channel)

        # ── 4. Narration (per-beat TTS, bounded parallel → beat_audio) ──────
        # P0: stream per-beat progress (45→54) so the monitor moves during narration
        # instead of freezing at "Narration timeline" for the whole TTS pass.
        _set_stage(JobStage.SEGMENT_BUILDING, 45, "Narration timeline")

        def _narr_progress(done: int, total: int) -> None:
            pct = 45 + int(9 * done / max(1, total))
            _set_stage(JobStage.SEGMENT_BUILDING, pct, f"Narration {done}/{total} beats")

        _voice_mode = (getattr(payload, "story_voice_mode", "dialogue") or "dialogue")
        synthesize_timeline(plan, job_id=job_id, audio_dir=audio_dir, subtitle_mode=subtitle_mode,
                            effective_channel=effective_channel, on_progress=_narr_progress,
                            voice_mode=_voice_mode)

        # ── 5. CUE SHEET (deterministic) ────────────────────────────────────
        plan.build_cues(subtitle_mode)
        cues = list(plan.render.cues)
        total_parts = len(cues)
        if total_parts == 0:
            raise RuntimeError("Story v2: cue sheet is empty — nothing to render")
        update_story_plan(job_id, plan.to_json())   # persist filled render state (resume)

        _output_stem = (
            safe_filename(getattr(payload, "title_overlay_text", "") or plan.topic or "")
            or f"story_{job_id[:8]}"
        )
        for i, c in enumerate(cues, start=1):
            upsert_job_part(job_id, i, f"cue_{i:04d}", JobPartStage.QUEUED,
                            progress_percent=0, duration=max(0.0, float(c.end_sec - c.start_sec)),
                            message=(c.visual_id or ""))

        _cue_workers = _worker_count("STORY_RENDER_WORKERS", 2, total_parts)
        # Cap per-encode threads so N parallel libx264 encodes don't oversubscribe the
        # CPU (0 = ffmpeg auto, used for the serial path).
        _cue_threads = max(1, (os.cpu_count() or 4) // _cue_workers) if _cue_workers > 1 else 0
        ctx = SimpleNamespace(
            job_id=job_id, effective_channel=effective_channel, shots_dir=shots_dir,
            width=width, height=height, fps=fps, bg_value=bg_value, ffmpeg_threads=_cue_threads,
            base_video_path=base_video_path, base_video_dur=base_video_dur,   # A1 (consumed in A2)
            base_video_has_audio=base_video_has_audio,                        # A4
        )

        # ── 6. Render cues (parallel; libx264/CPU → no NVENC contention) ────
        # WORKER threads run render_one_cue (pure ffmpeg, unique output file, no DB /
        # no plan mutation). Result COLLECTION happens on the MAIN thread in the
        # as_completed loop, so part-status writes + progress stay serial (no lock,
        # no worker-thread DB conn). STORY_RENDER_WORKERS=1 restores the serial path.
        _set_stage(JobStage.RENDERING, 55, f"Rendering {total_parts} cue(s)")
        results: dict[int, str] = {}
        failed_parts: list[dict] = []
        _rendered = 0
        # Mark every cue RENDERING up front (main thread) before the pool starts.
        for i, c in enumerate(cues, start=1):
            upsert_job_part(job_id, i, f"cue_{i:04d}", JobPartStage.RENDERING,
                            progress_percent=10, message=(c.visual_id or ""))

        def _collect_cue(i, r):
            nonlocal _rendered
            if r.get("clip"):
                results[i] = r["clip"]
                upsert_job_part(job_id, i, f"cue_{i:04d}", JobPartStage.DONE,
                                progress_percent=100, message="done")
            else:
                failed_parts.append({"part_no": i, "error": r.get("error", "")})
                upsert_job_part(job_id, i, f"cue_{i:04d}", JobPartStage.FAILED,
                                progress_percent=100, message=(r.get("error", "") or "")[:200])
            _rendered += 1
            _set_stage(JobStage.RENDERING, 55 + int(30 * _rendered / max(1, total_parts)),
                       f"Rendered {_rendered}/{total_parts}")

        if _cue_workers <= 1:
            for i, c in enumerate(cues, start=1):
                if cancel_registry.is_cancelled(job_id):
                    raise cancel_registry.JobCancelledError()
                _collect_cue(i, render_one_cue(ctx, plan, i, c))
        else:
            with ThreadPoolExecutor(max_workers=_cue_workers) as _ex:
                _futs = {}
                for i, c in enumerate(cues, start=1):
                    if cancel_registry.is_cancelled(job_id):
                        break  # stop submitting; running futures drain on __exit__
                    _futs[_ex.submit(render_one_cue, ctx, plan, i, c)] = i
                for f in as_completed(_futs):
                    i = _futs[f]
                    try:
                        r = f.result()
                    except Exception as exc:   # render_one_cue never raises, but be safe
                        r = {"clip": None, "error": str(exc)}
                    _collect_cue(i, r)
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()

        delivered_idx = sorted(results)
        clips = [results[i] for i in delivered_idx]
        if not clips:
            raise RuntimeError("Story v2: no cue rendered successfully")
        transitions = _delivered_transitions(cues, delivered_idx)

        # ── 7. Assemble (reuse content xfade assembler) ─────────────────────
        final_out, assembly = assemble_shots(
            ctx, plan, payload, output_dir=output_dir, output_stem=_output_stem,
            shot_clips=clips, transitions=transitions, set_stage=_set_stage,
        )

        # ── 7b. Background music per-scene (AI-planned mood) — best-effort ───
        if os.getenv("STORY_AUTO_BGM", "1") == "1":
            _mix_scene_bgm(job_id, effective_channel, plan, final_out, work_dir)

        # ── 8. Finalize (QA gate #8 + Sacred #1 result_json + DONE) ─────────
        _finalize_story_v2(
            job_id, effective_channel, payload, plan, output_dir=output_dir,
            output_stem=_output_stem, final_out=final_out, assembly=assembly,
            clips=clips, shots_dir=shots_dir, total_parts=total_parts,
            failed_parts=failed_parts, visual_fallbacks=visual_fallbacks,
            plan_meta=plan_meta,
        )

        # ── 9. Series memory (G1) — persist canonical characters + a rolling
        #      summary so the NEXT chapter grounds on this one. Best-effort; a
        #      no-op when story_series_id is empty (one-off chapter).
        from app.features.render.engine.pipeline.story_series_memory import persist_series_memory
        persist_series_memory(
            plan, (getattr(payload, "story_series_id", "") or ""),
            int(getattr(payload, "story_chapter_no", 0) or 0),
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


__all__ = ["run_story_v2"]
