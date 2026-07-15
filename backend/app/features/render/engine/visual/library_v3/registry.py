"""Manifest I/O and quality validation for Visual Library V3.

This registry validates authored inventory only. It intentionally exposes no
search, scoring or matching API.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .contracts import ASPECTS, CHARACTER_FRAMINGS, QUALITY_STATES, ArtifactSpec, VisualLibraryManifest

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,127}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_CHARACTER_MASTERS = {"full_body", "waist_up", "bust"}


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    location: str
    message: str


class ManifestValidationError(ValueError):
    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(f"{item.location}: {item.message}" for item in self.issues[:6])
        super().__init__(summary or "invalid Visual Library V3 manifest")


def _issue(out: list[ValidationIssue], severity: str, code: str, location: str, message: str) -> None:
    out.append(ValidationIssue(severity, code, location, message))


def _validate_id(out: list[ValidationIssue], value: str, location: str) -> None:
    if not _ID_RE.fullmatch(value or ""):
        _issue(out, "error", "invalid_id", location, "must be a stable lowercase id")


def _validate_version(out: list[ValidationIssue], value: str, location: str) -> None:
    if not _SEMVER_RE.fullmatch(value or ""):
        _issue(out, "error", "invalid_version", location, "must use semantic version x.y.z")


def _validate_artifact(
    out: list[ValidationIssue], artifact: ArtifactSpec, location: str, *,
    quality_state: str, root: Path | None,
) -> None:
    if not artifact.path:
        _issue(out, "error", "missing_artifact_path", location, "artifact path is required")
        return
    raw = Path(artifact.path)
    if raw.is_absolute() or ".." in raw.parts:
        _issue(out, "error", "unsafe_artifact_path", location, "artifact path must stay relative to the library root")
    if artifact.width <= 0 or artifact.height <= 0:
        _issue(out, "error", "invalid_dimensions", location, "positive width and height are required")
    if artifact.sha256 and not _SHA256_RE.fullmatch(artifact.sha256):
        _issue(out, "error", "invalid_sha256", location, "sha256 must contain 64 lowercase hex characters")
    if quality_state in ("review", "active") and not artifact.sha256:
        _issue(out, "error", "missing_sha256", location, "review/active artifacts require a content hash")
    if root is not None and not raw.is_absolute() and ".." not in raw.parts:
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            _issue(out, "error", "unsafe_artifact_path", location, "artifact resolves outside the library root")
        else:
            if not candidate.is_file():
                severity = "error" if quality_state in ("review", "active") else "warning"
                _issue(out, severity, "missing_artifact", location, f"file not found: {artifact.path}")


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    return {value for value in values if value in seen or seen.add(value)}


def validate_manifest(manifest: VisualLibraryManifest, *, root: str | Path | None = None) -> list[ValidationIssue]:
    """Return deterministic validation issues without mutating the manifest."""
    out: list[ValidationIssue] = []
    root_path = Path(root).resolve() if root is not None else None
    if manifest.schema_version != "3.0":
        _issue(out, "error", "unsupported_schema", "schema_version", "expected Visual Library schema 3.0")
    _validate_id(out, manifest.library_id, "library_id")
    _validate_version(out, manifest.version, "version")

    for sid in manifest.style_ids:
        _validate_id(out, sid, f"style_ids.{sid}")
    if duplicates := _duplicates(manifest.style_ids):
        for sid in sorted(duplicates):
            _issue(out, "error", "duplicate_style", f"style_ids.{sid}", "style id is duplicated")

    template_ids = {item.id for item in manifest.character_templates}
    scene_template_ids = {item.id for item in manifest.scene_templates}
    for duplicate in sorted(_duplicates(item.id for item in manifest.character_templates)):
        _issue(out, "error", "duplicate_character_template", f"character_templates.{duplicate}", "template id is duplicated")
    for duplicate in sorted(_duplicates(item.id for item in manifest.scene_templates)):
        _issue(out, "error", "duplicate_scene_template", f"scene_templates.{duplicate}", "template id is duplicated")

    for item in manifest.character_templates:
        loc = f"character_templates.{item.id}"
        _validate_id(out, item.id, loc)
        _validate_version(out, item.version, f"{loc}.version")
        if item.style_id not in manifest.style_ids:
            _issue(out, "error", "unknown_style", f"{loc}.style_id", "style is not declared by the manifest")
        unknown = set(item.supported_framings) - set(CHARACTER_FRAMINGS)
        if unknown:
            _issue(out, "error", "invalid_framing", f"{loc}.supported_framings", f"unsupported values: {sorted(unknown)}")
        if not item.layer_slots:
            _issue(out, "warning", "missing_layer_contract", f"{loc}.layer_slots", "template cannot be remastered by layers")

    for item in manifest.scene_templates:
        loc = f"scene_templates.{item.id}"
        _validate_id(out, item.id, loc)
        _validate_version(out, item.version, f"{loc}.version")
        if item.style_id not in manifest.style_ids:
            _issue(out, "error", "unknown_style", f"{loc}.style_id", "style is not declared by the manifest")
        unknown = set(item.supported_aspects) - set(ASPECTS)
        if unknown:
            _issue(out, "error", "invalid_aspect", f"{loc}.supported_aspects", f"unsupported values: {sorted(unknown)}")

    character_ids = {item.id for item in manifest.characters}
    scene_ids = {item.id for item in manifest.scenes}
    for duplicate in sorted(_duplicates(item.id for item in manifest.characters)):
        _issue(out, "error", "duplicate_character", f"characters.{duplicate}", "identity id is duplicated")
    for duplicate in sorted(_duplicates(item.id for item in manifest.scenes)):
        _issue(out, "error", "duplicate_scene", f"scenes.{duplicate}", "scene id is duplicated")

    for item in manifest.characters:
        loc = f"characters.{item.id}"
        _validate_id(out, item.id, loc)
        _validate_version(out, item.version, f"{loc}.version")
        if item.quality_state not in QUALITY_STATES:
            _issue(out, "error", "invalid_quality_state", f"{loc}.quality_state", "unknown quality state")
        if item.template_id not in template_ids:
            _issue(out, "error", "unknown_template", f"{loc}.template_id", "character template is not declared")
        if item.style_id not in manifest.style_ids:
            _issue(out, "error", "unknown_style", f"{loc}.style_id", "style is not declared by the manifest")
        unknown_styles = set(item.compatible_style_ids) - set(manifest.style_ids)
        if unknown_styles:
            _issue(out, "error", "unknown_compatible_style", f"{loc}.compatible_style_ids",
                   f"styles are not declared by the manifest: {sorted(unknown_styles)}")
        if not item.look:
            _issue(out, "error", "missing_look", f"{loc}.look", "visual identity fields are required")
        if not item.signature_features:
            _issue(out, "warning", "generic_identity", f"{loc}.signature_features", "identity has no signature feature")
        if item.quality_state in ("review", "active"):
            missing = _REQUIRED_CHARACTER_MASTERS - {master.framing for master in item.masters}
            if missing:
                _issue(out, "error", "incomplete_master_set", f"{loc}.masters", f"missing required framings: {sorted(missing)}")
            if not item.provenance.source or not item.provenance.license:
                _issue(out, "error", "missing_provenance", f"{loc}.provenance", "review/active identity requires source and license")
        for duplicate in sorted(_duplicates(master.id for master in item.masters)):
            _issue(out, "error", "duplicate_master", f"{loc}.masters.{duplicate}", "master id is duplicated")
        for master in item.masters:
            master_loc = f"{loc}.masters.{master.id}"
            _validate_id(out, master.id, master_loc)
            if master.framing not in CHARACTER_FRAMINGS:
                _issue(out, "error", "invalid_framing", f"{master_loc}.framing", "unsupported character framing")
            _validate_artifact(out, master.artifact, f"{master_loc}.artifact", quality_state=item.quality_state, root=root_path)
            if master.preview_artifact.path:
                _validate_artifact(out, master.preview_artifact, f"{master_loc}.preview_artifact",
                                   quality_state=item.quality_state, root=root_path)
        for index, artifact in enumerate(item.legacy_artifacts):
            _validate_artifact(out, artifact, f"{loc}.legacy_artifacts.{index}", quality_state="draft", root=root_path)

    for item in manifest.scenes:
        loc = f"scenes.{item.id}"
        _validate_id(out, item.id, loc)
        _validate_version(out, item.version, f"{loc}.version")
        if item.quality_state not in QUALITY_STATES:
            _issue(out, "error", "invalid_quality_state", f"{loc}.quality_state", "unknown quality state")
        if item.template_id not in scene_template_ids:
            _issue(out, "error", "unknown_template", f"{loc}.template_id", "scene template is not declared")
        if item.style_id not in manifest.style_ids:
            _issue(out, "error", "unknown_style", f"{loc}.style_id", "style is not declared by the manifest")
        unknown_styles = set(item.compatible_style_ids) - set(manifest.style_ids)
        if unknown_styles:
            _issue(out, "error", "unknown_compatible_style", f"{loc}.compatible_style_ids",
                   f"styles are not declared by the manifest: {sorted(unknown_styles)}")
        if item.quality_state in ("review", "active") and not item.safe_zones:
            _issue(out, "error", "missing_safe_zones", f"{loc}.safe_zones", "review/active scene requires aspect-safe zones")
        if item.quality_state in ("review", "active") and (not item.provenance.source or not item.provenance.license):
            _issue(out, "error", "missing_provenance", f"{loc}.provenance", "review/active scene requires source and license")
        if not item.layers:
            _issue(out, "error", "missing_scene_layers", f"{loc}.layers", "scene requires at least one visual layer")
        for layer, artifact in item.layers.items():
            _validate_artifact(out, artifact, f"{loc}.layers.{layer}", quality_state=item.quality_state, root=root_path)
        for index, artifact in enumerate(item.legacy_artifacts):
            _validate_artifact(out, artifact, f"{loc}.legacy_artifacts.{index}", quality_state="draft", root=root_path)

    valid_targets = character_ids | scene_ids
    for alias, target in sorted(manifest.legacy_aliases.items()):
        if not alias:
            _issue(out, "error", "invalid_legacy_alias", "legacy_aliases", "legacy alias cannot be empty")
        if target not in valid_targets:
            _issue(out, "error", "dangling_legacy_alias", f"legacy_aliases.{alias}", "target identity does not exist")
    return out


def load_manifest(path: str | Path, *, strict: bool = True) -> VisualLibraryManifest:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        manifest = VisualLibraryManifest.from_dict(json.load(handle))
    issues = validate_manifest(manifest, root=source.parent)
    errors = [item for item in issues if item.severity == "error"]
    if strict and errors:
        raise ManifestValidationError(errors)
    return manifest


def write_manifest(manifest: VisualLibraryManifest, path: str | Path, *, validate: bool = True) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if validate:
        errors = [item for item in validate_manifest(manifest, root=destination.parent) if item.severity == "error"]
        if errors:
            raise ManifestValidationError(errors)
    payload = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return destination


__all__ = [
    "ManifestValidationError", "ValidationIssue", "load_manifest",
    "validate_manifest", "write_manifest",
]
