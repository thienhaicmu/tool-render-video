"""
policy_safety.py — Safety gates for AI apply policy.

Phase 31: invalid policy names fall back to conservative.
Hard safety blocks are NEVER bypassed by any policy.
Never raises.
"""
from __future__ import annotations

from .policy_schema import AIApplyPolicy

_VALID_POLICIES = frozenset({"conservative", "balanced", "aggressive", "experimental"})

# Global hard blocks — no policy may enable these
_GLOBAL_HARD_BLOCKS = (
    "ffmpeg_mutation",
    "playback_speed_mutation",
    "subtitle_timing_rewrite",
    "segment_reorder",
    "executor_override",
    "validation_bypass",
    "autonomous_unlimited_rendering",
)

# Policy definitions — each builds on the previous, adding capabilities
_POLICY_DEFINITIONS: dict[str, dict] = {
    "conservative": {
        "allow_safe_mutations": True,
        "allow_multivariant_execution": False,
        "allow_execution_recommendations": True,
        "allow_execution_simulation": True,
        "allow_output_ranking": True,
        "allow_timing_candidates": False,
        "allow_creator_style_adaptation": True,
        "allow_visual_rhythm_guidance": True,
        "allow_aggressive_behavior": False,
        "explanation": [
            "Safest behavior — minimal AI influence scope",
            "Multivariant execution disabled",
            "Timing candidate application blocked",
        ],
    },
    "balanced": {
        "allow_safe_mutations": True,
        "allow_multivariant_execution": True,
        "allow_execution_recommendations": True,
        "allow_execution_simulation": True,
        "allow_output_ranking": True,
        "allow_timing_candidates": False,
        "allow_creator_style_adaptation": True,
        "allow_visual_rhythm_guidance": True,
        "allow_aggressive_behavior": False,
        "explanation": [
            "Balanced AI influence — safe multivariant execution enabled",
            "Timing candidate application still blocked",
        ],
    },
    "aggressive": {
        "allow_safe_mutations": True,
        "allow_multivariant_execution": True,
        "allow_execution_recommendations": True,
        "allow_execution_simulation": True,
        "allow_output_ranking": True,
        "allow_timing_candidates": False,
        "allow_creator_style_adaptation": True,
        "allow_visual_rhythm_guidance": True,
        "allow_aggressive_behavior": True,
        "explanation": [
            "Stronger AI influence enabled — aggressive behavior metadata unlocked",
            "Timing candidate application still blocked",
            "Global hard blocks preserved",
        ],
    },
    "experimental": {
        "allow_safe_mutations": True,
        "allow_multivariant_execution": True,
        "allow_execution_recommendations": True,
        "allow_execution_simulation": True,
        "allow_output_ranking": True,
        "allow_timing_candidates": True,
        "allow_creator_style_adaptation": True,
        "allow_visual_rhythm_guidance": True,
        "allow_aggressive_behavior": True,
        "explanation": [
            "Widest safe bounded orchestration — experimental capabilities enabled",
            "Timing candidates available (advisory only)",
            "Global hard blocks always preserved",
        ],
    },
}


def sanitize_policy(policy_name: str) -> str:
    """Return a valid policy name, falling back to conservative for invalid values. Never raises."""
    try:
        if isinstance(policy_name, str) and policy_name.lower() in _VALID_POLICIES:
            return policy_name.lower()
    except Exception:
        pass
    return "conservative"


def build_policy(policy_name: str) -> AIApplyPolicy:
    """Build an AIApplyPolicy for the given name. Falls back to conservative. Never raises."""
    try:
        safe_name = sanitize_policy(policy_name)
        defn = dict(_POLICY_DEFINITIONS.get(safe_name, _POLICY_DEFINITIONS["conservative"]))
        explanation = list(defn.pop("explanation", []))
        return AIApplyPolicy(
            policy_name=safe_name,
            warnings=[],
            explanation=explanation,
            **defn,
        )
    except Exception:
        return AIApplyPolicy(
            policy_name="conservative",
            warnings=["policy_build_error_fallback"],
            explanation=["Fallback to conservative due to build error"],
        )


def get_blocked_capabilities(policy: AIApplyPolicy) -> list[str]:
    """Return list of capability names that are blocked by this policy + hard blocks. Never raises."""
    try:
        blocked = list(_GLOBAL_HARD_BLOCKS)
        if not policy.allow_multivariant_execution:
            blocked.append("multivariant_execution")
        if not policy.allow_timing_candidates:
            blocked.append("timing_candidate_apply")
        if not policy.allow_aggressive_behavior:
            blocked.append("aggressive_behavior")
        if not policy.allow_safe_mutations:
            blocked.append("safe_mutations")
        return blocked
    except Exception:
        return list(_GLOBAL_HARD_BLOCKS)
