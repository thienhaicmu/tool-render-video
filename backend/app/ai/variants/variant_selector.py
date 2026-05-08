"""
variant_selector.py — Deterministic AI best variant selector. Phase 22.

Analyzes generated variants and selects the best advisory candidate.
Never raises. Never renders. Never mutates payload. Advisory-only.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.variants.variant_schema import AIVariantSet, AIVariantPlan
from app.ai.variants.variant_scoring import score_variant

logger = logging.getLogger("app.ai.variants")

# Minimum confidence to select a non-baseline variant
_MIN_SELECTION_CONFIDENCE: float = 0.50

# Purpose preference order (lower index = higher preference when scores tie)
_PURPOSE_PRIORITY: list[str] = [
    "retention",
    "hook",
    "story",
    "subtitle",
    "creator_style",
    "pacing",
    "safe_baseline",
]

# Risk ordering for tiebreak (lower index = preferred)
_RISK_PRIORITY: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


def select_best_variant(
    variant_set: Any,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Select the best advisory variant from a set.

    Returns:
        {
            "selected_variant_id": str | None,
            "selection_confidence": float,
            "selection_reasons": list[str],
            "rejected_variants": list[dict],
            "fallback_used": bool,
        }
    Never raises. Never renders. Never mutates payload.
    """
    try:
        return _select(variant_set, edit_plan, context or {})
    except Exception as exc:
        logger.debug("select_best_variant_failed: %s", exc)
        return _error_result(str(exc))


def _select(
    variant_set: Any,
    edit_plan: Any,
    context: dict,
) -> dict:
    # Resolve variants list
    variants: list[AIVariantPlan] = []
    try:
        if isinstance(variant_set, AIVariantSet):
            variants = list(variant_set.variants)
        elif isinstance(variant_set, dict):
            raw = variant_set.get("variants") or []
            # Already-serialised dicts — build lightweight proxies
            variants = [_dict_to_variant(v) for v in raw if isinstance(v, dict)]
        elif hasattr(variant_set, "variants"):
            variants = list(variant_set.variants)
    except Exception:
        variants = []

    if not variants:
        logger.info("ai_variant_selection_skipped: no variants available")
        return {
            "selected_variant_id": None,
            "selection_confidence": 0.0,
            "selection_reasons": ["no_variants_available"],
            "rejected_variants": [],
            "fallback_used": True,
        }

    # Score every variant
    scored: list[tuple[AIVariantPlan, dict]] = []
    for v in variants:
        try:
            result = score_variant(v, edit_plan, context)
            scored.append((v, result))
        except Exception:
            scored.append((v, {"score": 0.0, "expected_gain": 0.0, "reasons": [], "warnings": []}))

    # Sort: highest score first; tiebreak by purpose priority; tiebreak by risk priority
    def _sort_key(item: tuple[AIVariantPlan, dict]) -> tuple:
        v, r = item
        purpose_rank = next(
            (i for i, p in enumerate(_PURPOSE_PRIORITY) if p == v.purpose),
            len(_PURPOSE_PRIORITY),
        )
        risk_rank = _RISK_PRIORITY.get(str(v.risk), 2)
        return (-r["score"], purpose_rank, risk_rank)

    scored.sort(key=_sort_key)

    # Find the best safe candidate (non-high-risk with safe_to_render)
    best: Optional[tuple[AIVariantPlan, dict]] = None
    fallback_used = False

    for v, r in scored:
        if v.risk == "high":
            continue  # high-risk variants skipped unless sole option
        if v.safe_to_render or v.purpose == "safe_baseline":
            best = (v, r)
            break

    # If no safe candidate found, use any non-high-risk
    if best is None:
        for v, r in scored:
            if v.risk != "high":
                best = (v, r)
                break

    # Final fallback: first variant regardless of risk (only-option scenario)
    if best is None and scored:
        best = scored[0]
        fallback_used = True

    if best is None:
        return {
            "selected_variant_id": None,
            "selection_confidence": 0.0,
            "selection_reasons": ["no_selectable_variant"],
            "rejected_variants": _build_rejected(scored, None),
            "fallback_used": True,
        }

    selected_v, selected_r = best
    raw_score = float(selected_r.get("score", 0.0))
    selection_confidence = round(min(1.0, max(0.0, raw_score / 100.0)), 4)

    # Confidence gate: if too low, fall back to safe_baseline
    baseline_variant = next(
        (v for v, _ in scored if v.purpose == "safe_baseline"), None
    )
    if (
        selection_confidence < _MIN_SELECTION_CONFIDENCE
        and selected_v.purpose != "safe_baseline"
        and baseline_variant is not None
    ):
        fallback_used = True
        selected_v = baseline_variant
        baseline_score = next(
            (r for v, r in scored if v is baseline_variant),
            {"score": 60.0},
        )
        selection_confidence = round(
            min(1.0, max(0.0, float(baseline_score.get("score", 60.0)) / 100.0)), 4
        )
        selected_r = baseline_score
        logger.info(
            "ai_variant_selector_fallback variant_id=%s reason=low_confidence",
            selected_v.variant_id,
        )

    # Build selection reasons
    selection_reasons = _build_reasons(selected_v, selected_r, fallback_used)

    logger.info(
        "ai_variant_selected variant_id=%s purpose=%s confidence=%.4f fallback=%s",
        selected_v.variant_id,
        selected_v.purpose,
        selection_confidence,
        fallback_used,
    )

    return {
        "selected_variant_id": str(selected_v.variant_id),
        "selection_confidence": selection_confidence,
        "selection_reasons": selection_reasons,
        "rejected_variants": _build_rejected(scored, selected_v.variant_id),
        "fallback_used": fallback_used,
    }


