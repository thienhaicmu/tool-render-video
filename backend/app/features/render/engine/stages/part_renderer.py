"""
Per-part render logic extracted from run_render_pipeline() inner closures (Phase A-3).
PartRenderContext carries all closure-captured state.

After Sprint 6.D-2.x decomposition, this file is a thin orchestrator
skeleton: process_one_part owns the frozen JobPartStage state-machine
transitions and delegates layer work to 7 stages/* helpers. The
imports below reflect that smaller surface — most service-level helpers
that the original process_one_part used directly now live inside the
extracted stage modules. See docs/review/SPRINT_6D_PLAN.md.
"""
from __future__ import annotations

import logging
import os
import time

# Batch 10Q: JobPartStage was previously imported here for the 3 inline
# upsert_job_part calls. Those moved to part_db.py — every reference to
# the enum in this file is now in docstrings / comments only.
from app.features.render.engine.pipeline.qa_pipeline import (
    _resume_output_valid,
    _validate_render_output,
)
from app.features.render.engine.pipeline.render_events import _job_log
# Batch 10Q: ``upsert_job_part`` is no longer imported here — the 3 stage
# transitions this file owned (resume-skip DONE, WAITING, RENDERING)
# moved to part_db.py. Other stage helpers (part_done, part_asset_planner,
# part_cut) still import upsert_job_part directly for their own
# Sacred Contract #5 transitions; those are out of scope for this batch.
from app.features.render.engine.encoder.ffmpeg_helpers import set_thread_cancel_event

logger = logging.getLogger("app.render")

_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
# Sprint 7.2 (2026-06-05): FEATURE_BASE_CLIP_VALIDATION_ARTIFACT removed —
# see render_pipeline.py for the closure rationale.
# Sprint 7.4 (2026-06-05): raw_part skip flag — see render_pipeline.py.
_FEATURE_RAW_PART_SKIP: bool = os.getenv("FEATURE_RAW_PART_SKIP", "0") == "1"
# Sprint 7.8 (2026-06-05): motion-aware extension flag — see render_pipeline.py.
_FEATURE_RAW_PART_SKIP_MOTION_AWARE: bool = os.getenv("FEATURE_RAW_PART_SKIP_MOTION_AWARE", "0") == "1"


# Sprint 6.D-2.1: PartRenderContext dataclass extracted to a dedicated
# module. Re-exported here so existing external consumers
# (pipeline_render_loop.py, render_pipeline.py) keep their existing
# import paths working unchanged.
from app.features.render.engine.stages.part_render_context import PartRenderContext
# Sprint 6.D-2.2: prepare_part_assets extracted to a dedicated module.
# Re-exported here so the internal caller (process_one_part below)
# keeps using `prepare_part_assets(...)` via the bare reference.
from app.features.render.engine.stages.part_asset_planner import prepare_part_assets
# Sprint 6.D-2.3: CUT stage (post-WAITING / pre-RENDERING block) extracted
# to a dedicated module. Re-exported so the internal caller below keeps
# the bare reference; CutStageResult is consumed only inside process_one_part.
from app.features.render.engine.stages.part_cut import CutStageResult, run_cut_stage  # noqa: F401 (CutStageResult re-exported)
# Sprint 6.D-2.4: RENDER pre-flight (encoding params + progress-timer
# thread + cache key + PartExecutionPlan + CameraStrategy + feature-flag
# warning) extracted to a dedicated module. The encode-progress thread
# is STARTED inside run_render_preflight and the caller is responsible
# for encode_stop.set() + encode_timer.join() after the FFmpeg render
# completes. Plan Â§3.2 phase 2.4 was re-scoped here because the original
# TRANSCRIBE scope was already absorbed into prepare_part_assets (2.2).
from app.features.render.engine.stages.part_render_setup import (
    RenderPreflightResult,  # noqa: F401 (re-exported)
    run_render_preflight,
)
# Sprint 6.D-2.5a: FFmpeg encode core (base_clip + overlay composite +
# render_part_smart fallback + encode-thread lifecycle close + motion-crop
# recovery emit + visual_finish_applied emit) extracted to a dedicated
# module. The encode_stop.set() + encode_timer.join() pair that closes
# the encode-progress thread (started in run_render_preflight) lives
# inside run_render_encode's finally block.
from app.features.render.engine.stages.part_render_encode import (
    RenderEncodeResult,  # noqa: F401 (re-exported)
    run_render_encode,
)
# Sprint 6.D-2.5d: Per-part DONE block (quality intelligence + cover
# frame + JobPartStage.DONE terminal upsert + cleanup + return dict)
# extracted to a dedicated module. The terminal stage transition
# (Sacred Contract #5) moves WITH this helper since it is the natural
# return point of process_one_part.
from app.features.render.engine.stages.part_done import run_part_done
# Sprint 6.D-2.5b: Per-part voice TTS + audio mix block (subtitle and
# translated_subtitle voice paths + mix_narration_audio with atomic
# file swap) extracted to a dedicated module. Side-effect-only —
# mutates ctx.voice_part_tts_attempts / voice_mix_ok lists,
# part_manifest.narration_path, and overwrites final_part with the
# mixed video.
from app.features.render.engine.stages.part_voice_mix import run_part_voice_mix
# Sprint 6.D-2.5c (CRITICAL): Per-part finalize block (micro-pacing +
# intro/outro/logo + duration math + scoring + Sacred Contract #8
# qa_pipeline validation surface). Raises RuntimeError on validation
# failure — the per-part worker in pipeline_render_loop catches it
# and records the failure in result_json[failed_parts].
from app.features.render.engine.stages.part_render_finalize import run_part_finalize
# Sprint 6.D-2.6 / Batch 10P (MT-4 phase A): per-part filesystem path
# derivation (raw_part / srt_part / ass_part / translated_srt_part /
# final_part / part_name) extracted to a pure data helper.
from app.features.render.engine.stages.segment_metadata import build_part_paths  # noqa: F401
# Batch 10Q (MT-4 phase B): per-part DB-write facade. Centralizes the
# three Sacred Contract #5 stage transitions that ``process_one_part``
# emits inline (WAITING / RENDERING / resume-skip DONE). Other
# transitions (CUTTING, TRANSCRIBING, the per-part terminal DONE) live
# inside their respective stage helpers — part_cut, part_asset_planner,
# part_done — and stay there because they couple to stage-local state.
from app.features.render.engine.stages.part_db import (
    mark_part_rendering,
    mark_part_skipped_done,
    mark_part_waiting,
)


