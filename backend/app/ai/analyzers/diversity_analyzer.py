"""
diversity_analyzer.py — Goal-aware multi-clip diversity intelligence (S2.4).

Prevents multi-clip output from feeling repetitive by applying soft penalties
when candidates share hook type, moment archetype, or temporal zone with
already-selected clips.

Three diversity dimensions:
  1. hook_type        — avoid repeating same hook taxonomy type (S2.1 signal)
                        exact match penalized more than same emotional group
  2. moment_type      — avoid repeating same clip archetype (explainer / payoff /
                        hook_opener / full_story …) derived from hook + structure
  3. temporal_zone    — conservative; early/mid/late overlap is NOT a duplicate
                        penalty range 0.90–0.97 multiplier effect only

Key design constraints (required changes from approval):
  - Quality delta gate: diversity only fires when candidate is within 12 pts of
    top selected score.  95-score duplicate ALWAYS beats 70-score unique.
  - Temporal penalty is tiny (≈ _TEMPORAL_PENALTY_BASE fixed pts, equivalent to
    ~0.95× multiplier on typical scores).
  - Diversity strength scales with clip_count: 2=weak, 3–4=medium, 5+=full.
  - Hook exact-match penalty reduced when clips differ in moment_type — avoids
    over-penalizing clips that share hook type but differ in content value.

Set DIVERSITY_INTELLIGENCE_ENABLED=0 to disable entirely (rollback gate).

Public API:
    build_candidate_context(hook_type, phases, position_ratio) -> dict
    compute_diversity_penalty(candidate_ctx, selected_ctxs, goal,
                              top_score, candidate_score, clip_count) -> float
    DIVERSITY_INTELLIGENCE_ENABLED: bool
"""
from __future__ import annotations

import os

DIVERSITY_INTELLIGENCE_ENABLED: bool = (
    os.environ.get("DIVERSITY_INTELLIGENCE_ENABLED", "1") == "1"
)

# ── Quality-first gate ────────────────────────────────────────────────────────
# Diversity only fires when candidate is within this many points of top score.
# Guarantee: 95 - _MAX_TOTAL_PENALTY(15) = 80 > 70  → high-quality duplicate
# always beats mediocre unique when quality gap exceeds this threshold.
_QUALITY_DELTA_THRESHOLD = 12.0

# ── Clip-count diversity strength ─────────────────────────────────────────────
# More clips = stronger diversity enforcement (repetition compounds with count).
_COUNT_STRENGTH: dict[int, float] = {
    1: 0.0,   # single-clip: always no-op
    2: 0.30,  # weak
    3: 0.55,  # medium
    4: 0.70,  # medium-strong
}
_COUNT_STRENGTH_5_PLUS = 1.0

# ── Penalty base values (before count-strength and dimension-weight scaling) ──
_HOOK_EXACT_PENALTY   = 8.0   # exact hook type match
_HOOK_GROUP_PENALTY   = 3.0   # same emotional group, different type
_MOMENT_TYPE_PENALTY  = 6.0   # same clip archetype
_TEMPORAL_PENALTY     = 2.5   # same temporal zone  (≈0.95× on 50-pt scores)
_MAX_TOTAL_PENALTY    = 15.0  # absolute cap → 95-15=80, always beats 70-unique

# ── Hook type → emotional group ───────────────────────────────────────────────
# Grouping yields a partial penalty for same-category hooks, preventing over-
# penalization of clips that share a hook type but differ in content value
# (e.g., curiosity-hook explainer vs. curiosity-hook payoff are meaningfully
# different even though they share a hook taxonomy label).
_HOOK_EMOTION_GROUP: dict[str, str] = {
    "curiosity":    "intrigue",
    "surprise":     "reaction",
    "warning":      "authority",
    "authority":    "authority",
    "problem":      "tension",
    "challenge":    "tension",
    "story":        "narrative",
    "contrarian":   "narrative",
    "result_first": "payoff",
    "none":         "unknown",
}

# ── Temporal zone boundaries ──────────────────────────────────────────────────
_ZONE_EARLY = "early"   # position_ratio 0.00–0.40
_ZONE_MID   = "mid"     # position_ratio 0.40–0.70
_ZONE_LATE  = "late"    # position_ratio 0.70–1.00

