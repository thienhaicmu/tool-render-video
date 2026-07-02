"""
recap_pipeline.py — fully separate orchestrator for render_format="recap".

Phase R2. Kept ENTIRELY separate from render_pipeline.run_render_pipeline so the
clips path is never touched. Dispatched from routers/_common.process_render:

    if payload.render_format == "recap":
        run_recap(...)
    else:
        run_render_pipeline(...)

run_recap reuses the existing building blocks by COMPOSITION (not copy of logic):
  setup_render_pipeline · prepare_output_dir · prepare_render_source ·
  run_llm_pre_render (skip_segment_selection — we only need the full SRT) ·
  ai.llm.select_recap_plan · run_render_loop (renders each scene as a "part") ·
  recap_title_card + recap_assembler (concat scenes+act-cards → 1 long video) ·
  qa_pipeline._validate_render_output · upsert_job(JobStage.DONE).

Contract mirrors run_render_pipeline so process_render's cancel / failure /
metrics / close_thread_conn wrapper applies unchanged: same signature, raises
JobCancelledError on cancel, raises on failure, writes a terminal DB row on the
success path.

Sacred Contracts: #2 (gated by render_format, default "clips"); #3 (AI never
raises — select_recap_plan returns None → job fails cleanly); #4 (terminal
stage = JobStage.DONE); #7 (only DB writers are the shared repo helpers);
#8 (the single concatenated output passes qa_pipeline before DONE).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from app.core.config import TEMP_DIR
from app.core.stage import JobStage
from app.db.connection import close_thread_conn
from app.db.jobs_repo import list_job_parts, update_job_progress, upsert_job, update_recap_plan
from app.jobs import cancel as cancel_registry
from app.jobs.manager import MAX_CONCURRENT_JOBS as _MAX_CONCURRENT_JOBS
from app.features.render.ai.llm import select_recap_plan
from app.features.render.engine.encoder.ffmpeg_helpers import (
    nvenc_available,
    resolve_ffmpeg_threads,
    resolve_target_dimensions,
)
from app.features.render.engine.pipeline.pipeline_setup import setup_render_pipeline, prepare_output_dir
from app.features.render.engine.pipeline.pipeline_source_prep import prepare_render_source
from app.features.render.engine.pipeline.pipeline_config import _resolve_profile
from app.features.render.engine.pipeline.llm_pipeline import run_llm_pre_render
from app.features.render.engine.pipeline.pipeline_render_loop import run_render_loop
from app.features.render.engine.pipeline.qa_pipeline import _validate_render_output
from app.features.render.engine.pipeline.render_events import (
    _emit_render_event,
    _job_log,
    _resolve_job_log_dir,
    register_job_log_dir,
    unregister_job_log_dir,
)
from app.features.render.engine.pipeline.render_pipeline import (
    JOB_SEMAPHORE,
    _render_active_lock,
    _render_active_count,
)
from app.features.render.engine.stages.part_renderer import PartRenderContext
from app.features.render.engine.stages.recap_assembler import concat_clips
from app.features.render.engine.stages.recap_title_card import make_act_title_card

logger = logging.getLogger("app.render.recap")

# P1-2 — per-episode narration refinement. The whole-film recap call authors
# narration for every scene at once, so later scenes degrade. When ON, re-author
# each episode's narration in a focused call. Default OFF → recap is
# byte-identical; the wiring below is a no-op. Costs +1 LLM call per episode.
_RECAP_PER_EPISODE_NARRATION: bool = os.getenv("RECAP_PER_EPISODE_NARRATION", "0") == "1"

# Windows-illegal filename chars (+ control chars). Episode titles come from the
# AI (e.g. "Tập 1: Mở màn án mạng") and may contain ':' '/' etc.
import re as _re
_FS_ILLEGAL_RE = _re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(name: str, max_len: int = 120) -> str:
    """Make an AI-authored title safe to use as a filename stem. Strips illegal
    chars, collapses whitespace, trims trailing dots/spaces (Windows), caps
    length. Returns '' if nothing usable survives. Never raises."""
    try:
        s = _FS_ILLEGAL_RE.sub(" ", str(name or ""))
        s = _re.sub(r"\s+", " ", s).strip().strip(".").strip()
        if len(s) > max_len:
            s = s[:max_len].rsplit(" ", 1)[0].strip() or s[:max_len].strip()
        return s
    except Exception:
        return ""


def _scored_from_recap_plan(recap_plan) -> list[dict]:
    """Flatten RecapPlan episodes→acts→scenes into the chronological `scored`
    shape the render loop / part_renderer expects. Neutral scores (recap order
    is chronological, not viral-ranked). `episode_index` + `act_index` ride
    along so the finalize step can group scenes back into episodes (→ one output
    each) and acts (→ title cards). R6: `audio_mode` tells part_voice_mix whether
    to narrate or let the source audio play raw."""
    out: list[dict] = []
    _global_act = 0     # monotonically-increasing act id for title-card grouping
    for ep_i, ep in enumerate(recap_plan.episodes):
        n_acts = len(ep.acts)
        _prev_intent = ""   # N5: continuity resets at each episode boundary
        for act_local, act in enumerate(ep.acts):
            for scene in act.scenes:
                start = float(scene.start)
                end = float(scene.end)
                if end <= start:
                    continue
                _mode = "original" if (getattr(scene, "audio_mode", "narrate") == "original") else "narrate"
                # R3 + N5: compose the per-scene DIRECTOR'S INTENT — act position +
                # previous scene's intent + this scene's intent — so the narrator
                # tells ONE continuous story that flows scene→scene.
                _intent = (scene.narration_intent or "").strip()
                _act_tag = f"Act {act_local + 1}/{n_acts}"
                if act.title:
                    _act_tag += f" — {act.title}"
                if act.beat:
                    _act_tag += f" ({act.beat})"
                _ep_tag = f"Ep {ep_i + 1}/{len(recap_plan.episodes)}"
                _hint_parts = [f"[Recap {_ep_tag} · {_act_tag}]"]
                if _prev_intent:
                    _hint_parts.append(f"Previously: {_prev_intent}.")
                if _intent:
                    _hint_parts.append(f"Now: {_intent}")
                _editorial = " ".join(_hint_parts).strip() if (_intent or act.title or _prev_intent) else ""
                if _intent:
                    _prev_intent = _intent
                out.append({
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "viral_score": 50.0,
                    "hook_score": 50.0,
                    "motion_score": 50.0,
                    "diversity_score": 50.0,
                    "retention_score": 50.0,
                    "audio_energy": 50.0,
                    "clip_name": (scene.title or f"scene_{len(out)+1}"),
                    "ai_title": scene.title or "",
                    "ai_reason": scene.narration_intent or "",
                    "narration_intent": _intent,
                    "editorial_hint": _editorial,
                    # AI-authored recap narration. Empty for "original" scenes —
                    # part_voice_mix then skips voice and keeps the source audio.
                    "narration_text": (scene.narration or "").strip(),
                    "audio_mode": _mode,
                    "source": "recap",
                    "content_type_hint": "",
                    "is_climax": bool(scene.is_climax),
                    "episode_index": ep_i,
                    "episode_title": ep.title or "",
                    "act_index": _global_act,
                    "act_title": act.title or "",
                    "act_beat": act.beat or "",
                })
            _global_act += 1
    return out


def _check_recap_coverage(recap_plan, video_duration: float) -> dict:
    """N5 — measure how well the selected scenes span the film. Returns metrics
    + a `weak` flag (scenes clustered into a small span, or a large uncovered
    gap between consecutive scenes). Never raises."""
    dur = float(video_duration) if video_duration and video_duration > 0 else 0.0
    scenes = sorted(recap_plan.scenes(), key=lambda s: float(s.start))
    if not scenes or dur <= 0:
        return {"weak": False, "span_pct": 0.0, "max_gap_pct": 0.0, "scenes": len(scenes)}
    first = float(scenes[0].start)
    last = float(scenes[-1].end)
    span_pct = max(0.0, min(100.0, (last - first) / dur * 100.0))
    # Largest uncovered gap between consecutive selected scenes.
    max_gap = 0.0
    for a, b in zip(scenes, scenes[1:]):
        max_gap = max(max_gap, float(b.start) - float(a.end))
    max_gap_pct = max(0.0, min(100.0, max_gap / dur * 100.0))
    # Weak when the plan covers < 50% of the runtime OR leaves a > 40% hole.
    weak = span_pct < 50.0 or max_gap_pct > 40.0
    return {
        "weak": bool(weak),
        "span_pct": round(span_pct, 1),
        "max_gap_pct": round(max_gap_pct, 1),
        "scenes": len(scenes),
        "first_scene_sec": round(first, 1),
        "last_scene_sec": round(last, 1),
    }


def run_recap(
    job_id: str,
    payload,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
) -> None:
    """Orchestrate a recap/review render. Raises JobCancelledError on cancel and
    re-raises on failure (process_render writes the terminal failed row)."""
    _setup = setup_render_pipeline(payload)
    effective_channel = _setup.effective_channel
    output_dir = _setup.output_dir
    prepare_output_dir(job_id, effective_channel, output_dir)
    register_job_log_dir(job_id, _resolve_job_log_dir(output_dir, effective_channel))
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    tuned = _resolve_profile(payload)
    retry_count = max(0, min(5, int(getattr(payload, "retry_count", 0) or 0)))
    current_stage = JobStage.STARTING

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage
        current_stage = stage
        update_job_progress(job_id, stage, max(0, min(99, int(progress))), message)
        _job_log(effective_channel, job_id, f"[STAGE] {stage} | {message}")
        from app.core.stage import STAGE_TO_EVENT
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id,
            event=STAGE_TO_EVENT.get(stage, "render.start"),
            level="INFO", message=message, step=str(stage),
            context={"progress_percent": progress, "render_format": "recap"},
        )

    upsert_job(
        job_id, "render", effective_channel, "running", payload.model_dump(), {},
        stage=JobStage.STARTING, progress_percent=1,
        message="Initializing recap render",
    )
    _job_log(effective_channel, job_id, f"Recap render started | profile={payload.render_profile}")

    try:
        # 1. Source prep ------------------------------------------------------
        _src = prepare_render_source(
            job_id=job_id, effective_channel=effective_channel, payload=payload,
            work_dir=work_dir, output_dir=output_dir, hook_applied_text="",
            set_stage=_set_stage, load_session_fn=load_session_fn,
        )
        source = _src.source
        source_path = _src.source_path
        _output_stem = _src.output_stem
        video_duration = float(source.get("duration") or 0.0)

        # 2b (start nền). SceneMap substrate (D-2-thin) chỉ cần source_path —
        # không phụ thuộc SRT — nên chạy trên thread nền SONG SONG với Whisper
        # + lời gọi LLM thay vì tuần tự sau Whisper như trước. Consumer đầu
        # tiên (snap-to-shots bên dưới) join trước khi đọc kết quả. Thất bại
        # hay None không bao giờ chặn render — giữ nguyên hành vi cũ. Đánh
        # đổi nhỏ: job bị cancel giữa chừng thì thread nền vẫn chạy nốt
        # scenedetect (daemon, vô hại — chỉ tốn CPU nền một lần).
        _scene_map_holder: dict = {"map": None}

        def _scene_map_worker() -> None:
            try:
                from app.features.render.engine.pipeline.scene_map_stage import (
                    run_scene_map as _run_scene_map,
                )
                _scene_map_holder["map"] = _run_scene_map(
                    job_id=job_id, channel_code=effective_channel,
                    video_path=source_path,
                    emit_fn=_emit_render_event,
                )
            except Exception:
                # Phòng thủ — stage đã tự bắt lỗi, nhưng thread nền tuyệt đối
                # không được làm sập render vì một khâu quan sát/substrate.
                _scene_map_holder["map"] = None

        _scene_map_thread = threading.Thread(
            target=_scene_map_worker, daemon=True,
            name=f"scene_map_{job_id[:8]}",
        )
        _scene_map_thread.start()

        # 2. Full transcript (Whisper) — skip clip selection ------------------
        _pre = run_llm_pre_render(
            source_path=source_path, source=source, work_dir=work_dir, payload=payload,
            tuned=tuned, job_id=job_id, effective_channel=effective_channel,
            retry_count=retry_count, cancel_registry=cancel_registry,
            set_stage_fn=_set_stage, skip_segment_selection=True,
        )
        full_srt = _pre.full_srt
        full_srt_available = _pre.full_srt_available
        target_platform = _pre.target_platform

        _ai_srt = ""
        if full_srt_available and full_srt and Path(full_srt).exists():
            try:
                _ai_srt = Path(full_srt).read_text(encoding="utf-8")
            except Exception:
                _ai_srt = ""
        if not _ai_srt.strip():
            raise RuntimeError("Recap: transcript empty — cannot select scenes")

        # 2b. SceneMap giờ chạy trên thread nền (khởi động trước Whisper ở
        # trên). Kết quả được join + đọc ngay trước bước snap-to-shots —
        # consumer đầu tiên của nó — để tối đa phần chạy chồng lấp với
        # Whisper và lời gọi LLM.

        # 3. Recap scene selection (AI) --------------------------------------
        _set_stage(JobStage.SEGMENT_BUILDING, 30, "AI selecting recap scenes + acts")
        from app.core import config as _cfg
        from app.features.render.engine.pipeline.llm_stage import _resolve_api_key as _resolve_llm_api_key
        _provider = (getattr(payload, "ai_provider", "") or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
        _api_key, _ = _resolve_llm_api_key(payload, _provider)

        # Architecture-review Batch A: emit a WS event after each hidden
        # Story Intelligence pass so the UI sees progress between pass-1
        # (story), pass-2 (editorial), pass-3 (binding). Each callback is
        # invoked with the produced model (None on failure) and is safely
        # swallowed by the dispatcher if it raises. Sacred Contract #6:
        # ADDITIVE event names — the top-level {job, parts, summary}
        # WebSocket shape is untouched.
        def _on_pass1_done(story_model) -> None:
            ok = story_model is not None
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="recap.pass1.done",
                level=("INFO" if ok else "WARNING"),
                message=(
                    "Pass 1 (Story Understanding) complete"
                    if ok else
                    "Pass 1 (Story Understanding) returned empty — single-pass fallback"
                ),
                step="render.recap",
                context={
                    "pass": "story",
                    "ok": ok,
                    "story_model": (story_model.to_public_dict() if ok else None),
                },
            )

        def _on_pass2_done(editorial) -> None:
            ok = editorial is not None
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id,
                event="recap.pass2.done",
                level=("INFO" if ok else "WARNING"),
                message=(
                    "Pass 2 (Editorial Blueprint) complete"
                    if ok else
                    "Pass 2 (Editorial Blueprint) returned empty — binding without it"
                ),
                step="render.recap",
                context={
                    "pass": "editorial",
                    "ok": ok,
                    "editorial": (editorial.to_public_dict() if ok else None),
                },
            )

        # Architecture-review Batch C (2026-06-30): hoist Story Intelligence
        # (pass-1) out of the dispatcher into a named pipeline stage. When the
        # hoist is enabled, the Comprehension stage produces the StoryModel
        # externally (and owns the recap.pass1.done WS event); the dispatcher
        # then skips its internal pass-1. When the hoist is disabled via
        # ``STORY_INTELLIGENCE_HOIST_ENABLED=0``, behaviour falls back to the
        # bit-identical Batch-A path (legacy lambda fires on_pass1_done from
        # inside the dispatcher).
        from app.features.render.engine.pipeline.comprehension_stage import (
            run_comprehension as _run_comprehension,
            is_hoist_enabled as _comprehension_enabled,
        )
        _hoist_on = _comprehension_enabled()
        _external_story = None
        if _hoist_on:
            _external_story = _run_comprehension(
                job_id=job_id, channel_code=effective_channel,
                srt_content=_ai_srt, video_duration=video_duration,
                provider=_provider, api_key=_api_key,
                model=getattr(payload, "llm_model", None),
                target_language=(getattr(payload, "voice_language", "") or "vi-VN"),
                tone=(getattr(payload, "rewrite_tone", "") or ""),
                emit_fn=_emit_render_event,
            )
        # Pass-1 callback wiring: only the kill-switch path forwards the Batch A
        # lambda. With the hoist enabled the Comprehension stage already owns
        # the recap.pass1.done event (success AND failure). When Comprehension
        # failed, the dispatcher's internal pass-1 still runs as a quality
        # fallback but emits no extra WS event (no double-fire).
        _pass1_callback = None if _hoist_on else _on_pass1_done

        recap_plan = select_recap_plan(
            provider=_provider, srt_content=_ai_srt, video_duration=video_duration,
            target_language=(getattr(payload, "voice_language", "") or "vi-VN"),
            tone=(getattr(payload, "rewrite_tone", "") or ""),
            api_key=_api_key, model=getattr(payload, "llm_model", None),
            story_model=_external_story,
            on_pass1_done=_pass1_callback,
            on_pass2_done=_on_pass2_done,
        )
        if recap_plan is None or not recap_plan.acts:
            raise RuntimeError("Recap: AI returned no usable plan")
        # Architecture-review Batch B (2026-06-30): bind each StoryBeat (plot
        # turn) to the RecapScene that executes it BEFORE the plan is
        # persisted, so the link is part of the durable record. Deterministic
        # — no LLM trust, no prompt change. Re-edit UI and "did pass-3 cover
        # every plot turn?" diagnostics consume bound_scene_index from here.
        try:
            recap_plan.bind_story_beats_to_scenes()
        except Exception:
            # Defensive — domain method already guards, but the recap render
            # must never abort on a binding/observability concern.
            pass

        # Join thread SceneMap nền (thường đã xong từ lâu — Whisper + LLM
        # chậm hơn scenedetect nhiều). join không timeout để giữ đúng
        # semantics của lời gọi inline trước đây: scenedetect chưa xong thì
        # chờ, kết quả None thì bước snap tự bỏ qua như cũ.
        _scene_map_thread.join()
        _scene_map = _scene_map_holder["map"]

        # Architecture-review Batch D-2-snap (2026-06-30): snap each scene's
        # start/end to the nearest shot boundary from the SceneMap produced
        # by D-2-thin earlier in this pipeline run. Deterministic — no LLM
        # trust, no prompt change. Closes the "AI picks dialog boundaries
        # not shot boundaries" gap flagged in the architecture review.
        # ``RECAP_SNAP_TO_SHOTS_ENABLED=0`` is the kill switch; default ON.
        # ``RECAP_SNAP_TOLERANCE_SEC`` (default 0.5) governs the in-tolerance
        # window — matches scene_detector's _TV2_MERGE_GAP_SEC by design.
        try:
            import os as _os
            if _os.getenv("RECAP_SNAP_TO_SHOTS_ENABLED", "1") == "1" and _scene_map is not None:
                try:
                    _tol = float(_os.getenv("RECAP_SNAP_TOLERANCE_SEC", "0.5"))
                except (TypeError, ValueError):
                    _tol = 0.5
                _snap_count = recap_plan.snap_scenes_to_shots(_scene_map, tolerance_sec=_tol)
                _job_log(
                    effective_channel, job_id,
                    f"Recap: snap-to-shots applied — {_snap_count} timestamp(s) shifted "
                    f"(tolerance={_tol:.2f}s)"
                )
        except Exception:
            # Defensive — domain method already guards, but the recap render
            # must never abort on a snap concern.
            pass

        # Duration-band reconciler (2026-07-02): deterministically enforce the
        # recap's own 10–25%-of-runtime spec. Structural measurement showed the
        # LLM ignores even a HARD prompt budget (post-prompt-fix sample still at
        # 69% of runtime), so — same philosophy as snap-to-shots — the guarantee
        # is deterministic: cap over-long scenes at 40s, then drop non-essential
        # scenes (never climax / original-audio holds) globally longest-first.
        # Runs BEFORE narration refinement so narration is authored for the
        # final scene set, and before persist. ``RECAP_TRIM_TO_BAND=0`` is the
        # kill switch; default ON. Never fatal.
        try:
            import os as _os_trim
            if _os_trim.getenv("RECAP_TRIM_TO_BAND", "1") == "1" and video_duration > 0:
                _trim = recap_plan.trim_to_duration_band(video_duration)
                if _trim.get("changed"):
                    _job_log(
                        effective_channel, job_id,
                        f"Recap: trimmed to duration band — capped={_trim['capped_scenes']} "
                        f"dropped={_trim['dropped_scenes']} "
                        f"ratio {_trim['ratio_before']}→{_trim['ratio_after']} "
                        f"(in_band={_trim['in_band']})",
                    )
                    _emit_render_event(
                        channel_code=effective_channel, job_id=job_id,
                        event="recap.trimmed_to_band", level="INFO",
                        message=(
                            f"Recap trimmed to length band: {_trim['before_sec']:.0f}s → "
                            f"{_trim['after_sec']:.0f}s"
                        ),
                        step="render.recap", context=_trim,
                    )
        except Exception:
            # Defensive — domain method already guards, but the recap render
            # must never abort on a length-governance concern.
            pass

        # P1-2 — per-episode narration refinement (env-gated, default OFF → no-op).
        # Re-author each episode's narration in a focused call so later scenes
        # don't degrade. Best-effort: any failure keeps the original narration.
        # Never fatal (Sacred Contract #3 spirit).
        if _RECAP_PER_EPISODE_NARRATION:
            try:
                from app.features.render.ai.llm import select_episode_narration as _sel_ep_narr
                _refined_total = 0
                for _ep in recap_plan.episodes:
                    _ep_scenes = _ep.scenes()
                    if not _ep_scenes:
                        continue
                    _payload = [
                        {
                            "index": _i, "start": _sc.start, "end": _sc.end,
                            "title": _sc.title, "intent": _sc.narration_intent,
                            "audio_mode": _sc.audio_mode,
                        }
                        for _i, _sc in enumerate(_ep_scenes)
                    ]
                    _narr = _sel_ep_narr(
                        provider=_provider, episode_scenes=_payload,
                        story_model=recap_plan.story,
                        target_language=(getattr(payload, "voice_language", "") or "vi-VN"),
                        tone=(getattr(payload, "rewrite_tone", "") or ""),
                        api_key=_api_key, model=getattr(payload, "llm_model", None),
                        episode_title=_ep.title,
                    )
                    if not _narr:
                        continue
                    for _i, _sc in enumerate(_ep_scenes):
                        if str(_sc.audio_mode) == "original":
                            continue  # keep source-audio scenes silent
                        _txt = _narr.get(_i)
                        if _txt and _txt.strip():
                            _sc.narration = _txt.strip()
                            _refined_total += 1
                if _refined_total:
                    _job_log(
                        effective_channel, job_id,
                        f"Recap: per-episode narration refined ({_refined_total} scene(s))",
                    )
                    _emit_render_event(
                        channel_code=effective_channel, job_id=job_id,
                        event="recap.narration.refined", level="INFO",
                        message=f"Per-episode narration refined ({_refined_total} scene(s))",
                        step="render.recap", context={"scenes_refined": _refined_total},
                    )
            except Exception as _pen_exc:
                logger.warning(
                    "recap: per-episode narration refinement failed (non-fatal): %s", _pen_exc,
                )

        update_recap_plan(job_id, recap_plan.to_json())
        # Build the chronological scene list now (pure) so the plan.ready event
        # can ship full per-scene timing for the editor-style timeline view.
        scored = _scored_from_recap_plan(recap_plan)
        if not scored:
            raise RuntimeError("Recap: plan produced no valid scenes")
        total_parts = len(scored)
        _n_original = sum(1 for s in scored if s.get("audio_mode") == "original")
        # Per-scene blocks (part_no order = render order) for the NLE timeline:
        # each carries its duration → the FE lays them out proportionally.
        _scene_blocks = [
            {
                "n": i, "ep": int(s.get("episode_index", 0)), "act": int(s.get("act_index", 0)),
                "start": round(float(s.get("start", 0.0)), 1), "end": round(float(s.get("end", 0.0)), 1),
                "dur": round(float(s.get("duration", 0.0)), 1),
                "title": str(s.get("ai_title", "") or ""),
                "mode": str(s.get("audio_mode", "narrate")),
                "climax": bool(s.get("is_climax", False)),
            }
            for i, s in enumerate(scored, start=1)
        ]
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="recap.plan.ready",
            level="INFO",
            message=(
                f"Recap plan: {recap_plan.episode_count()} episode(s), "
                f"{len(recap_plan.acts)} acts, {recap_plan.scene_count()} scenes "
                f"({_n_original} original-audio)"
            ),
            step="render.recap", context={
                "episodes": [
                    {"title": ep.title, "acts": len(ep.acts), "scenes": ep.scene_count()}
                    for ep in recap_plan.episodes
                ],
                "acts": [{"title": a.title, "beat": a.beat, "scenes": len(a.scenes)} for a in recap_plan.acts],
                # Full per-scene blocks (timing + mode) for the editor timeline.
                "scenes": _scene_blocks,
                # Back-compat: flat per-scene audio mode in part order.
                "scene_modes": [b["mode"] for b in _scene_blocks],
                "original_audio_scenes": _n_original,
                "total_target_sec": recap_plan.total_target_sec,
                # Story Model — what the AI understood before it edited (R7 two-pass).
                # to_public_dict() is JSON-safe (Character/StoryBeat entities → dicts).
                "story_summary": recap_plan.story_summary,
                "story_model": recap_plan.story.to_public_dict(),
                # Editorial Blueprint — HOW the AI planned to tell it (R7.3 pass-2).
                "editorial": recap_plan.editorial.to_public_dict(),
            },
        )

        # N5 — coverage check: does the plan span the whole film, or did the AI
        # cluster scenes in one part / leave a huge gap? Diagnostic only (emit
        # event + log) so the operator can see a weak plan; never blocks render.
        try:
            _cov = _check_recap_coverage(recap_plan, video_duration)
            _emit_render_event(
                channel_code=effective_channel, job_id=job_id, event="recap.coverage",
                level=("WARNING" if _cov["weak"] else "INFO"),
                message=(
                    f"Recap coverage: span={_cov['span_pct']:.0f}% of film, "
                    f"largest gap={_cov['max_gap_pct']:.0f}%"
                    + (" — weak (scenes clustered / big gap)" if _cov["weak"] else "")
                ),
                step="render.recap", context=_cov,
            )
            if _cov["weak"]:
                _job_log(
                    effective_channel, job_id,
                    f"recap_coverage_warning span={_cov['span_pct']:.0f}% max_gap={_cov['max_gap_pct']:.0f}% "
                    f"— AI plan may not cover the whole film",
                    kind="warning",
                )
        except Exception:
            pass

        # 4. Render each scene as a "part" (reuse the clips render loop) ------
        # R6: force subtitle ON for "original audio" scenes so the viewer can
        # follow the raw source dialogue even when global subtitles are off.
        _add_sub = bool(getattr(payload, "add_subtitle", False))
        subtitle_enabled_by_idx = {
            i: (_add_sub or str(scored[i - 1].get("audio_mode", "")) == "original")
            for i in range(1, total_parts + 1)
        }
        try:
            _src_stat_for_motion = source_path.stat()
        except Exception:
            _src_stat_for_motion = None
        try:
            _user_req = int(getattr(payload, "max_parallel_parts", 0) or 0)
            _hw_cap = max(1, _MAX_CONCURRENT_JOBS)
            # Máy có GPU: giới hạn worker theo số phiên NVENC (mặc định 3).
            # Worker vượt giới hạn chỉ ngồi block trên NVENC_SEMAPHORE — tốn
            # thread/RAM và tranh CPU với motion pass mà không thêm throughput.
            # Đồng bộ với cách clips path (render_pipeline) tính hw_cap ở chế
            # độ GPU; máy không có NVENC giữ nguyên công thức cũ.
            if nvenc_available():
                _hw_cap = min(_hw_cap, max(1, int(os.getenv("NVENC_MAX_SESSIONS", "3"))))
            max_workers = max(1, min(_user_req, _hw_cap)) if _user_req > 0 else _hw_cap
        except Exception:
            max_workers = 1
        # P1 (perf): recap was hardcoding ffmpeg_threads=1 → each per-scene encode
        # ran single-threaded, leaving most CPU cores idle (~31% on a 16-core box)
        # on the CPU/libx264 path. Use the shared helper to give each parallel
        # part a fair thread slice (min(8, cores // workers)) so the box is
        # saturated. Output is byte-for-byte the same quality (threads only affect
        # speed, not the codec/crf).
        try:
            _ffmpeg_threads = resolve_ffmpeg_threads(max_workers)
        except Exception:
            _ffmpeg_threads = 1

        # R6 fix: scenes are INTERNAL intermediates, not deliverables. Render them
        # into a temp dir so the per-part finalize (which writes
        # output_dir/<clip_name>.mp4) does NOT scatter 26 named scene files into
        # the user's save folder. Only the assembled episode video(s) land in the
        # real output_dir (step 5). The scenes dir is cleaned up after QA.
        scenes_dir = work_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        _part_ctx = PartRenderContext(
            job_id=job_id, effective_channel=effective_channel, total_parts=total_parts,
            retry_count=retry_count, work_dir=work_dir, output_dir=scenes_dir,
            source_path=source_path, source=source, output_stem=_output_stem,
            payload=payload, existing_parts={int(x["part_no"]): x for x in list_job_parts(job_id)},
            target_platform=target_platform, tuned=tuned, ffmpeg_threads=_ffmpeg_threads,
            cancel_registry=cancel_registry, src_stat_for_motion=_src_stat_for_motion,
            full_srt=full_srt, full_srt_available=full_srt_available,
            subtitle_enabled_by_idx=subtitle_enabled_by_idx, subtitle_cutoff=0,
            voice_audio_path=None, mv_market=_setup.mv_market, mv_cfg=_setup.mv_cfg,
            hook_apply_enabled=False, hook_applied_text="", hook_score=0.0,
            hook_overlay_enabled=False, dna_clean_visual=_pre.dna_clean_visual,
            normalized_text_layers=[], voice_part_tts_attempts=[], voice_mix_ok=[],
            sub_translate_attempts=[], sub_translate_partial=[], sub_translate_clean=[],
            sub_translate_failed_parts=[], recovery_notes=[], render_plan=None,
        )
        _loop = run_render_loop(
            part_ctx=_part_ctx, scored=scored, source=source, total_parts=total_parts,
            max_workers=max_workers, normalized_text_layers=[],
            effective_channel=effective_channel, job_id=job_id, set_stage_fn=_set_stage,
            job_semaphore=JOB_SEMAPHORE, render_active_lock=_render_active_lock,
            render_active_count=_render_active_count,
        )
        failed_parts = _loop.failed_parts

        # 5. Assemble: one output video PER EPISODE (Tập) --------------------
        _n_eps = recap_plan.episode_count()
        _set_stage(JobStage.WRITING_REPORT, 90, f"Assembling recap ({_n_eps} episode(s))")
        _episodes = _assemble_recap_episodes(
            job_id=job_id, effective_channel=effective_channel, payload=payload,
            output_dir=output_dir, output_stem=_output_stem, source_path=source_path,
            scored=scored, recap_plan=recap_plan,
        )
        if not _episodes:
            raise RuntimeError("Recap: assembly produced no output")

        # 6. QA each delivered episode (Sacred #8) — keep the ones that pass --
        _outputs: list[dict] = []
        _failed_eps: list[int] = []
        for _ep in _episodes:
            # 2026-07-02: expected_duration was previously omitted, so a
            # concat-broken episode (container said 15,134s vs ~295s planned)
            # sailed through QA on the "has video + has audio + >10KB" checks
            # alone. Passing the assembler's summed input duration arms the
            # duration-tolerance check in _validate_render_output.
            _exp_dur = float(_ep.get("expected_duration") or 0.0)
            _qa = _validate_render_output(
                Path(_ep["path"]),
                expected_duration=_exp_dur if _exp_dur > 0 else None,
                expect_audio=True,
            )
            if not _qa["ok"]:
                _failed_eps.append(int(_ep["episode_index"]))
                _job_log(
                    effective_channel, job_id,
                    f"recap_episode_qa_failed ep={_ep['episode_index'] + 1}: {_qa.get('error')}",
                    kind="warning",
                )
                continue
            _ep["duration"] = float(_qa["metadata"].get("duration") or 0.0)
            _outputs.append(_ep)
        if not _outputs:
            raise RuntimeError("Recap: every episode failed QA")

        # A3: episodes are assembled + validated — the per-scene intermediates in
        # scenes_dir are no longer needed. Remove them so they don't accumulate.
        # (On a total failure above we KEEP them for debugging — this only runs
        # once at least one episode is delivered.)
        try:
            import shutil as _shutil
            _shutil.rmtree(scenes_dir, ignore_errors=True)
            _job_log(effective_channel, job_id, "recap: cleaned per-scene intermediates", kind="debug")
        except Exception:
            pass

        # 7. Terminal result_json + DONE -------------------------------------
        # N episode outputs. Episode 1 is "best" by convention; rank follows
        # episode order. Every entry carries the Sacred #1 keys.
        _output_entries: list[dict] = []
        for _rank, _ep in enumerate(_outputs, start=1):
            _is_best = _rank == 1
            _ep_no = int(_ep["episode_index"]) + 1
            _dur_ep = float(_ep.get("duration") or 0.0)
            _title = _ep.get("title") or f"Recap — Tập {_ep_no}"
            _output_entries.append({
                "part_no": _rank, "path": _ep["path"], "output_file": _ep["path"],
                "output_path": _ep["path"], "title": _title,
                "clip_name": f"recap_ep{_ep_no:02d}", "ai_title": _title,
                "episode_no": _ep_no, "start_sec": 0.0, "end_sec": _dur_ep,
                "duration": _dur_ep, "viral_score": 100.0,
                # Sacred Contract #1 keys — present on EVERY output.
                "output_rank_score": float(max(1, 101 - _rank)),
                "is_best_output": _is_best, "is_best_clip": _is_best,
            })
        _total_dur = sum(float(e.get("duration") or 0.0) for e in _output_entries)
        _result = {
            "outputs": _output_entries,
            "render_format": "recap",
            "story_summary": recap_plan.story_summary,
            "story_model": recap_plan.story.to_public_dict(),
            "editorial": recap_plan.editorial.to_public_dict(),
            "recap_plan": recap_plan.to_json(),
            "recap_episodes_count": len(_output_entries),
            "output_ranking": [dict(e, output_rank=i) for i, e in enumerate(_output_entries, start=1)],
            "best_clip": _output_entries[0],
            "successful_outputs_count": len(_output_entries),
            "failed_outputs_count": len(failed_parts) + len(_failed_eps),
            "failed_parts": [int(f.get("part_no", 0)) for f in failed_parts],
            "failed_episodes": _failed_eps,
            "selected_segments_count": total_parts,
            "is_partial_success": bool(failed_parts) or bool(_failed_eps),
            "ai_director": {"enabled": False},
            "recap_acts": [
                {"title": a.title, "beat": a.beat, "scenes": len(a.scenes)} for a in recap_plan.acts
            ],
        }
        upsert_job(
            job_id, "render", effective_channel, "completed", payload.model_dump(), _result,
            stage=JobStage.DONE, progress_percent=100,
            message=f"Recap complete: {len(_output_entries)} episode(s), {recap_plan.scene_count()} scenes, {_total_dur:.0f}s",
        )
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="render.complete",
            level="INFO", message="Recap render complete", step="render.complete",
            context={"duration_sec": _total_dur, "scenes": total_parts,
                     "episodes": len(_output_entries), "acts": len(recap_plan.acts)},
        )
        _job_log(
            effective_channel, job_id,
            f"Recap DONE: {len(_output_entries)} episode(s) ({_total_dur:.0f}s total)",
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


def _assemble_recap_episodes(
    *, job_id, effective_channel, payload, output_dir, output_stem,
    source_path, scored, recap_plan,
) -> list[dict]:
    """R6: assemble ONE output video per EPISODE. Within each episode, insert an
    act title card before the first scene of each act, then concat
    [card, scenes…] → {output_stem}_recap_epNN.mp4. Returns a list of
    {episode_index, title, path} for the episodes that produced a file (partial
    success: an episode whose clips all failed is skipped, not fatal)."""
    parts = {int(p["part_no"]): p for p in list_job_parts(job_id)}
    width, height = resolve_target_dimensions(str(getattr(payload, "aspect_ratio", "16:9") or "16:9"))
    try:
        fps = float(getattr(payload, "output_fps", 0) or 0) or 30.0
    except Exception:
        fps = 30.0

    card_dir = TEMP_DIR / job_id / "recap_cards"
    card_dir.mkdir(parents=True, exist_ok=True)

    # Group the rendered scene parts by episode, preserving order.
    n_eps = recap_plan.episode_count()
    single = n_eps <= 1
    by_episode: dict[int, list[tuple[int, dict]]] = {}
    for idx, seg in enumerate(scored, start=1):
        by_episode.setdefault(int(seg.get("episode_index", 0)), []).append((idx, seg))

    ep_titles = {i: (ep.title or "") for i, ep in enumerate(recap_plan.episodes)}
    out_episodes: list[dict] = []
    _used_names: set[str] = set()

    for ep_i in sorted(by_episode.keys()):
        ordered_clips: list[str] = []
        _seen_acts: set[int] = set()
        for idx, seg in by_episode[ep_i]:
            act_i = int(seg.get("act_index", 0))
            if act_i not in _seen_acts:
                _seen_acts.add(act_i)
                _card = card_dir / f"act_{act_i:02d}.mp4"
                if make_act_title_card(
                    source_video=str(source_path), at_sec=float(seg.get("start", 0.0)),
                    title_text=str(seg.get("act_title") or f"Act {act_i + 1}"),
                    out_path=str(_card), width=width, height=height, fps=fps,
                ):
                    ordered_clips.append(str(_card))
            _row = parts.get(idx)
            _file = (_row or {}).get("output_file") if _row else None
            if _file and Path(_file).exists() and Path(_file).stat().st_size > 0:
                ordered_clips.append(str(_file))

        if not ordered_clips:
            continue

        # Filename = "<film> - <AI chapter/episode title>.mp4" (FS-safe). Falls
        # back to "<film> - Tập N" when the AI left the title empty, and to
        # "<film> - Recap" for a single untitled episode. Collisions get a numeric
        # suffix so two episodes never overwrite each other.
        _ep_title = (ep_titles.get(ep_i) or "").strip()
        if _ep_title:
            _label = _ep_title
        elif single:
            _label = "Recap"
        else:
            _label = f"Tập {ep_i + 1}"
        _base = _safe_filename(f"{output_stem} - {_label}") or f"{output_stem}_recap_ep{ep_i + 1:02d}"
        _name = _base
        _n = 2
        while _name.lower() in _used_names or (Path(output_dir) / f"{_name}.mp4").exists():
            _name = f"{_base} ({_n})"
            _n += 1
        _used_names.add(_name.lower())
        _out = Path(output_dir) / f"{_name}.mp4"
        _res = concat_clips(ordered_clips, str(_out), width=width, height=height, fps=fps)
        if not _res.get("ok"):
            _job_log(effective_channel, job_id, f"recap_episode_concat_failed ep={ep_i + 1}", kind="warning")
            continue
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="recap.concat.done",
            level="INFO", message=f"Recap episode {ep_i + 1} assembled ({_res.get('method')})",
            step="render.recap",
            context={"episode": ep_i + 1, "clips": len(ordered_clips), "method": _res.get("method")},
        )
        out_episodes.append({
            "episode_index": ep_i,
            "title": ep_titles.get(ep_i, "") or (None if single else f"Tập {ep_i + 1}"),
            "path": str(_out),
            # Sum of input-clip durations (probed by concat_clips) — QA uses it
            # to reject a broken assembly whose container duration drifted.
            "expected_duration": float(_res.get("expected_duration") or 0.0),
        })

    return out_episodes
