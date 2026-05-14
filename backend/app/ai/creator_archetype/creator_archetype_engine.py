"""
creator_archetype_engine.py — Phase 61A Creator Archetype Strategy Foundation.

Metadata-only module. Maps creator types to deterministic render style
strategy preferences for subtitle, camera, hook, and ranking domains.

Advisory only — does NOT execute anything, does NOT override user settings,
does NOT bypass execution modes, does NOT bypass quality gates.

Execution promotion can happen later through existing safe influence layers.

Supported archetypes
--------------------
    podcast, talking_head, educational, viral_short_form,
    storytelling, interview, motivation

Unknown or missing creator_type → fallback (available=False, empty strategy).

Conflict safety
---------------
    User explicit settings       > archetype strategy
    Execution mode (Phase 60D)   > archetype strategy
    Quality gates (Phase 59D)    > archetype strategy
    creator_preference_profile   > archetype defaults
    Platform strategy            may refine but not override creator safety

Public API
----------
    build_creator_archetype_strategy(edit_plan, context=None) -> dict

Output shape (known archetype)
------------------------------
    {
        "creator_archetype_strategy": {
            "available":      true,
            "creator_type":   "podcast",
            "strategy": {
                "subtitle": {
                    "style_bias":           "clean_pro",
                    "density_bias":         "balanced",
                    "keyword_emphasis":     "selective",
                    "readability_priority": "high"
                },
                "camera": {
                    "motion_energy":       "low",
                    "stability_priority":  "high",
                    "crop_aggressiveness": "low",
                    "jitter_sensitivity":  "high"
                },
                "hook": {
                    "hook_energy":        "moderate",
                    "curiosity_style":    "soft_direct",
                    "retention_priority": "medium_high"
                },
                "ranking": {
                    "priority": "retention_creator_fit"
                }
            },
            "confidence": 0.82,
            "reasoning":  ["Podcast creator style favors clean subtitles and stable framing."],
            "mode_compatibility": {
                "off":        "advisory_only",
                "safe":       "conservative_guidance",
                "balanced":   "full_guidance",
                "aggressive": "full_guidance_extended"
            }
        }
    }

Output shape (unknown / fallback)
----------------------------------
    {
        "creator_archetype_strategy": {
            "available":    false,
            "creator_type": "unknown",
            "strategy":     {},
            "confidence":   0.0,
            "reasoning":    []
        }
    }

Safety contract
---------------
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No execution promotion
    ❌ No executor override
    ✅ Reads edit_plan attributes only
    ✅ Deterministic: same inputs → same output
    ✅ All confidence values clamped to [0.0, 1.0]
    ✅ All strategy values from allowed sets
    ✅ Returns fallback on any error
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.creator_archetype")

# ---------------------------------------------------------------------------
# Allowed value sets (enforced by _normalize)
# ---------------------------------------------------------------------------
_ALLOWED: dict[str, frozenset[str]] = {
    "subtitle.style_bias":          frozenset({"clean_pro", "bold_impact", "minimal_clean", "compact_dynamic"}),
    "subtitle.density_bias":        frozenset({"compact", "balanced", "expanded"}),
    "subtitle.keyword_emphasis":    frozenset({"none", "selective", "moderate", "strong"}),
    "subtitle.readability_priority": frozenset({"standard", "medium", "high"}),
    "camera.motion_energy":         frozenset({"low", "low_medium", "medium", "medium_high", "high"}),
    "camera.stability_priority":    frozenset({"standard", "medium", "high"}),
    "camera.crop_aggressiveness":   frozenset({"low", "medium", "high"}),
    "camera.jitter_sensitivity":    frozenset({"standard", "medium", "high"}),
    "hook.hook_energy":             frozenset({"low", "low_medium", "moderate", "medium_high", "high"}),
    "hook.curiosity_style":         frozenset({"none", "soft_direct", "curiosity_driven", "pattern_interrupt", "emotional", "trust_curiosity"}),
    "hook.retention_priority":      frozenset({"standard", "medium", "medium_high", "high"}),
    "ranking.priority":             frozenset({
        "retention_creator_fit", "creator_fit_retention", "retention_readability",
        "hook_strength_retention", "retention_narrative", "trust_clarity",
        "retention_emotional_moment",
    }),
}

# Supported creator archetypes
_SUPPORTED_ARCHETYPES: frozenset[str] = frozenset({
    "podcast", "talking_head", "educational", "viral_short_form",
    "storytelling", "interview", "motivation",
})

# Base confidence for a known archetype (before profile modulation)
_BASE_CONFIDENCE: float = 0.82

# Mode compatibility mapping (same for all archetypes — describes how the mode
# gates strategy application, not the strategy itself)
_MODE_COMPATIBILITY: dict[str, str] = {
    "off":        "advisory_only",
    "safe":       "conservative_guidance",
    "balanced":   "full_guidance",
    "aggressive": "full_guidance_extended",
}

# ---------------------------------------------------------------------------
# Per-archetype strategy data
# ---------------------------------------------------------------------------
_ARCHETYPE_STRATEGIES: dict[str, dict] = {
    "podcast": {
        "subtitle": {
            "style_bias":           "clean_pro",
            "density_bias":         "balanced",
            "keyword_emphasis":     "selective",
            "readability_priority": "high",
        },
        "camera": {
            "motion_energy":       "low",
            "stability_priority":  "high",
            "crop_aggressiveness": "low",
            "jitter_sensitivity":  "high",
        },
        "hook": {
            "hook_energy":        "moderate",
            "curiosity_style":    "soft_direct",
            "retention_priority": "medium_high",
        },
        "ranking": {"priority": "retention_creator_fit"},
        "_reasoning": "Podcast creator style favors clean subtitles and stable framing.",
    },
    "talking_head": {
        "subtitle": {
            "style_bias":           "clean_pro",
            "density_bias":         "balanced",
            "keyword_emphasis":     "selective",
            "readability_priority": "high",
        },
        "camera": {
            "motion_energy":       "low",
            "stability_priority":  "high",
            "crop_aggressiveness": "low",
            "jitter_sensitivity":  "high",
        },
        "hook": {
            "hook_energy":        "moderate",
            "curiosity_style":    "soft_direct",
            "retention_priority": "high",
        },
        "ranking": {"priority": "creator_fit_retention"},
        "_reasoning": "Talking head creators rely on stable subject continuity and clear readable subtitles.",
    },
    "educational": {
        "subtitle": {
            "style_bias":           "clean_pro",
            "density_bias":         "balanced",
            "keyword_emphasis":     "moderate",
            "readability_priority": "high",
        },
        "camera": {
            "motion_energy":       "low",
            "stability_priority":  "high",
            "crop_aggressiveness": "low",
            "jitter_sensitivity":  "high",
        },
        "hook": {
            "hook_energy":        "moderate",
            "curiosity_style":    "curiosity_driven",
            "retention_priority": "high",
        },
        "ranking": {"priority": "retention_readability"},
        "_reasoning": "Educational creators prioritize clarity, concept keywords, and stable framing.",
    },
    "viral_short_form": {
        "subtitle": {
            "style_bias":           "compact_dynamic",
            "density_bias":         "compact",
            "keyword_emphasis":     "strong",
            "readability_priority": "medium",
        },
        "camera": {
            "motion_energy":       "medium",
            "stability_priority":  "medium",
            "crop_aggressiveness": "medium",
            "jitter_sensitivity":  "medium",
        },
        "hook": {
            "hook_energy":        "high",
            "curiosity_style":    "pattern_interrupt",
            "retention_priority": "high",
        },
        "ranking": {"priority": "hook_strength_retention"},
        "_reasoning": "Viral short-form creators need compact subtitles, strong hooks, and medium camera energy.",
    },
    "storytelling": {
        "subtitle": {
            "style_bias":           "clean_pro",
            "density_bias":         "balanced",
            "keyword_emphasis":     "selective",
            "readability_priority": "high",
        },
        "camera": {
            "motion_energy":       "low_medium",
            "stability_priority":  "medium",
            "crop_aggressiveness": "low",
            "jitter_sensitivity":  "medium",
        },
        "hook": {
            "hook_energy":        "low_medium",
            "curiosity_style":    "soft_direct",
            "retention_priority": "high",
        },
        "ranking": {"priority": "retention_narrative"},
        "_reasoning": "Storytelling creators use open-loop curiosity and moderate motion to sustain narrative flow.",
    },
    "interview": {
        "subtitle": {
            "style_bias":           "clean_pro",
            "density_bias":         "balanced",
            "keyword_emphasis":     "none",
            "readability_priority": "high",
        },
        "camera": {
            "motion_energy":       "low",
            "stability_priority":  "high",
            "crop_aggressiveness": "low",
            "jitter_sensitivity":  "high",
        },
        "hook": {
            "hook_energy":        "low_medium",
            "curiosity_style":    "trust_curiosity",
            "retention_priority": "medium_high",
        },
        "ranking": {"priority": "trust_clarity"},
        "_reasoning": "Interview creators prioritize trust, clarity, and stable framing over dynamic energy.",
    },
    "motivation": {
        "subtitle": {
            "style_bias":           "bold_impact",
            "density_bias":         "compact",
            "keyword_emphasis":     "strong",
            "readability_priority": "medium",
        },
        "camera": {
            "motion_energy":       "medium_high",
            "stability_priority":  "medium",
            "crop_aggressiveness": "medium",
            "jitter_sensitivity":  "medium",
        },
        "hook": {
            "hook_energy":        "high",
            "curiosity_style":    "emotional",
            "retention_priority": "high",
        },
        "ranking": {"priority": "retention_emotional_moment"},
        "_reasoning": "Motivation creators use bold impact subtitles, high energy hooks, and dynamic-safe camera.",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_creator_archetype_strategy(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build creator archetype strategy metadata for this render.

    Returns:
        {"creator_archetype_strategy": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build_strategy(edit_plan, job_id)
    except Exception as exc:
        logger.warning("creator_archetype_unexpected_error job_id=%s: %s", job_id, exc)
        return _fallback_strategy()


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build_strategy(edit_plan: Any, job_id: str) -> dict:
    # Determine creator_type (primary source: creator_preference_profile from Phase 50D)
    profile = _attr_dict(edit_plan, "creator_preference_profile")
    creator_type = str(profile.get("creator_type") or "unknown").lower().strip()

    if creator_type not in _SUPPORTED_ARCHETYPES:
        logger.debug(
            "creator_archetype_unknown job_id=%s creator_type=%r", job_id, creator_type
        )
        return _fallback_strategy(creator_type=creator_type)

    archetype = _ARCHETYPE_STRATEGIES[creator_type]

    # Build validated strategy (private _reasoning key stripped out)
    strategy = _build_validated_strategy(archetype)

    # Confidence: base modulated by creator_preference_profile confidence
    profile_conf = float(profile.get("confidence") or 0.0)
    confidence = _compute_confidence(profile_conf)

    reasoning = [archetype["_reasoning"]]

    logger.info(
        "creator_archetype_strategy_built job_id=%s creator_type=%s confidence=%.3f",
        job_id, creator_type, confidence,
    )

    return {
        "creator_archetype_strategy": {
            "available":    True,
            "creator_type": creator_type,
            "strategy":     strategy,
            "confidence":   confidence,
            "reasoning":    reasoning,
            "mode_compatibility": dict(_MODE_COMPATIBILITY),
        }
    }


# ---------------------------------------------------------------------------
# Strategy construction
# ---------------------------------------------------------------------------

def _build_validated_strategy(archetype: dict) -> dict:
    """Build strategy dict with validated allowed values. Strips internal keys."""
    domains = ("subtitle", "camera", "hook", "ranking")
    out: dict = {}
    for domain in domains:
        raw = archetype.get(domain, {})
        validated: dict = {}
        for key, value in raw.items():
            allowed_key = f"{domain}.{key}"
            allowed = _ALLOWED.get(allowed_key)
            if allowed is not None:
                validated[key] = _normalize(value, allowed, f"{domain}.{key}_unknown")
            else:
                validated[key] = str(value)
        out[domain] = validated
    return out


def _normalize(value: str, allowed: frozenset, fallback: str) -> str:
    """Return value if in allowed set, otherwise fallback."""
    v = str(value).lower().strip()
    return v if v in allowed else fallback


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def _compute_confidence(profile_conf: float) -> float:
    """Blend base archetype confidence with creator_preference_profile signal."""
    profile_signal = max(0.0, min(1.0, float(profile_conf or 0.0)))
    if profile_signal > 0.0:
        conf = _BASE_CONFIDENCE * 0.65 + profile_signal * 0.35
    else:
        conf = _BASE_CONFIDENCE
    return round(max(0.0, min(1.0, conf)), 4)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr_dict(obj: Any, attr: str) -> dict:
    """Duck-typed attribute access returning a dict or {}."""
    try:
        val = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _fallback_strategy(creator_type: str = "unknown") -> dict:
    return {
        "creator_archetype_strategy": {
            "available":    False,
            "creator_type": creator_type,
            "strategy":     {},
            "confidence":   0.0,
            "reasoning":    [],
        }
    }
