"""Build a draft Visual Library V3 manifest from three identified legacy assets.

The pilot proves identity/template/version contracts only. It does not approve
the old artwork and does not perform Planner matching.

Run from backend/: python scripts/build_visual_library_v3_pilot.py
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import (  # noqa: E402
    ArtifactSpec,
    CharacterIdentitySpec,
    CharacterMasterSpec,
    CharacterTemplateSpec,
    ProvenanceSpec,
    SceneIdentitySpec,
    SceneTemplateSpec,
    VisualLibraryManifest,
    validate_manifest,
    write_manifest,
)
from app.features.render.engine.visual.v2.jp_catalog import role_look  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DEFAULT_OUT = DATA / "visual_library_v3_pilot.json"
STYLE = "jp_anime_clean_v1"


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"not a supported PNG: {path}")
    return struct.unpack(">II", header[16:24])


def _sidecar(path: Path) -> dict:
    source = path.with_suffix(path.suffix + ".json")
    if not source.is_file():
        return {}
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _artifact(path: Path) -> ArtifactSpec:
    width, height = _png_size(path)
    return ArtifactSpec(
        path=path.relative_to(DATA).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        width=width,
        height=height,
        transparent="character" in path.parts,
    )


def _provenance(path: Path) -> ProvenanceSpec:
    sidecar = _sidecar(path)
    return ProvenanceSpec(
        source=str(sidecar.get("source") or path.relative_to(ROOT).as_posix()),
        license=str(sidecar.get("license") or "in-house"),
        author="AIVideoStudio procedural legacy pack",
    )


def _character(
    identity_id: str, role_id: str, template_id: str, path: Path, *,
    display_name: str, region: str, era: str, role: str, signature_features: tuple[str, ...],
) -> CharacterIdentitySpec:
    look = role_look(role_id).to_dict()
    return CharacterIdentitySpec(
        id=identity_id,
        version="0.1.0",
        display_name=display_name,
        template_id=template_id,
        style_id=STYLE,
        region=region,
        era=era,
        role=role,
        quality_state="draft",
        look=look,
        signature_features=signature_features,
        immutable_fields=(
            "look.skin", "look.hair_color", "look.eye_color", "look.hair_back",
            "look.hair_front", "look.outfit", "signature_features",
        ),
        masters=(
            CharacterMasterSpec(
                id=f"{identity_id}.full_body.base",
                framing="full_body",
                artifact=_artifact(path),
            ),
        ),
        provenance=_provenance(path),
    )


def build_manifest() -> VisualLibraryManifest:
    ceo = DATA / "asset_library/character/jp/hiendai/jp_anime_clean_v1/jp_ceo_woman.png"
    samurai = DATA / "asset_library/character/jp/codai/jp_anime_clean_v1/jp_samurai.png"
    cafe = DATA / "asset_library/background/jp/hiendai/jp_anime_clean_v1/jp_cafe.png"
    for source in (ceo, samurai, cafe):
        if not source.is_file():
            raise FileNotFoundError(source)

    character_layers = (
        "anatomy", "skin", "face", "eyes", "hair_back", "hair_front",
        "outfit_base", "outfit_detail", "accessories", "effects",
    )
    framings = ("full_body", "three_quarter", "waist_up", "bust", "close_up", "profile")
    poses = ("stand", "walk", "sit", "point", "hold", "fight", "run", "kneel")
    emotions = ("neutral", "happy", "sad", "angry", "surprised", "afraid", "determined")
    return VisualLibraryManifest(
        schema_version="3.0",
        library_id="story_visual_library_pilot",
        version="0.1.0",
        style_ids=(STYLE,),
        character_templates=(
            CharacterTemplateSpec(
                id="adult_female_balanced_v1", version="0.1.0", style_id=STYLE,
                renderer_id="visual_v2.anime_char", anatomy_model="adult_6_5_heads",
                layer_slots=character_layers, supported_framings=framings,
                supported_poses=poses, supported_emotions=emotions,
            ),
            CharacterTemplateSpec(
                id="adult_male_balanced_v1", version="0.1.0", style_id=STYLE,
                renderer_id="visual_v2.anime_char", anatomy_model="adult_7_heads",
                layer_slots=character_layers, supported_framings=framings,
                supported_poses=poses, supported_emotions=emotions,
            ),
        ),
        scene_templates=(
            SceneTemplateSpec(
                id="interior_public_space_v1", version="0.1.0", style_id=STYLE,
                renderer_id="visual_v2.anime_scene",
                layer_slots=("background", "midground", "foreground", "lighting", "atmosphere"),
                supported_aspects=("16:9", "9:16", "1:1"),
                supported_shot_sizes=("wide", "medium", "close_up"),
                supported_times=("day", "night"), supported_weather=("clear", "rain"),
            ),
        ),
        characters=(
            _character(
                "jp_modern_ceo_woman_01", "jp_ceo_woman", "adult_female_balanced_v1", ceo,
                display_name="Japanese modern CEO woman", region="jp", era="modern", role="ceo",
                signature_features=("structured office suit", "controlled upright silhouette", "dark styled hair"),
            ),
            _character(
                "jp_historical_samurai_man_01", "jp_samurai", "adult_male_balanced_v1", samurai,
                display_name="Japanese historical samurai", region="jp", era="historical", role="samurai",
                signature_features=("light armor", "topknot silhouette", "katana"),
            ),
        ),
        scenes=(
            SceneIdentitySpec(
                id="jp_modern_cafe_01", version="0.1.0", display_name="Japanese modern cafe",
                template_id="interior_public_space_v1", style_id=STYLE, region="jp", era="modern",
                scene_kind="cafe", quality_state="draft", layers={"background": _artifact(cafe)},
                provenance=_provenance(cafe),
            ),
        ),
        legacy_aliases={
            "jp_ceo_woman": "jp_modern_ceo_woman_01",
            "jp_samurai": "jp_historical_samurai_man_01",
            "jp_cafe": "jp_modern_cafe_01",
        },
    )


def main() -> int:
    manifest = build_manifest()
    issues = validate_manifest(manifest, root=DATA)
    errors = [item for item in issues if item.severity == "error"]
    if errors:
        for item in errors:
            print(f"ERROR {item.code} {item.location}: {item.message}")
        return 1
    write_manifest(manifest, DEFAULT_OUT)
    print(f"wrote {DEFAULT_OUT}")
    for item in issues:
        print(f"{item.severity.upper()} {item.code} {item.location}: {item.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
