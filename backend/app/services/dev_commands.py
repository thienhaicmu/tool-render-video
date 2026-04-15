import fnmatch
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import CHANNELS_DIR, LOGS_DIR
from app.services.qa_runner import run_test_command


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LAST_ERROR: dict[str, Any] | None = None
_FIX_MODES = {"dev", "force"}
_KNOWN_BUG_CLASSES = {
    "filesystem/render_path",
    "download_format_fallback",
    "upload_selector_wait",
    "login_state",
    "profile_runtime",
    "proxy_runtime",
    "generic",
}


def _fix_feature_registry() -> dict[str, dict[str, Any]]:
    # Extensible registry: add new domain/features here only.
    return {
        "render": {
            "keywords": ["render", "video.render", "ffmpeg"],
            "features": {
                "download": {
                    "keywords": ["download", "youtube", "yt-dlp", "source"],
                    "files": ["backend/app/services/downloader.py", "backend/app/routes/render.py"],
                    "workflow_steps": ["video.download"],
                    "bug_classes": ["download_format_fallback"],
                    "fix_strategy": "targeted-download-fallback",
                    "likely_functions": ["download_youtube", "_try_download", "prepare_source"],
                },
                "scene": {
                    "keywords": ["scene", "cut", "segment", "detect"],
                    "files": ["backend/app/services/scene_detector.py", "backend/app/services/segment_builder.py"],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["generic"],
                    "fix_strategy": "targeted-scene-processing",
                    "likely_functions": ["detect_scenes", "build_segments"],
                },
                "trim_black": {
                    "keywords": ["trim", "black", "intro"],
                    "files": ["backend/app/routes/render.py", "backend/app/services/render_engine.py"],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["filesystem/render_path", "generic"],
                    "fix_strategy": "targeted-black-trim",
                    "likely_functions": ["quick_process"],
                },
                "ffmpeg": {
                    "keywords": ["ffmpeg", "encode", "filter"],
                    "files": ["backend/app/services/render_engine.py", "backend/app/routes/render.py"],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["filesystem/render_path", "generic"],
                    "fix_strategy": "targeted-ffmpeg",
                    "likely_functions": ["quick_process"],
                },
                "output_path": {
                    "keywords": ["output_path", "output", "path", "mkdir"],
                    "files": ["backend/app/routes/render.py", "backend/app/services/render_engine.py"],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["filesystem/render_path"],
                    "fix_strategy": "safe-path-remediation",
                    "likely_functions": ["quick_process", "prepare_source"],
                },
            },
        },
        "upload": {
            "keywords": ["upload", "post"],
            "features": {
                "selector": {
                    "keywords": ["selector", "file", "input", "wait", "ui"],
                    "files": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
                    "workflow_steps": ["upload.file.select", "upload.ui.ready"],
                    "bug_classes": ["upload_selector_wait"],
                    "fix_strategy": "auto_patch_minimal",
                    "likely_functions": ["_upload_once", "_try_select_upload_option", "_wait_upload_started"],
                },
                "submit": {
                    "keywords": ["submit", "post-button", "publish"],
                    "files": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
                    "workflow_steps": ["upload.submit"],
                    "bug_classes": ["generic"],
                    "fix_strategy": "targeted-upload-submit",
                    "likely_functions": ["_upload_once", "_wait_upload_outcome"],
                },
            },
        },
        "login": {
            "keywords": ["login", "auth", "session"],
            "features": {
                "session": {
                    "keywords": ["session", "check", "authenticated", "persist"],
                    "files": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
                    "workflow_steps": ["login.check"],
                    "bug_classes": ["login_state"],
                    "fix_strategy": "targeted-login-state",
                    "likely_functions": ["check_login_with_persistent_profile", "login_with_persistent_profile"],
                }
            },
        },
        "proxy": {
            "keywords": ["proxy", "network"],
            "features": {
                "apply": {
                    "keywords": ["apply", "save", "runtime"],
                    "files": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
                    "workflow_steps": ["proxy.apply"],
                    "bug_classes": ["proxy_runtime"],
                    "fix_strategy": "targeted-proxy-runtime",
                    "likely_functions": ["_build_launch_kwargs", "save_upload_settings"],
                }
            },
        },
        "profile": {
            "keywords": ["profile", "browser-profile"],
            "features": {
                "select": {
                    "keywords": ["select", "create", "reuse"],
                    "files": ["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"],
                    "workflow_steps": ["profile.create/select"],
                    "bug_classes": ["profile_runtime"],
                    "fix_strategy": "targeted-profile-runtime",
                    "likely_functions": ["ensure_upload_account_profile", "_sync_profile_dir_for_browser"],
                }
            },
        },
        "scheduler": {
            "keywords": ["scheduler", "schedule", "rule"],
            "features": {
                "rules": {
                    "keywords": ["rules", "rule", "mapping", "slot"],
                    "files": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
                    "workflow_steps": ["rule.load"],
                    "bug_classes": ["generic"],
                    "fix_strategy": "targeted-scheduler-rules",
                    "likely_functions": ["upload_schedule", "compute_schedule_slots"],
                }
            },
        },
    }


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


