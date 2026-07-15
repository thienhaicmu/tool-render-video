"""Deterministic Planner-to-V3 scene matching for active scene identities."""
from __future__ import annotations

import os
from types import SimpleNamespace

from ..character_resolver import MATCHED, MATCHED_EXACT, MISSING, NEEDS_APPROVAL, _char_tokens
from .active_catalog import ActiveCatalog
from .contracts import SceneIdentitySpec

MATCH_MIN = 4.0
ASSIGN_MIN = 1.0


def _scene_tokens(scene: SceneIdentitySpec) -> set[str]:
    values = [
        scene.display_name, scene.scene_kind, scene.region, scene.era,
        *[str(item.get("recipe") or "") for item in scene.variants],
        *[str(item.get("time") or "") for item in scene.variants],
    ]
    proxy = SimpleNamespace(
        name=scene.display_name,
        archetype=scene.scene_kind,
        canonical_desc=" ".join(value for value in values if value),
        gender="",
        age="",
    )
    return _char_tokens(proxy)


def _style_allowed(scene: SceneIdentitySpec, style: str) -> bool:
    if not style:
        return True
    return style in {scene.style_id, *scene.compatible_style_ids} or any(
        str(item.get("style_id") or "") == style for item in scene.variants
    )


def _score(setting, scene: SceneIdentitySpec, setting_tokens: set[str], *, region: str) -> float:
    score = float(len(setting_tokens & _scene_tokens(scene)))
    if region and scene.region == region:
        score += 1.0
    return score


def match_scenes(
    plan,
    catalog: ActiveCatalog,
    *,
    honor_existing: bool = True,
    region: str = "",
    style: str = "",
    apply: bool = False,
) -> dict:
    """Match settings to active V3 scenes; repeated scene identities are allowed."""
    report = {"statuses": {}, "assigned": {}, "scores": {}, "needs_approval": [], "missing": []}
    settings = list(getattr(plan, "settings", None) or [])
    if not settings:
        return report
    region = (region or getattr(plan, "region", "") or "").strip().lower()
    style = (style or getattr(plan, "art_style", "") or "").strip().lower()
    candidates = [
        scene for scene in catalog.scenes
        if (not region or not scene.region or scene.region == region) and _style_allowed(scene, style)
    ]
    by_id = {scene.id: scene for scene in candidates}

    def exact_target(value: str) -> SceneIdentitySpec | None:
        target = (value or "").strip()
        if target in by_id:
            return by_id[target]
        alias = catalog.resolve_legacy_alias(target)
        return by_id.get(alias or "")

    for setting in settings:
        sid = (getattr(setting, "id", "") or "").strip()
        target = exact_target(getattr(setting, "visual_scene_identity_id", "")) if honor_existing else None
        if target is None and honor_existing:
            target = exact_target(getattr(setting, "asset", ""))
        if target is not None:
            report["statuses"][sid] = MATCHED_EXACT
            report["assigned"][sid] = target.id
            if apply:
                setting.visual_scene_identity_id = target.id
            continue
        # A legacy background slug remains owned by the legacy path.
        if honor_existing and getattr(setting, "asset", ""):
            continue
        tokens = _char_tokens(SimpleNamespace(
            name=getattr(setting, "name", ""),
            archetype=getattr(setting, "scene_kind", ""),
            canonical_desc=getattr(setting, "canonical_desc", ""),
            gender="", age="",
        ))
        best = None
        best_score = -1.0
        for scene in candidates:
            score = _score(setting, scene, tokens, region=region)
            if score > best_score:
                best, best_score = scene, score
        if best is None or best_score < ASSIGN_MIN:
            report["statuses"][sid] = MISSING
            report["missing"].append(sid)
            if apply:
                setting.visual_scene_identity_id = ""
            continue
        status = MATCHED if best_score >= MATCH_MIN else NEEDS_APPROVAL
        report["statuses"][sid] = status
        report["assigned"][sid] = best.id
        report["scores"][sid] = round(best_score, 3)
        if status == NEEDS_APPROVAL:
            report["needs_approval"].append(sid)
        if apply:
            setting.visual_scene_identity_id = best.id
    if apply:
        try:
            plan.render.scene_asset_status = dict(report["statuses"])
        except Exception:
            pass
    return report


def scene_manifest_path() -> str:
    configured = os.getenv("STORY_V3_SCENE_MANIFEST", "").strip()
    if configured:
        return configured
    from pathlib import Path
    default = Path(__file__).resolve().parents[7] / "data" / "visual_library_v3_legacy_scenes_approved_pilot.json"
    return str(default) if default.is_file() else ""


def scene_matcher_enabled() -> bool:
    return os.getenv("STORY_V3_MATCHING", "1") == "1" and bool(scene_manifest_path())


__all__ = [
    "ASSIGN_MIN", "MATCH_MIN", "match_scenes", "scene_manifest_path", "scene_matcher_enabled",
    "MATCHED", "MATCHED_EXACT", "MISSING", "NEEDS_APPROVAL",
]
