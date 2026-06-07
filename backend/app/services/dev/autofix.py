"""Autofix machinery + the ``/fix`` command.

Audit MT-1 (Batch 10J 2026-06-06): extracted verbatim from
``app.services.dev_commands``. Owns the code-target inference helpers
(``_traceback_project_files``, ``_module_map``, ``_workflow_step_map``,
``_event_map``, ``_error_code_map``, ``_context_map``,
``_infer_code_targets``, ``_extract_paths``, ``_target_files``), the
deterministic patcher (``_apply_upload_selector_wait_autofix``), and
the ``/fix`` command handler.

``_choose_error`` is imported from ``bug.py`` at call time inside
``_cmd_fix`` to mirror the lazy-import pattern bug.py uses for
``_infer_code_targets`` — the two modules form a single ranking-then-
patching loop but each exposes its own command handler.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.dev._shared import (
    PROJECT_ROOT,
    _existing_repo_files,
)
from app.services.dev.bug import (
    _infer_bug_class,
    _likely_functions_for_targets,
    get_last_error,
)
from app.services.dev.log import _classify, _workflow_step_label
from app.services.dev.registry import _narrow_targets_with_registry, _parse_fix_target


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
    """Map a log module name → candidate file paths in the live tree.

    Batch 10M cleanup: dropped ``upload_engine`` + ``channel_service``'s
    stale ``routes/channels.py`` partner. The upload subsystem was retired
    in Phase 4F.5A; channel_service still exists but its old route was
    deleted in Batch 10H. ``services/db.py`` was retired in Batch 9.
    """
    m = (module or "").strip().lower()
    table = {
        "render_engine":   ["backend/app/features/render/engine/pipeline/render_pipeline.py",
                            "backend/app/features/render/router.py"],
        "downloader":      ["backend/app/features/download/engine/downloader.py"],
        "channel_service": ["backend/app/services/channel_service.py"],
        "render":          ["backend/app/features/render/router.py",
                            "backend/app/features/render/engine/pipeline/render_pipeline.py"],
        "main":            ["backend/app/main.py"],
    }
    return table.get(m, [])


def _workflow_step_map(step: str) -> list[str]:
    """Batch 10M cleanup: dropped the upload / login / profile / proxy /
    rule.load steps; their backing files were deleted with the upload
    subsystem retirement. ``app.start`` no longer points at the retired
    ``services/db.py``."""
    s = (step or "").strip().lower()
    if s == "video.download":
        return ["backend/app/features/download/engine/downloader.py"]
    if s == "video.render":
        return ["backend/app/features/render/router.py",
                "backend/app/features/render/engine/pipeline/render_pipeline.py"]
    if s == "app.start":
        return ["backend/app/main.py"]
    return []


def _event_map(event: str) -> list[str]:
    """Batch 10M cleanup: dropped upload / login / proxy / profile event
    prefixes (their files are gone). ``render.*`` events now point at the
    feature-layer paths."""
    e = (event or "").strip().lower()
    if e.startswith("video.download"):
        return ["backend/app/features/download/engine/downloader.py"]
    if e.startswith("render."):
        return ["backend/app/features/render/router.py",
                "backend/app/features/render/engine/pipeline/render_pipeline.py"]
    return []


def _error_code_map(code: str) -> list[str]:
    """Batch 10M cleanup: error-code families LG / UP / PX / BR / SC pointed
    at retired upload files. They now return [] so the orchestrator falls
    back to other inference signals (traceback / module / context). RT no
    longer cites ``services/db.py``."""
    c = (code or "").strip().upper()
    fam = c[:2]
    maps = {
        "DL": ["backend/app/features/download/engine/downloader.py"],
        "RN": ["backend/app/features/render/router.py",
               "backend/app/features/render/engine/pipeline/render_pipeline.py"],
        "FS": ["backend/app/features/render/router.py",
               "backend/app/services/channel_service.py"],
        "RT": ["backend/app/main.py"],
    }
    return maps.get(fam, [])


def _context_map(context: dict[str, Any], message: str = "") -> list[str]:
    """Batch 10M cleanup: dropped selector / browser / profile heuristics
    (their files are gone). Kept the path-related and url-related cues
    because they still map to live render / downloader files."""
    import json
    ctext = " ".join([str(message or ""), json.dumps(context or {}, ensure_ascii=False)])
    ctext = ctext.lower()
    out: list[str] = []
    if any(k in ctext for k in ["file_path", "output", "root folder", "path", "permission denied"]):
        out.extend(["backend/app/features/render/router.py",
                    "backend/app/services/channel_service.py"])
    if any(k in ctext for k in ["url", "video_id", "youtube"]):
        out.extend(["backend/app/features/download/engine/downloader.py"])
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
    # Batch 10M cleanup: removed the upload-engine special case (subsystem
    # was retired in Phase 4F.5A). The generic branches below cover what
    # remains — render / download / generic logs.
    if wf_step and wf_step != "unknown":
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
    """Batch 10M cleanup: dropped login / upload / browser-profile /
    proxy-network / scheduler-rules / ui-selector categories — their
    files are gone with the upload subsystem retirement. ``startup/runtime``
    no longer cites the retired ``services/db.py``."""
    maps = {
        "download":         ["backend/app/features/download/engine/downloader.py"],
        "render":           ["backend/app/features/render/router.py",
                             "backend/app/features/render/engine/pipeline/render_pipeline.py"],
        "file system":      ["backend/app/features/render/router.py",
                             "backend/app/services/channel_service.py"],
        "startup/runtime":  ["backend/app/main.py"],
    }
    out = []
    for rel in maps.get(category, []):
        p = (PROJECT_ROOT / rel)
        if p.exists():
            out.append(str(p))
    return out


# Batch 10M cleanup (2026-06-06): ``_apply_upload_selector_wait_autofix``
# removed. It patched ``backend/app/services/upload_engine.py``, which was
# deleted with the Phase 4F.5A upload subsystem retirement. The
# ``upload_selector_wait`` bug class still exists in ``bug.py`` for
# historical-log compatibility, but ``/fix`` no longer attempts an
# auto-patch for it — it falls through to the planned/manual-fix path.


def _cmd_fix(command_text: str) -> dict:
    # Lazy import to mirror the bug.py ↔ autofix.py loop: _choose_error
    # lives in bug.py and is also what /error calls, so we read it via
    # the public surface there.
    from app.services.dev.bug import _choose_error

    parsed = get_last_error() or _choose_error()
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

    elif bug_class in {"download_format_fallback", "login_state",
                       "profile_runtime", "proxy_runtime", "upload_selector_wait"}:
        # Batch 10M: ``upload_selector_wait`` now falls into this planned-fix
        # bucket alongside the other manual-confirmation classes. The
        # auto-patch helper that used to run here patched the deleted
        # ``services/upload_engine.py`` and was removed.
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
            else (target_spec.get("fix_strategy") or "manual-targeted-recommendation")
        ),
        "## Files changed": changes,
        "## Patch summary": patch,
        "## Risks / assumptions": risks or ["Auto-fix is conservative by design."],
        "## Recommended next command": "/test dev" if status != "ok" else "/test",
    }
