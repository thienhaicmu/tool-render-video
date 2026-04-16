import fnmatch
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import LOGS_DIR
from app.services.qa_runner import run_test_command


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LAST_ERROR: dict[str, Any] | None = None


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(PROJECT_ROOT), capture_output=True, text=True)


def _http_get(url: str, timeout: int = 6) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)


def _service_url() -> str:
    host = str(os.getenv("HOST", "127.0.0.1")).strip() or "127.0.0.1"
    port = str(os.getenv("PORT", "8000")).strip() or "8000"
    return f"http://{host}:{port}"


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _parse_status_paths(status_text: str) -> list[str]:
    out: list[str] = []
    for raw in (status_text or "").splitlines():
        if len(raw) < 4:
            continue
        payload = raw[3:].strip()
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1].strip()
        if payload:
            out.append(payload)
    return out


def _excluded_patterns() -> list[str]:
    raw = os.getenv("DEV_COMMIT_EXCLUDE", "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _filter_excluded(files: list[str]) -> list[str]:
    patterns = _excluded_patterns()
    if not patterns:
        return files
    return [f for f in files if not any(fnmatch.fnmatch(f, pat) for pat in patterns)]


def _auto_commit_message(files: list[str]) -> str:
    scopes = []
    seen = set()
    for p in files[:8]:
        parts = p.replace("\\", "/").split("/")
        scope = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
        if scope and scope not in seen:
            scopes.append(scope)
            seen.add(scope)
    shortstat = _run_git(["diff", "--cached", "--shortstat"])
    stat = (shortstat.stdout or "").strip()
    scope_text = ", ".join(scopes[:3]) if scopes else "repo"
    return f"Update {scope_text} ({stat or f'{len(files)} file(s)'})"


def _cmd_commit(command_text: str) -> dict:
    status = _run_git(["status", "--porcelain"])
    if status.returncode != 0:
        raise RuntimeError((status.stderr or status.stdout or "git status failed").strip())
    changed = _parse_status_paths(status.stdout)
    if not changed:
        return {
            "command": "/commit",
            "status": "noop",
            "Summary": "No changes to commit.",
            "Files committed": [],
            "Commit message": "",
            "Git result": "no-op",
        }
    to_stage = _filter_excluded(changed)
    if not to_stage:
        return {
            "command": "/commit",
            "status": "noop",
            "Summary": "All changed files excluded by DEV_COMMIT_EXCLUDE.",
            "Files committed": [],
            "Commit message": "",
            "Git result": "no-op",
        }
    add = _run_git(["add", "--", *to_stage])
    if add.returncode != 0:
        raise RuntimeError((add.stderr or add.stdout or "git add failed").strip())
    staged = _run_git(["diff", "--cached", "--name-only"])
    files = [x.strip() for x in (staged.stdout or "").splitlines() if x.strip()]
    if not files:
        return {
            "command": "/commit",
            "status": "noop",
            "Summary": "No staged changes.",
            "Files committed": [],
            "Commit message": "",
            "Git result": "no-op",
        }
    msg = command_text[len("/commit"):].strip() if command_text.startswith("/commit") else ""
    msg = msg or _auto_commit_message(files)
    c = _run_git(["commit", "-m", msg])
    if c.returncode != 0:
        raise RuntimeError((c.stderr or c.stdout or "git commit failed").strip())
    head = _run_git(["rev-parse", "--short", "HEAD"])
    return {
        "command": "/commit",
        "status": "ok",
        "Summary": f"Committed {len(files)} file(s).",
        "Files committed": files,
        "Commit message": msg,
        "Git result": {"commit_id": (head.stdout or "").strip(), "stdout": (c.stdout or "").strip()},
    }


def _read_tail_lines(path: Path, max_bytes: int = 500_000, max_lines: int = 3000) -> list[str]:
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    with path.open("rb") as f:
        if start:
            f.seek(start)
            f.readline()
        data = f.read().decode("utf-8", errors="replace")
    lines = data.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _current_jobs() -> list[tuple[str, str]]:
    try:
        from app.services.db import list_jobs
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


def _discover_logs() -> list[tuple[Path, str]]:
    seen = set()
    out: list[tuple[Path, str]] = []
    for jid, _ch in _current_jobs():
        p = LOGS_DIR / "render" / f"{jid}.log"
        rp = p.resolve()
        if p.exists() and p.is_file() and rp not in seen:
            out.append((p, "current_job"))
            seen.add(rp)
    for p, typ in [(LOGS_DIR / "error.log", "error_log"), (LOGS_DIR / "app.log", "app_log")]:
        rp = p.resolve()
        if p.exists() and p.is_file() and rp not in seen:
            out.append((p, typ))
            seen.add(rp)
    recent: list[Path] = []
    if LOGS_DIR.exists():
        recent.extend([p for p in LOGS_DIR.rglob("*.log") if p.is_file()])
    for p in sorted(recent, key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        rp = p.resolve()
        if rp not in seen:
            out.append((p, "recent_log"))
            seen.add(rp)
    return out


def _err_code(text: str) -> str:
    m = re.search(r"\b([A-Z]{2}\d{3,4})\b", text or "")
    return m.group(1) if m else ""


def _severity(level: str) -> int:
    lv = (level or "").upper()
    if lv in {"CRITICAL", "FATAL"}:
        return 4
    if lv == "ERROR":
        return 3
    return 1


def _classify(text: str, code: str) -> str:
    if code:
        fam = code[:2]
        fam_map = {
            "DL": "download", "RN": "render", "LG": "login", "UP": "upload",
            "PX": "proxy/network", "FS": "file system", "BR": "browser/profile",
            "SC": "scheduler", "RT": "startup/runtime",
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
        ("scheduler", ["schedule", "slot", "queued"]),
        ("ui selector/wait", ["selector", "visible", "wait"]),
        ("file system", ["not found", "permission denied", "access is denied", "path"]),
        ("startup/runtime", ["startup", "uvicorn", "address already in use"]),
    ]
    for cat, keys in rules:
        if any(k in t for k in keys):
            return cat
    return "unknown"


def _parse_entries(path: Path, src_type: str) -> list[dict]:
    lines = _read_tail_lines(path)
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
            "_lines": lines,
        })
    return out