def _build_reasons(
    variant: AIVariantPlan,
    score_result: dict,
    fallback_used: bool,
) -> list[str]:
    reasons: list[str] = []
    if fallback_used:
        reasons.append("low_confidence_fallback_to_safe_baseline")
    purpose = variant.purpose
    if purpose == "safe_baseline":
        reasons.append("safe_baseline_selected_for_stability")
    elif purpose == "retention":
        reasons.append("retention_focused_variant_highest_score")
    elif purpose == "hook":
        reasons.append("hook_strengthening_variant_highest_score")
    elif purpose == "story":
        reasons.append("story_coherence_variant_highest_score")
    elif purpose == "subtitle":
        reasons.append("subtitle_optimization_variant_highest_score")
    elif purpose == "creator_style":
        reasons.append("creator_style_match_variant_highest_score")
    elif purpose == "pacing":
        reasons.append("pacing_variant_highest_score")

    # Add scoring reasons (top 2)
    score_reasons = score_result.get("reasons") or []
    for r in score_reasons[:2]:
        if r not in reasons:
            reasons.append(r)

    return reasons


def _build_rejected(
    scored: list[tuple[AIVariantPlan, dict]],
    selected_id: Optional[str],
) -> list[dict]:
    rejected = []
    for v, r in scored:
        if str(v.variant_id) == str(selected_id or ""):
            continue
        rejected.append({
            "variant_id": str(v.variant_id),
            "purpose": str(v.purpose),
            "score": float(r.get("score", 0.0)),
            "reason": "lower_score_or_higher_risk",
        })
    return rejected


def _dict_to_variant(d: dict) -> AIVariantPlan:
    """Reconstruct a minimal AIVariantPlan from a serialised dict."""
    from app.ai.variants.variant_schema import AIVariantPlan
    return AIVariantPlan(
        variant_id=str(d.get("variant_id") or ""),
        label=str(d.get("label") or ""),
        purpose=str(d.get("purpose") or "safe_baseline"),
        confidence=float(d.get("confidence") or 0.0),
        risk=str(d.get("risk") or "low"),
        suggested_changes=dict(d.get("suggested_changes") or {}),
        expected_gain=float(d.get("expected_gain") or 0.0),
        safe_to_render=bool(d.get("safe_to_render") or False),
        warnings=list(d.get("warnings") or []),
    )


def _error_result(exc_name: str) -> dict:
    return {
        "selected_variant_id": None,
        "selection_confidence": 0.0,
        "selection_reasons": [f"selector_error:{exc_name}"],
        "rejected_variants": [],
        "fallback_used": True,
    }
