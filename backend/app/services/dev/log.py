"""Log discovery + parsing + classification + the ``/log`` command.

Audit MT-1 (Batch 10J 2026-06-06): extracted verbatim from
``app.services.dev_commands``. Public surface: ``_cmd_log`` (the
command handler) + the helpers shared with the error / autofix
sub-modules (``_classify``, ``_workflow_step_label``,
``_discover_logs``, ``_parse_entries``, etc.).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import CHANNELS_DIR, LOGS_DIR

from app.services.dev._shared import (
    _err_code,
    _read_tail_lines,
    _severity,
    _to_epoch,
)


def _current_jobs() -> list[tuple[str, str]]:
    try:
        from app.db.jobs_repo import list_jobs
        rows = list_jobs()
    except Exception:
        return []
    out = []
    for r in rows[:40]:
        status = str(r.get("status") or "").lower()
        if status in {"running", "queued", "failed"}:
            jid = str(r.get("job_id") or "").strip()
            ch = str(r.get("channel_code") or "").strip()
            if jid and ch:
                out.append((jid, ch))
    return out[:8]


def _current_render_job() -> dict[str, Any] | None:
    try:
        from app.db.jobs_repo import list_jobs
        rows = list_jobs()
    except Exception:
        return None
    for r in rows:
        kind = str(r.get("kind") or "").lower()
        status = str(r.get("status") or "").lower()
        if kind == "render" and status in {"running", "queued", "failed"}:
            return r
    return None


def _discover_logs() -> list[tuple[Path, str]]:
    seen = set()
    out: list[tuple[Path, str]] = []
    for jid, ch in _current_jobs():
        for p in [CHANNELS_DIR / ch / "logs" / f"{jid}.log", CHANNELS_DIR / ch / "upload" / "logs" / f"{jid}.log"]:
            rp = p.resolve()
            if p.exists() and p.is_file() and rp not in seen:
                out.append((p, "current_job"))
                seen.add(rp)
    for p, typ in [(LOGS_DIR / "error.log", "error_log"), (LOGS_DIR / "app.log", "app_log")]:
        rp = p.resolve()
        if p.exists() and p.is_file() and rp not in seen:
            out.append((p, typ))
            seen.add(rp)
    session_log = LOGS_DIR / "dev_run.log"
    rp = session_log.resolve()
    if session_log.exists() and session_log.is_file() and rp not in seen:
        out.append((session_log, "session_log"))
        seen.add(rp)
    recent: list[Path] = []
    for root in [LOGS_DIR, CHANNELS_DIR]:
        if root.exists():
            recent.extend([p for p in root.rglob("*.log") if p.is_file()])
    for p in sorted(recent, key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        rp = p.resolve()
        if rp not in seen:
            out.append((p, "recent_log"))
            seen.add(rp)
    return out


def _tail_preview(path: Path, lines: int = 80) -> list[str]:
    try:
        return _read_tail_lines(path, max_bytes=300_000, max_lines=lines)[-lines:]
    except Exception:
        return []


def _latest_session_start_epoch() -> float | None:
    # Session marker emitted by /run.
    p = LOGS_DIR / "dev_run.log"
    if not p.exists():
        return None
    try:
        lines = _read_tail_lines(p, max_bytes=200_000, max_lines=1000)
    except Exception:
        return None
    latest: float | None = None
    marker = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+/run requested", re.IGNORECASE)
    for ln in lines:
        m = marker.match(ln.strip())
        if not m:
            continue
        ep = _to_epoch(m.group("ts"))
        if ep is None:
            continue
        latest = ep if latest is None else max(latest, ep)
    return latest


def _classify(text: str, code: str) -> str:
    if code:
        fam = code[:2]
        fam_map = {
            "DL": "download", "RN": "render", "LG": "login", "UP": "upload",
            "PX": "proxy/network", "FS": "file system", "BR": "browser/profile",
            "SC": "scheduler/rules", "RT": "startup/runtime",
        }
        if fam in fam_map:
            return fam_map[fam]
    t = (text or "").lower()
    rules = [
        ("download", ["yt-dlp", "youtube", "extractor", "download"]),
        ("render", ["ffmpeg", "render", "subtitle", "encode"]),
        ("login", ["login", "sign in", "captcha", "2fa"]),
        ("upload", ["upload", "post-button", "file input"]),
        ("browser/profile", ["browser-profile", "portable", "profile"]),
        ("proxy/network", ["proxy", "network", "timeout", "dns"]),
        ("scheduler/rules", ["schedule", "slot", "queued", "rule", "mapping"]),
        ("ui selector/wait", ["selector", "visible", "wait"]),
        ("file system", ["not found", "permission denied", "access is denied", "path"]),
        ("startup/runtime", ["startup", "uvicorn", "address already in use"]),
    ]
    for cat, keys in rules:
        if any(k in t for k in keys):
            return cat
    return "unknown"


def _workflow_step_label(entry: dict[str, Any], category: str) -> str:
    step = str(entry.get("step") or "").strip()
    event = str(entry.get("event") or "").strip().lower()
    module = str(entry.get("module") or "").strip().lower()
    text = " ".join(
        [str(entry.get("message") or ""), str(entry.get("exception") or ""), str(entry.get("traceback") or "")]
    ).lower()
    if step:
        legacy_map = {
            "upload_select_file": "upload.file.select",
            "upload_ui_ready": "upload.ui.ready",
            "video_download": "video.download",
            "render.quick_process": "video.render",
            "profile.create_or_select": "profile.create/select",
            "schedule.trigger": "rule.load",
            "app.startup": "app.start",
        }
        return legacy_map.get(step.lower(), step)
    if event.startswith("upload.") or module == "upload_engine":
        if "selector" in text or "file" in text:
            return "upload.file.select"
        if "submit" in text or "post-button" in text:
            return "upload.submit"
        return "upload.ui.ready"
    if event.startswith("video.download") or category == "download":
        return "video.download"
    if event.startswith("render.") or category == "render":
        return "video.render"
    if event.startswith("login.") or category == "login":
        return "login.check"
    if event.startswith("proxy.") or category == "proxy/network":
        return "proxy.apply"
    if event.startswith("profile.") or category == "browser/profile":
        return "profile.create/select"
    if category == "scheduler/rules":
        return "rule.load"
    if category == "startup/runtime":
        return "app.start"
    return "unknown"


def _source_type_for_entry(entry: dict[str, Any], active_job_ids: set[str], session_start_epoch: float | None) -> str:
    src_type = str(entry.get("source_type") or "")
    jid = str(entry.get("job_id") or "").strip()
    entry_epoch = float(entry.get("entry_epoch") or 0)
    if src_type == "current_job" or (jid and jid in active_job_ids):
        return "current job"
    if session_start_epoch is not None and entry_epoch >= session_start_epoch:
        return "current session"
    if src_type == "session_log":
        return "current session"
    return "historical fallback"


def _parse_entries(path: Path, src_type: str) -> list[dict]:
    lines = _read_tail_lines(path)
    file_epoch = path.stat().st_mtime
    patt = re.compile(r"(ERROR|Exception|Traceback|Failed|timeout|crash)", re.IGNORECASE)
    out = []
    for idx, ln in enumerate(lines):
        obj = None
        s = ln.strip()
        if s.startswith("{"):
            try:
                tmp = json.loads(s)
                if isinstance(tmp, dict):
                    obj = tmp
            except Exception:
                obj = None
        if obj is not None:
            level = str(obj.get("level") or obj.get("severity") or "INFO").upper()
            msg = str(obj.get("message") or obj.get("msg") or "")
            if _severity(level) < 3 and not patt.search(msg):
                continue
            ts = str(obj.get("timestamp") or "")
            out.append({
                "timestamp": str(obj.get("timestamp") or ""),
                "level": level,
                "event": str(obj.get("event") or ""),
                "module": str(obj.get("module") or ""),
                "message": msg,
                "error_code": str(obj.get("error_code") or _err_code(msg)),
                "job_id": str(obj.get("job_id") or ""),
                "step": str(obj.get("step") or ""),
                "context": obj.get("context") if isinstance(obj.get("context"), dict) else {},
                "exception": str(obj.get("exception") or ""),
                "traceback": str(obj.get("traceback") or ""),
                "line_no": idx,
                "source_file": str(path),
                "source_type": src_type,
                "entry_epoch": _to_epoch(ts) or file_epoch,
                "_lines": lines,
            })
            continue
        m = re.match(r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<lv>[^\]]+)\]\s*(?P<msg>.*)$", ln)
        ts = m.group("ts") if m else ""
        lv = (m.group("lv") if m else ("ERROR" if patt.search(ln) else "INFO")).upper()
        msg = m.group("msg") if m else ln
        if _severity(lv) < 3 and not patt.search(msg):
            continue
        out.append({
            "timestamp": ts,
            "level": lv,
            "event": "",
            "module": "",
            "message": msg,
            "error_code": _err_code(msg),
            "job_id": "",
            "step": "",
            "context": {},
            "exception": msg if "exception" in msg.lower() else "",
            "traceback": msg if "traceback" in msg.lower() else "",
            "line_no": idx,
            "source_file": str(path),
            "source_type": src_type,
            "entry_epoch": _to_epoch(ts) or file_epoch,
            "_lines": lines,
        })
    return out


def _latest_render_event(lines: list[str]) -> dict[str, Any]:
    for ln in reversed(lines or []):
        s = (ln or "").strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        event = str(obj.get("event") or "").lower()
        module = str(obj.get("module") or "").lower()
        if event.startswith("render.") or module == "render":
            return obj
    return {}


def _latest_prepare_source_signal(lines: list[str]) -> dict[str, Any]:
    for ln in reversed(lines or []):
        s = (ln or "").strip()
        if not s:
            continue
        if s.startswith("{"):
            try:
                obj = json.loads(s)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                event = str(obj.get("event") or "").lower()
                if event.startswith("render.prepare_source"):
                    return {
                        "type": "structured",
                        "timestamp": str(obj.get("timestamp") or ""),
                        "event": str(obj.get("event") or ""),
                        "step": str(obj.get("step") or ""),
                        "message": str(obj.get("message") or ""),
                    }
        if re.search(r"prepare[-_ ]source", s, flags=re.IGNORECASE):
            return {
                "type": "text",
                "timestamp": "",
                "event": "prepare-source",
                "step": "render.prepare_source",
                "message": s,
            }
    return {}


def _cmd_log(command_text: str) -> dict:
    line_count = 80
    m = re.search(r"\b(\d{1,4})\b", command_text or "")
    if m:
        line_count = max(20, min(400, int(m.group(1))))

    render_job = _current_render_job()
    log_sources: list[tuple[str, Path]] = []
    if render_job:
        jid = str(render_job.get("job_id") or "").strip()
        ch = str(render_job.get("channel_code") or "").strip()
        for p in [CHANNELS_DIR / ch / "logs" / f"{jid}.log", CHANNELS_DIR / ch / "upload" / "logs" / f"{jid}.log"]:
            if p.exists() and p.is_file():
                log_sources.append(("current_job", p))
    for tag, p in [
        ("current_session", LOGS_DIR / "dev_run.log"),
        ("app", LOGS_DIR / "app.log"),
        ("error", LOGS_DIR / "error.log"),
    ]:
        if p.exists() and p.is_file():
            log_sources.append((tag, p))

    unique_sources: list[tuple[str, Path]] = []
    seen = set()
    for t, p in log_sources:
        rp = str(p.resolve())
        if rp in seen:
            continue
        seen.add(rp)
        unique_sources.append((t, p))

    snapshots = []
    latest_event = {}
    latest_prepare_source = {}
    for t, p in unique_sources:
        lines = _tail_preview(p, lines=line_count)
        evt = _latest_render_event(lines)
        if not latest_event and evt:
            latest_event = evt
        prep = _latest_prepare_source_signal(lines)
        if not latest_prepare_source and prep:
            latest_prepare_source = prep
        snapshots.append({
            "type": t,
            "path": str(p),
            "tail": lines[-30:],
            "latest_render_event": evt,
            "latest_prepare_source": prep,
        })

    progress = {}
    if render_job:
        progress = {
            "job_id": str(render_job.get("job_id") or ""),
            "status": str(render_job.get("status") or ""),
            "stage": str(render_job.get("stage") or ""),
            "message": str(render_job.get("message") or ""),
            "progress_percent": int(render_job.get("progress_percent") or 0),
        }
    return {
        "command": "/log",
        "status": "ok" if snapshots else "noop",
        "Summary": "Render log snapshot collected." if snapshots else "No log sources found.",
        "Active render job": progress,
        "Current render step": str(progress.get("stage") or (latest_event.get("step") if latest_event else "")),
        "Latest render event": latest_event,
        "Latest prepare-source": latest_prepare_source,
        "Log sources": [{"type": s["type"], "path": s["path"]} for s in snapshots],
        "Log snapshots": snapshots,
    }