def _choose_error() -> dict[str, Any]:
    entries = []
    src_rank = {"current_job": 40, "error_log": 30, "app_log": 20, "recent_log": 10}
    for p, typ in _discover_logs():
        try:
            entries.extend(_parse_entries(p, typ))
        except Exception:
            continue
    if not entries:
        return {"status": "noop", "summary": "No relevant ERROR/CRITICAL entries found."}
    def rank(e: dict) -> tuple[int, int]:
        score = src_rank.get(str(e.get("source_type") or ""), 0) + _severity(str(e.get("level") or "")) * 10
        if e.get("error_code"):
            score += 15
        if e.get("event"):
            score += 8
        if e.get("module"):
            score += 5
        if e.get("step"):
            score += 3
        return score, int(e.get("line_no") or 0)
    chosen = max(entries, key=rank)
    code = str(chosen.get("error_code") or "")
    full_text = " ".join(str(chosen.get(k) or "") for k in ["message", "exception", "traceback", "event", "module", "step"])
    category = _classify(full_text, code)
    lines = chosen.get("_lines") or []
    i = int(chosen.get("line_no") or 0)
    snippet = "\n".join(lines[max(0, i - 6): min(len(lines), i + 7)])
    code_infer = _infer_code_targets(chosen)
    return {
        "status": "ok",
        "summary": str(chosen.get("message") or chosen.get("exception") or "Error detected"),
        "category": category,
        "error_code": code,
        "module_step": " / ".join([x for x in [str(chosen.get("module") or "").strip(), str(chosen.get("step") or "").strip()] if x]),
        "context": {
            "timestamp": chosen.get("timestamp", ""),
            "job_id": chosen.get("job_id", ""),
            "event": chosen.get("event", ""),
            "source_file": chosen.get("source_file", ""),
            "line_no": chosen.get("line_no", 0),
            "snippet": snippet,
        },
        "log_source": str(chosen.get("source_file") or ""),
        "likely_code_area": code_infer.get("human", f"{category} logic"),
        "code_targets": code_infer.get("targets", []),
        "code_target_priority": code_infer.get("priority_sources", {}),
        "root_cause": f"Likely {category} issue in application logic (not log file).",
        "actions": _actions_for(category),
        "parsed": chosen,
    }


