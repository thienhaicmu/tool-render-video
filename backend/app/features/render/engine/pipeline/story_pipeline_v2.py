"""
story_pipeline_v2.py — Story Mode v2 orchestrator (Super-Prompt + Cue Sheet, B7).

One flat, length-independent AI cost profile: 1 super plan call → N images (≤ceiling)
→ ~1 TTS per voice-run → a deterministic CUE SHEET → per-cue Ken Burns render →
assemble → QA → DONE. Replaces the v1 scene/shot pipeline as the dispatch target for
render_format="story" (routers/_common.process_render).

Flow (all engine blocks reused; nothing in the clips/recap/content paths is touched):
  setup_render_pipeline · prepare_output_dir · generate_story_plan_v2 (1 super call) ·
  apply_voice_cast_v2 · generate_visual_image (per Visual, gpt-image-1) ·
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
import shutil
import subprocess
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
from app.features.render.engine.visual.story_image import generate_visual_image
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
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

logger = logging.getLogger("app.render.story")


def _worker_count(env_name: str, default: int, n_items: int) -> int:
    """Bounded worker count for a parallel phase: env override, capped at the item
    count, floored at 1. ``=1`` restores the serial path (byte-identical rollback)."""
    try:
        w = int(os.getenv(env_name, str(default)) or default)
    except (TypeError, ValueError):
        w = default
    return max(1, min(w, max(1, int(n_items or 1))))


def _subtitle_mode(payload) -> str:
    """Map the request flags → v2 subtitle_mode. Default hook_only; add_subtitle=False
    → off. (full-subtitle is not exposed on the wire yet — niche.)"""
    return "hook_only" if bool(getattr(payload, "add_subtitle", True)) else "off"


def _resolve_story_plan_v2(payload, *, job_id, resume_mode, source, chapter, idea,
                           duration_sec, genre, language, art_style, aspect, subtitle_mode) -> StoryPlan:
    """Resolve the StoryPlan v2 to render: approved override → persisted (resume) →
    fresh super-plan call. Raises RuntimeError when no usable plan is available."""
    override = (getattr(payload, "story_plan_override", "") or "").strip()
    if override:
        plan = StoryPlan.from_json(override)
        if plan is not None and plan.schema_version == 2 and not plan.is_empty() and plan.image_count() > 0:
            logger.info("story v2: using approved story_plan_override (%d visuals)", plan.image_count())
            return plan

    if resume_mode:
        persisted = get_story_plan(job_id)
        if persisted:
            plan = StoryPlan.from_json(persisted)
            if plan is not None and plan.schema_version == 2 and not plan.is_empty() and plan.image_count() > 0:
                logger.info("story v2: resume — using persisted plan (%d visuals)", plan.image_count())
                return plan

    # Fresh super-plan. GPT-centric: provider from payload else STORY_AI_PROVIDER.
    provider = (getattr(payload, "ai_provider", "") or "").strip().lower()
    if not provider:
        provider = (os.getenv("STORY_AI_PROVIDER", "openai") or "openai").strip().lower()
    api_key, resolve_key = "", None
    try:
        from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
        api_key, _ = _resolve_api_key(payload, provider)
        resolve_key = lambda _p: _resolve_api_key(payload, _p)[0]  # noqa: E731
    except Exception:
        api_key, resolve_key = "", None
    plan = generate_story_plan_v2(
        provider=provider, source=source, chapter=chapter, idea=idea,
        duration_sec=duration_sec, genre=genre, language=language, art_style=art_style,
        aspect_ratio=aspect, subtitle_mode=subtitle_mode,
        series_id=(getattr(payload, "story_series_id", "") or ""),
        chapter_no=int(getattr(payload, "story_chapter_no", 0) or 0),
        api_key=api_key, model=(getattr(payload, "llm_model", None) or None),
        resolve_key=resolve_key,
    )
    if plan is None or plan.is_empty() or plan.image_count() == 0:
        raise RuntimeError("Story v2: super plan returned no usable StoryPlan")
    if not (plan.language or "").strip():
        plan.language = language
    return plan


def _generate_images(plan, out_dir: Path, art_style: str, img_w: int, img_h: int,
                     *, job_id: str, effective_channel: str, provider: str = "gpt_image") -> list:
    """Generate one image per Visual → plan.render.visual_assets[vid]. Returns the
    list of visual_ids that FELL BACK (no image). Never raises per-visual.

    Images land in a PERSISTENT dir (``out_dir`` under CACHE_DIR, not the temp
    shots dir) so they survive the finalize cleanup and the live-monitor thumbnail
    endpoint can serve them during AND after the render. The plan is persisted +
    a ``story.visual.ready`` event emitted after EACH image so the FE reveals the
    visuals one by one (best-effort — a persist/emit hiccup never fails a visual)."""
    fallbacks: list = []
    total = plan.image_count()
    seed = int(plan.seed or 0)

    def _gen_one(v):
        # WORKER thread: pure image gen (network/file I/O). No DB, no plan mutation —
        # only reads plan.render.refs. Returns (visual_id, path|None). Never raises.
        try:
            out = out_dir / f"{v.id}.png"
            refs = {cid: plan.render.refs[cid] for cid in getattr(v, "character_ids", [])
                    if cid in plan.render.refs}
            return v.id, generate_visual_image(v, refs, art_style, img_w, img_h, str(out),
                                               seed=seed, provider=provider)
        except Exception:
            return v.id, None

    def _collect(vid, p):
        # MAIN thread only: mutate plan + persist + emit (serial → no lock needed).
        if p:
            plan.render.visual_assets[vid] = p
            try:
                update_story_plan(job_id, plan.to_json())
            except Exception:
                pass
            try:
                _emit_render_event(
                    channel_code=effective_channel, job_id=job_id,
                    event="story.visual.ready", level="INFO",
                    message=f"Key-visual {vid} ready ({len(plan.render.visual_assets)}/{total})",
                    step="render.story",
                    context={"visual_id": vid, "done": len(plan.render.visual_assets), "total": total},
                )
            except Exception:
                pass
        else:
            fallbacks.append(vid)

    workers = _worker_count("STORY_IMAGE_WORKERS", 3, total)
    if workers <= 1:
        for v in plan.visuals:
            vid, p = _gen_one(v)
            _collect(vid, p)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_gen_one, v): v.id for v in plan.visuals}
            for f in as_completed(futs):
                try:
                    vid, p = f.result()
                except Exception:
                    vid, p = futs[f], None
                _collect(vid, p)
    return fallbacks


def _delivered_transitions(cues: list, delivered_idx: list) -> list:
    """len-1 transition list aligned to the DELIVERED clips (skips failed cues): use
    the NEXT delivered cue's transition. Pure, never raises."""
    trans: list = []
    for i in range(len(delivered_idx) - 1):
        nxt = cues[delivered_idx[i + 1] - 1]
        trans.append(getattr(nxt, "transition", "") or "fade")
    return trans


