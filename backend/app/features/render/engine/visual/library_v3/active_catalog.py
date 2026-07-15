"""Read-only handoff from approved V3 art to a future matcher.

This module exposes only identities whose manifest state is ``active``. It
resolves an explicit identity id or a legacy alias, but it never searches,
scores, ranks or infers a Planner character. Runtime matching can depend on
this boundary without accidentally using review artwork.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .contracts import CharacterIdentitySpec, SceneIdentitySpec, VisualLibraryManifest
from .registry import load_manifest


@dataclass(frozen=True)
class ActiveCatalog:
    """The approved V3 subset used as input to a later matching stage."""

    library_id: str
    version: str
    source_path: str
    characters: tuple[CharacterIdentitySpec, ...]
    scenes: tuple[SceneIdentitySpec, ...]
    legacy_aliases: Mapping[str, str]

    @classmethod
    def from_manifest(cls, manifest: VisualLibraryManifest, *, source_path: str = "") -> "ActiveCatalog":
        active_characters = tuple(item for item in manifest.characters if item.quality_state == "active")
        active_scenes = tuple(item for item in manifest.scenes if item.quality_state == "active")
        active_ids = {item.id for item in active_characters} | {item.id for item in active_scenes}
        aliases = {
            alias: target
            for alias, target in manifest.legacy_aliases.items()
            if target in active_ids
        }
        return cls(
            library_id=manifest.library_id,
            version=manifest.version,
            source_path=source_path,
            characters=active_characters,
            scenes=active_scenes,
            legacy_aliases=MappingProxyType(aliases),
        )

    @property
    def character_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.characters)

    @property
    def scene_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.scenes)

    def character(self, identity_id: str) -> CharacterIdentitySpec | None:
        return next((item for item in self.characters if item.id == identity_id), None)

    def scene(self, identity_id: str) -> SceneIdentitySpec | None:
        return next((item for item in self.scenes if item.id == identity_id), None)

    def resolve_legacy_alias(self, alias: str) -> str | None:
        """Return an approved target for an exact legacy alias, if available."""
        target = self.legacy_aliases.get((alias or "").strip())
        return target if target and (self.character(target) or self.scene(target)) else None


def load_active_catalog(path: str | Path) -> ActiveCatalog:
    """Load a validated manifest and expose only its explicitly active items."""
    source = Path(path)
    return ActiveCatalog.from_manifest(load_manifest(source), source_path=str(source))


__all__ = ["ActiveCatalog", "load_active_catalog"]