def _actions_for(category: str) -> list[str]:
    m = {
        "download": ["Check yt-dlp extraction fallback and cookies.", "Run URL health check endpoint."],
        "render": ["Verify ffmpeg invocation and output path.", "Validate input file existence."],
        "login": ["Run login/check and re-authenticate if needed."],
        "upload": ["Validate upload UI readiness selectors and file input visibility."],
        "browser/profile": ["Verify portable runtime and profile path write access."],
        "proxy/network": ["Validate proxy settings and test direct mode."],
        "scheduler": ["Validate schedule slot/timezone config and job state updates."],
        "ui selector/wait": ["Refresh selectors and replace brittle waits with explicit checks."],
        "file system": ["Create missing paths if safe.", "Verify permissions."],
        "startup/runtime": ["Check health endpoint/port conflicts and startup logs."],
        "unknown": ["Inspect traceback snippet and re-run /test for more signals."],
    }
    return m.get(category, m["unknown"])


def _traceback_project_files(text: str) -> list[str]:
    files: list[str] = []
    for m in re.finditer(r'File "([^"]+)", line \d+', text or ""):
        p = Path(m.group(1))
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        # Prefer files inside this repo only
        try:
            rp.relative_to(PROJECT_ROOT)
            files.append(str(rp))
        except Exception:
            continue
    # de-dup keep order
    seen = set()
    out = []
    for f in files:
        if f not in seen:
            out.append(f)
            seen.add(f)
    return out


def _module_map(module: str) -> list[str]:
    m = (module or "").strip().lower()
    table = {
        "upload_engine": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "render_engine": ["backend/app/services/render_engine.py", "backend/app/routes/render.py"],
        "downloader": ["backend/app/services/downloader.py", "backend/app/routes/render.py"],
        "channel_service": ["backend/app/services/channel_service.py", "backend/app/routes/channels.py"],
        "db": ["backend/app/services/db.py"],
        "main": ["backend/app/main.py"],
    }
    return table.get(m, [])


def _event_map(event: str) -> list[str]:
    e = (event or "").strip().lower()
    if e.startswith("video.download"):
        return ["backend/app/services/downloader.py", "backend/app/routes/render.py"]
    if e.startswith("login."):
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if e.startswith("upload."):
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if e.startswith("proxy."):
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if e.startswith("profile.") or e.startswith("browser."):
        return ["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"]
    if e.startswith("render."):
        return ["backend/app/routes/render.py", "backend/app/services/render_engine.py"]
    return []


def _error_code_map(code: str) -> list[str]:
    c = (code or "").strip().upper()
    fam = c[:2]
    maps = {
        "DL": ["backend/app/services/downloader.py", "backend/app/routes/render.py"],
        "RN": ["backend/app/routes/render.py", "backend/app/services/render_engine.py"],
        "LG": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "UP": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "PX": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "FS": ["backend/app/routes/render.py", "backend/app/services/channel_service.py", "backend/app/services/upload_engine.py"],
        "BR": ["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"],
        "SC": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "RT": ["backend/app/main.py", "backend/app/services/db.py"],
    }
    return maps.get(fam, [])


def _context_map(context: dict[str, Any], message: str = "") -> list[str]:
    ctext = " ".join([str(message or ""), json.dumps(context or {}, ensure_ascii=False)])
    ctext = ctext.lower()
    out: list[str] = []
    if "selector" in ctext:
        out.extend(["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"])
    if any(k in ctext for k in ["file_path", "output", "root folder", "path", "permission denied"]):
        out.extend(["backend/app/routes/render.py", "backend/app/services/upload_engine.py", "backend/app/services/channel_service.py"])
    if any(k in ctext for k in ["url", "video_id", "youtube"]):
        out.extend(["backend/app/services/downloader.py", "backend/app/routes/render.py"])
    if any(k in ctext for k in ["browser", "profile", "user_data_dir"]):
        out.extend(["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"])
    return out


def _existing_repo_files(rels: list[str]) -> list[str]:
    out = []
    for rel in rels:
        p = PROJECT_ROOT / rel
        if p.exists():
            out.append(str(p))
    return out


