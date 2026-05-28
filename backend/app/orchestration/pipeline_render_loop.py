"""
pipeline_render_loop.py — FFmpeg encode loop extracted from run_render_pipeline().

Encapsulates the JOB_SEMAPHORE acquire/release, worker throttle, per-part
sequential/parallel dispatch, and part-failure handling.

Phase A-7 extraction.  Frozen contracts unchanged:
  - part status names: QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
  - _emit_render_event call shape unchanged
  - WebSocket event field shape unchanged
"""
from __future__ import annotations

import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from app.core.stage import JobStage, JobPartStage
from app.orchestration.qa_pipeline import (
    _failed_part_progress,
    _render_part_failure_detail,
)
from app.orchestration.render_events import _emit_render_event, _job_log
from app.orchestration.stages.part_renderer import (
    PartRenderContext,
    process_one_part as _run_part,
)
from app.services import cancel_registry
from app.services.db import upsert_job_part
from app.services.render_engine import resolve_ffmpeg_threads


@dataclass
class RenderLoopResult:
    outputs: list
    rows: list
    failed_parts: list


def run_render_loop(
    part_ctx: PartRenderContext,
    scored: list,
    source: dict,
    total_parts: int,
    max_workers: int,
    normalized_text_layers: list,
    effective_channel: str,
    job_id: str,
    set_stage_fn: Callable,
    job_semaphore: threading.Semaphore,
    render_active_lock: threading.Lock,
    render_active_count: list,
) -> RenderLoopResult:
    """Acquire semaphore, throttle workers, run the sequential/parallel render loop.

    part_ctx.ffmpeg_threads is finalized here after contention-based throttling.
    Shared mutable lists (recovery_notes, voice_mix_ok, etc.) in part_ctx are
    updated in-place by process_one_part() — callers see the changes via the
    original list references they passed during PartRenderContext construction.
    """
    job_semaphore.acquire()
    with render_active_lock:
        render_active_count[0] += 1
        _render_slot = render_active_count[0]
    try:
        if _render_slot > 1:
            max_workers = max(1, max_workers // _render_slot)
            _job_log(
                effective_channel, job_id,
                f"Throttling to {max_workers} worker(s) — {_render_slot} concurrent render(s) active",
                kind="info",
            )
        _ffmpeg_threads = resolve_ffmpeg_threads(max_workers)
        part_ctx.ffmpeg_threads = _ffmpeg_threads
        _job_log(
            effective_channel, job_id,
            f"ffmpeg_threads={_ffmpeg_threads} cpu_total={os.cpu_count() or 4} max_workers={max_workers}",
        )

        outputs: list = []
        rows: list = []
        completed_parts = 0
        failed_parts: list = []
        set_stage_fn(
            JobStage.RENDERING_PARALLEL if max_workers > 1 else JobStage.RENDERING,
            30,
            f"Rendering parts 0/{total_parts}",
        )
        _t_render_loop = time.perf_counter()
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.ffmpeg.start",
            level="INFO",
            message="Running ffmpeg render",
            step="render.ffmpeg",
            context={"total_parts": total_parts, "workers": max_workers},
        )
        if normalized_text_layers:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.text_layers.apply",
                level="INFO",
                message="Applying text overlay layers during render",
                step="render.text_layers",
                context={"layer_count": len(normalized_text_layers), "total_parts": total_parts},
            )

        if max_workers == 1:
            for idx, seg in enumerate(scored, start=1):
                if cancel_registry.is_cancelled(job_id):
                    raise cancel_registry.JobCancelledError()
                try:
                    result = _run_part(part_ctx, idx, seg)
                    if result["output"]:
                        outputs.append(result["output"])
                    if result["row"]:
                        rows.append(result["row"])
                except Exception as part_err:
                    failure_detail = _render_part_failure_detail(idx, part_err)
                    failed_parts.append(failure_detail)
                    upsert_job_part(
                        job_id,
                        idx,
                        f"{source['slug']}_part_{idx:03d}.mp4",
                        JobPartStage.FAILED,
                        _failed_part_progress(job_id, idx),
                        seg["start"],
                        seg["end"],
                        seg["duration"],
                        seg.get("viral_score", 0),
                        seg.get("motion_score", 0),
                        seg.get("hook_score", 0),
                        "",
                        f"Failed: {part_err}",
                    )
                    _job_log(
                        effective_channel,
                        job_id,
                        f"Part {idx}/{total_parts} failed: "
                        f"phase={failure_detail['phase']} code={failure_detail['code']} error={part_err}",
                        kind="error",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="part_degraded",
                        level="WARNING",
                        message=f"Clip {idx} failed — {len(outputs)}/{total_parts} clips completed so far",
                        step="render.part",
                        context={
                            "part_no": idx,
                            "total_parts": total_parts,
                            "completed_so_far": len(outputs),
                            "failed_so_far": len(failed_parts),
                            "error_code": failure_detail["code"],
                            "phase": failure_detail["phase"],
                        },
                    )
                completed_parts += 1
                progress = 30 + int((completed_parts / total_parts) * 60)
                set_stage_fn(JobStage.RENDERING, progress, f"Processed {completed_parts}/{total_parts} parts")
        else:
            future_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, seg in enumerate(scored, start=1):
                    if cancel_registry.is_cancelled(job_id):
                        break  # stop submitting; running futures will self-cancel
                    future_map[executor.submit(_run_part, part_ctx, idx, seg)] = idx

                for future in as_completed(future_map):
                    idx = future_map[future]
                    seg = scored[idx - 1]
                    try:
                        result = future.result()
                        if result["output"]:
                            outputs.append(result["output"])
                        if result["row"]:
                            rows.append(result["row"])
                    except cancel_registry.JobCancelledError:
                        raise  # propagate immediately; executor.__exit__ waits for running futures
                    except Exception as part_err:
                        failure_detail = _render_part_failure_detail(idx, part_err)
                        failed_parts.append(failure_detail)
                        upsert_job_part(
                            job_id,
                            idx,
                            f"{source['slug']}_part_{idx:03d}.mp4",
                            JobPartStage.FAILED,
                            _failed_part_progress(job_id, idx),
                            seg["start"],
                            seg["end"],
                            seg["duration"],
                            seg.get("viral_score", 0),
                            seg.get("motion_score", 0),
                            seg.get("hook_score", 0),
                            "",
                            f"Failed: {part_err}",
                        )
                        _job_log(
                            effective_channel,
                            job_id,
                            f"Part {idx}/{total_parts} failed: "
                            f"phase={failure_detail['phase']} code={failure_detail['code']} error={part_err}",
                            kind="error",
                        )
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="part_degraded",
                            level="WARNING",
                            message=f"Clip {idx} failed — {len(outputs)}/{total_parts} clips completed so far",
                            step="render.part",
                            context={
                                "part_no": idx,
                                "total_parts": total_parts,
                                "completed_so_far": len(outputs),
                                "failed_so_far": len(failed_parts),
                                "error_code": failure_detail["code"],
                                "phase": failure_detail["phase"],
                            },
                        )
                    completed_parts += 1
                    progress = 30 + int((completed_parts / total_parts) * 60)
                    set_stage_fn(
                        JobStage.RENDERING_PARALLEL,
                        progress,
                        f"Processed {completed_parts}/{total_parts} parts",
                    )
            # Catch cancel that completed all futures before propagating (e.g. last part cancelled)
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()

        _render_loop_ms = int((time.perf_counter() - _t_render_loop) * 1000)
        _job_log(
            effective_channel, job_id,
            f"Render loop done: {len(outputs)}/{total_parts} parts in {_render_loop_ms}ms "
            f"({_render_loop_ms // 1000}s) with {max_workers} worker(s)",
        )
    finally:
        with render_active_lock:
            render_active_count[0] -= 1
        job_semaphore.release()

    return RenderLoopResult(outputs=outputs, rows=rows, failed_parts=failed_parts)
