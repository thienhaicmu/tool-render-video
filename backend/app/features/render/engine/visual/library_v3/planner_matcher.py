"""Deterministic Planner-to-V3 identity matching.

The matcher is deliberately separate from the manifest registry and the legacy
asset resolver. It can only see an ``ActiveCatalog`` and therefore cannot pick
review artwork. ``apply=False`` is the default so callers can inspect a report
before changing a StoryPlan.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from ..character_resolver import (
    MATCHED,
    MATCHED_EXACT,
    MISSING,
    NEEDS_APPROVAL,
    _char_tokens,
)
from .active_catalog import ActiveCatalog
from .contracts import CharacterIdentitySpec

MATCH_MIN = 5.0
ASSIGN_MIN = 2.0
DEFAULT_CHARACTER_MANIFEST = (
    Path(__file__).resolve().parents[7] / "data" / "visual_library_v3_legacy_characters_approved_pilot.json"
)


def _project_path(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[7] / path
    return str(path)


def _identity_tokens(identity: CharacterIdentitySpec) -> set[str]:
    look = identity.look or {}
    values = [
        identity.display_name,
        identity.role,
        identity.region,
        identity.era,
        *identity.signature_features,
        str(look.get("gender") or ""),
        str(look.get("age") or ""),
        str(look.get("outfit") or ""),
        str(look.get("hair_back") or ""),
        str(look.get("hair_front") or ""),
        str(look.get("body_build") or ""),
        str(look.get("accessories") or ""),
        str(look.get("face_shape") or ""),
    ]
    proxy = SimpleNamespace(
        name=identity.display_name,
        archetype=identity.role,
        canonical_desc=" ".join(value for value in values if value),
        gender=str(look.get("gender") or ""),
        age=str(look.get("age") or ""),
    )
    return _char_tokens(proxy)


def _identity_gender(identity: CharacterIdentitySpec) -> str:
    return str((identity.look or {}).get("gender") or "").strip().lower()


def _identity_age(identity: CharacterIdentitySpec) -> str:
    return str((identity.look or {}).get("age") or "").strip().lower()


def _score(char, identity: CharacterIdentitySpec, char_tokens: set[str], *, region: str) -> float:
    score = float(len(char_tokens & _identity_tokens(identity)))
    gender = (getattr(char, "gender", "") or "").strip().lower()
    age = (getattr(char, "age", "") or "").strip().lower()
    if gender and _identity_gender(identity) == gender:
        score += 3.0
    if age and _identity_age(identity) == age:
        score += 2.0
    if region and identity.region == region:
        score += 1.0
    return score


def _style_allowed(identity: CharacterIdentitySpec, style: str) -> bool:
    if not style:
        return True
    return style in {identity.style_id, *identity.compatible_style_ids}


def match_characters(
    plan,
    catalog: ActiveCatalog,
    *,
    locked: dict[str, str] | None = None,
    honor_existing: bool = True,
    region: str = "",
    style: str = "",
    apply: bool = False,
) -> dict:
    """Match Planner characters to active V3 identities.

    The report uses the same status vocabulary as the legacy resolver. The
    ``assigned`` values are V3 identity IDs, never legacy asset slugs. When
    ``apply`` is true, assignments are written to
    ``CharacterDef.visual_identity_id`` and ``plan.render.asset_status``; the
    existing ``CharacterDef.asset`` field is intentionally untouched.
    """
    report = {
        "statuses": {},
        "assigned": {},
        "scores": {},
        "needs_approval": [],
        "missing": [],
    }
    chars = list(getattr(plan, "characters", None) or [])
    if not chars:
        return report

    region = (region or getattr(plan, "region", "") or "").strip().lower()
    style = (style or getattr(plan, "art_style", "") or "").strip().lower()
    locked = {str(key): str(value).strip() for key, value in (locked or {}).items() if str(value).strip()}
    candidates = [
        identity for identity in catalog.characters
        if (not region or not identity.region or identity.region == region)
        and _style_allowed(identity, style)
    ]
    by_id = {identity.id: identity for identity in candidates}
    used: set[str] = set()
    pending = []

    def exact_target(value: str) -> CharacterIdentitySpec | None:
        target = (value or "").strip()
        if target in by_id:
            return by_id[target]
        alias = catalog.resolve_legacy_alias(target)
        return by_id.get(alias or "")

    def assign(char, identity: CharacterIdentitySpec, status: str, score: float | None = None) -> None:
        cid = (getattr(char, "id", "") or "").strip()
        report["statuses"][cid] = status
        report["assigned"][cid] = identity.id
        if score is not None:
            report["scores"][cid] = round(score, 3)
        used.add(identity.id)
        if apply:
            char.visual_identity_id = identity.id

    for char in chars:
        cid = (getattr(char, "id", "") or "").strip()
        target = exact_target(locked.get(cid, ""))
        if target is None and honor_existing:
            target = exact_target(getattr(char, "visual_identity_id", ""))
        if target is None and honor_existing:
            target = exact_target(getattr(char, "asset", ""))
        # A non-V3 legacy slug is owned by the legacy resolver. Do not silently
        # replace a locked or hand-picked legacy asset with a V3 identity.
        if target is None and honor_existing and (
            locked.get(cid) or getattr(char, "asset", "")
        ):
            continue
        if target is not None and target.id not in used:
            assign(char, target, MATCHED_EXACT)
        else:
            pending.append(char)

    for char in pending:
        cid = (getattr(char, "id", "") or "").strip()
        char_gender = (getattr(char, "gender", "") or "").strip().lower()
        char_age = (getattr(char, "age", "") or "").strip().lower()
        tokens = _char_tokens(char)
        best = None
        best_score = -1.0
        for identity in candidates:
            if identity.id in used:
                continue
            identity_gender = _identity_gender(identity)
            identity_age = _identity_age(identity)
            if char_gender and identity_gender and char_gender != identity_gender:
                continue
            if char_age and identity_age and char_age != identity_age:
                continue
            score = _score(char, identity, tokens, region=region)
            if score > best_score:
                best, best_score = identity, score
        if best is None or best_score < ASSIGN_MIN:
            report["statuses"][cid] = MISSING
            report["missing"].append(cid)
            if apply:
                char.visual_identity_id = ""
            continue
        status = MATCHED if best_score >= MATCH_MIN else NEEDS_APPROVAL
        assign(char, best, status, best_score)
        if status == NEEDS_APPROVAL:
            report["needs_approval"].append(cid)

    if apply:
        try:
            plan.render.asset_status = dict(report["statuses"])
        except Exception:
            pass
    return report


def matcher_enabled() -> bool:
    """Return whether the V3 runtime matcher is enabled and has a manifest."""
    return os.getenv("STORY_V3_MATCHING", "1") == "1" and bool(configured_manifest_path())


def configured_manifest_path() -> str:
    configured = os.getenv("STORY_V3_CHARACTER_MANIFEST", "").strip()
    if configured:
        return _project_path(configured)
    return str(DEFAULT_CHARACTER_MANIFEST) if DEFAULT_CHARACTER_MANIFEST.is_file() else ""


__all__ = [
    "ASSIGN_MIN", "DEFAULT_CHARACTER_MANIFEST", "MATCH_MIN", "configured_manifest_path",
    "matcher_enabled", "match_characters",
    "MATCHED", "MATCHED_EXACT", "MISSING", "NEEDS_APPROVAL",
]