def _infer_code_targets(parsed: dict[str, Any]) -> dict[str, Any]:
    tb_text = " ".join([str(parsed.get("traceback") or ""), str(parsed.get("exception") or ""), str(parsed.get("message") or "")])
    tb_files = _traceback_project_files(tb_text)
    module_files = _existing_repo_files(_module_map(str(parsed.get("module") or "")))
    event_files = _existing_repo_files(_event_map(str(parsed.get("event") or "")))
    code_files = _existing_repo_files(_error_code_map(str(parsed.get("error_code") or "")))
    ctx_files = _existing_repo_files(_context_map(parsed.get("context") or {}, str(parsed.get("message") or "")))

    ordered = []
    for bucket in [tb_files, module_files, event_files, code_files, ctx_files]:
        for f in bucket:
            if f not in ordered:
                ordered.append(f)

    module = str(parsed.get("module") or "").strip()
    step = str(parsed.get("step") or "").strip()
    category = _classify(
        " ".join(str(parsed.get(k) or "") for k in ["message", "exception", "traceback", "event", "module", "step"]),
        str(parsed.get("error_code") or ""),
    )
    if category == "upload" and module == "upload_engine":
        human = f"{module or 'upload_engine'} -> {step or 'upload_select_file'} -> upload UI selector/wait logic"
    elif module or step:
        human = " -> ".join([x for x in [module, step, f"{category} logic"] if x])
    else:
        human = f"{category} logic"
    return {
        "targets": ordered,
        "human": human,
        "priority_sources": {
            "traceback": tb_files,
            "module": module_files,
            "event": event_files,
            "error_code": code_files,
            "context": ctx_files,
        },
    }


def _extract_paths(text: str) -> list[Path]:
    out: list[Path] = []
    for rgx in [r"[A-Za-z]:\\[^\s\"']+", r"/[A-Za-z0-9_\-./]+"]:
        for m in re.findall(rgx, text or ""):
            try:
                out.append(Path(m))
            except Exception:
                continue
    return out


def _target_files(category: str) -> list[str]:
    maps = {
        "download": ["backend/app/services/downloader.py", "backend/app/routes/render.py"],
        "render": ["backend/app/routes/render.py", "backend/app/services/render_engine.py"],
        "login": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "upload": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "browser/profile": ["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"],
        "proxy/network": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "scheduler": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
        "ui selector/wait": ["backend/app/services/upload_engine.py"],
        "file system": ["backend/app/routes/render.py", "backend/app/services/upload_engine.py", "backend/app/services/channel_service.py"],
        "startup/runtime": ["backend/app/main.py", "backend/app/services/db.py"],
    }
    out = []
    for rel in maps.get(category, []):
        p = (PROJECT_ROOT / rel)
        if p.exists():
            out.append(str(p))
    return out


def _cmd_error() -> dict:
    global _LAST_ERROR
    parsed = _choose_error()
    _LAST_ERROR = parsed
    return {
        "command": "/error",
        "status": parsed.get("status", "ok"),
        "## Error summary": parsed.get("summary", ""),
        "## Error category": parsed.get("category", "unknown"),
        "## Error code": parsed.get("error_code", ""),
        "## Module / step": parsed.get("module_step", ""),
        "## Log source": parsed.get("log_source", ""),
        "## Likely code area": parsed.get("likely_code_area", ""),
        "## Relevant context": parsed.get("context", {}),
        "## Likely root cause": parsed.get("root_cause", ""),
        "## Suggested next actions": parsed.get("actions", []),
    }


def _cmd_fix() -> dict:
    global _LAST_ERROR
    parsed = _LAST_ERROR or _choose_error()
    category = parsed.get("category", "unknown")
    ctx = parsed.get("context", {}) if isinstance(parsed.get("context"), dict) else {}
    snippet = str(ctx.get("snippet", ""))
    changes: list[str] = []
    patch: list[str] = []
    status = "noop"
    risks: list[str] = []
    if category in {"file system", "startup/runtime"}:
        for p in _extract_paths(snippet):
            try:
                target = p.parent if p.suffix else p
                if not target.exists():
                    target.mkdir(parents=True, exist_ok=True)
                    changes.append(str(target))
                    patch.append(f"Created missing path: {target}")
            except Exception:
                continue
        if changes:
            status = "ok"
    if status == "noop":
        target_info = _infer_code_targets(parsed.get("parsed", {}) if isinstance(parsed.get("parsed"), dict) else {})
        likely_targets = target_info.get("targets") or _target_files(category)
        patch.append("No safe automatic patch with high confidence for this category.")
        patch.append(f"Likely files: {likely_targets or ['unknown']}")
        if target_info.get("human"):
            patch.append(f"Likely code area: {target_info.get('human')}")
        risks.append("Manual confirmation required before code edits.")
    return {
        "command": "/fix",
        "status": status,
        "## Summary": "Applied minimal automatic patch." if status == "ok" else "No automatic patch applied.",
        "## Parsed error used": {
            "summary": parsed.get("summary", ""),
            "category": category,
            "error_code": parsed.get("error_code", ""),
        },
        "## Root cause targeted": category,
        "## Fix strategy": "safe-path-remediation" if status == "ok" else "manual-targeted-recommendation",
        "## Files changed": changes,
        "## Patch summary": patch,
        "## Risks / assumptions": risks or ["Auto-fix is conservative by design."],
        "## Recommended next command": "/test",
    }


