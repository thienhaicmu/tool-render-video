"""recap_profile.py — one dial for the recap Story-Intelligence feature flags.

Architecture-review upgrade (2026-07-04). The recap path grew SIX independent
env flags controlling its AI passes + deterministic guards:

    RECAP_TWO_PASS · RECAP_EDITORIAL_PASS · STORY_INTELLIGENCE_HOIST_ENABLED
    RECAP_SNAP_TO_SHOTS_ENABLED · RECAP_TRIM_TO_BAND · RECAP_PER_EPISODE_NARRATION

That surface is hard to reason about and hard to test in combination. This module
adds a SINGLE ``RECAP_INTELLIGENCE_PROFILE`` dial (basic | standard | max) that
maps to a coherent flag combo, while keeping every individual env var as an
explicit override (an individual var, when set, ALWAYS wins over the profile).

Resolution order for ``recap_flag(name)``:
    1. The individual env var (``os.getenv(name)``) — if set, it wins.
    2. The active ``RECAP_INTELLIGENCE_PROFILE`` default for that flag.
    3. The HARD default — which equals the "standard" profile and is byte-identical
       to the pre-profile ``os.getenv(name, "<default>") == "1"`` behaviour.

So with NO profile and NO individual override, behaviour is bit-identical to
before this module existed. ``standard`` == today's shipped defaults.

Never raises (Sacred Contract #3 spirit): any failure falls back to the hard
default so a bad env value can never break recap dispatch.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("app.render.recap.profile")

# HARD defaults — MUST equal the pre-profile getenv defaults exactly so that
# "no profile set" is byte-identical to the previous behaviour.
_HARD_DEFAULT: dict[str, bool] = {
    "RECAP_TWO_PASS": True,
    "RECAP_EDITORIAL_PASS": False,
    "STORY_INTELLIGENCE_HOIST_ENABLED": True,
    "RECAP_SNAP_TO_SHOTS_ENABLED": True,
    "RECAP_TRIM_TO_BAND": True,
    "RECAP_PER_EPISODE_NARRATION": False,
}

# Profiles. ``standard`` is intentionally identical to _HARD_DEFAULT.
#   basic    — fewest LLM calls: single-pass binding, no editorial/hoist/refine.
#              Deterministic guards (snap/trim) stay ON — they're cheap + improve
#              output regardless.
#   standard — today's shipped behaviour (two-pass + hoist + snap + trim).
#   max      — every quality pass: + editorial blueprint + per-episode narration.
_PROFILES: dict[str, dict[str, bool]] = {
    "basic": {
        "RECAP_TWO_PASS": False,
        "RECAP_EDITORIAL_PASS": False,
        "STORY_INTELLIGENCE_HOIST_ENABLED": False,
        "RECAP_SNAP_TO_SHOTS_ENABLED": True,
        "RECAP_TRIM_TO_BAND": True,
        "RECAP_PER_EPISODE_NARRATION": False,
    },
    "standard": dict(_HARD_DEFAULT),
    "max": {
        "RECAP_TWO_PASS": True,
        "RECAP_EDITORIAL_PASS": True,
        "STORY_INTELLIGENCE_HOIST_ENABLED": True,
        "RECAP_SNAP_TO_SHOTS_ENABLED": True,
        "RECAP_TRIM_TO_BAND": True,
        "RECAP_PER_EPISODE_NARRATION": True,
    },
}

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def active_profile() -> str:
    """The resolved profile name, or "" when unset/unknown (→ hard defaults)."""
    p = (os.getenv("RECAP_INTELLIGENCE_PROFILE", "") or "").strip().lower()
    return p if p in _PROFILES else ""


def recap_flag(name: str) -> bool:
    """Resolve one recap feature flag. Individual env var overrides the profile,
    which overrides the hard default. Never raises."""
    try:
        raw = os.getenv(name)
        if raw is not None:
            v = raw.strip().lower()
            if v in _TRUE:
                return True
            if v in _FALSE:
                return False
            # Unrecognised value → fall through to profile/hard default.
        prof = active_profile()
        if prof and name in _PROFILES[prof]:
            return _PROFILES[prof][name]
        return _HARD_DEFAULT.get(name, False)
    except Exception:
        return _HARD_DEFAULT.get(name, False)


__all__ = ["recap_flag", "active_profile"]
