from __future__ import annotations

from dataclasses import replace

import pytest

from app.features.render.engine.visual.library_v3 import (
    ActiveCatalog,
    ArtifactSpec,
    CharacterIdentitySpec,
    CharacterMasterSpec,
    CharacterTemplateSpec,
    ManifestValidationError,
    ProvenanceSpec,
    VisualLibraryManifest,
    build_character_master,
    load_manifest,
    validate_manifest,
    write_manifest,
    load_active_catalog,
    match_characters,
    resolve_character_preview,
)
from app.domain.story_plan_v2 import CharacterDef, StoryPlan
from app.features.render.engine.visual.v2.look_spec import derive_look


STYLE = "anime_clean_v3"
HASH = "a" * 64


def _template() -> CharacterTemplateSpec:
    return CharacterTemplateSpec(
        id="adult_female_balanced_v1",
        version="1.0.0",
        style_id=STYLE,
        renderer_id="visual_v3.character",
        anatomy_model="adult_6_5_heads",
        layer_slots=("anatomy", "face", "hair", "outfit"),
        supported_framings=("full_body", "waist_up", "bust"),
        supported_poses=("stand",),
        supported_emotions=("neutral",),
    )


def _master(asset_name: str, framing: str) -> CharacterMasterSpec:
    return CharacterMasterSpec(
        id=f"hero_01.{framing}.base",
        framing=framing,
        artifact=ArtifactSpec(
            path=asset_name,
            sha256=HASH,
            width=2048,
            height=3072,
            transparent=True,
        ),
    )


def _manifest(tmp_path, *, state: str = "draft") -> VisualLibraryManifest:
    framings = ("full_body",) if state == "draft" else ("full_body", "waist_up", "bust")
    masters = []
    for framing in framings:
        name = f"hero_01_{framing}.png"
        (tmp_path / name).write_bytes(b"asset")
        masters.append(_master(name, framing))
    return VisualLibraryManifest(
        schema_version="3.0",
        library_id="unit_test_library",
        version="1.0.0",
        style_ids=(STYLE,),
        character_templates=(_template(),),
        characters=(
            CharacterIdentitySpec(
                id="hero_01",
                version="1.0.0",
                display_name="Hero",
                template_id="adult_female_balanced_v1",
                style_id=STYLE,
                region="jp",
                era="modern",
                role="hero",
                quality_state=state,
                look={"face_shape": "oval", "hair": "long_black"},
                signature_features=("red hair ribbon",),
                immutable_fields=("look.face_shape", "look.hair"),
                masters=tuple(masters),
                provenance=ProvenanceSpec(source="in-house", license="owned") if state != "draft" else ProvenanceSpec(),
            ),
        ),
        legacy_aliases={"old_hero": "hero_01"},
    )


def _codes(manifest, tmp_path) -> set[str]:
    return {item.code for item in validate_manifest(manifest, root=tmp_path) if item.severity == "error"}


def test_draft_allows_an_incomplete_master_set(tmp_path):
    manifest = _manifest(tmp_path)
    assert _codes(manifest, tmp_path) == set()


def test_review_requires_three_framings_hash_and_provenance(tmp_path):
    manifest = _manifest(tmp_path)
    character = replace(
        manifest.characters[0],
        quality_state="review",
        provenance=ProvenanceSpec(),
        masters=(replace(manifest.characters[0].masters[0], artifact=replace(
            manifest.characters[0].masters[0].artifact, sha256=""
        )),),
    )
    manifest = replace(manifest, characters=(character,))
    codes = _codes(manifest, tmp_path)
    assert {"incomplete_master_set", "missing_sha256", "missing_provenance"} <= codes


