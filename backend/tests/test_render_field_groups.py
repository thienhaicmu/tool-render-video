"""A2 (2026-06-27) — RenderRequest field-group registry guard.

Pins that app/models/render_field_groups.FIELD_GROUPS stays a complete,
disjoint partition of RenderRequest's fields. The point is the failure
modes:

  - a NEW RenderRequest field that nobody classified → completeness test
    fails, forcing a deliberate grouping decision (no silent god-object
    sprawl);
  - a field listed in two groups → disjointness test fails;
  - a stale entry naming a field that no longer exists on RenderRequest →
    existence test fails.

No behaviour / contract is touched — RenderRequest stays the flat 152-field
model. See the registry module docstring for why nesting was rejected.
"""
from __future__ import annotations

from collections import Counter

from app.models.render import RenderRequest
from app.models.render_field_groups import ALL_GROUPED_FIELDS, FIELD_GROUPS, group_of

_RENDER_FIELDS = frozenset(RenderRequest.model_fields.keys())


def test_every_render_request_field_is_grouped():
    """Completeness — a new RenderRequest field must be added to a group."""
    ungrouped = _RENDER_FIELDS - ALL_GROUPED_FIELDS
    assert not ungrouped, (
        f"{len(ungrouped)} RenderRequest field(s) are not in any group in "
        f"render_field_groups.FIELD_GROUPS: {sorted(ungrouped)}. Classify each "
        f"into a logical group (this is the A2 guard against god-object sprawl)."
    )


def test_no_stale_fields_in_registry():
    """Every grouped name must still exist on RenderRequest."""
    stale = ALL_GROUPED_FIELDS - _RENDER_FIELDS
    assert not stale, (
        f"render_field_groups names fields that no longer exist on "
        f"RenderRequest: {sorted(stale)}. Remove or rename them."
    )


def test_groups_are_pairwise_disjoint():
    """No field may belong to two groups."""
    counts = Counter(name for names in FIELD_GROUPS.values() for name in names)
    dupes = {name: c for name, c in counts.items() if c > 1}
    assert not dupes, f"Fields assigned to more than one group: {dupes}"


def test_registry_partitions_exactly():
    """Belt-and-suspenders: the grouped set equals the model field set."""
    assert ALL_GROUPED_FIELDS == _RENDER_FIELDS, (
        "FIELD_GROUPS is not an exact partition of RenderRequest fields. "
        f"missing={sorted(_RENDER_FIELDS - ALL_GROUPED_FIELDS)} "
        f"extra={sorted(ALL_GROUPED_FIELDS - _RENDER_FIELDS)}"
    )


def test_group_of_resolves_known_and_unknown():
    assert group_of("subtitle_style") == "subtitle"
    assert group_of("gemini_api_key") == "credentials"
    assert group_of("nonexistent_field_zzz") is None