def _cmd_run() -> dict:
    status, _ = _http_get(_service_url() + "/health", timeout=3)
    run_cmd = str(PROJECT_ROOT / "run-backend.ps1")
    log_src = LOGS_DIR / "dev_run.log"
    if status == 200:
        return {
            "command": "/run",
            "status": "ok",
            "Summary": "Application already running.",
            "Run command used": run_cmd,
            "Startup status": "already-running",
            "Log source": str(log_src),
        }
    log_src.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "run-backend.ps1")]
    with log_src.open("a", encoding="utf-8") as lf:
        lf.write(f"[{_now()}] /run requested\n")
        subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=lf, stderr=subprocess.STDOUT, text=True)
    time.sleep(2)
    status2, _ = _http_get(_service_url() + "/health", timeout=3)
    return {
        "command": "/run",
        "status": "ok" if status2 == 200 else "partial",
        "Summary": "Run command executed.",
        "Run command used": " ".join(cmd),
        "Startup status": "started" if status2 == 200 else "start-requested",
        "Log source": str(log_src),
    }


def _cmd_test(command_text: str) -> dict:
    return run_test_command(command_text)


def _cmd_status() -> dict:
    st, health = _http_get(_service_url() + "/health", timeout=3)
    err = _cmd_error()
    g = _run_git(["status", "--porcelain"])
    dirty = _parse_status_paths(g.stdout) if g.returncode == 0 else []
    return {
        "command": "/status",
        "status": "ok",
        "System status summary": {"app_running": st == 200, "health": health[:120], "timestamp": _now()},
        "Health by subsystem": {"logs_dir": str(LOGS_DIR), "git_dirty_count": len(dirty)},
        "Recent issues": {"error_summary": err.get("## Error summary", ""), "error_category": err.get("## Error category", "unknown")},
        "Recommended next action": "/test" if st == 200 else "/run",
    }


def _cmd_features() -> dict:
    return {
        "command": "/features",
        "status": "ok",
        "Feature inventory": {
            "video pipeline": "implemented",
            "browser/profile": "implemented",
            "login/auth": "implemented",
            "proxy": "implemented",
            "upload": "implemented",
            "scheduling": "implemented",
            "ui": "partial",
            "commands/devtools": "implemented",
            "logs/diagnostics": "implemented",
            "configuration/storage": "implemented",
        },
        "Quality assessment": "Core flows exist; external UI and service dependencies remain main flake risk.",
        "Missing capability map": ["deterministic browser e2e harness", "selector drift monitoring"],
        "Suggested roadmap priorities": ["stabilize selector packs", "expand structured error_code coverage"],
    }


def execute_dev_command(command_text: str) -> dict:
    cmd = (command_text or "").strip()
    if not cmd:
        raise ValueError("command is required")
    if cmd.startswith("/run"):
        return _cmd_run()
    if cmd.startswith("/test"):
        return _cmd_test(cmd)
    if cmd.startswith("/error"):
        return _cmd_error()
    if cmd.startswith("/fix"):
        return _cmd_fix()
    if cmd.startswith("/status"):
        return _cmd_status()
    if cmd.startswith("/commit"):
        return _cmd_commit(cmd)
    if cmd.startswith("/features"):
        return _cmd_features()
    raise ValueError("Unsupported command. Supported commands: /run, /test, /error, /fix, /status, /commit, /features")
