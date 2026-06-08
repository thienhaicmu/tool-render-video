"""End-to-end smoke test driver — validates Batches 10A-F on a real render.

Drives the running backend through:
  1. POST /api/render/prepare-source
  2. POST /api/render/process (Strict payload, gemini-2.5-flash)
  3. Poll GET /api/jobs/{id} until terminal status

Sweeps for evidence of each 10A-F closure:
  - 10A ST-15: db_conn_acquire_seconds histogram present at /metrics
  - 10C BR11: /api/jobs/{id}/ai-summary returns ai_status enum
  - 10F BR14: no .tmp orphans in APP_DATA_DIR/cache

Outputs a JSON evidence blob to stdout. Run the backend separately:
    cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

# Force UTF-8 stdout so the evidence print doesn't crash on Windows cp1252
# when the source filename contains emoji (caught during the 2026-06-06
# Batch 10 smoke — the prior baseline ran a separate eval driver).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


BASE = "http://127.0.0.1:8765"


def _request(method: str, path: str, *, body: dict | None = None, timeout: float = 30.0) -> dict:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return {"_status": e.code, "_error": e.read().decode("utf-8", errors="replace")[:500]}
    except Exception as e:
        return {"_status": 0, "_error": f"{type(e).__name__}: {e}"}
    try:
        return json.loads(payload) if payload else {"_status": 200}
    except Exception:
        return {"_status": 200, "_raw": payload[:300]}


def _get_text(path: str, *, timeout: float = 10.0) -> str:
    url = f"{BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"<ERROR {type(e).__name__}: {e}>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="Absolute path to local source MP4")
    ap.add_argument("--output", required=True, help="Output directory for rendered clips")
    ap.add_argument("--max-wait-sec", type=int, default=900, help="Polling timeout (default 15m)")
    args = ap.parse_args()

    src_path = Path(args.video)
    out_path = Path(args.output)
    if not src_path.exists():
        print(json.dumps({"FATAL": f"video not found: {src_path}"}), flush=True)
        return 2
    out_path.mkdir(parents=True, exist_ok=True)

    evidence: dict[str, Any] = {"phase": {}, "batch_10_evidence": {}}

    # ── Phase 0: health ─────────────────────────────────────────────────────
    health = _request("GET", "/api/render/queue-status")
    evidence["phase"]["health"] = health

    # ── Phase 1: prepare-source ─────────────────────────────────────────────
    prep = _request(
        "POST", "/api/render/prepare-source",
        body={"source_video_path": str(src_path)},
        timeout=300.0,
    )
    evidence["phase"]["prepare_source"] = {
        k: v for k, v in prep.items() if k in ("session_id", "duration", "title", "_status", "_error")
    }
    session_id = prep.get("session_id")
    if not session_id:
        print(json.dumps({"FATAL": "prepare-source failed", "detail": evidence}, indent=2), flush=True)
        return 3

    # ── Phase 2: submit render ──────────────────────────────────────────────
    # Batch 10O: the wire endpoint is now RenderRequestPublic — BE-only
    # fields like channel_code / ai_clip_min_duration_sec are rejected
    # at the boundary (HTTP 422). The smoke driver mirrors the FE shape:
    # output_mode='manual' + output_dir; channel resolves server-side to
    # 'manual' (the default for non-channel-mode renders).
    payload = {
        "source_mode": "local",
        "source_video_path": str(src_path),
        "edit_session_id": session_id,
        "output_mode": "manual",
        "output_dir": str(out_path),
        "output_count": 1,
        "min_part_sec": 30,
        "max_part_sec": 60,
        "render_profile": "fast",
        "add_subtitle": False,
        "voice_enabled": False,
        "motion_aware_crop": False,
        "llm_enabled": True,
        "ai_provider": "gemini",
        "llm_model": "gemini-2.5-flash",
        "ai_cloud_provider": "gemini",
        "ai_cloud_model": "gemini-2.5-flash",
    }
    sub = _request("POST", "/api/render/process", body=payload, timeout=30.0)
    evidence["phase"]["process_submit"] = sub
    job_id = sub.get("job_id")
    if not job_id:
        print(json.dumps({"FATAL": "process submit failed", "detail": evidence}, indent=2), flush=True)
        return 4

    # ── Phase 3: poll until terminal ───────────────────────────────────────
    started = time.time()
    last_status: dict[str, Any] = {}
    poll_log: list[dict[str, Any]] = []
    while True:
        if time.time() - started > args.max_wait_sec:
            print(json.dumps({"TIMEOUT": "exceeded max-wait", "last": last_status}, indent=2), flush=True)
            return 5
        time.sleep(5)
        status = _request("GET", f"/api/jobs/{job_id}")
        last_status = status
        snap = {
            "elapsed_sec": int(time.time() - started),
            "status":      status.get("status"),
            "stage":       status.get("stage"),
            "progress":    status.get("progress_percent"),
            "message":     (status.get("message") or "")[:120],
        }
        # Only log when something interesting changes.
        if not poll_log or any(snap[k] != poll_log[-1].get(k) for k in ("status", "stage", "progress")):
            poll_log.append(snap)
            print(json.dumps({"POLL": snap}), flush=True)
        term = (status.get("status") or "").lower()
        if term in ("completed", "completed_with_errors", "failed", "cancelled"):
            break
    evidence["phase"]["poll_log"] = poll_log
    evidence["phase"]["final_status"] = last_status.get("status")

    # ── Evidence sweep: Batch 10C BR11 (ai_status field) ───────────────────
    ai = _request("GET", f"/api/jobs/{job_id}/ai-summary")
    evidence["batch_10_evidence"]["BR11_ai_status"] = {
        "available":      ai.get("available"),
        "ai_status":      ai.get("ai_status"),
        "status_message": ai.get("status_message"),
        "output_count":   ai.get("output_count"),
        "best_part_no":   ai.get("best_part_no"),
    }

    # ── Evidence sweep: Batch 10A ST-15 (db_conn histogram at /metrics) ────
    metrics = _get_text("/metrics", timeout=10.0)
    evidence["batch_10_evidence"]["ST-15_db_conn_metric"] = {
        "histogram_name_present": "db_conn_acquire_seconds" in metrics,
        "role_db_conn_present":   'role="db_conn"' in metrics,
        "role_thread_present":    'role="_thread_conn"' in metrics,
        # Count distinct sample buckets to confirm the histogram has been
        # observed at runtime (not just registered with no samples).
        "sample_count_lines":     metrics.count("db_conn_acquire_seconds_bucket"),
    }

    # ── Evidence sweep: Batch 10F BR14 (no .tmp orphans in cache) ──────────
    from pathlib import Path as _Path
    # APP_DATA_DIR resolution mirrors backend.app.core.config.
    cache_root = _Path("d:/tool-render-video/data/cache")
    tmp_files: list[str] = []
    if cache_root.exists():
        for p in cache_root.rglob("*.tmp"):
            try:
                tmp_files.append(str(p.relative_to(cache_root)))
            except Exception:
                tmp_files.append(str(p))
    evidence["batch_10_evidence"]["BR14_tmp_orphans"] = {
        "cache_root":        str(cache_root),
        "tmp_orphan_count":  len(tmp_files),
        "tmp_orphan_sample": tmp_files[:10],
    }

    # ── Evidence sweep: render output produced ─────────────────────────────
    if out_path.exists():
        rendered = sorted(p.name for p in out_path.glob("*.mp4") if p.is_file())
        evidence["batch_10_evidence"]["output_files"] = rendered

    print("\n" + "=" * 60, flush=True)
    print("EVIDENCE BLOB:", flush=True)
    print(json.dumps(evidence, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
