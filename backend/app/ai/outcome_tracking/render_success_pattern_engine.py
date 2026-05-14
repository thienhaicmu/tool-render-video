"""
render_success_pattern_engine.py — Phase 62C Success Pattern Mining.

Pattern-mining-only module. Discovers deterministic render success patterns
from a single render's outcome metadata to identify what signal combinations
consistently work better.

NO autonomous optimization.  NO render mutation.  NO influence mutation.
NO rerender.  NO self-training.  NO external persistence.

A "pattern" in this context represents the observed combination of:
    creator_type × platform × subtitle/camera signals × outcome classification

For a single render, evidence_count reflects the number of distinct positive
signals confirming the pattern (not a count of historical renders).

Pattern classification (deterministic, explicit thresholds):
    strong_pattern:     success_score >= 0.80 AND evidence_count >= 3
    moderate_pattern:   success_score >= 0.65 AND evidence_count >= 2
    weak_pattern:       insufficient evidence or score below 0.65
    conflicting_pattern: positive and negative signals contradict each other

Conflicting detection (any of):
    - ab_winner = ai_on  AND  creator_fit = low
    - overall_result = improved  AND  bench_status = needs_review

Success score formula (weighted blend, deterministic):
    ab_component     = delta-based [0, 1], 0.5 when no baseline
    quality_norm     = overall_quality / 100
    benchmark_score  = {best_fit: 1.0, improving: 0.7, needs_review: 0.4, unknown: 0.2}
    effectiveness    = {strong: 1.0, moderate: 0.7, weak: 0.3}

    success_score = ab × 0.35 + quality × 0.25 + benchmark × 0.20 + effectiveness × 0.20

Evidence count (confirming signals within this render):
    +1 for ab_winner = ai_on
    +1 for ai_effectiveness in (strong, moderate)
    +1 for creator_fit in (high, medium)
    +1 for subtitle_quality >= 75 AND subtitle_applied
    +1 for camera_quality  >= 75 AND camera_applied
    +1 for overall_quality >= 75

Public API:
    build_render_success_patterns(edit_plan, context=None) -> dict

Output shape (available):
    {
        "render_success_patterns": {
            "available": true,
            "patterns": [
                {
                    "pattern_id":      "podcast_tiktok_clean_pro_stable",
                    "creator_type":    "podcast",
                    "platform":        "tiktok",
                    "signals": {
                        "subtitle_style":   "clean_pro",
                        "subtitle_density":  "balanced",
                        "keyword_emphasis": "selective",
                        "camera_style":     "stable",
                        "camera_stability": "high",
                        "motion_energy":    "low",
                        "ranking_priority": "retention_creator_fit",
                        "hook_style":       "moderate"
                    },
                    "success_score":    0.815,
                    "evidence_count":   5,
                    "confidence":       0.807,
                    "classification":   "strong_pattern",
                    "reasoning": [
                        "Stable framing and clean subtitles consistently improved podcast content.",
                        "A/B winner ai_on with delta +6 confirms positive signal."
                    ]
                }
            ],
            "confidence": 0.807,
            "reasoning": [
                "Strong creator-focused pattern detected for podcast on tiktok."
            ]
        }
    }

Output shape (fallback):
    {
        "render_success_patterns": {
            "available":  false,
            "patterns":   [],
            "confidence": 0.0,
            "reasoning":  []
        }
    }

Safety contract:
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No autonomous optimization
    ❌ No external persistence
    ✅ Pattern mining only — advisory metadata
    ✅ Deterministic: same inputs → same output
    ✅ Returns fallback on any error
    ✅ Success scores and confidence clamped to [0.0, 1.0]
    ✅ Conflicting patterns advisory-only, no auto-blocking
    ✅ Never claims strong pattern without evidence
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.outcome_tracking")

# ---------------------------------------------------------------------------
# Classification thresholds (explicit, tested)
# ---------------------------------------------------------------------------
_STRONG_SCORE:       float = 0.80
_MODERATE_SCORE:     float = 0.65
_STRONG_EVIDENCE:    int   = 3
_MODERATE_EVIDENCE:  int   = 2

# Quality threshold for per-domain evidence contribution
_DOMAIN_QUALITY_THRESHOLD: int = 75

# Success score weights (sum = 1.0)
_W_AB_DELTA      = 0.35
_W_QUALITY       = 0.25
_W_BENCHMARK     = 0.20
_W_EFFECTIVENESS = 0.20

# Benchmark status → score contribution
_BENCH_SCORE: dict[str, float] = {
    "best_fit":     1.0,
    "improving":    0.7,
    "needs_review": 0.4,
    "unknown":      0.2,
}

# AI effectiveness → score contribution
_EFFECTIVENESS_SCORE: dict[str, float] = {
    "strong":   1.0,
    "moderate": 0.7,
    "weak":     0.3,
}

# Supported creator archetypes and platforms (unknown falls back gracefully)
_KNOWN_CREATOR_TYPES: frozenset[str] = frozenset({
    "podcast", "talking_head", "educational", "viral_short_form",
    "storytelling", "interview", "motivation",
})
_KNOWN_PLATFORMS: frozenset[str] = frozenset({
    "tiktok", "youtube_shorts", "reels", "instagram_reels",
})

# Max reasoning lines
_MAX_REASONING        = 4
_MAX_PATTERN_REASONING = 3


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_render_success_patterns(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build render success pattern metadata.

    Returns:
        {"render_success_patterns": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "render_success_patterns_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback()


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback()

    # ── Read signal inputs ─────────────────────────────────────────────────
    rot     = _get_dict(edit_plan, "render_outcome_tracking")
    cpr     = _get_dict(edit_plan, "creator_preference_reinforcement")
    crs     = _get_dict(edit_plan, "creator_render_strategy")
    ab_eval = _get_dict(edit_plan, "ai_ab_evaluation")
    bench   = _get_dict(edit_plan, "creator_benchmark_summary")

    # ── Extract core signals ───────────────────────────────────────────────
    rot_available    = bool(rot.get("available"))
    creator_type     = str(rot.get("creator_type") or "unknown").lower()
    overall_result   = str(rot.get("overall_result") or "neutral")
    ai_effectiveness = str(rot.get("ai_effectiveness") or "weak")
    rot_confidence   = _clamp_f(rot.get("confidence"))
    quality          = rot.get("quality") or {}
    ai_execution     = rot.get("ai_execution") or {}
    ab_result        = rot.get("ab_result") or {}
    bench_result     = rot.get("benchmark_result") or {}

    ab_available     = bool(ab_eval.get("available"))
    ab_winner        = str(ab_result.get("winner") or "unknown")
    ab_overall_delta = int(ab_result.get("overall_delta") or 0)
    creator_fit      = str(bench_result.get("creator_fit") or "low")
    bench_status     = str(bench.get("benchmark_status") or "unknown")

    # Platform from creator_preference_profile via rot (fallback chain)
    creator_prof = _get_dict(edit_plan, "creator_preference_profile")
    platform = str(creator_prof.get("platform") or "unknown").lower()

    # ── Gate check ────────────────────────────────────────────────────────
    if not rot_available or creator_type == "unknown":
        return _fallback()
    if not any(quality.get(k, 0) > 0 for k in ("subtitle", "camera", "hook", "overall")):
        return _fallback()

    # ── Compute success score ─────────────────────────────────────────────
    success_score = _compute_success_score(
        ab_available, ab_winner, ab_overall_delta,
        quality, bench_status, ai_effectiveness,
    )

    # ── Compute evidence count ────────────────────────────────────────────
    evidence_count = _compute_evidence_count(
        ab_winner, ai_effectiveness, creator_fit,
        quality, ai_execution,
    )

    # ── Detect conflicting signals ─────────────────────────────────────────
    is_conflicting = _is_conflicting(ab_winner, creator_fit, overall_result, bench_status)

    # ── Classify pattern ──────────────────────────────────────────────────
    classification = _classify_pattern(success_score, evidence_count, is_conflicting)

    # ── Build signal dict from creator_render_strategy ────────────────────
    signals = _build_signals(crs)

    # ── Camera style descriptor ───────────────────────────────────────────
    camera_style = _camera_style_descriptor(
        signals.get("camera_stability", "medium"),
        signals.get("motion_energy", "medium"),
    )
    if camera_style:
        signals["camera_style"] = camera_style

    # ── Pattern ID ────────────────────────────────────────────────────────
    pattern_id = _make_pattern_id(
        creator_type, platform,
        signals.get("subtitle_style", "unknown"),
        camera_style or "unknown",
    )

    # ── Pattern confidence ────────────────────────────────────────────────
    evidence_bonus  = min(0.30, evidence_count * 0.06)
    pattern_conf    = round(max(0.0, min(1.0, success_score * 0.7 + evidence_bonus)), 4)

    # ── Pattern reasoning ─────────────────────────────────────────────────
    pattern_reasoning = _build_pattern_reasoning(
        classification, creator_type, platform,
        ab_winner, ab_overall_delta, ab_available, quality,
    )

    pattern = {
        "pattern_id":     pattern_id,
        "creator_type":   creator_type,
        "platform":       platform,
        "signals":        signals,
        "success_score":  success_score,
        "evidence_count": evidence_count,
        "confidence":     pattern_conf,
        "classification": classification,
        "reasoning":      pattern_reasoning,
    }

    # ── Overall confidence and reasoning ──────────────────────────────────
    overall_conf     = pattern_conf
    overall_reasoning = _build_overall_reasoning(classification, creator_type, platform)

    logger.info(
        "render_success_patterns_built job_id=%s creator=%s platform=%s "
        "classification=%s score=%.3f evidence=%d confidence=%.3f",
        job_id, creator_type, platform,
        classification, success_score, evidence_count, overall_conf,
    )

    return {
        "render_success_patterns": {
            "available":  True,
            "patterns":   [pattern],
            "confidence": overall_conf,
            "reasoning":  overall_reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Success score
# ---------------------------------------------------------------------------

def _compute_success_score(
    ab_available: bool,
    ab_winner: str,
    ab_overall_delta: int,
    quality: dict,
    bench_status: str,
    ai_effectiveness: str,
) -> float:
    """Compute success score [0.0, 1.0] as weighted blend of four signals."""
    # A/B component
    if ab_available:
        if ab_winner == "ai_on":
            ab_norm = min(1.0, max(0.0, ab_overall_delta / 10.0))
        elif ab_winner == "ai_off":
            # Penalised but not zero — render happened, partial credit
            ab_norm = max(0.0, (1.0 - min(1.0, abs(ab_overall_delta) / 10.0))) * 0.5
        else:
            ab_norm = 0.5  # tie
    else:
        ab_norm = 0.5  # no baseline → neutral assumption

    quality_norm  = max(0.0, min(1.0, quality.get("overall", 0) / 100.0))
    bench_score   = _BENCH_SCORE.get(bench_status, 0.2)
    eff_score     = _EFFECTIVENESS_SCORE.get(ai_effectiveness, 0.3)

    raw = (
        ab_norm     * _W_AB_DELTA +
        quality_norm * _W_QUALITY +
        bench_score  * _W_BENCHMARK +
        eff_score    * _W_EFFECTIVENESS
    )
    return round(max(0.0, min(1.0, raw)), 4)


# ---------------------------------------------------------------------------
# Evidence count
# ---------------------------------------------------------------------------

def _compute_evidence_count(
    ab_winner: str,
    ai_effectiveness: str,
    creator_fit: str,
    quality: dict,
    ai_execution: dict,
) -> int:
    """Count distinct positive signals confirming the pattern (0–6)."""
    count = 0
    if ab_winner == "ai_on":
        count += 1
    if ai_effectiveness in ("strong", "moderate"):
        count += 1
    if creator_fit in ("high", "medium"):
        count += 1
    if (quality.get("subtitle", 0) >= _DOMAIN_QUALITY_THRESHOLD
            and ai_execution.get("subtitle_applied")):
        count += 1
    if (quality.get("camera", 0) >= _DOMAIN_QUALITY_THRESHOLD
            and ai_execution.get("camera_applied")):
        count += 1
    if quality.get("overall", 0) >= _DOMAIN_QUALITY_THRESHOLD:
        count += 1
    return count


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def _is_conflicting(
    ab_winner: str,
    creator_fit: str,
    overall_result: str,
    bench_status: str,
) -> bool:
    """True when positive and negative signals contradict each other."""
    # AI won AB test but benchmark says poor creator fit
    if ab_winner == "ai_on" and creator_fit == "low":
        return True
    # Outcome improved but benchmark evidence is against it
    if overall_result == "improved" and bench_status == "needs_review":
        return True
    return False


# ---------------------------------------------------------------------------
# Pattern classification
# ---------------------------------------------------------------------------

def _classify_pattern(
    success_score: float,
    evidence_count: int,
    is_conflicting: bool,
) -> str:
    """Classify pattern deterministically.

    conflicting_pattern takes precedence over score-based classification.
    """
    if is_conflicting:
        return "conflicting_pattern"
    if success_score >= _STRONG_SCORE and evidence_count >= _STRONG_EVIDENCE:
        return "strong_pattern"
    if success_score >= _MODERATE_SCORE and evidence_count >= _MODERATE_EVIDENCE:
        return "moderate_pattern"
    return "weak_pattern"


# ---------------------------------------------------------------------------
# Signal dict
# ---------------------------------------------------------------------------

def _build_signals(crs: dict) -> dict:
    """Extract key strategy signals from creator_render_strategy."""
    strategy = crs.get("strategy") or {}
    sub_s    = strategy.get("subtitle") or {}
    cam_s    = strategy.get("camera")   or {}
    hook_s   = strategy.get("hook")     or {}
    rank_s   = strategy.get("ranking")  or {}

    signals: dict = {}

    # Subtitle
    subtitle_style = str(sub_s.get("style") or "").strip()
    if subtitle_style:
        signals["subtitle_style"] = subtitle_style
    subtitle_density = str(sub_s.get("density") or "").strip()
    if subtitle_density:
        signals["subtitle_density"] = subtitle_density
    keyword_emphasis = str(sub_s.get("keyword_emphasis") or "").strip()
    if keyword_emphasis:
        signals["keyword_emphasis"] = keyword_emphasis

    # Camera
    stability = str(cam_s.get("stability_priority") or "").strip()
    if stability:
        signals["camera_stability"] = stability
    crop = str(cam_s.get("crop_aggressiveness") or "").strip()
    if crop:
        signals["camera_aggressiveness"] = crop
    motion = str(cam_s.get("motion_energy") or "").strip()
    if motion:
        signals["motion_energy"] = motion

    # Hook
    hook_energy = str(hook_s.get("hook_energy") or "").strip()
    if hook_energy:
        signals["hook_style"] = hook_energy

    # Ranking
    priority = str(rank_s.get("priority") or "").strip()
    if priority:
        signals["ranking_priority"] = priority

    return signals


def _camera_style_descriptor(stability: str, motion: str) -> str:
    """Derive a human-readable camera style descriptor."""
    if stability == "high" and motion in ("low", "low_medium"):
        return "stable"
    if motion in ("high", "medium_high"):
        return "dynamic"
    if stability == "high":
        return "stable_focused"
    return "balanced"


# ---------------------------------------------------------------------------
# Pattern ID
# ---------------------------------------------------------------------------

def _sanitize_id_part(s: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in s.lower())[:20]


def _make_pattern_id(
    creator_type: str,
    platform: str,
    subtitle_style: str,
    camera_style: str,
) -> str:
    """Build a safe, deterministic, human-readable pattern ID."""
    parts = [creator_type, platform, subtitle_style, camera_style]
    safe_parts = [_sanitize_id_part(p) for p in parts if p and p.lower() != "unknown"]
    result = "_".join(p for p in safe_parts if p)
    return result[:80] if result else "unknown_pattern"


# ---------------------------------------------------------------------------
# Reasoning builders
# ---------------------------------------------------------------------------

def _build_pattern_reasoning(
    classification: str,
    creator_type: str,
    platform: str,
    ab_winner: str,
    ab_overall_delta: int,
    ab_available: bool,
    quality: dict,
) -> list:
    lines: list = []
    platform_str = f" on {platform}" if platform and platform != "unknown" else ""

    if classification == "strong_pattern":
        lines.append(
            f"Stable framing and clean subtitles consistently improved {creator_type} content{platform_str}."
        )
    elif classification == "moderate_pattern":
        lines.append(
            f"{creator_type.replace('_', ' ').title()} content showed improvement with current subtitle/camera settings{platform_str}."
        )
    elif classification == "conflicting_pattern":
        lines.append(
            f"Mixed outcome signals for {creator_type}{platform_str} — no clear pattern yet."
        )
    else:
        lines.append(
            f"Evidence remains weak for {creator_type} on {platform}." if platform != "unknown"
            else f"Evidence remains weak for this {creator_type} creator type."
        )

    if ab_available and ab_winner == "ai_on" and ab_overall_delta > 0:
        lines.append(
            f"A/B winner ai_on with delta +{ab_overall_delta} confirms positive signal."
        )
    elif ab_available and ab_winner == "ai_off":
        lines.append("A/B winner ai_off — this combination underperformed vs baseline.")
    elif not ab_available:
        lines.append("No A/B baseline available — pattern confidence is conservative.")

    overall_q = quality.get("overall", 0)
    if overall_q >= 80:
        lines.append(f"Overall quality {overall_q} supports this pattern.")

    return lines[:_MAX_PATTERN_REASONING]


def _build_overall_reasoning(
    classification: str,
    creator_type: str,
    platform: str,
) -> list:
    lines: list = []
    platform_str = f" on {platform}" if platform and platform != "unknown" else ""

    if classification == "strong_pattern":
        lines.append(
            f"Strong creator-focused pattern detected for {creator_type}{platform_str}."
        )
        lines.append(
            "Stable creator-focused subtitle/camera combinations perform consistently."
        )
    elif classification == "moderate_pattern":
        lines.append(
            f"Moderate pattern detected for {creator_type}{platform_str} — improving but not yet strong."
        )
    elif classification == "conflicting_pattern":
        lines.append(
            f"Conflicting signals detected for {creator_type}{platform_str} — advisory only."
        )
        lines.append("Positive and negative evidence contradict — monitor across renders.")
    else:
        lines.append(
            f"Insufficient evidence for a reliable pattern for {creator_type}{platform_str}."
        )

    return lines[:_MAX_REASONING]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = (
            edit_plan.get(attr) if isinstance(edit_plan, dict)
            else getattr(edit_plan, attr, None)
        )
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _clamp_f(val: Any) -> float:
    try:
        return max(0.0, min(1.0, float(val or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _fallback() -> dict:
    return {
        "render_success_patterns": {
            "available":  False,
            "patterns":   [],
            "confidence": 0.0,
            "reasoning":  [],
        }
    }
