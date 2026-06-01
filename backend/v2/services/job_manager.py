"""
job_manager.py — ThreadPoolExecutor queue cho render jobs v2.

Mỗi job chạy pipeline.run_pipeline() trong 1 thread riêng.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from v2.core.constants import MAX_CONCURRENT_PARTS
from v2.domain.render.models import RenderRequest, RenderResult

logger = logging.getLogger("v2.services.job_manager")

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=MAX_CONCURRENT_PARTS,
                    thread_name_prefix="render-v2",
                )
    return _executor


def submit_render_job(
    job_id: str,
    request: RenderRequest,
    work_dir: Path,
    emit_fn: Callable[[str, dict], None],
    cancel_event: Optional[threading.Event] = None,
) -> Future[RenderResult]:
    """Submit render job vào queue. Trả về Future để track progress."""
    from v2.domain.render.pipeline import run_pipeline
    logger.info("submit_render_job job_id=%s", job_id)
    return get_executor().submit(run_pipeline, job_id, request, work_dir, emit_fn, cancel_event)
