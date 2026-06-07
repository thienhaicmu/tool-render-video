"""Bug classification + error analysis + the ``/error`` command.

Audit MT-1 (Batch 10J 2026-06-06): extracted verbatim from
``app.services.dev_commands``. Owns:

- The ``_KNOWN_BUG_CLASSES`` constant and the rule-based bug
  classification helpers (``_infer_bug_class``, ``_interpret_bug``,
  ``_category_to_domain``, ``_likely_functions_for_targets``).
- The ``_choose_error`` log-scoring routine and its ``_actions_for``
  recommendation table.
- The ``_cmd_error`` handler and the cross-command ``_LAST_ERROR``
  state with explicit ``get_last_error`` / ``set_last_error`` accessors
  (consumed by ``app.services.dev.autofix._cmd_fix``).

``_choose_error`` calls ``autofix._infer_code_targets`` via a lazy
import inside the function body to avoid an import cycle (autofix
also imports ``_choose_error`` from here).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.dev._shared import _severity
from app.services.dev.log import (
    _classify,
    _current_jobs,
    _discover_logs,
    _latest_session_start_epoch,
    _parse_entries,
    _source_type_for_entry,
    _workflow_step_label,
)


_KNOWN_BUG_CLASSES = {
    "filesystem/render_path",
    "download_format_fallback",
    "upload_selector_wait",
    "login_state",
    "profile_runtime",
    "proxy_runtime",
    "generic",
}


# Cross-command state: ``_cmd_error`` populates this so a subsequent
# ``_cmd_fix`` invocation can act on the same parsed entry without
# re-running the heavy log scan. Kept private; touch via the
# get_/set_ accessors below so the storage location can move later
# without ripple-edits.
_LAST_ERROR: dict[str, Any] | None = None


def get_last_error() -> dict[str, Any] | None:
    """Return the last error parsed by ``_cmd_error`` (or None)."""
    return _LAST_ERROR


def set_last_error(parsed: dict[str, Any] | None) -> None:
    """Update the last-error slot. Used by ``_cmd_error`` to record
    the value for the next ``_cmd_fix`` call."""
    global _LAST_ERROR
    _LAST_ERROR = parsed


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


def _choose_error() -> dict[str, Any]:
    # Lazy import breaks the bug ↔ autofix circular dependency.
    from app.services.dev.autofix import _infer_code_targets

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


def _cmd_error() -> dict:
    parsed = _choose_error()
    set_last_error(parsed)
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
