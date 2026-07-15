"""Serializable contracts for Visual Library V3.

The contracts describe authored inventory. They do not infer, rank or match a
Story character to an identity. Keeping that boundary explicit lets the art
library be rebuilt and approved before Planner matching is introduced.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


QUALITY_STATES = ("draft", "review", "active", "deprecated", "quarantined")
CHARACTER_FRAMINGS = (
    "full_body", "three_quarter", "waist_up", "bust", "close_up",
    "profile", "back_three_quarter",
)
ASPECTS = ("16:9", "9:16", "1:1")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(_text(item) for item in value if _text(item))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class ProvenanceSpec:
    source: str = ""
    license: str = ""
    author: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "ProvenanceSpec":
        value = _mapping(data)
        return cls(
            source=_text(value.get("source")),
            license=_text(value.get("license")),
            author=_text(value.get("author")),
        )


@dataclass(frozen=True)
class ArtifactSpec:
    path: str = ""
    sha256: str = ""
    width: int = 0
    height: int = 0
    transparent: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "ArtifactSpec":
        value = _mapping(data)
        try:
            width = int(value.get("width") or 0)
            height = int(value.get("height") or 0)
        except (TypeError, ValueError):
            width, height = 0, 0
        return cls(
            path=_text(value.get("path")),
            sha256=_text(value.get("sha256")).lower(),
            width=width,
            height=height,
            transparent=bool(value.get("transparent")),
        )


@dataclass(frozen=True)
class CharacterTemplateSpec:
    id: str = ""
    version: str = ""
    style_id: str = ""
    renderer_id: str = ""
    anatomy_model: str = ""
    layer_slots: tuple[str, ...] = ()
    supported_framings: tuple[str, ...] = ()
    supported_poses: tuple[str, ...] = ()
    supported_emotions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Any) -> "CharacterTemplateSpec":
        value = _mapping(data)
        return cls(
            id=_text(value.get("id")),
            version=_text(value.get("version")),
            style_id=_text(value.get("style_id")),
            renderer_id=_text(value.get("renderer_id")),
            anatomy_model=_text(value.get("anatomy_model")),
            layer_slots=_tuple(value.get("layer_slots")),
            supported_framings=_tuple(value.get("supported_framings")),
            supported_poses=_tuple(value.get("supported_poses")),
            supported_emotions=_tuple(value.get("supported_emotions")),
        )


@dataclass(frozen=True)
class CharacterMasterSpec:
    id: str = ""
    framing: str = ""
    facing: str = "front"
    outfit_state: str = "base"
    pose: str = "stand"
    emotion: str = "neutral"
    artifact: ArtifactSpec = field(default_factory=ArtifactSpec)
    preview_artifact: ArtifactSpec = field(default_factory=ArtifactSpec)

    @classmethod
    def from_dict(cls, data: Any) -> "CharacterMasterSpec":
        value = _mapping(data)
        return cls(
            id=_text(value.get("id")),
            framing=_text(value.get("framing")),
            facing=_text(value.get("facing")) or "front",
            outfit_state=_text(value.get("outfit_state")) or "base",
            pose=_text(value.get("pose")) or "stand",
            emotion=_text(value.get("emotion")) or "neutral",
            artifact=ArtifactSpec.from_dict(value.get("artifact")),
            preview_artifact=ArtifactSpec.from_dict(value.get("preview_artifact")),
        )


@dataclass(frozen=True)
class CharacterIdentitySpec:
    id: str = ""
    version: str = ""
    display_name: str = ""
    template_id: str = ""
    style_id: str = ""
    compatible_style_ids: tuple[str, ...] = ()
    region: str = ""
    era: str = ""
    role: str = ""
    quality_state: str = "draft"
    look: dict[str, Any] = field(default_factory=dict)
    signature_features: tuple[str, ...] = ()
    immutable_fields: tuple[str, ...] = ()
    masters: tuple[CharacterMasterSpec, ...] = ()
    legacy_artifacts: tuple[ArtifactSpec, ...] = ()
    provenance: ProvenanceSpec = field(default_factory=ProvenanceSpec)

    @classmethod
    def from_dict(cls, data: Any) -> "CharacterIdentitySpec":
        value = _mapping(data)
        masters = value.get("masters") if isinstance(value.get("masters"), list) else []
        return cls(
            id=_text(value.get("id")),
            version=_text(value.get("version")),
            display_name=_text(value.get("display_name")),
            template_id=_text(value.get("template_id")),
            style_id=_text(value.get("style_id")),
            compatible_style_ids=_tuple(value.get("compatible_style_ids")),
            region=_text(value.get("region")),
            era=_text(value.get("era")),
            role=_text(value.get("role")),
            quality_state=_text(value.get("quality_state")) or "draft",
            look=_mapping(value.get("look")),
            signature_features=_tuple(value.get("signature_features")),
            immutable_fields=_tuple(value.get("immutable_fields")),
            masters=tuple(CharacterMasterSpec.from_dict(item) for item in masters),
            legacy_artifacts=tuple(
                ArtifactSpec.from_dict(item)
                for item in value.get("legacy_artifacts", [])
                if isinstance(item, dict)
            ),
            provenance=ProvenanceSpec.from_dict(value.get("provenance")),
        )


@dataclass(frozen=True)
class SceneTemplateSpec:
    id: str = ""
    version: str = ""
    style_id: str = ""
    renderer_id: str = ""
    layer_slots: tuple[str, ...] = ()
    supported_aspects: tuple[str, ...] = ()
    supported_shot_sizes: tuple[str, ...] = ()
    supported_times: tuple[str, ...] = ()
    supported_weather: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Any) -> "SceneTemplateSpec":
        value = _mapping(data)
        return cls(
            id=_text(value.get("id")),
            version=_text(value.get("version")),
            style_id=_text(value.get("style_id")),
            renderer_id=_text(value.get("renderer_id")),
            layer_slots=_tuple(value.get("layer_slots")),
            supported_aspects=_tuple(value.get("supported_aspects")),
            supported_shot_sizes=_tuple(value.get("supported_shot_sizes")),
            supported_times=_tuple(value.get("supported_times")),
            supported_weather=_tuple(value.get("supported_weather")),
        )


@dataclass(frozen=True)
class SceneIdentitySpec:
    id: str = ""
    version: str = ""
    display_name: str = ""
    template_id: str = ""
    style_id: str = ""
    compatible_style_ids: tuple[str, ...] = ()
    region: str = ""
    era: str = ""
    scene_kind: str = ""
    quality_state: str = "draft"
    layers: dict[str, ArtifactSpec] = field(default_factory=dict)
    safe_zones: dict[str, Any] = field(default_factory=dict)
    variants: tuple[dict[str, Any], ...] = ()
    legacy_artifacts: tuple[ArtifactSpec, ...] = ()
    provenance: ProvenanceSpec = field(default_factory=ProvenanceSpec)

    @classmethod
    def from_dict(cls, data: Any) -> "SceneIdentitySpec":
        value = _mapping(data)
        raw_layers = _mapping(value.get("layers"))
        raw_variants = value.get("variants") if isinstance(value.get("variants"), list) else []
        return cls(
            id=_text(value.get("id")),
            version=_text(value.get("version")),
            display_name=_text(value.get("display_name")),
            template_id=_text(value.get("template_id")),
            style_id=_text(value.get("style_id")),
            compatible_style_ids=_tuple(value.get("compatible_style_ids")),
            region=_text(value.get("region")),
            era=_text(value.get("era")),
            scene_kind=_text(value.get("scene_kind")),
            quality_state=_text(value.get("quality_state")) or "draft",
            layers={key: ArtifactSpec.from_dict(item) for key, item in raw_layers.items()},
            safe_zones=_mapping(value.get("safe_zones")),
            variants=tuple(_mapping(item) for item in raw_variants),
            legacy_artifacts=tuple(
                ArtifactSpec.from_dict(item)
                for item in value.get("legacy_artifacts", [])
                if isinstance(item, dict)
            ),
            provenance=ProvenanceSpec.from_dict(value.get("provenance")),
        )


@dataclass(frozen=True)
class VisualLibraryManifest:
    schema_version: str = "3.0"
    library_id: str = ""
    version: str = ""
    style_ids: tuple[str, ...] = ()
    character_templates: tuple[CharacterTemplateSpec, ...] = ()
    scene_templates: tuple[SceneTemplateSpec, ...] = ()
    characters: tuple[CharacterIdentitySpec, ...] = ()
    scenes: tuple[SceneIdentitySpec, ...] = ()
    legacy_aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> "VisualLibraryManifest":
        value = _mapping(data)
        return cls(
            schema_version=_text(value.get("schema_version")) or "3.0",
            library_id=_text(value.get("library_id")),
            version=_text(value.get("version")),
            style_ids=_tuple(value.get("style_ids")),
            character_templates=tuple(
                CharacterTemplateSpec.from_dict(item)
                for item in value.get("character_templates", [])
                if isinstance(item, dict)
            ),
            scene_templates=tuple(
                SceneTemplateSpec.from_dict(item)
                for item in value.get("scene_templates", [])
                if isinstance(item, dict)
            ),
            characters=tuple(
                CharacterIdentitySpec.from_dict(item)
                for item in value.get("characters", [])
                if isinstance(item, dict)
            ),
            scenes=tuple(
                SceneIdentitySpec.from_dict(item)
                for item in value.get("scenes", [])
                if isinstance(item, dict)
            ),
            legacy_aliases={_text(key): _text(target) for key, target in _mapping(value.get("legacy_aliases")).items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "ASPECTS", "CHARACTER_FRAMINGS", "QUALITY_STATES", "ArtifactSpec",
    "CharacterIdentitySpec", "CharacterMasterSpec", "CharacterTemplateSpec",
    "ProvenanceSpec", "SceneIdentitySpec", "SceneTemplateSpec", "VisualLibraryManifest",
]