def _current_render_job() -> dict[str, Any] | None:
    try:
        from app.services.db import list_jobs
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


def _err_code(text: str) -> str:
    m = re.search(r"\b([A-Z]{2}\d{3,4})\b", text or "")
    return m.group(1) if m else ""


def _to_epoch(ts: str) -> float | None:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        # Supports ISO forms like 2026-04-15T08:00:00Z
        raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw).timestamp()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
    return None


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


def _infer_bug_class(category: str, text: str) -> str:
    t = (text or "").lower()
    if category in {"render", "file system"} and any(
        k in t for k in ["filenotfounderror", "winerror 3", "cannot find the path", "no such file", "not found"]
    ):
        return "filesystem/render_path"
    if category == "download" and any(k in t for k in ["requested format is not available", "tried formats", "yt-dlp"]):
        return "download_format_fallback"
    if category in {"upload", "ui selector/wait"} and any(k in t for k in ["selector", "input[type=file]", "upload ui", "timeout"]):
        return "upload_selector_wait"
    if category == "login":
        return "login_state"
    if category == "browser/profile":
        return "profile_runtime"
    if category == "proxy/network":
        return "proxy_runtime"
    return "generic"


def _interpret_bug(category: str, workflow_step: str, summary: str, snippet: str) -> str:
    merged = f"{summary} {snippet}".lower()
    bug_class = _infer_bug_class(category, merged)
    if bug_class == "filesystem/render_path":
        return (
            "Render/filesystem path bug: runtime path preparation or normalization is producing a missing/invalid path; "
            "output/input parent directory creation or path validation is likely incomplete."
        )
    if bug_class == "upload_selector_wait":
        return (
            "Upload UI bug: selector/readiness detection is failing, likely due to missing fallback selector, hidden input, "
            "or insufficient explicit wait before file selection."
        )
    if bug_class == "download_format_fallback":
        return (
            "Download format bug: format selection is too brittle for current YouTube responses; fallback strategy is insufficient "
            "for available formats/network conditions."
        )
    if category == "proxy/network":
        return "Proxy/network bug: runtime cannot reach required upstream endpoints with current network/proxy configuration."
    if category == "login":
        return "Login flow bug: authentication/session state detection or persistence is failing in current workflow step."
    if category == "browser/profile":
        return "Browser/profile bug: runtime/profile resolution is inconsistent with expected browser/profile state."
    if workflow_step == "unknown":
        return "Bug detected but workflow mapping is incomplete from current logs; inspect traceback/context for precise root cause."
    return f"{category} bug in workflow step '{workflow_step}' based on current log evidence."


def _likely_functions_for_targets(bug_class: str, targets: list[str]) -> list[str]:
    hints: list[str] = []
    lower_targets = " | ".join(targets).lower()
    if bug_class == "filesystem/render_path":
        if "routes\\render.py" in lower_targets or "routes/render.py" in lower_targets:
            hints.append("quick_process")
            hints.append("prepare_source")
        if "services\\render_engine.py" in lower_targets or "services/render_engine.py" in lower_targets:
            hints.append("render pipeline path preparation helper (TODO exact function)")
    if bug_class == "upload_selector_wait":
        hints.extend(["_upload_once", "_try_select_upload_option", "_wait_upload_started"])
    if bug_class == "download_format_fallback":
        hints.extend(["download_youtube", "_try_download", "check_youtube_download_health"])
    if not hints:
        hints.append("TODO infer exact function from traceback/module")
    # de-dup
    out: list[str] = []
    seen = set()
    for h in hints:
        if h not in seen:
            out.append(h)
            seen.add(h)
    return out