def process_one_part(ctx: PartRenderContext, idx: int, seg: dict):
    # Audit MT-4 phase A closure (Batch 10P, 2026-06-06): the six
    # per-part filesystem paths were derived inline here in 22 lines of
    # branching logic. Moved verbatim to segment_metadata.build_part_paths
    # so the path-derivation contract has its own test surface. Bindings
    # below preserve the original local-variable names so the rest of
    # this function stays byte-identical.
    _paths              = build_part_paths(ctx, idx, seg)
    raw_part            = _paths.raw_part
    srt_part            = _paths.srt_part
    ass_part            = _paths.ass_part
    translated_srt_part = _paths.translated_srt_part
    final_part          = _paths.final_part
    part_name           = _paths.part_name
    _variant_type       = str(seg.get("variant_type") or "")
    _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx}/{ctx.total_parts} start", kind="debug")
    import os as _os2
    if _os2.getenv("RENDER_DEBUG_LOG", "0") == "1":
        try:
            import json as _json2
            _meta_path = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_meta.json"
            _meta_data = {
                "part": idx,
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "duration": float(seg.get("duration", 0)),
                "viral_score": float(seg.get("viral_score", 0)),
                "motion_score": float(seg.get("motion_score", 0)),
                "hook_score": float(seg.get("hook_score", 0)),
                "content_type": seg.get("content_type_hint", ""),
                "variant": seg.get("variant_type", ""),
                "files": {
                    "raw": str(raw_part),
                    "srt": str(srt_part),
                    "ass": str(ass_part),
                    "output": str(final_part),
                },
            }
            _meta_path.write_text(_json2.dumps(_meta_data, indent=2), encoding="utf-8")
            logger.debug("debug_artifact segment_meta=%s", _meta_path)
        except Exception as _meta_exc:
            logger.debug("debug_artifact segment_meta_failed part=%d: %s", idx, _meta_exc)

    if ctx.cancel_registry.is_cancelled(ctx.job_id):
        raise ctx.cancel_registry.JobCancelledError()
    _cancel_ev = ctx.cancel_registry.get_event(ctx.job_id)
    if _cancel_ev is not None:
        set_thread_cancel_event(_cancel_ev)

    _existing_part_info = ctx.existing_parts.get(idx, {})
    # Audit FINDING-BR12 closure (Batch 10B 2026-06-06): resume decision is
    # disk-truth, not DB-truth. The ``job_parts.output_file`` column
    # defaults to '' and is sometimes left empty by interrupted writers, so
    # using it as the resume signal would either over-skip (DB stale, file
    # gone) or over-render (DB empty-string, file present). Instead we:
    #   1. Require the DB ``status == 'done'`` flag (cheap precondition)
    #   2. Recompute ``final_part`` from ``output_dir + part_name``
    #      (independent of DB state)
    #   3. Run the SAME ``_validate_render_output`` gate that fresh
    #      renders pass through (T1.2 — Sacred Contract #8 closure;
    #      see below).
    if (
        ctx.payload.resume_from_last
        and ((_existing_part_info.get("status") or "").lower() == "done")
        and final_part.exists()
        and final_part.stat().st_size > 0
    ):
        # T1.2 — Audit 2026-06-08 closure (Batch A V9-A1/V9-G1 — Sacred
        # Contract #8 partial bypass). Previously the resume-skip
        # predicate used only ``_resume_output_valid`` (single ffprobe
        # call asserting duration > 0). That misses 4 of the 5 hard
        # checks in ``_validate_render_output``: size floor 10 KB,
        # video-stream presence, duration tolerance vs the segment's
        # expected duration, and audio-stream presence. A part that
        # "completed" but is truncated, video-streamless, or far off
        # the expected duration could be re-served as DONE on resume.
        # Now resume runs through the SAME QA gate as a fresh render.
        # expect_audio=None: the resume path can't reliably know whether
        # audio was originally required (voice_enabled state may have
        # changed across runs), so missing-audio surfaces as a warning
        # rather than a hard failure — matches the fresh-render policy
        # for legacy callers (see qa_pipeline.py:165-178).
        _resume_qa = _validate_render_output(
            final_part,
            expected_duration=float(seg.get("duration") or 0.0),
            expect_audio=None,
        )
        if _resume_qa.get("ok"):
            # Batch 10Q (MT-4 phase B): the 13-arg inline upsert is now a
            # named facade call — Sacred Contract #5 transition (resume-skip
            # → DONE @ 100) lives in part_db.mark_part_skipped_done.
            mark_part_skipped_done(ctx, idx, _paths, seg)
            _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} skipped: final output already exists", kind="debug")
            return {"idx": idx, "output": str(final_part), "row": None, "skipped": True}
        # QA rejected the cached output — fall through to re-render the
        # part. Log the rejection reason so operators can distinguish a
        # legit re-render from "resume did nothing" in the job log.
        _job_log(
            ctx.effective_channel, ctx.job_id,
            f"Part {idx} resume-skip rejected by QA "
            f"(code={_resume_qa.get('code') or '?'}): "
            f"{_resume_qa.get('error') or 'unknown'} — re-rendering",
            kind="warning",
        )

    # Batch 10Q: first DB write after the resume check — Sacred Contract
    # #5 WAITING @ 5%. The 13-arg inline call moved to part_db.mark_part_waiting.
    mark_part_waiting(ctx, idx, _paths, seg)

    _t_part_start = time.perf_counter()
    _subtitle_ass_ms = 0
    _render_ms = _micro_pacing_ms = _quality_validation_ms = 0

    # Sprint 6.D-2.3: CUT stage (post-WAITING / pre-RENDERING) moved to
    # app.features.render.engine.stages.part_cut.run_cut_stage. All 9 returned
    # fields are aliased back to their original local names so the
    # downstream RENDER block stays byte-for-byte unchanged.
    _cut = run_cut_stage(ctx, idx, seg, raw_part, part_name, final_part)
    _trim_offset         = _cut.trim_offset
    _effective_start     = _cut.effective_start
    _effective_end       = _cut.effective_end
    _force_accurate_cut  = _cut.force_accurate_cut
    _visual_trim         = _cut.visual_trim
    _part_timeline       = _cut.part_timeline
    _part_manifest       = _cut.part_manifest
    _cut_ms              = _cut.cut_ms
    _first_frame_scan_ms = _cut.first_frame_scan_ms

    (_part_assets, _srt_count, _srt_meta,
     _hook_subtitle_formatted, _subtitle_ass_ms) = prepare_part_assets(
        ctx, idx, seg, srt_part, ass_part, translated_srt_part,
        _effective_start, _part_manifest, part_name, final_part,
        raw_part,
    )
    part_subtitle_enabled = _part_assets.subtitle_enabled
    _part_text_layers = list(_part_assets.text_layers)
    _part_text_layers_overlay = list(_part_assets.text_layers_overlay)
    _effective_subtitle_style = _part_assets.subtitle_style
    _hook_overlay_applied_for_part = _part_assets.hook_overlay_applied
    overlay_title = (ctx.payload.title_overlay_text or "").strip() or ctx.source["title"]
    # Batch 10Q: assets ready, encode about to start — Sacred Contract #5
    # RENDERING @ 70%. The 13-arg inline call moved to part_db.mark_part_rendering.
    mark_part_rendering(ctx, idx, _paths, seg)

    # Sprint 6.D-2.4: RENDER pre-flight (encoding params + progress-timer
    # thread + cache key + PartExecutionPlan + CameraStrategy +
    # feature-flag warning) moved to part_render_setup.run_render_preflight.
    # 13 returned fields aliased back to original local names so the
    # downstream FFmpeg core block stays byte-for-byte unchanged.
    _preflight = run_render_preflight(
        ctx, idx, seg, part_name, str(final_part),
        _effective_start, _trim_offset, _visual_trim,
        _force_accurate_cut, part_subtitle_enabled,
    )
    _vf_ct                = _preflight.vf_ct
    _vf_crf_delta         = _preflight.vf_crf_delta
    _part_video_crf       = _preflight.part_video_crf
    _vf_bitrate_profile   = _preflight.vf_bitrate_profile
    _vf_subtitle_bump     = _preflight.vf_subtitle_bump
    _encode_stop          = _preflight.encode_stop
    _encode_timer         = _preflight.encode_timer
    _t_encode             = _preflight.t_encode
    _t_render             = _preflight.t_render
    _motion_ck            = _preflight.motion_ck
    _motion_crop_fallback = _preflight.motion_crop_fallback
    _part_plan            = _preflight.part_plan
    _camera_strategy      = _preflight.camera_strategy

    # Sprint 6.D-2.5a: FFmpeg encode core (base_clip + overlay composite +
    # render_part_smart fallback + encode-thread lifecycle close + motion-crop
    # recovery + visual_finish_applied) moved to part_render_encode.run_render_encode.
    # The single returned field is aliased back to its original local name
    # so the downstream voice/mix/finalize blocks stay byte-for-byte unchanged.
    _encode = run_render_encode(
        ctx, idx, seg, raw_part, ass_part, final_part,
        part_subtitle_enabled, overlay_title,
        _part_manifest, _part_timeline,
        _part_text_layers, _part_text_layers_overlay,
        _effective_subtitle_style, _preflight,
    )
    _render_ms = _encode.render_ms
    # Sprint 6.D-2.5b: Voice TTS + audio mix block (subtitle and
    # translated_subtitle paths + mix_narration_audio with atomic file
    # swap) moved to part_voice_mix.run_part_voice_mix. Side-effect-only:
    # mutates ctx.voice_part_tts_attempts / voice_mix_ok, manifest.narration_path,
    # and overwrites final_part in-place when narration was generated.
    run_part_voice_mix(
        ctx, idx, seg, srt_part, translated_srt_part, final_part, _part_manifest,
    )
    # Sprint 6.D-2.5c: Finalize block (micro-pacing + intro/outro/logo +
    # duration math + scoring + Sacred Contract #8 qa_pipeline validation)
    # moved to part_render_finalize.run_part_finalize. The helper raises
    # RuntimeError on validation failure — propagates up to the per-part
    # worker in pipeline_render_loop which records the failure.
    run_part_finalize(
        ctx, idx, seg, srt_part, ass_part, final_part,
        part_subtitle_enabled, _hook_overlay_applied_for_part,
        _hook_subtitle_formatted, _srt_count,
        _trim_offset, _effective_start, _part_timeline,
        _t_part_start, _cut_ms, _first_frame_scan_ms, _subtitle_ass_ms,
        _preflight, _encode,
    )
    # Sprint 6.D-2.5d: Per-part DONE block (quality intelligence +
    # cover frame + JobPartStage.DONE terminal upsert + cleanup +
    # return dict) moved to part_done.run_part_done. The function
    # returns the dict shape that process_one_part has always handed
    # back to its caller (pipeline_render_loop.run_render_loop).
    return run_part_done(
        ctx, idx, seg, raw_part, srt_part, ass_part, final_part,
        part_name, _srt_meta, _variant_type, part_subtitle_enabled,
    )

