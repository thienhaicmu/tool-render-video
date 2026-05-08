"""
output_ranker.py — Deterministic AI output ranker.

Phase 30: ranks completed variant outputs using available metadata.
No file reads, no file writes, no network, no GPU. Never raises.

Scoring model (all additive, clamped to [0, 100]):
  base                   50.0
  + output_score bonus   up to +30 (scaled from existing rank score)
  + selected variant     +10 if output matches variant_selection
  + creator style fit    +5 if style confidence >= 0.60
  + retention/story gain +5 if simulation estimated_retention_gain > 0
  - quality penalty      -10 per warning flag
  - failed output        -50 (makes failed outputs rank last)
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from .output_schema import AIOutputScore, AIOutputRanking
from .output_safety import sanitize_output_metadata, is_output_rankable

logger = logging.getLogger(__name__)

_SCORE_BASE = 50.0
_SELECTED_VARIANT_BONUS = 10.0
_CREATOR_STYLE_BONUS = 5.0
_RETENTION_GAIN_BONUS = 5.0
_WARNING_PENALTY = 10.0
_FAILED_PENALTY = 50.0
_OUTPUT_SCORE_MAX_BONUS = 30.0


def rank_variant_outputs(
    outputs: Any,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> AIOutputRanking:
    """Rank variant outputs deterministically using available metadata. Never raises."""
    context = context or {}
    try:
        output_list = _normalize_outputs(outputs)
        if not output_list:
            return AIOutputRanking(
                available=False,
                mode="recommendation_only",
                outputs=[],
                best_output_id=None,
                best_output_path="",
                warnings=["no_rankable_outputs"],
            )

        ai_context = _extract_ai_context(edit_plan)
        scored = [_score_output(o, ai_context) for o in output_list]
        scored.sort(key=lambda x: x.score, reverse=True)

        for rank_idx, s in enumerate(scored, start=1):
            s.rank = rank_idx

        if scored:
            scored[0].recommended = True

        best = scored[0] if scored else None
        warnings: list[str] = []
        if any(s.warnings for s in scored):
            warnings.append("some_outputs_have_warnings")

        ranking = AIOutputRanking(
            available=True,
            mode="recommendation_only",
            outputs=scored,
            best_output_id=best.output_id if best else None,
            best_output_path=best.path if best else "",
            warnings=warnings,
        )

        logger.info(
            "ai_output_ranking_created outputs=%d best=%s",
            len(scored), ranking.best_output_id or "none",
        )
        return ranking

    except Exception as exc:
        logger.warning("ai_output_ranking_fallback: %s", exc)
        return AIOutputRanking(
            available=False,
            mode="recommendation_only",
            outputs=[],
            best_output_id=None,
            best_output_path="",
            warnings=[f"ai_output_ranking_error:{type(exc).__name__}"],
        )


def _normalize_outputs(outputs: Any) -> list[dict]:
    """Normalize various output formats into a list of rankable dicts. Never raises."""
    if not outputs:
        return []
    if isinstance(outputs, dict):
        outputs = [outputs]
    if not isinstance(outputs, (list, tuple)):
        return []
    result = []
    for i, o in enumerate(outputs):
        if isinstance(o, str):
            o = {"output_id": f"out_{i}", "path": o}
        if not isinstance(o, dict):
            continue
        safe = sanitize_output_metadata(o)
        if not safe.get("output_id"):
            safe["output_id"] = str(o.get("part_no") or f"out_{i}")
        if not safe.get("path"):
            safe["path"] = str(o.get("output_file") or o.get("path") or "")
        if is_output_rankable(safe):
            result.append(safe)
    return result


def _extract_ai_context(edit_plan: Any) -> dict:
    """Extract relevant AI metadata from the edit plan. Never raises."""
    try:
        if edit_plan is None:
            return {}
        result: dict = {}

        vs = getattr(edit_plan, "variant_selection", None)
        if isinstance(vs, dict):
            result["recommended_variant_id"] = (
                vs.get("recommended_variant_id") or vs.get("selected_id") or ""
            )

        csa = getattr(edit_plan, "creator_style_adaptation", None)
        if isinstance(csa, dict):
            result["creator_style"] = csa.get("adapted_style") or csa.get("detected_style") or ""
            result["creator_style_confidence"] = float(csa.get("confidence", 0.0))

        sim = getattr(edit_plan, "execution_simulation", None)
        if isinstance(sim, dict):
            sims = sim.get("simulations") or []
            if sims and isinstance(sims[0], dict):
                result["estimated_retention_gain"] = float(
                    sims[0].get("estimated_retention_gain", 0.0)
                )

        mvx = getattr(edit_plan, "multivariant_execution", None)
        if isinstance(mvx, dict):
            result["executed_plan_ids"] = list(mvx.get("executed_plan_ids") or [])

        return result
    except Exception:
        return {}


def _score_output(output: dict, ai_context: dict) -> AIOutputScore:
    """Score a single output entry. Never raises."""
    try:
        output_id = str(output.get("output_id") or "")
        path = str(output.get("path") or "")
        variant_id = str(output.get("variant_id") or output.get("plan_id") or "")
        failed = bool(output.get("failed", False))
        warnings_list: list[str] = []

        # Start from base
        score = _SCORE_BASE
        explanation: list[str] = [f"base={_SCORE_BASE}"]

        # Penalty for failed output
        if failed:
            score -= _FAILED_PENALTY
            warnings_list.append("output_failed")
            explanation.append(f"failed_penalty=-{_FAILED_PENALTY}")

        # Existing output_rank_score bonus (up to +30)
        existing_score = float(
            output.get("output_rank_score")
            or output.get("final_score")
            or output.get("output_score")
            or 0.0
        )
        if existing_score > 0:
            bonus = round(min(_OUTPUT_SCORE_MAX_BONUS, existing_score * 0.30), 2)
            score += bonus
            explanation.append(f"rank_score_bonus=+{bonus}")

        # Selected variant bonus
        recommended_variant = ai_context.get("recommended_variant_id") or ""
        executed_ids = ai_context.get("executed_plan_ids") or []
        if variant_id and (variant_id == recommended_variant or variant_id in executed_ids):
            score += _SELECTED_VARIANT_BONUS
            explanation.append(f"selected_variant_bonus=+{_SELECTED_VARIANT_BONUS}")

        # Creator style confidence bonus
        style_conf = float(ai_context.get("creator_style_confidence", 0.0))
        if style_conf >= 0.60:
            score += _CREATOR_STYLE_BONUS
            explanation.append(f"creator_style_bonus=+{_CREATOR_STYLE_BONUS}")

        # Retention/simulation gain bonus
        retention_gain = float(ai_context.get("estimated_retention_gain", 0.0))
        if retention_gain > 0:
            score += _RETENTION_GAIN_BONUS
            explanation.append(f"retention_gain_bonus=+{_RETENTION_GAIN_BONUS}")

        # Warning penalty
        raw_warnings = output.get("warnings") or []
        if isinstance(raw_warnings, list) and raw_warnings:
            penalty = min(len(raw_warnings), 3) * _WARNING_PENALTY
            score -= penalty
            warnings_list.extend(str(w) for w in raw_warnings[:3])
            explanation.append(f"warning_penalty=-{penalty}")

        # Quality flags from validation
        quality_flags: list[str] = []
        validation_passed = output.get("validation_passed")
        if validation_passed is False:
            quality_flags.append("validation_failed")
            score -= _WARNING_PENALTY
            explanation.append(f"validation_penalty=-{_WARNING_PENALTY}")
        elif validation_passed is True:
            quality_flags.append("validation_passed")

        # Size/duration indicators
        size = output.get("size_bytes")
        if isinstance(size, (int, float)) and size > 0:
            quality_flags.append("has_size")
        duration = output.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            quality_flags.append("has_duration")

        score = round(max(0.0, min(100.0, score)), 2)
        confidence = 0.85 if not failed else 0.40

        return AIOutputScore(
            output_id=output_id,
            path=path,
            variant_id=variant_id,
            score=score,
            confidence=confidence,
            rank=0,  # assigned after sorting
            recommended=False,  # assigned after sorting
            quality_flags=quality_flags,
            warnings=warnings_list,
            explanation=explanation,
        )
    except Exception as exc:
        return AIOutputScore(
            output_id=str(output.get("output_id") or "unknown"),
            path="",
            score=0.0,
            confidence=0.0,
            warnings=[f"scoring_error:{type(exc).__name__}"],
            explanation=["error during scoring"],
        )
