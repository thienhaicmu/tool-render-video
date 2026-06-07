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
    import json
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