def test_active_identity_with_required_masters_passes(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    assert _codes(manifest, tmp_path) == set()


def test_artifact_must_stay_inside_library_root(tmp_path):
    manifest = _manifest(tmp_path)
    master = manifest.characters[0].masters[0]
    bad_master = replace(master, artifact=replace(master.artifact, path="../outside.png"))
    character = replace(manifest.characters[0], masters=(bad_master,))
    assert "unsafe_artifact_path" in _codes(replace(manifest, characters=(character,)), tmp_path)


def test_legacy_alias_must_target_a_declared_identity(tmp_path):
    manifest = replace(_manifest(tmp_path), legacy_aliases={"old_hero": "missing_identity"})
    assert "dangling_legacy_alias" in _codes(manifest, tmp_path)


def test_active_catalog_excludes_review_items_and_aliases(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    review = replace(manifest.characters[0], id="review_hero", quality_state="review")
    manifest = replace(
        manifest,
        characters=(manifest.characters[0], review),
        legacy_aliases={"old_hero": "hero_01", "old_review": "review_hero"},
    )
    path = tmp_path / "approved.json"
    write_manifest(manifest, path)

    catalog = load_active_catalog(path)

    assert isinstance(catalog, ActiveCatalog)
    assert catalog.character_ids == ("hero_01",)
    assert catalog.character("review_hero") is None
    assert catalog.resolve_legacy_alias("old_hero") == "hero_01"
    assert catalog.resolve_legacy_alias("old_review") is None


def test_active_catalog_does_not_infer_unknown_ids(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    catalog = ActiveCatalog.from_manifest(manifest)

    assert catalog.character("hero") is None
    assert catalog.resolve_legacy_alias("hero") is None


def test_planner_matcher_uses_active_identity_and_apply_is_explicit(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    catalog = ActiveCatalog.from_manifest(manifest)
    plan = StoryPlan(characters=[CharacterDef(
        id="planner_hero", name="Hero", archetype="adult female",
        gender="female", age="adult", canonical_desc="long black hair red hair ribbon",
    )])

    report = match_characters(plan, catalog)

    assert report["assigned"]["planner_hero"] == "hero_01"
    assert report["statuses"]["planner_hero"] in ("matched", "needs_approval")
    assert plan.characters[0].visual_identity_id == ""
    assert plan.render.asset_status == {}

    applied = match_characters(plan, catalog, apply=True)

    assert applied["assigned"]["planner_hero"] == "hero_01"
    assert plan.characters[0].visual_identity_id == "hero_01"
    assert plan.render.asset_status["planner_hero"] == applied["statuses"]["planner_hero"]


def test_planner_matcher_rejects_review_identity_and_mismatched_gender(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    review = replace(manifest.characters[0], id="review_hero", quality_state="review")
    manifest = replace(manifest, characters=(manifest.characters[0], review))
    catalog = ActiveCatalog.from_manifest(manifest)
    plan = StoryPlan(characters=[CharacterDef(
        id="planner_man", name="Unknown", gender="male", age="adult",
        canonical_desc="unknown character",
    )])

    report = match_characters(plan, catalog)

    assert report["assigned"] == {}
    assert report["missing"] == ["planner_man"]


def test_artifact_bridge_resolves_only_active_identity(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    review = replace(manifest.characters[0], id="review_hero", quality_state="review")
    manifest = replace(manifest, characters=(manifest.characters[0], review))
    path = tmp_path / "approved.json"
    write_manifest(manifest, path)

    resolved = resolve_character_preview("hero_01", manifest_path=path, framing="bust")

    assert resolved.endswith("hero_01_bust.png")
    assert resolve_character_preview("review_hero", manifest_path=path) == ""
    assert resolve_character_preview("unknown", manifest_path=path) == ""


def test_visual_identity_id_round_trips_and_runtime_gate_is_opt_in(monkeypatch):
    plan = StoryPlan(characters=[CharacterDef(id="hero", visual_identity_id="hero_01")])
    restored = StoryPlan.from_json(plan.to_json())
    from app.features.render.engine.visual.library_v3.planner_matcher import matcher_enabled

    assert restored.characters[0].visual_identity_id == "hero_01"
    monkeypatch.setenv("STORY_V3_MATCHING", "0")
    assert matcher_enabled() is False
    monkeypatch.setenv("STORY_V3_MATCHING", "1")
    monkeypatch.setenv("STORY_V3_CHARACTER_MANIFEST", "approved.json")
    assert matcher_enabled() is True


def test_identity_compatible_styles_must_be_declared(tmp_path):
    manifest = _manifest(tmp_path)
    character = replace(manifest.characters[0], compatible_style_ids=("unknown_style",))
    issues = validate_manifest(replace(manifest, characters=(character,)), root=tmp_path)
    assert any(item.code == "unknown_compatible_style" for item in issues)


def test_legacy_artifacts_are_preserved_and_validated_as_draft(tmp_path):
    legacy_path = tmp_path / "legacy_hero.png"
    legacy_path.write_bytes(b"legacy")
    manifest = _manifest(tmp_path)
    character = replace(
        manifest.characters[0],
        legacy_artifacts=(ArtifactSpec(path=legacy_path.name, width=64, height=64),),
    )
    issues = validate_manifest(replace(manifest, characters=(character,)), root=tmp_path)
    assert not any(item.code == "missing_artifact" for item in issues)


def test_preview_artifact_is_optional_but_validated_when_present(tmp_path):
    preview_path = tmp_path / "hero_preview.png"
    preview_path.write_bytes(b"preview")
    manifest = _manifest(tmp_path)
    master = manifest.characters[0].masters[0]
    updated_master = replace(
        master,
        preview_artifact=ArtifactSpec(path=preview_path.name, sha256=HASH, width=1024, height=1536),
    )
    character = replace(manifest.characters[0], masters=(updated_master,) + manifest.characters[0].masters[1:])
    issues = validate_manifest(replace(manifest, characters=(character,)), root=tmp_path)
    assert not any(item.code == "missing_artifact" for item in issues)


def test_duplicate_character_identity_is_rejected(tmp_path):
    manifest = _manifest(tmp_path)
    manifest = replace(manifest, characters=(manifest.characters[0], manifest.characters[0]))
    assert "duplicate_character" in _codes(manifest, tmp_path)


def test_manifest_round_trip_is_atomic_and_strict(tmp_path):
    manifest = _manifest(tmp_path, state="active")
    destination = tmp_path / "manifest.json"
    write_manifest(manifest, destination)
    loaded = load_manifest(destination)
    assert loaded == manifest
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))


def test_write_rejects_invalid_manifest(tmp_path):
    manifest = replace(_manifest(tmp_path), version="not-semver")
    with pytest.raises(ManifestValidationError):
        write_manifest(manifest, tmp_path / "manifest.json")


def test_character_master_uses_native_framing_viewboxes(tmp_path):
    look = derive_look(
        "hero-framing",
        gender="female",
        outfit="office_suit",
        base={
            "face_shape": "heart",
            "eye_shape": "sharp",
            "body_build": "athletic",
            "signature_features": ["red ribbon"],
        },
    )
    full = build_character_master(look, framing="full_body", identity_id="hero_01")
    close = build_character_master(look, framing="close_up", identity_id="hero_01")
    assert 'data-character-id="hero_01"' in full
    assert 'data-character-framing="full_body"' in full
    assert 'viewBox="0 0 1024 1536"' in full
    assert 'data-character-framing="close_up"' in close
    assert 'viewBox="312 92 400 600"' in close
    assert 'data-eye-shape="sharp"' in close
    assert 'data-character-id="hero_01"' in close
    assert full != close


def test_character_master_unknown_framing_degrades_to_full_body():
    svg = build_character_master(derive_look("hero-invalid"), framing="not-a-frame")
    assert 'data-character-framing="full_body"' in svg
    assert 'viewBox="0 0 1024 1536"' in svg


def test_character_master_keeps_identity_fields_across_framings():
    look = derive_look("stable-identity", base={
        "face_shape": "angular",
        "hair_color": "#123456",
        "outfit": "office_suit",
        "signature_features": ["silver pin"],
    })
    masters = [build_character_master(look, framing=frame, identity_id="stable-01")
               for frame in ("full_body", "waist_up", "close_up")]
    assert all('data-character-id="stable-01"' in svg for svg in masters)
    assert all('data-eye-shape=' in svg for svg in masters)
    assert len(set(masters)) == 3


def test_identity_surface_fields_reach_rendered_layers():
    look = derive_look("surface-fields", base={
        "hair_texture": "curly",
        "outfit": "armor_light",
        "outfit_material": "metal",
        "outfit_silhouette": "armored",
    })
    svg = build_character_master(look, identity_id="surface-01")
    assert 'data-hair-texture="curly"' in svg
    assert 'data-outfit-material="metal"' in svg
    assert 'data-outfit-silhouette="armored"' in svg