def _category_to_domain(category: str) -> str:
    m = {
        "render": "render",
        "download": "render",
        "upload": "upload",
        "ui selector/wait": "upload",
        "login": "login",
        "proxy/network": "proxy",
        "browser/profile": "profile",
        "scheduler/rules": "scheduler",
        "file system": "render",
        "startup/runtime": "render",
    }
    return m.get((category or "").strip().lower(), "")


def _parse_fix_target(command_text: str) -> dict[str, Any]:
    tokens = [t.strip().lower() for t in (command_text or "").split() if t.strip()]
    payload = {
        "domain": "",
        "feature": "",
        "bug_class": "",
        "mode": "",
        "raw_tokens": tokens[1:] if tokens[:1] == ["/fix"] else tokens,
    }
    args = payload["raw_tokens"]
    if not args:
        return payload
    registry = _fix_feature_registry()

    if args and args[-1] in _FIX_MODES:
        payload["mode"] = args[-1]
        args = args[:-1]

    domain = args[0] if args and args[0] in registry else ""
    feature = ""
    bug_class = ""
    rest = args[1:] if domain else args

    if domain and rest:
        if rest[0] in registry[domain]["features"]:
            feature = rest[0]
            rest = rest[1:]

    # Infer domain by feature keyword if domain omitted.
    if not domain and args:
        probe = args[0]
        for d, spec in registry.items():
            if probe in spec.get("features", {}):
                domain = d
                feature = probe
                rest = args[1:]
                break

    # Infer feature by keyword match when domain set.
    if domain and not feature and rest:
        probe = rest[0]
        for f, fs in registry[domain]["features"].items():
            kws = set(fs.get("keywords", []))
            if probe == f or probe in kws:
                feature = f
                rest = rest[1:]
                break

    if rest:
        if rest[0] in _KNOWN_BUG_CLASSES:
            bug_class = rest[0]
        elif re.match(r"^[a-z_/-]+$", rest[0]):
            bug_class = rest[0]

    payload["domain"] = domain
    payload["feature"] = feature
    payload["bug_class"] = bug_class
    return payload


def _registry_target_spec(target: dict[str, Any]) -> dict[str, Any]:
    out = {"files": [], "workflow_steps": [], "bug_classes": [], "fix_strategy": "", "likely_functions": []}
    domain = str(target.get("domain") or "")
    feature = str(target.get("feature") or "")
    if not domain:
        return out
    reg = _fix_feature_registry()
    dom = reg.get(domain)
    if not dom:
        return out
    if feature and feature in dom.get("features", {}):
        fs = dom["features"][feature]
        out.update({
            "files": fs.get("files", []),
            "workflow_steps": fs.get("workflow_steps", []),
            "bug_classes": fs.get("bug_classes", []),
            "fix_strategy": fs.get("fix_strategy", ""),
            "likely_functions": fs.get("likely_functions", []),
        })
        return out
    # Domain only: aggregate.
    files: list[str] = []
    steps: list[str] = []
    bugs: list[str] = []
    funcs: list[str] = []
    for fs in dom.get("features", {}).values():
        files.extend(fs.get("files", []))
        steps.extend(fs.get("workflow_steps", []))
        bugs.extend(fs.get("bug_classes", []))
        funcs.extend(fs.get("likely_functions", []))
    out["files"] = list(dict.fromkeys(files))
    out["workflow_steps"] = list(dict.fromkeys(steps))
    out["bug_classes"] = list(dict.fromkeys(bugs))
    out["likely_functions"] = list(dict.fromkeys(funcs))
    return out


def _narrow_targets_with_registry(
    likely_targets: list[str],
    likely_functions: list[str],
    workflow_step: str,
    bug_class: str,
    category: str,
    target: dict[str, Any],
) -> tuple[list[str], list[str], str, str, dict[str, Any]]:
    spec = _registry_target_spec(target)
    if not spec["files"] and not spec["workflow_steps"] and not spec["bug_classes"]:
        return likely_targets, likely_functions, workflow_step, bug_class, spec

    reg_files = _existing_repo_files(spec["files"])
    if reg_files:
        intersect = [p for p in likely_targets if p in reg_files]
        likely_targets = intersect or reg_files
    if spec["likely_functions"]:
        merged = list(dict.fromkeys([*spec["likely_functions"], *likely_functions]))
        likely_functions = merged
    if spec["workflow_steps"]:
        if not workflow_step or workflow_step == "unknown":
            workflow_step = spec["workflow_steps"][0]
    if target.get("bug_class"):
        bug_class = str(target.get("bug_class"))
    elif spec["bug_classes"]:
        # If user's domain target differs from current error domain, use feature bug-class default.
        current_domain = _category_to_domain(category)
        if target.get("domain") and target.get("domain") != current_domain:
            bug_class = spec["bug_classes"][0]
    return likely_targets, likely_functions, workflow_step, bug_class, spec


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


