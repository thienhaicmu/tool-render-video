from __future__ import annotations

import concurrent.futures
import json
import shutil
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException

from app.core.config import TEMP_DIR
from app.core.stage import JobStage
from app.models.schemas import DownloadBatchRequest, DownloadRetryRequest
from app.services.db import get_job, list_job_parts, update_job_progress, upsert_job, upsert_job_part
from app.services.downloader import detect_public_video_source, download_public_video
from app.services.job_manager import submit_job


router = APIRouter(prefix="/api/download", tags=["download"])
_MAX_PARALLEL_DOWNLOADS = 2


def _clean_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in urls or []:
        url = str(raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {url}")
    return detect_public_video_source(url)


def _resolve_output_dir(raw_output_dir: str) -> Path:
    raw = str(raw_output_dir or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Choose a save folder before starting downloads")
    out = Path(raw).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid output folder: {exc}") from exc
    return out


def _friendly_download_error(exc: Exception) -> str:
    text = str(exc or "").strip()
    low = text.lower()
    if "unsupported link" in low or "invalid url" in low:
        return "Unsupported link"
    if "private" in low or "unavailable" in low or "not available" in low:
        return "Private or unavailable video"
    if "login" in low or "sign in" in low or "cookies" in low:
        return "Login required"
    return "Download could not be completed"


def _unique_output_path(output_dir: Path, src_path: Path) -> Path:
    stem = src_path.stem.strip() or "video"
    suffix = src_path.suffix or ".mp4"
    candidate = output_dir / f"{stem}{suffix}"
    idx = 1
    while candidate.exists():
        candidate = output_dir / f"{stem}_{idx}{suffix}"
        idx += 1
    return candidate


def _read_download_payload(job_id: str) -> dict:
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Download job not found")
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Download payload is invalid: {exc}") from exc
    return payload


def _compute_download_batch_result(job_id: str, output_dir: str):
    parts = list_job_parts(job_id)
    total = len(parts)
    done = sum(1 for p in parts if str(p.get("status") or "").lower() == "done")
    failed = sum(1 for p in parts if str(p.get("status") or "").lower() == "failed")
    unsupported = sum(1 for p in parts if str(p.get("status") or "").lower() == "unsupported")
    if done > 0 and failed == 0:
        status = "completed"
        message = f"Saved {done} file{'s' if done != 1 else ''}"
        stage = JobStage.DONE
    elif done > 0:
        status = "completed"
        message = f"Saved {done}/{total} file{'s' if total != 1 else ''}"
        stage = JobStage.DONE
    else:
        status = "failed"
        message = "No files were downloaded"
        stage = JobStage.FAILED
    return {
        "output_dir": output_dir,
        "total_items": total,
        "completed_items": done,
        "failed_items": failed,
        "unsupported_items": unsupported,
    }, message, stage, status


def process_download_batch(job_id: str, payload: DownloadBatchRequest, retry_part_numbers: set[int] | None = None):
    urls = _clean_urls(payload.urls)
    output_dir = _resolve_output_dir(payload.output_dir)
    total = len(urls)
    retry_set = set(retry_part_numbers or range(1, total + 1))
    parts_snapshot = {int(p["part_no"]): p for p in list_job_parts(job_id)}
    progress_lock = threading.Lock()
    processed_selected = 0
    active_progress: dict[int, int] = {}

    stable_done = sum(
        1
        for part_no, row in parts_snapshot.items()
        if part_no not in retry_set and str(row.get("status") or "").lower() == "done"
    )

    def _current_batch_pct() -> int:
        in_flight = sum(active_progress.values())
        return max(0, min(99, int(((stable_done + processed_selected + (in_flight / 100.0)) / max(1, total)) * 100)))

    upsert_job(
        job_id,
        "download",
        "downloads",
        "running",
        payload.model_dump(),
        {"output_dir": str(output_dir), "total_items": total},
        stage=JobStage.DOWNLOADING,
        progress_percent=max(1, int((stable_done / max(1, total)) * 100)),
        message="Starting batch download",
    )

    for idx, url in enumerate(urls, start=1):
        source = detect_public_video_source(url)
        current = parts_snapshot.get(idx, {})
        if idx not in retry_set:
            if current:
                upsert_job_part(
                    job_id,
                    idx,
                    current.get("part_name") or url,
                    current.get("status") or "done",
                    int(current.get("progress_percent") or 100),
                    output_file=current.get("output_file") or "",
                    message=current.get("message") or "Saved",
                )
            continue
        initial_status = "unsupported" if source == "unknown" else "waiting"
        initial_message = "Unsupported link" if source == "unknown" else f"Waiting · {source.title()}"
        upsert_job_part(job_id, idx, url, initial_status, 0, output_file="", message=initial_message)

    def _run_one(idx: int, url: str):
        nonlocal processed_selected
        source = detect_public_video_source(url)
        item_tmp_dir = TEMP_DIR / "downloads" / job_id / f"item_{idx:03d}"
        item_tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            if source == "unknown":
                upsert_job_part(job_id, idx, url, "unsupported", 0, output_file="", message="Unsupported link")
                return

            def _progress_callback(item_pct: int, label: str):
                with progress_lock:
                    active_progress[idx] = max(1, min(99, int(item_pct)))
                    pct = _current_batch_pct()
                upsert_job_part(job_id, idx, url, "downloading", max(1, item_pct), output_file="", message=label)
                update_job_progress(job_id, JobStage.DOWNLOADING, pct, f"{source.title()} {idx}/{total}: {label}", status="running")

            with progress_lock:
                active_progress[idx] = 1
                pct = _current_batch_pct()
            upsert_job_part(job_id, idx, url, "downloading", 1, output_file="", message="Connecting")
            update_job_progress(job_id, JobStage.DOWNLOADING, pct, f"{source.title()} {idx}/{total}: Connecting", status="running")
            downloaded = download_public_video(url, item_tmp_dir, progress_callback=_progress_callback)
            src_path = Path(downloaded["filepath"]).resolve()
            final_path = _unique_output_path(output_dir, src_path)
            shutil.move(str(src_path), str(final_path))
            part_name = downloaded.get("title") or final_path.stem or url
            upsert_job_part(job_id, idx, part_name, "done", 100, output_file=str(final_path), message="Saved")
        except Exception as exc:
            friendly = _friendly_download_error(exc)
            upsert_job_part(job_id, idx, url, "failed", 0, output_file="", message=friendly)
        finally:
            try:
                shutil.rmtree(item_tmp_dir, ignore_errors=True)
            except Exception:
                pass
            with progress_lock:
                active_progress.pop(idx, None)
                processed_selected += 1
                pct = int(((stable_done + processed_selected) / max(1, total)) * 100)
            update_job_progress(job_id, JobStage.DOWNLOADING, pct, f"Processed {stable_done + processed_selected}/{total} links", status="running")

    targets = [(idx, url) for idx, url in enumerate(urls, start=1) if idx in retry_set]
    max_workers = min(_MAX_PARALLEL_DOWNLOADS, max(1, len(targets)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="download-item") as pool:
        futures = [pool.submit(_run_one, idx, url) for idx, url in targets]
        for fut in concurrent.futures.as_completed(futures):
            try:
                fut.result()
            except Exception:
                pass

    result, message, stage, status = _compute_download_batch_result(job_id, str(output_dir))
    upsert_job(
        job_id,
        "download",
        "downloads",
        status,
        payload.model_dump(),
        result,
        stage=stage,
        progress_percent=100,
        message=message,
    )


@router.post("/process")
def create_download_batch(payload: DownloadBatchRequest):
    urls = _clean_urls(payload.urls)
    if not urls:
        raise HTTPException(status_code=400, detail="Paste at least one public video link")
    for url in urls:
        _validate_url(url)
    output_dir = _resolve_output_dir(payload.output_dir)
    job_id = str(uuid.uuid4())
    normalized = DownloadBatchRequest(urls=urls, output_dir=str(output_dir))
    upsert_job(
        job_id,
        "download",
        "downloads",
        "queued",
        normalized.model_dump(),
        {"output_dir": str(output_dir), "total_items": len(urls)},
        stage=JobStage.QUEUED,
        progress_percent=0,
        message=f"Queued {len(urls)} downloads",
    )
    submitted = submit_job(job_id, process_download_batch, job_id, normalized, None)
    if not submitted:
        raise HTTPException(status_code=409, detail="Download job is already running")
    return {
        "job_id": job_id,
        "status": "queued",
        "count": len(urls),
        "output_dir": str(output_dir),
        "items": [{"part_no": idx, "url": url, "source": detect_public_video_source(url)} for idx, url in enumerate(urls, start=1)],
    }


@router.post("/retry/{job_id}")
def retry_download_items(job_id: str, payload: DownloadRetryRequest):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Download job not found")
    if str(row.get("kind") or "").lower() != "download":
        raise HTTPException(status_code=400, detail="Job is not a download batch")
    if str(row.get("status") or "").lower() == "running":
        raise HTTPException(status_code=409, detail="Download batch is already running")

    source_payload = DownloadBatchRequest(**_read_download_payload(job_id))
    existing_parts = list_job_parts(job_id)
    failed_parts = [int(p["part_no"]) for p in existing_parts if str(p.get("status") or "").lower() == "failed"]
    part_numbers = [int(x) for x in (payload.part_numbers or []) if int(x) > 0]
    retry_parts = set(part_numbers or failed_parts)
    if not retry_parts:
        raise HTTPException(status_code=400, detail="No failed downloads to retry")

    for part_no in retry_parts:
        if part_no > len(source_payload.urls):
            raise HTTPException(status_code=400, detail=f"Invalid queue item: {part_no}")

    upsert_job(
        job_id,
        "download",
        "downloads",
        "queued",
        source_payload.model_dump(),
        {"output_dir": source_payload.output_dir, "retry_part_numbers": sorted(retry_parts)},
        stage=JobStage.QUEUED,
        progress_percent=0,
        message=f"Retry queued for {len(retry_parts)} item(s)",
    )
    submitted = submit_job(job_id, process_download_batch, job_id, source_payload, retry_parts)
    if not submitted:
        raise HTTPException(status_code=409, detail="Download batch is already running")
    return {"job_id": job_id, "status": "queued", "retried": sorted(retry_parts)}
