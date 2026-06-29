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
from app.features.render.engine.encoder.ffmpeg_helpers import resolve_target_dimensions
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


def _scored_from_recap_plan(recap_plan) -> list[dict]:
    """Flatten RecapPlan acts→scenes into the chronological `scored` shape the
    render loop / part_renderer expects. Neutral scores (recap order is
    chronological, not viral-ranked). `act_index` rides along so the finalize
    step can group scenes back into acts for title cards."""
    out: list[dict] = []
    n_acts = len(recap_plan.acts)
    for act_i, act in enumerate(recap_plan.acts):
        for scene in act.scenes:
            start = float(scene.start)
            end = float(scene.end)
            if end <= start:
                continue
            # R3: compose the per-scene DIRECTOR'S INTENT — act position + the
            # plan's narration_intent — so the narrator tells one continuous
            # story across scenes (not isolated per-clip blurbs).
            _intent = (scene.narration_intent or "").strip()
            _act_tag = f"Act {act_i + 1}/{n_acts}"
            if act.title:
                _act_tag += f" — {act.title}"
            if act.beat:
                _act_tag += f" ({act.beat})"
            _editorial = f"[Recap {_act_tag}] {_intent}".strip() if (_intent or act.title) else ""
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
                "source": "recap",
                "content_type_hint": "",
                "is_climax": bool(scene.is_climax),
                "act_index": act_i,
                "act_title": act.title or "",
                "act_beat": act.beat or "",
            })
    return out


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

        # 3. Recap scene selection (AI) --------------------------------------
        _set_stage(JobStage.SEGMENT_BUILDING, 30, "AI selecting recap scenes + acts")
        from app.core import config as _cfg
        from app.features.render.engine.pipeline.llm_stage import _resolve_api_key as _resolve_llm_api_key
        _provider = (getattr(payload, "ai_provider", "") or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
        _api_key, _ = _resolve_llm_api_key(payload, _provider)
        recap_plan = select_recap_plan(
            provider=_provider, srt_content=_ai_srt, video_duration=video_duration,
            target_language=(getattr(payload, "voice_language", "") or "vi-VN"),
            tone=(getattr(payload, "rewrite_tone", "") or ""),
            api_key=_api_key, model=getattr(payload, "llm_model", None),
        )
        if recap_plan is None or not recap_plan.acts:
            raise RuntimeError("Recap: AI returned no usable plan")
        update_recap_plan(job_id, recap_plan.to_json())
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="recap.plan.ready",
            level="INFO", message=f"Recap plan: {len(recap_plan.acts)} acts, {recap_plan.scene_count()} scenes",
            step="render.recap", context={
                "acts": [{"title": a.title, "beat": a.beat, "scenes": len(a.scenes)} for a in recap_plan.acts],
                "total_target_sec": recap_plan.total_target_sec,
            },
        )

        scored = _scored_from_recap_plan(recap_plan)
        if not scored:
            raise RuntimeError("Recap: plan produced no valid scenes")
        total_parts = len(scored)

        # 4. Render each scene as a "part" (reuse the clips render loop) ------
        subtitle_enabled_by_idx = {
            i: bool(getattr(payload, "add_subtitle", False)) for i in range(1, total_parts + 1)
        }
        try:
            _src_stat_for_motion = source_path.stat()
        except Exception:
            _src_stat_for_motion = None
        try:
            _user_req = int(getattr(payload, "max_parallel_parts", 0) or 0)
            _hw_cap = max(1, _MAX_CONCURRENT_JOBS)
            max_workers = max(1, min(_user_req, _hw_cap)) if _user_req > 0 else _hw_cap
        except Exception:
            max_workers = 1

        _part_ctx = PartRenderContext(
            job_id=job_id, effective_channel=effective_channel, total_parts=total_parts,
            retry_count=retry_count, work_dir=work_dir, output_dir=output_dir,
            source_path=source_path, source=source, output_stem=_output_stem,
            payload=payload, existing_parts={int(x["part_no"]): x for x in list_job_parts(job_id)},
            target_platform=target_platform, tuned=tuned, ffmpeg_threads=1,
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

        # 5. Assemble: act cards + scene clips → ONE long video --------------
        _set_stage(JobStage.WRITING_REPORT, 90, "Assembling recap video")
        _final_path = _assemble_recap(
            job_id=job_id, effective_channel=effective_channel, payload=payload,
            output_dir=output_dir, output_stem=_output_stem, source_path=source_path,
            scored=scored, recap_plan=recap_plan,
        )
        if not _final_path:
            raise RuntimeError("Recap: assembly produced no output")

        # 6. QA the single delivered output (Sacred #8) ----------------------
        _qa = _validate_render_output(Path(_final_path), expect_audio=True)
        if not _qa["ok"]:
            raise RuntimeError(f"Recap output failed QA: {_qa.get('error')}")
        _dur = float(_qa["metadata"].get("duration") or 0.0)

        # 7. Terminal result_json + DONE -------------------------------------
        _output_entry = {
            "part_no": 1, "path": _final_path, "output_file": _final_path,
            "output_path": _final_path, "title": source.get("title") or "Recap",
            "clip_name": "recap", "ai_title": "Recap", "start_sec": 0.0,
            "end_sec": _dur, "duration": _dur, "viral_score": 100.0,
            # Sacred Contract #1 keys (one output, it is the best by definition).
            "output_rank_score": 100.0, "is_best_output": True, "is_best_clip": True,
        }
        _result = {
            "outputs": [_output_entry],
            "render_format": "recap",
            "recap_plan": recap_plan.to_json(),
            "output_ranking": [dict(_output_entry, output_rank=1)],
            "best_clip": _output_entry,
            "successful_outputs_count": 1,
            "failed_outputs_count": len(failed_parts),
            "failed_parts": [int(f.get("part_no", 0)) for f in failed_parts],
            "selected_segments_count": total_parts,
            "is_partial_success": bool(failed_parts),
            "ai_director": {"enabled": False},
            "recap_acts": [
                {"title": a.title, "beat": a.beat, "scenes": len(a.scenes)} for a in recap_plan.acts
            ],
        }
        upsert_job(
            job_id, "render", effective_channel, "completed", payload.model_dump(), _result,
            stage=JobStage.DONE, progress_percent=100,
            message=f"Recap complete: {recap_plan.scene_count()} scenes, {_dur:.0f}s",
        )
        _emit_render_event(
            channel_code=effective_channel, job_id=job_id, event="render.complete",
            level="INFO", message="Recap render complete", step="render.complete",
            context={"duration_sec": _dur, "scenes": total_parts, "acts": len(recap_plan.acts)},
        )
        _job_log(effective_channel, job_id, f"Recap DONE: {_final_path} ({_dur:.0f}s)")
    finally:
        try:
            unregister_job_log_dir(job_id)
        except Exception:
            pass
        try:
            close_thread_conn()
        except Exception:
            pass


def _assemble_recap(
    *, job_id, effective_channel, payload, output_dir, output_stem,
    source_path, scored, recap_plan,
) -> Optional[str]:
    """Build act title cards, then concat [card, scenes…] per act into 1 video."""
    # Map rendered scene files from the DB (output_file column) by part order.
    parts = {int(p["part_no"]): p for p in list_job_parts(job_id)}
    width, height = resolve_target_dimensions(str(getattr(payload, "aspect_ratio", "16:9") or "16:9"))
    try:
        fps = float(getattr(payload, "output_fps", 0) or 0) or 30.0
    except Exception:
        fps = 30.0

    card_dir = TEMP_DIR / job_id / "recap_cards"
    card_dir.mkdir(parents=True, exist_ok=True)
    ordered_clips: list[str] = []
    _seen_acts: set[int] = set()

    for idx, seg in enumerate(scored, start=1):
        act_i = int(seg.get("act_index", 0))
        # One title card before the first scene of each act.
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
        return None

    _out = Path(output_dir) / f"{output_stem}_recap.mp4"
    _res = concat_clips(ordered_clips, str(_out), width=width, height=height, fps=fps)
    if not _res.get("ok"):
        return None
    _emit_render_event(
        channel_code=effective_channel, job_id=job_id, event="recap.concat.done",
        level="INFO", message=f"Recap assembled ({_res.get('method')})",
        step="render.recap", context={"clips": len(ordered_clips), "method": _res.get("method")},
    )
    return str(_out)