def _choose_error() -> dict[str, Any]:
    entries = []
    src_rank = {"current job": 60, "current session": 30, "historical fallback": 10}
    active_jobs = {jid for jid, _ in _current_jobs()}
    session_start_epoch = _latest_session_start_epoch()
    for p, typ in _discover_logs():
        try:
            entries.extend(_parse_entries(p, typ))
        except Exception:
            continue
    if not entries:
        return {"status": "noop", "summary": "No relevant ERROR/CRITICAL entries found."}

    for e in entries:
        e["error_source_type"] = _source_type_for_entry(e, active_jobs, session_start_epoch)

    current_job_entries = [e for e in entries if e.get("error_source_type") == "current job"]
    current_session_entries = [e for e in entries if e.get("error_source_type") == "current session"]
    if current_job_entries:
        candidates = current_job_entries
    elif current_session_entries:
        candidates = current_session_entries
    else:
        candidates = entries

    def _signal_score(e: dict) -> int:
        msg = str(e.get("message") or "")
        raw = " ".join([msg, str(e.get("exception") or ""), str(e.get("traceback") or "")]).lower()
        score = 0
        if re.search(r"\b(error:|exception|traceback)\b", raw):
            score += 14
        if "prepare-source error" in raw or "download attempt failed" in raw:
            score += 10
        if str(e.get("event") or "").strip():
            score += 4
        if str(e.get("module") or "").strip():
            score += 4
        if str(e.get("step") or "").strip():
            score += 4
        if "http/1.1" in raw and "500 internal server error" in raw and not re.search(r"\b(error:|exception|traceback)\b", raw):
            score -= 12
        return score

    def rank(e: dict) -> tuple[int, int, int]:
        score = src_rank.get(str(e.get("error_source_type") or ""), 0) + _severity(str(e.get("level") or "")) * 10
        if e.get("error_code"):
            score += 15
        if e.get("event"):
            score += 8
        if e.get("module"):
            score += 5
        if e.get("step"):
            score += 3
        score += _signal_score(e)
        return score, int(e.get("entry_epoch") or 0), int(e.get("line_no") or 0)

    chosen = max(candidates, key=rank)
    lines = chosen.get("_lines") or []
    i = int(chosen.get("line_no") or 0)
    snippet = "\n".join(lines[max(0, i - 6): min(len(lines), i + 7)])
    code = str(chosen.get("error_code") or "")
    summary_text = str(chosen.get("message") or chosen.get("exception") or "Error detected")
    if re.match(r"^\s*(traceback|exception)\b", summary_text, re.IGNORECASE):
        detail_lines = [ln.strip() for ln in snippet.splitlines() if re.search(r"(Error|Exception):", ln)]
        if detail_lines:
            summary_text = detail_lines[-1]
    full_text = " ".join(
        [summary_text, str(chosen.get("exception") or ""), str(chosen.get("traceback") or ""), str(chosen.get("event") or ""), str(chosen.get("module") or ""), str(chosen.get("step") or ""), snippet]
    )
    category = _classify(full_text, code)
    workflow_step = _workflow_step_label(chosen, category)
    bug_class = _infer_bug_class(category, full_text)
    bug_interpretation = _interpret_bug(category, workflow_step, summary_text, snippet)
    chosen["_derived_category"] = category
    chosen["_derived_workflow_step"] = workflow_step
    code_infer = _infer_code_targets(chosen)
    source_type = str(chosen.get("error_source_type") or "historical fallback")
    root_cause = f"Likely {category} issue in application logic (not log file)."
    if source_type == "historical fallback":
        root_cause += " Current-session error signal not found; using historical fallback."
    if bug_class == "filesystem/render_path":
        root_cause = (
            "Likely invalid/missing runtime path composition for render I/O; parent directory creation or path normalization "
            "is not consistent with current execution context."
        )
    return {
        "status": "ok",
        "summary": summary_text,
        "category": category,
        "bug_class": bug_class,
        "bug_interpretation": bug_interpretation,
        "error_code": code,
        "error_source_type": source_type,
        "workflow_step": workflow_step,
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
        "root_cause": root_cause,
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
        "scheduler/rules": ["Validate schedule slot/timezone config and job state updates.", "Validate rule/channel mapping inputs."],
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
        "render": ["backend/app/routes/render.py", "backend/app/services/render_engine.py"],
        "db": ["backend/app/services/db.py"],
        "main": ["backend/app/main.py"],
    }
    return table.get(m, [])


