"""Feature registry + fix-target parsing.

Audit MT-1 (Batch 10J 2026-06-06): extracted verbatim from
``app.services.dev_commands``. The registry maps domain→feature→
{files, workflow_steps, bug_classes, fix_strategy, likely_functions}
so the /fix command can narrow a generic log signal down to a concrete
target.

Note: some file paths inside the registry tables reference modules
that no longer exist (e.g., ``routes/channels.py`` deleted in Batch
10H). The references are static lookup hints; they don't cause runtime
errors. Cleaning them is a separate concern (audit follow-up).
"""
from __future__ import annotations

import re
from typing import Any

from app.services.dev._shared import _existing_repo_files
from app.services.dev.bug import _KNOWN_BUG_CLASSES, _category_to_domain


_FIX_MODES = {"dev", "force"}


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
