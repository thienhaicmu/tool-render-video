"""Feature registry + fix-target parsing.

Audit MT-1 (Batch 10J 2026-06-06): extracted from
``app.services.dev_commands``. The registry maps domain→feature→
{files, workflow_steps, bug_classes, fix_strategy, likely_functions}
so the /fix command can narrow a generic log signal down to a concrete
target.

Batch 10M cleanup (2026-06-06): every entry now points at a path that
exists in the current tree. The pre-Phase-1-18 paths (services/
downloader.py, services/render_engine.py, services/upload_engine.py,
services/scene_detector.py, routes/render.py, routes/channels.py,
routes/upload.py) were left behind by the feature-layer migration and
the Phase 4F.5A upload retirement.

The whole ``upload`` / ``login`` / ``proxy`` / ``profile`` / ``scheduler``
domain tree was removed entirely — those subsystems were retired with
the upload pipeline (FINDING-API05 + the wider Phase 4F.5A purge).
``_apply_upload_selector_wait_autofix`` (which only patched
``upload_engine.py``) was deleted alongside autofix.py's lookup tables.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.dev._shared import _existing_repo_files
from app.services.dev.bug import _KNOWN_BUG_CLASSES, _category_to_domain


_FIX_MODES = {"dev", "force"}


def _fix_feature_registry() -> dict[str, dict[str, Any]]:
    # Extensible registry: add new domain/features here only.
    # File paths are validated against the live tree via
    # tests/test_dev_registry_paths_live.py — adding a stale path will
    # fail the suite.
    return {
        "render": {
            "keywords": ["render", "video.render", "ffmpeg"],
            "features": {
                "download": {
                    "keywords": ["download", "youtube", "yt-dlp", "source"],
                    "files": [
                        "backend/app/features/download/engine/downloader.py",
                        "backend/app/features/render/router.py",
                    ],
                    "workflow_steps": ["video.download"],
                    "bug_classes": ["download_format_fallback"],
                    "fix_strategy": "targeted-download-fallback",
                    "likely_functions": ["download_youtube", "_try_download", "prepare_source"],
                },
                "scene": {
                    "keywords": ["scene", "cut", "segment", "detect"],
                    "files": [
                        "backend/app/features/render/engine/pipeline/scene_detector.py",
                        "backend/app/features/render/engine/pipeline/pipeline_segment_selection.py",
                    ],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["generic"],
                    "fix_strategy": "targeted-scene-processing",
                    "likely_functions": ["detect_scenes", "build_segments"],
                },
                "trim_black": {
                    "keywords": ["trim", "black", "intro"],
                    "files": [
                        "backend/app/features/render/router.py",
                        "backend/app/features/render/engine/pipeline/render_pipeline.py",
                    ],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["filesystem/render_path", "generic"],
                    "fix_strategy": "targeted-black-trim",
                    "likely_functions": ["quick_process"],
                },
                "ffmpeg": {
                    "keywords": ["ffmpeg", "encode", "filter"],
                    "files": [
                        "backend/app/features/render/engine/pipeline/render_pipeline.py",
                        "backend/app/features/render/engine/encoder/ffmpeg_helpers.py",
                    ],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["filesystem/render_path", "generic"],
                    "fix_strategy": "targeted-ffmpeg",
                    "likely_functions": ["quick_process"],
                },
                "output_path": {
                    "keywords": ["output_path", "output", "path", "mkdir"],
                    "files": [
                        "backend/app/features/render/router.py",
                        "backend/app/features/render/engine/pipeline/render_pipeline.py",
                    ],
                    "workflow_steps": ["video.render"],
                    "bug_classes": ["filesystem/render_path"],
                    "fix_strategy": "safe-path-remediation",
                    "likely_functions": ["quick_process", "prepare_source"],
                },
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
