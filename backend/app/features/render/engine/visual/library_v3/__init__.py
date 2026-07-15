"""Versioned, data-first contracts for the Story visual library.

This package owns visual identities, templates, masters, scenes and quality
state. It deliberately does not contain Planner matching or runtime selection.
"""

from .contracts import (
    ArtifactSpec,
    CharacterIdentitySpec,
    CharacterMasterSpec,
    CharacterTemplateSpec,
    ProvenanceSpec,
    SceneIdentitySpec,
    SceneTemplateSpec,
    VisualLibraryManifest,
)
from .registry import ManifestValidationError, load_manifest, validate_manifest, write_manifest
from .character_renderer import (
    build_character_master,
    build_planner_character_inner,
    build_planner_character_master,
    planner_character_look,
    render_identity_master,
    render_planner_character_png,
)
from .active_catalog import ActiveCatalog, load_active_catalog
from .planner_matcher import PROCEDURAL, configured_manifest_path, match_characters
from .artifact_bridge import resolve_character_preview
from .scene_artifact_bridge import resolve_scene_preview
from .scene_matcher import match_scenes

__all__ = [
    "ArtifactSpec",
    "ActiveCatalog",
    "CharacterIdentitySpec",
    "CharacterMasterSpec",
    "CharacterTemplateSpec",
    "build_character_master",
    "build_planner_character_inner",
    "build_planner_character_master",
    "ManifestValidationError",
    "ProvenanceSpec",
    "PROCEDURAL",
    "SceneIdentitySpec",
    "SceneTemplateSpec",
    "VisualLibraryManifest",
    "load_manifest",
    "load_active_catalog",
    "configured_manifest_path",
    "match_characters",
    "resolve_character_preview",
    "resolve_scene_preview",
    "match_scenes",
    "validate_manifest",
    "write_manifest",
    "render_identity_master",
    "render_planner_character_png",
    "planner_character_look",
]