# ── Goal-aware dimension weights ──────────────────────────────────────────────
# 1.0 = full weight on that dimension.  Lower values dampen the penalty.
_GOAL_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    "viral": {
        # Emotional variety most important: reaction vs. explanation vs. reveal
        "hook_type":   0.8,
        "moment_type": 1.0,
        "temporal":    0.5,   # viral hooks can legitimately cluster early
    },
    "education": {
        # Topic-zone spread primary: different lesson phases → different value
        "hook_type":   0.5,
        "moment_type": 0.8,
        "temporal":    1.0,
    },
    "podcast": {
        # Different conversation zones: different opinions / exchanges
        "hook_type":   0.7,
        "moment_type": 0.7,
        "temporal":    1.0,
    },
    "product": {
        # Avoid 5× benefit hooks — want benefit + proof + demo + CTA variety
        "hook_type":   1.0,
        "moment_type": 0.9,
        "temporal":    0.6,
    },
    "storytelling": {
        # Enforce setup + conflict + resolution spread
        "hook_type":   0.5,
        "moment_type": 0.9,
        "temporal":    1.0,
    },
}
_DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "hook_type":   0.8,
    "moment_type": 0.8,
    "temporal":    0.7,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_candidate_context(
    hook_type: str = "none",
    phases: list[str] | None = None,
    position_ratio: float = 0.5,
) -> dict:
    """Build a diversity context dict for one candidate.

    Fields returned:
      hook_type       str   — from hook_intelligence_type (S2.1 9-type taxonomy)
      moment_type     str   — clip archetype derived from hook + structure phases
      position_ratio  float — candidate_start / total_duration [0, 1]
      temporal_zone   str   — "early" / "mid" / "late"
    """
    ht = str(hook_type or "none").lower().strip()
    mt = _derive_moment_type(ht, list(phases or []))
    pr = max(0.0, min(1.0, float(position_ratio)))
    return {
        "hook_type":      ht,
        "moment_type":    mt,
        "position_ratio": pr,
        "temporal_zone":  _temporal_zone(pr),
    }


