"""Inventory legacy character files into the V3 identity contract.

This is a migration map, not a matcher and not a quality approval step. It
groups style variants of the same legacy slug under one logical identity while
preserving every source artifact and its provenance.

Run from backend/: python scripts/build_visual_library_v3_legacy_character_map.py
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import (  # noqa: E402
    ArtifactSpec,
    CharacterIdentitySpec,
    CharacterTemplateSpec,
    ProvenanceSpec,
    VisualLibraryManifest,
    write_manifest,
)
from app.features.render.engine.visual.v2.jp_catalog import get_role, role_look  # noqa: E402
from app.features.render.engine.visual.v2.look_spec import derive_look  # noqa: E402
from app.features.render.engine.visual.v2.theme_pack import (  # noqa: E402
    STYLE_US_CINEMATIC,
    STYLE_US_EDITORIAL,
    STYLE_US_STORYBOOK,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LEGACY_ROOT = DATA / "asset_library" / "character"
OUTPUT = DATA / "visual_library_v3_legacy_characters.json"
DEFAULT_STYLE = "legacy_default_v1"
US_STYLE_IDS = (STYLE_US_EDITORIAL, STYLE_US_CINEMATIC, STYLE_US_STORYBOOK)


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return 0, 0
    return struct.unpack(">II", header[16:24])


def _sidecar(path: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + ".json")
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
    except (OSError, ValueError):
        return {}


def _tokens(sidecar: dict) -> str:
    return " ".join(str(sidecar.get(key) or "") for key in ("name", "tags", "desc")).lower()


def _infer_gender(text: str, slug: str) -> str:
    role = get_role(slug)
    if role:
        return role["gender"]
    if re.search(r"female|woman|girl|mother|daughter|wife|queen|miko|geisha|sister", text):
        return "female"
    if re.search(r"male|man|boy|father|son|husband|king|samurai|police", text):
        return "male"
    return derive_look(slug).gender


def _infer_age(text: str, slug: str) -> str:
    role = get_role(slug)
    if role:
        return role["age"]
    if re.search(r"child|kid|boy|girl|student", text):
        return "child"
    if re.search(r"elder|elderly|grandma|grandmother|grandpa|grandfather|old", text):
        return "elder"
    return "adult"


def _infer_outfit(text: str, slug: str) -> str:
    role = get_role(slug)
    if role:
        return role["outfit"]
    for token, outfit in (
        ("office|ceo|director|executive", "office_suit"),
        ("doctor|physician|hospital", "doctor_coat"),
        ("police|officer", "police_uniform"),
        ("engineer|technician|lab", "engineer_workwear"),
        ("student|school", "school_uniform"),
        ("samurai|warrior|armor", "armor_light"),
        ("kimono|geisha|miko|merchant|historical", "kimono"),
        ("cafe|barista|clerk|staff", "apron_staff"),
        ("hoodie", "hoodie"),
    ):
        if re.search(token, text):
            return outfit
    return "tee_casual"


def _safe_id(*parts: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", "_".join(parts).lower()).strip("_")
    return value[:120] or "legacy_character"


def _default_style(region: str, identity_id: str, source_styles: tuple[str, ...]) -> str:
    if region == "us":
        digest = hashlib.sha1(identity_id.encode("utf-8")).digest()[0]
        return US_STYLE_IDS[digest % len(US_STYLE_IDS)]
    if "jp_anime_clean_v1" in source_styles:
        return "jp_anime_clean_v1"
    return source_styles[0]


def _artifact(path: Path) -> ArtifactSpec:
    width, height = _png_size(path)
    return ArtifactSpec(
        path=path.relative_to(DATA).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        width=width,
        height=height,
        transparent=True,
    )


def _records() -> dict[tuple[str, str, str], list[tuple[Path, str, dict]]]:
    grouped: dict[tuple[str, str, str], list[tuple[Path, str, dict]]] = defaultdict(list)
    for path in sorted(LEGACY_ROOT.rglob("*.png")):
        rel = path.relative_to(DATA).parts
        if len(rel) < 4:
            continue
        region, genre, slug = rel[2], rel[3], path.stem
        style = rel[4] if len(rel) >= 6 else DEFAULT_STYLE
        grouped[(region, genre, slug)].append((path, style, _sidecar(path)))
    return grouped


def build_manifest() -> VisualLibraryManifest:
    grouped = _records()
    styles = sorted({style for records in grouped.values() for _, style, _ in records})
    if DEFAULT_STYLE not in styles:
        styles.append(DEFAULT_STYLE)
    if any(region == "us" for region, _, _ in grouped):
        styles.extend(US_STYLE_IDS)
    styles = sorted(set(styles))

    templates = []
    template_ids = set()
    for style in styles:
        for gender, anatomy in (("female", "adult_6_5_heads"), ("male", "adult_7_heads")):
            template_id = _safe_id(f"adult_{gender}_balanced_v1", style)
            template_ids.add((gender, style))
            templates.append(CharacterTemplateSpec(
                id=template_id, version="0.1.0", style_id=style,
                renderer_id="visual_v3.character", anatomy_model=anatomy,
                layer_slots=("anatomy", "skin", "face", "eyes", "hair_back", "hair_front",
                             "outfit_base", "outfit_detail", "accessories", "effects"),
                supported_framings=("full_body", "three_quarter", "waist_up", "bust", "close_up", "profile"),
                supported_poses=("stand", "walk", "sit", "point", "hold", "fight", "run", "kneel"),
                supported_emotions=("neutral", "happy", "sad", "angry", "surprised", "afraid", "determined"),
            ))

    characters = []
    aliases = {}
    slug_targets: dict[str, set[str]] = defaultdict(set)
    for (region, genre, slug), records in sorted(grouped.items()):
        text = _tokens(records[0][2])
        role = get_role(slug)
        gender = _infer_gender(text, slug)
        age = _infer_age(text, slug)
        outfit = _infer_outfit(text, slug)
        identity_id = _safe_id(region, genre, slug)
        styles_for_identity = tuple(sorted({style for _, style, _ in records}))
        default_style = _default_style(region, identity_id, styles_for_identity)
        compatible_styles = tuple(sorted(set(styles_for_identity) | (
            set(US_STYLE_IDS) if region == "us" else set()
        )))
        look = (role_look(slug).to_dict() if role else derive_look(
            identity_id, gender=gender, age=age, outfit=outfit,
            base={"signature_features": [slug.replace("_", " ")]},
        ))
        name = str(records[0][2].get("name") or slug.replace("_", " ")).split("/")[0].strip()
        legacy = tuple(_artifact(path) for path, _, _ in records)
        for path, style, _ in records:
            aliases[f"legacy/{path.relative_to(DATA).as_posix()}"] = identity_id
        slug_targets[slug].add(identity_id)
        characters.append(CharacterIdentitySpec(
            id=identity_id,
            version="0.1.0",
            display_name=name,
            template_id=_safe_id(f"adult_{gender}_balanced_v1", default_style),
            style_id=default_style,
            compatible_style_ids=compatible_styles,
            region=region,
            era="historical" if genre == "codai" else "modern",
            role=slug,
            quality_state="draft",
            look=look,
            signature_features=(slug.replace("_", " "),),
            immutable_fields=("look.face_shape", "look.eye_color", "look.hair_color", "look.outfit", "signature_features"),
            legacy_artifacts=legacy,
            provenance=ProvenanceSpec(
                source="legacy_asset_library",
                license=str(records[0][2].get("license") or "legacy-unverified"),
                author="legacy migration map",
            ),
        ))
    for slug, targets in sorted(slug_targets.items()):
        if len(targets) == 1:
            aliases[slug] = next(iter(targets))
    return VisualLibraryManifest(
        schema_version="3.0", library_id="story_visual_library_legacy_characters",
        version="0.1.0", style_ids=tuple(styles),
        character_templates=tuple(templates), characters=tuple(characters),
        legacy_aliases=aliases,
    )


if __name__ == "__main__":
    manifest = build_manifest()
    write_manifest(manifest, OUTPUT)
    print(f"wrote {OUTPUT}")
    print(f"identities={len(manifest.characters)} legacy_artifacts={sum(len(c.legacy_artifacts) for c in manifest.characters)} styles={len(manifest.style_ids)}")
