"""Dispatcher + simple command handlers.

Audit MT-1 (Batch 10J 2026-06-06): the top of the decomposition. Owns:

- The ``execute_dev_command`` dispatcher (the sole public surface of
  the dev/ package, consumed by ``routes/devtools.py``).
- The simple commands that don't justify their own file: ``/run``,
  ``/test``, ``/commit``, ``/status``, ``/features``.

The heavier handlers live in their own sub-modules:
``log._cmd_log``, ``bug._cmd_error``, ``autofix._cmd_fix``.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import time

from app.core.config import LOGS_DIR

from app.services.dev._shared import (
    PROJECT_ROOT,
    _http_get,
    _now,
    _run_git,
    _service_url,
)
from app.services.dev.autofix import _cmd_fix
from app.services.dev.bug import _cmd_error
from app.services.dev.log import _cmd_log


# ── /commit support helpers ────────────────────────────────────────────────


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


# ── Simple command handlers ────────────────────────────────────────────────


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
        subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=lf, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
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
    from app.services.qa_runner import run_test_command
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


# ── Public dispatcher ──────────────────────────────────────────────────────


def execute_dev_command(command_text: str) -> dict:
    """Dispatch a /-prefixed dev command to its handler.

    Public surface — consumed by ``app.routes.devtools.run_dev_command``.
    Adding a new command means registering it here and writing its
    handler in the appropriate sub-module.
    """
    cmd = (command_text or "").strip()
    if not cmd:
        raise ValueError("command is required")
    if cmd.startswith("/run"):
        return _cmd_run()
    if cmd.startswith("/test"):
        return _cmd_test(cmd)
    if cmd.startswith("/log"):
        return _cmd_log(cmd)
    if cmd.startswith("/error"):
        return _cmd_error()
    if cmd.startswith("/fix"):
        return _cmd_fix(cmd)
    if cmd.startswith("/status"):
        return _cmd_status()
    if cmd.startswith("/commit"):
        return _cmd_commit(cmd)
    if cmd.startswith("/features"):
        return _cmd_features()
    raise ValueError("Unsupported command. Supported commands: /run, /test, /log, /error, /fix, /status, /commit, /features")