def compute_diversity_penalty(
    candidate_ctx: dict,
    selected_ctxs: list[dict],
    goal: str = "",
    top_score: float = 100.0,
    candidate_score: float = 100.0,
    clip_count: int = 1,
) -> float:
    """Return diversity penalty in [0, 15.0] to subtract from comparison score.

    IMPORTANT — this penalty is for selection ordering ONLY.
    Callers MUST NOT store the penalized score in any segment output field.
    The returned segment dicts should always carry the original pre-penalty score.

    Returns 0.0 when:
      - DIVERSITY_INTELLIGENCE_ENABLED is False  (env gate)
      - clip_count <= 1                          (single clip: always no-op)
      - selected_ctxs is empty                  (first clip: nothing to compare)
      - top_score - candidate_score > 12.0      (quality delta gate: quality wins)

    Hook penalty reduction: if candidate and selected share hook_type but differ
    in moment_type, the hook_exact penalty is halved — avoids over-penalizing
    clips that share a hook label but differ in content structure and value.
    """
    if not DIVERSITY_INTELLIGENCE_ENABLED:
        return 0.0
    if clip_count <= 1 or not selected_ctxs:
        return 0.0
    if top_score - candidate_score > _QUALITY_DELTA_THRESHOLD:
        return 0.0

    strength = _get_count_strength(clip_count)
    goal_key = str(goal or "").lower().strip()
    dw = _GOAL_DIMENSION_WEIGHTS.get(goal_key, _DEFAULT_DIMENSION_WEIGHTS)

    c_hook   = candidate_ctx.get("hook_type",     "none")
    c_group  = _HOOK_EMOTION_GROUP.get(c_hook, "unknown")
    c_moment = candidate_ctx.get("moment_type",   "unknown")
    c_zone   = candidate_ctx.get("temporal_zone", _ZONE_MID)

    hook_exact      = False
    hook_group      = False
    moment_match    = False
    temporal_match  = False
    # Track whether a hook_exact match also has a moment_type match —
    # if they share hook type but NOT moment type, the hook penalty is halved.
    hook_exact_also_moment = False

    for ctx in selected_ctxs:
        s_hook   = ctx.get("hook_type",     "none")
        s_group  = _HOOK_EMOTION_GROUP.get(s_hook, "unknown")
        s_moment = ctx.get("moment_type",   "unknown")
        s_zone   = ctx.get("temporal_zone", _ZONE_MID)

        if c_hook != "none" and c_hook == s_hook:
            hook_exact = True
            if c_moment != "unknown" and c_moment == s_moment:
                hook_exact_also_moment = True
        if c_group != "unknown" and c_group == s_group:
            hook_group = True
        if c_moment != "unknown" and c_moment == s_moment:
            moment_match = True
        if c_zone == s_zone:
            temporal_match = True

    penalty = 0.0
    hw = dw.get("hook_type",   0.8)
    mw = dw.get("moment_type", 0.8)
    tw = dw.get("temporal",    0.7)

    # Hook dimension — same exact type is more penalized than same group.
    # Penalty is HALVED when clips share hook type but differ in moment_type,
    # because different structures (hook_opener vs. payoff vs. full_story)
    # mean the clips feel different in content even if opening style matches.
    if hook_exact:
        hook_pen = _HOOK_EXACT_PENALTY if hook_exact_also_moment else _HOOK_EXACT_PENALTY * 0.5
        penalty += hook_pen * hw
    elif hook_group:
        penalty += _HOOK_GROUP_PENALTY * hw

    # Moment archetype dimension (emotion / reveal / explanation / payoff)
    if moment_match:
        penalty += _MOMENT_TYPE_PENALTY * mw

    # Temporal zone — very conservative, small fixed penalty.
    # 2.5 pts on a 50-pt score ≈ 0.95× multiplier, well within 0.90–0.97 target.
    if temporal_match:
        penalty += _TEMPORAL_PENALTY * tw

    return max(0.0, min(_MAX_TOTAL_PENALTY, penalty * strength))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_count_strength(clip_count: int) -> float:
    """Diversity strength factor [0, 1] scaled by target clip count."""
    if clip_count <= 1:
        return 0.0
    return _COUNT_STRENGTH.get(clip_count, _COUNT_STRENGTH_5_PLUS)


def _temporal_zone(position_ratio: float) -> str:
    """Broad temporal zone for a clip's start position."""
    if position_ratio < 0.40:
        return _ZONE_EARLY
    if position_ratio < 0.70:
        return _ZONE_MID
    return _ZONE_LATE


def _derive_moment_type(hook_type: str, phases: list[str]) -> str:
    """Derive clip archetype from hook type and detected structure phases.

    Archetypes (best-moment diversity dimension):
      full_story   — opening + development + payoff all present
      hook_payoff  — opening + payoff, no middle development
      hook_opener  — opening phase only (hook-heavy, no resolution)
      payoff       — payoff present, no opening (reveal / punchline)
      explainer    — development only (no hook, no payoff = tutorial / context)
      narrative    — story or contrarian hook type → implied narrative arc
      unknown      — insufficient signals to classify

    When phases is empty, falls back to hook_type for archetype inference.
    This graceful degradation ensures diversity works even when structure
    analysis (S2.3) is disabled or no transcript is available.
    """
    phase_set = set(phases)
    if phase_set >= {"opening", "development", "payoff"}:
        return "full_story"
    if {"opening", "payoff"} <= phase_set:
        return "hook_payoff"
    if "opening" in phase_set and len(phase_set) == 1:
        return "hook_opener"
    if "payoff" in phase_set and "opening" not in phase_set:
        return "payoff"
    if "development" in phase_set and "opening" not in phase_set and "payoff" not in phase_set:
        return "explainer"
    # No phase information — fall back to hook type heuristics
    if hook_type in {"result_first"}:
        return "payoff"
    if hook_type in {"authority", "warning", "problem"}:
        return "explainer"
    if hook_type in {"story", "contrarian"}:
        return "narrative"
    return "unknown"
