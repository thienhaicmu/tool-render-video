"""
conflict_resolver.py — Creator preference conflict resolution. Phase 50D.

Philosophy:
  - Creator history > market signals
  - Unknown creator signal → trust market
  - Both known and different → creator wins with conservative adjustment
  - "When in doubt, do less" — conservative-first

Safety contract:
  ❌ No render mutation
  ❌ No executor override
  ✅ Deterministic — same inputs always produce same output
  ✅ Never raises
"""
from __future__ import annotations

# Ordered from calmest to most energetic
_EMPHASIS_ORDER = ["none", "subtle", "moderate", "strong"]
_CAMERA_ORDER   = ["static_center", "smooth_subject", "dynamic_subject"]
_STYLE_SET      = frozenset({"viral_bold", "clean_pro", "boxed_caption"})


def resolve_style_conflict(creator: str, market: str) -> tuple[str, str]:
    """Resolve subtitle style conflict.

    Creator always wins when known.  Market used as fallback when creator is unknown.

    Returns:
        (resolved_style, conflict_note)  — note is "" when no conflict existed.
    """
    creator_known = creator in _STYLE_SET
    market_known  = market in _STYLE_SET

    if creator_known:
        if market_known and creator != market:
            return creator, f"Creator style {creator!r} preferred over market signal {market!r}"
        return creator, ""

    if market_known:
        return market, f"No creator style history — using market signal {market!r}"

    return "unknown", ""


def resolve_emphasis_conflict(creator: str, market: str) -> tuple[str, str]:
    """Resolve keyword emphasis conflict with conservative one-step compromise.

    When creator prefers less emphasis than market:
      → nudge one step toward market (creator-biased compromise)
    When creator prefers equal or more emphasis than market:
      → creator wins unchanged

    Returns:
        (resolved_emphasis, conflict_note)
    """
    ci = _EMPHASIS_ORDER.index(creator) if creator in _EMPHASIS_ORDER else -1
    mi = _EMPHASIS_ORDER.index(market)  if market  in _EMPHASIS_ORDER else -1

    if ci < 0:
        return (_EMPHASIS_ORDER[mi] if mi >= 0 else "unknown"), ""
    if mi < 0 or ci == mi:
        return creator, ""

    if ci < mi:
        # Creator quieter than market → nudge one step toward market
        resolved = _EMPHASIS_ORDER[ci + 1]
        return resolved, (
            f"Emphasis compromise: creator {creator!r} + market {market!r} → {resolved!r}"
        )
    # Creator louder than market → creator wins
    return creator, f"Creator emphasis {creator!r} stronger than market {market!r} — creator wins"


def resolve_camera_conflict(creator: str, market: str) -> tuple[str, str]:
    """Resolve camera motion style conflict.

    When creator and market differ:
      - Creator calmer than market → safe middle ground
      - Creator more dynamic than market → creator wins

    Returns:
        (resolved_motion_style, conflict_note)
    """
    ci = _CAMERA_ORDER.index(creator) if creator in _CAMERA_ORDER else -1
    mi = _CAMERA_ORDER.index(market)  if market  in _CAMERA_ORDER else -1

    if ci < 0:
        return (_CAMERA_ORDER[mi] if mi >= 0 else "unknown"), ""
    if mi < 0 or ci == mi:
        return creator, ""

    if ci < mi:
        # Creator prefers calmer camera — safe middle ground
        middle   = (ci + mi) // 2
        resolved = _CAMERA_ORDER[middle]
        return resolved, (
            f"Camera compromise: creator {creator!r} + market {market!r} → {resolved!r}"
        )
    # Creator prefers more dynamic than market → creator wins
    return creator, f"Creator camera {creator!r} preferred over market signal {market!r}"