def _mix_scene_bgm(job_id, effective_channel, plan, final_out, work_dir) -> None:
    """Dựng track nhạc nền per-scene (mood do AI plan) + duck dưới lời kể, ghi đè
    ``final_out`` tại chỗ. Best-effort — thiếu file nhạc / bất kỳ lỗi nào → giao video
    KHÔNG nhạc, không bao giờ fail render (Sacred Contract #3 spirit). Chạy TRƯỚC QA
    nên file giao được validate kèm nhạc (Sacred Contract #8)."""
    tmp = str(final_out) + ".bgm.mp4"
    try:
        segments = plan.bgm_scenes()
        if not segments:
            return
        total = float(getattr(plan.render, "total_sec", 0.0) or 0.0)
        from app.features.render.engine.audio.mixer import build_scene_bgm_track, mix_with_bgm
        bgm_dir = Path(work_dir) / "story_bgm"
        track = build_scene_bgm_track(segments, total, str(bgm_dir / "bgm_timeline.wav"))
        if not track:
            _job_log(effective_channel, job_id,
                     "Story v2: no BGM (no music files for the planned moods — see BGM_DIR)")
            return
        mix_with_bgm(video_path=str(final_out), bgm_path=track, output_path=tmp, duck=True)
        Path(tmp).replace(final_out)
        moods = sorted({(m or "default") for m, _s, _e in segments})
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="story.bgm.ready",
            level="INFO", message=f"Background music mixed ({len(segments)} scene(s))",
            step="render.story", context={"scenes": len(segments), "moods": moods},
        )
        _job_log(effective_channel, job_id,
                 f"Story v2: BGM mixed ({len(segments)} scene(s), moods={moods})")
    except Exception as exc:
        logger.warning("story v2: BGM mix failed (non-fatal): %s", exc)
        try:
            if Path(tmp).exists():
                Path(tmp).unlink()
        except Exception:
            pass


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

        if source == "idea":
            if not idea:
                raise RuntimeError("Story v2: source=idea but story_idea is empty")
        elif not chapter:
            raise RuntimeError("Story v2: empty content_script — nothing to render")

        # ── 1. Super plan (1 AI call) ───────────────────────────────────────
        _set_stage(JobStage.ANALYZING, 12, "Story Director: super plan (1 call)")
        plan = _resolve_story_plan_v2(
            payload, job_id=job_id, resume_mode=resume_mode, source=source, chapter=chapter,
            idea=idea, duration_sec=duration_sec, genre=genre, language=language,
            art_style=art_style, aspect=aspect, subtitle_mode=subtitle_mode,
        )
        update_story_plan(job_id, plan.to_json())

        # ── 2. Voice cast (AI-decided; fills render.voices) ─────────────────
        apply_voice_cast_v2(plan, language, narrator_gender=narrator_gender)

        # ── 3. Images (≤ceiling; per Visual) ────────────────────────────────
        _set_stage(JobStage.SEGMENT_BUILDING, 30,
                   f"Storyboard: {plan.image_count()} image(s), {plan.beat_count()} beat(s)")
        # Persistent visuals dir (under CACHE_DIR — survives the shots_dir cleanup
        # so the live-monitor thumbnail endpoint keeps serving after DONE; reclaimed
        # by the periodic cache prune).
        visuals_dir = CACHE_DIR / "story_visuals" / job_id
        visuals_dir.mkdir(parents=True, exist_ok=True)
        # Phase 2 — FINAL image provider from the payload (validator guarantees a valid
        # value; default "gpt_image" = the existing paid, character-consistent path).
        image_provider = (getattr(payload, "story_image_provider", "gpt_image") or "gpt_image").strip().lower()
        if image_provider not in ("gpt_image", "pollinations"):
            image_provider = "gpt_image"
        visual_fallbacks = _generate_images(
            plan, visuals_dir, art_style, img_w, img_h,
            job_id=job_id, effective_channel=effective_channel, provider=image_provider,
        )
        if visual_fallbacks:
            _hint = "OPENAI_API_KEY / prompts" if image_provider == "gpt_image" else "network / prompts"
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="story.visual.fallback", level="WARNING",
                message=(f"{len(visual_fallbacks)}/{plan.image_count()} image(s) unavailable — "
                         f"used a solid background. Check {_hint}."),
                step="render.story",
                context={"fallback_visuals": visual_fallbacks, "total": plan.image_count()},
            )

        # ── 4. Narration (per voice-run TTS → beat_audio) ───────────────────
        _set_stage(JobStage.SEGMENT_BUILDING, 45, "Narration timeline")
        synthesize_timeline(plan, job_id=job_id, audio_dir=audio_dir, subtitle_mode=subtitle_mode)

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


def _finalize_story_v2(job_id, effective_channel, payload, plan, *, output_dir, output_stem,
                       final_out, assembly, clips, shots_dir, total_parts,
                       failed_parts, visual_fallbacks):
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


__all__ = ["run_story_v2"]