def _workflow_step_map(step: str) -> list[str]:
    s = (step or "").strip().lower()
    if s in {"upload.file.select", "upload.ui.ready", "upload.submit"}:
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if s in {"video.download"}:
        return ["backend/app/services/downloader.py", "backend/app/routes/render.py"]
    if s in {"video.render"}:
        return ["backend/app/routes/render.py", "backend/app/services/render_engine.py"]
    if s in {"login.check"}:
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if s in {"profile.create/select"}:
        return ["backend/app/services/upload_engine.py", "backend/app/routes/channels.py"]
    if s in {"proxy.apply"}:
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if s in {"rule.load"}:
        return ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"]
    if s in {"app.start"}:
        return ["backend/app/main.py", "backend/app/services/db.py"]
    return []


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
    derived_category = str(parsed.get("_derived_category") or "").strip()
    wf_step = str(parsed.get("_derived_workflow_step") or "").strip()
    if not derived_category:
        derived_category = _classify(
            " ".join(str(parsed.get(k) or "") for k in ["message", "exception", "traceback", "event", "module", "step"]),
            str(parsed.get("error_code") or ""),
        )
    if not wf_step:
        wf_step = _workflow_step_label(parsed, derived_category)
    workflow_files = _existing_repo_files(_workflow_step_map(wf_step))
    module_files = _existing_repo_files(_module_map(str(parsed.get("module") or "")))
    event_files = _existing_repo_files(_event_map(str(parsed.get("event") or "")))
    code_files = _existing_repo_files(_error_code_map(str(parsed.get("error_code") or "")))
    ctx_files = _existing_repo_files(_context_map(parsed.get("context") or {}, str(parsed.get("message") or "")))

    ordered = []
    for bucket in [tb_files, workflow_files, module_files, event_files, code_files, ctx_files]:
        for f in bucket:
            if f not in ordered:
                ordered.append(f)

    module = str(parsed.get("module") or "").strip()
    step = str(parsed.get("step") or "").strip()
    category = derived_category
    if category == "upload" and module == "upload_engine":
        human = f"{module or 'upload_engine'} -> {step or 'upload_select_file'} -> upload UI selector/wait logic"
    elif wf_step and wf_step != "unknown":
        human = f"{wf_step} -> {category} logic"
    elif module or step:
        human = " -> ".join([x for x in [module, step, f"{category} logic"] if x])
    else:
        human = f"{category} logic"
    return {
        "targets": ordered,
        "human": human,
        "priority_sources": {
            "traceback": tb_files,
            "workflow_step": workflow_files,
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
        "scheduler/rules": ["backend/app/services/upload_engine.py", "backend/app/routes/upload.py"],
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


def _apply_upload_selector_wait_autofix() -> tuple[list[str], list[str], list[str]]:
    """
    Minimal, deterministic auto-fix for high-confidence upload selector/wait bugs.
    Patches only known upload wait/selection logic in upload_engine.py.
    """
    target = PROJECT_ROOT / "backend/app/services/upload_engine.py"
    if not target.exists():
        return [], [], ["upload_engine.py not found"]
    text = target.read_text(encoding="utf-8")
    original = text
    patch_notes: list[str] = []
    warnings: list[str] = []

    old = (
        "            page.goto(upload_url, wait_until=\"domcontentloaded\", timeout=90000)\n"
        "            page.wait_for_timeout(1200)\n"
    )
    new = (
        "            page.goto(upload_url, wait_until=\"domcontentloaded\", timeout=90000)\n"
        "            page.wait_for_timeout(1200)\n"
        "            try:\n"
        "                page.wait_for_load_state(\"networkidle\", timeout=15000)\n"
        "            except Exception:\n"
        "                pass\n"
    )
    if old in text and "wait_for_load_state(\"networkidle\"" not in text:
        text = text.replace(old, new, 1)
        patch_notes.append("Added explicit upload-page readiness wait (networkidle).")

    old = "            input_selector = _wait_any_selector(page, file_input, timeout_ms=30000)\n"
    new = (
        "            input_selector = _wait_any_selector(page, file_input, timeout_ms=45000)\n"
        "            if not input_selector:\n"
        "                _try_select_upload_option(page, selectors)\n"
        "                input_selector = _wait_any_selector(page, file_input, timeout_ms=20000) or _first_existing_selector(page, file_input)\n"
    )
    if old in text and "timeout_ms=45000" not in text:
        text = text.replace(old, new, 1)
        patch_notes.append("Strengthened file-input selector wait with fallback retry path.")

    old = (
        "            if not input_selector:\n"
        "                _screenshot_on_error(page, \"upload_input_not_found\")\n"
        "                raise RuntimeError(\"Upload file input is not available on upload screen.\")\n"
    )
    new = (
        "            if not input_selector:\n"
        "                _screenshot_on_error(page, \"upload_input_not_found\")\n"
        "                raise RuntimeError(\"Upload file input is not available on upload screen after readiness checks.\")\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        patch_notes.append("Improved missing-input error clarity.")

    old = "            page.set_input_files(input_selector, str(video_path))\n"
    new = (
        "            try:\n"
        "                page.set_input_files(input_selector, str(video_path))\n"
        "            except Exception:\n"
        "                page.locator(input_selector).first.set_input_files(str(video_path))\n"
    )
    if old in text and "page.locator(input_selector).first.set_input_files" not in text:
        text = text.replace(old, new, 1)
        patch_notes.append("Added resilient set_input_files fallback via locator().first.")

    old = "        \"text=/0%|1%|2%|3%|4%|5%/i\",\n"
    new = "        \"text=/\\\\b\\\\d{1,3}%\\\\b/i\",\n"
    if old in text:
        text = text.replace(old, new, 1)
        patch_notes.append("Broadened upload-progress marker detection from 0-5% to generic percent pattern.")

    if text == original:
        warnings.append("No deterministic upload selector/wait patch point found.")
        return [], patch_notes, warnings

    target.write_text(text, encoding="utf-8")
    return [str(target)], patch_notes, warnings


def _cmd_error() -> dict:
    global _LAST_ERROR
    parsed = _choose_error()
    _LAST_ERROR = parsed
    return {
        "command": "/error",
        "status": parsed.get("status", "ok"),
        "## Error source type": parsed.get("error_source_type", "historical fallback"),
        "## Log source": parsed.get("log_source", ""),
        "## Error timestamp": (parsed.get("context") or {}).get("timestamp", ""),
        "## Error summary": parsed.get("summary", ""),
        "## Error category": parsed.get("category", "unknown"),
        "## Error code": parsed.get("error_code", ""),
        "## Workflow step": parsed.get("workflow_step", "unknown"),
        "## Module / likely code area": parsed.get("likely_code_area", ""),
        "## Relevant context": parsed.get("context", {}),
        "## Bug interpretation": parsed.get("bug_interpretation", ""),
        "## Likely root cause": parsed.get("root_cause", ""),
        "## Suggested next actions": parsed.get("actions", []),
    }


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


def _cmd_fix(command_text: str) -> dict:
    global _LAST_ERROR
    parsed = _LAST_ERROR or _choose_error()
    category = parsed.get("category", "unknown")
    workflow_step = str(parsed.get("workflow_step") or "unknown")
    bug_class = str(parsed.get("bug_class") or _infer_bug_class(str(category), str(parsed.get("summary") or "")))
    fix_target = _parse_fix_target(command_text)
    ctx = parsed.get("context", {}) if isinstance(parsed.get("context"), dict) else {}
    snippet = str(ctx.get("snippet", ""))
    summary = str(parsed.get("summary") or "")
    changes: list[str] = []
    patch: list[str] = []
    status = "noop"
    risks: list[str] = []
    target_info = _infer_code_targets(parsed.get("parsed", {}) if isinstance(parsed.get("parsed"), dict) else {})
    likely_targets = target_info.get("targets") or _target_files(category)
    likely_functions = _likely_functions_for_targets(bug_class, likely_targets)
    likely_targets, likely_functions, workflow_step, bug_class, target_spec = _narrow_targets_with_registry(
        likely_targets=likely_targets,
        likely_functions=likely_functions,
        workflow_step=workflow_step,
        bug_class=bug_class,
        category=str(category),
        target=fix_target,
    )
    merged_text = f"{summary}\n{snippet}"

    if bug_class == "filesystem/render_path":
        for p in _extract_paths(merged_text):
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
            patch.append("Applied safe runtime path remediation for detected render/filesystem bug.")
        else:
            status = "planned"
            patch.append("Path bug detected but no missing directory target could be created from current evidence.")
            patch.append(f"Likely files: {likely_targets or ['unknown']}")
            patch.append(f"Likely functions: {likely_functions}")
            risks.append("Manual code-level patch likely required for path composition/validation.")

    elif bug_class == "upload_selector_wait":
        # High-confidence auto-patch when upload-engine target is clearly identified.
        has_upload_engine_target = any(str(p).replace("\\", "/").endswith("backend/app/services/upload_engine.py") for p in likely_targets)
        has_key_functions = any(fn in likely_functions for fn in ["_upload_once", "_try_select_upload_option", "_wait_upload_started"])
        if has_upload_engine_target and has_key_functions:
            changed, patch_notes, patch_warnings = _apply_upload_selector_wait_autofix()
            if changed:
                status = "ok"
                changes.extend(changed)
                patch.append("Applied minimal upload selector/wait auto-fix in upload engine.")
                patch.extend(patch_notes)
                if patch_warnings:
                    risks.extend(patch_warnings)
            else:
                status = "planned"
                patch.append("Upload selector bug recognized, but deterministic patch points were not found.")
                patch.append(f"Likely files: {likely_targets or ['unknown']}")
                patch.append(f"Likely functions: {likely_functions}")
                if patch_notes:
                    patch.extend(patch_notes)
                if patch_warnings:
                    risks.extend(patch_warnings)
        else:
            status = "planned"
            patch.append("Upload selector bug recognized but confidence is not high enough for auto-patch.")
            patch.append(f"Likely files: {likely_targets or ['unknown']}")
            patch.append(f"Likely functions: {likely_functions}")
            risks.append("Likely target function set is incomplete.")

    elif bug_class in {"download_format_fallback", "login_state", "profile_runtime", "proxy_runtime"}:
        status = "planned"
        patch.append("Recognized bug class; automatic code patch skipped to avoid risky behavior changes.")
        patch.append(f"Likely files: {likely_targets or ['unknown']}")
        patch.append(f"Likely functions: {likely_functions}")
        if target_info.get("human"):
            patch.append(f"Likely code area: {target_info.get('human')}")
        if workflow_step and workflow_step != "unknown":
            patch.append(f"Workflow step: {workflow_step}")
        risks.append("Manual confirmation required before editing workflow automation/download logic.")

    if status == "noop":
        status = "planned"
        patch.append("Auto-fix confidence is low for current bug evidence.")
        patch.append(f"Likely files: {likely_targets or ['unknown']}")
        patch.append(f"Likely functions: {likely_functions}")
        if target_info.get("human"):
            patch.append(f"Likely code area: {target_info.get('human')}")
        if workflow_step and workflow_step != "unknown":
            patch.append(f"Workflow step: {workflow_step}")
        risks.append("Manual confirmation required before code edits.")

    return {
        "command": "/fix",
        "status": status,
        "## Summary": "Applied minimal automatic patch." if status == "ok" else "Prepared targeted fix plan.",
        "## Target domain": fix_target.get("domain", ""),
        "## Target feature": fix_target.get("feature", ""),
        "## Current error used": {
            "source_type": parsed.get("error_source_type", "historical fallback"),
            "summary": parsed.get("summary", ""),
            "category": category,
            "error_code": parsed.get("error_code", ""),
        },
        "## Bug class": bug_class,
        "## Workflow step targeted": workflow_step,
        "## Root cause targeted": category,
        "## Fix strategy": (
            "safe-path-remediation"
            if (status == "ok" and bug_class == "filesystem/render_path")
            else ("auto_patch_minimal" if (status == "ok" and bug_class == "upload_selector_wait") else (target_spec.get("fix_strategy") or "manual-targeted-recommendation"))
        ),
        "## Files changed": changes,
        "## Patch summary": patch,
        "## Risks / assumptions": risks or ["Auto-fix is conservative by design."],
        "## Recommended next command": "/test dev" if status != "ok" else "/test",
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
