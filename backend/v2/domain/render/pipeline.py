"""
pipeline.py — Orchestrator: chain 9 stages theo đúng thứ tự.

Quy tắc:
- Mỗi stage được gọi tuần tự với result của stage trước
- check_cancel() được gọi ở đầu mỗi stage (trong stage)
- Exception từ stage được bắt ở đây và convert thành RenderResult failed
- Partial success (s08 có part fail) KHÔNG được convert thành pipeline fail
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from v2.core.exceptions import CancelledError, RenderError
from v2.core.types import PipelineContext
from v2.domain.render.models import RenderRequest, RenderResult
from v2.domain.render.stages import (
    s01_validate,
    s02_transcribe,
    s03_groq_select,
    s04_analyze,
    s05_scene_detect,
    s06_score_filter,
    s07_plan,
    s08_render_parts,
    s09_qa_rank,
)

logger = logging.getLogger("v2.render.pipeline")


def run_pipeline(
    job_id: str,
    request: RenderRequest,
    work_dir: Path,
    emit_fn: Callable[[str, dict], None],
    cancel_event: Optional[threading.Event] = None,
) -> RenderResult:
    """
    Chạy toàn bộ render pipeline theo thứ tự:
      s01 → s02 → s03 → s04 → s05 → s06 → s07 → s08 → s09

    Luôn trả về RenderResult — không raise ra ngoài.
    """
    if cancel_event is None:
        cancel_event = threading.Event()

    ctx = PipelineContext(
        job_id=job_id,
        work_dir=work_dir,
        cancel_event=cancel_event,
        emit_fn=emit_fn,
    )

    try:
        # s01 — Validate source
        validate_result = s01_validate.run(ctx, request.source_path)

        # s02 — Transcribe full video
        transcribe_result = s02_transcribe.run(ctx, validate_result)

        # s03 — Groq chọn segments (1 API call duy nhất, hoặc skip)
        groq_result = s03_groq_select.run(ctx, transcribe_result, request)

        # s04 — Content analysis CHỈ trên segments đã chọn
        analyze_result = s04_analyze.run(ctx, groq_result, validate_result, transcribe_result)

        # s05 — Scene detection CHỈ trên segments đã chọn
        scene_result = s05_scene_detect.run(ctx, groq_result, validate_result)

        # s06 — Score + filter + platform bias
        filter_result = s06_score_filter.run(
            ctx, groq_result, analyze_result, scene_result, validate_result, request
        )

        # s07 — AI Director local (camera/subtitle/pacing plans)
        plan_result = s07_plan.run(ctx, filter_result, analyze_result, request)

        # s08 — Parallel FFmpeg render
        parts_result = s08_render_parts.run(
            ctx, filter_result, plan_result, validate_result, transcribe_result, request
        )

        # s09 — QA validate + rank
        qa_result = s09_qa_rank.run(ctx, parts_result, request)

        status = (
            "completed" if qa_result.failed_parts == 0
            else "completed_with_errors" if qa_result.success_parts > 0
            else "failed"
        )

        return RenderResult(
            job_id=job_id,
            status=status,
            total_parts=qa_result.total_parts,
            success_parts=qa_result.success_parts,
            failed_parts=qa_result.failed_parts,
            best_output=qa_result.best_output,
            output_rank_score=max(
                (o.output_rank_score for o in qa_result.ranked_outputs), default=0.0
            ),
            is_best_output=any(o.is_best_output for o in qa_result.ranked_outputs),
            is_best_clip=any(o.is_best_clip for o in qa_result.ranked_outputs),
            outputs=[
                {
                    "path": str(o.part.output_path),
                    "output_rank_score": o.output_rank_score,
                    "is_best_output": o.is_best_output,
                    "is_best_clip": o.is_best_clip,
                    "qa_passed": o.qa_passed,
                }
                for o in qa_result.ranked_outputs
                if o.part.output_path
            ],
        )

    except CancelledError:
        logger.info("pipeline cancelled job_id=%s", job_id)
        return RenderResult(
            job_id=job_id, status="cancelled",
            total_parts=0, success_parts=0, failed_parts=0,
        )
    except Exception as exc:
        logger.exception("pipeline_failed job_id=%s: %s", job_id, exc)
        return RenderResult(
            job_id=job_id, status="failed",
            total_parts=0, success_parts=0, failed_parts=0,
            warnings=[str(exc)],
        )
