"""catalog/scheduler.py — AcquisitionScheduler: background queue worker.

Polls acquisition_queue every ACQUISITION_POLL_INTERVAL seconds, submits
pending items to DownloadService, and tracks completions via download_jobs.

Design constraints:
- Daemon thread — dies with the process, never blocks shutdown
- All tick logic wrapped in try/except — scheduler failures never affect
  existing router.py → DownloadService download flow
- Polling-based (no callback) — simple, consistent with existing patterns
- Only 1 item started per tick — natural rate-limit, no burst
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from pathlib import Path

logger = logging.getLogger("app.scheduler")

_POLL_INTERVAL: float = float(os.getenv("ACQUISITION_POLL_INTERVAL", "5"))
_MAX_CONCURRENT: int = int(os.getenv("ACQUISITION_MAX_CONCURRENT", "3"))


class AcquisitionScheduler:
    """Background worker that drains acquisition_queue into DownloadService."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="acq-scheduler",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()
        logger.info("acquisition scheduler started (poll=%.0fs max_concurrent=%d)",
                    _POLL_INTERVAL, _MAX_CONCURRENT)

    def stop(self) -> None:
        self._stop.set()

    def enqueue(
        self,
        url: str,
        platform: str = "",
        quality: str = "best",
        output_dir: str = "",
        priority: int = 5,
        max_retries: int = 3,
    ) -> str:
        """Add a URL to the acquisition queue. Returns queue_id."""
        from app.db.queue_repo import enqueue as _enqueue
        queue_id = str(uuid.uuid4())
        _enqueue(queue_id, url, platform, quality, priority, output_dir, max_retries)
        logger.debug("scheduler.enqueue: queue_id=%s priority=%d url=%s",
                     queue_id, priority, url[:80])
        return queue_id

    # ── Internal ──────────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.warning("scheduler tick error: %s", exc)
            self._stop.wait(_POLL_INTERVAL)

    def _tick(self) -> None:
        self._check_running_jobs()
        self._start_pending_jobs()

    def _check_running_jobs(self) -> None:
        """Poll download_jobs for items currently running → promote to done/failed."""
        from app.db.queue_repo import list_queue, update_queue_item
        from app.db.download_repo import get_download_job
        from app.db.catalog_repo import get_asset_by_dedup_key
        from app.features.download.catalog.service import _catalog_service
        from app.db.connection import _utc_now_iso

        running = list_queue(status="running", limit=50)
        for item in running:
            job_id = item.get("download_job_id", "")
            if not job_id:
                continue
            try:
                job = get_download_job(job_id)
                if not job:
                    continue
                job_status = job.get("status", "")

                if job_status == "done":
                    asset_id = ""
                    try:
                        key = _catalog_service.dedup_key(item["url"])
                        asset = get_asset_by_dedup_key(key)
                        if asset:
                            asset_id = asset["asset_id"]
                    except Exception:
                        pass
                    update_queue_item(
                        item["queue_id"],
                        status="done",
                        asset_id=asset_id,
                        completed_at=_utc_now_iso(),
                    )
                    logger.info("scheduler.done: queue_id=%s asset_id=%s",
                                item["queue_id"], asset_id)

                elif job_status == "failed":
                    retry = (item.get("retry_count") or 0) + 1
                    max_r = item.get("max_retries") or 3
                    if retry < max_r:
                        update_queue_item(
                            item["queue_id"],
                            status="queued",
                            retry_count=retry,
                            error_msg=job.get("error_msg", ""),
                            download_job_id="",
                        )
                        logger.info("scheduler.retry: queue_id=%s attempt=%d/%d",
                                    item["queue_id"], retry, max_r)
                    else:
                        update_queue_item(
                            item["queue_id"],
                            status="failed",
                            retry_count=retry,
                            error_msg=job.get("error_msg", ""),
                            completed_at=_utc_now_iso(),
                        )
                        logger.warning("scheduler.exhausted: queue_id=%s retries=%d",
                                       item["queue_id"], retry)

                elif job_status == "cancelled":
                    update_queue_item(
                        item["queue_id"],
                        status="cancelled",
                        completed_at=_utc_now_iso(),
                    )

            except Exception as exc:
                logger.warning("scheduler._check_running_jobs error item=%s: %s",
                               item.get("queue_id"), exc)

    def _start_pending_jobs(self) -> None:
        """Pick next queued item and submit to DownloadService (1 per tick)."""
        from app.db.queue_repo import count_running, get_next_queued, update_queue_item
        from app.db.download_repo import create_download_job
        from app.features.download.service import _service
        from app.db.connection import _utc_now_iso

        try:
            if count_running() >= _MAX_CONCURRENT:
                return
            item = get_next_queued()
            if not item:
                return

            job_id = str(uuid.uuid4())
            url = item["url"]
            platform = item.get("platform") or ""
            quality = item.get("quality") or "best"
            raw_dir = item.get("output_dir") or ""
            output_dir = Path(raw_dir) if raw_dir else Path(".")

            create_download_job(job_id, url, platform, str(output_dir))
            _service.submit(job_id, url, output_dir, quality=quality, platform=platform)
            update_queue_item(
                item["queue_id"],
                status="running",
                download_job_id=job_id,
                started_at=_utc_now_iso(),
            )
            logger.info("scheduler.start: queue_id=%s job_id=%s url=%s",
                        item["queue_id"], job_id, url[:80])

        except Exception as exc:
            logger.warning("scheduler._start_pending_jobs error: %s", exc)
            if "item" in dir() and item:
                try:
                    update_queue_item(
                        item["queue_id"],
                        status="failed",
                        error_msg=str(exc),
                        completed_at=_utc_now_iso(),
                    )
                except Exception:
                    pass


_scheduler = AcquisitionScheduler()
