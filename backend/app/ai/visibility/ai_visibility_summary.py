from __future__ import annotations

from copy import deepcopy
from typing import Any


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_score(part: dict, names: list[str]) -> float | None:
    for name in names:
        if name in part:
            score = _as_float(part.get(name))
            if score is not None:
                return score
    components = part.get("ranking_components")
    if isinstance(components, dict):
        for name in names:
            if name in components:
                score = _as_float(components.get(name))
                if score is not None:
                    return score
    return None


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


_CONFIDENCE_LABELS: dict[str, str] = {
    "strong":        "Strong candidate",
    "worth_testing": "Worth testing",
    "experimental":  "Experimental pick",
}

_SIGNAL_BADGE_LABELS: dict[str, str] = {
    "hook_score":           "Strong hook",
    "retention_score":      "Good retention",
    "market_score":         "Market fit",
    "duration_fit_score":   "Good duration",
    "segment_viral_score":  "High energy",
    "speech_density_score": "Speech density",
}


def build_ai_visibility_summary(part: dict, *, is_best: bool = False) -> dict:
    """Build UI-ready explainability from existing output metadata only."""
    if not isinstance(part, dict) or not part:
        return {}

    badges: list[str] = []
    reasons: list[str] = []
    warnings: list[str] = []
    signals: dict[str, float] = {}

    output_score = _first_score(part, ["output_score", "output_rank_score", "final_score"])
    hook_score = _first_score(part, ["hook_score"])
    retention_score = _first_score(part, ["retention_score"])
    market_score = _first_score(part, ["market_score", "market_viral_score", "mv_viral_score"])
    duration_fit_score = _first_score(part, ["duration_fit_score"])
    quality_penalty = _first_score(part, ["quality_penalty"])

    for key, value in {
        "output_score": output_score,
        "hook_score": hook_score,
        "retention_score": retention_score,
        "market_score": market_score,
        "duration_fit_score": duration_fit_score,
        "quality_penalty": quality_penalty,
    }.items():
        if value is not None:
            signals[key] = round(value, 3)

    # Max 2 badges — dominant signal first, then one suppressed signal that scored highly
    dominant = str(part.get("dominant_signal") or "")
    if dominant and dominant in _SIGNAL_BADGE_LABELS:
        dom_val = _first_score(part, [dominant])
        if dom_val is not None and dom_val >= 60:
            _append_unique(badges, _SIGNAL_BADGE_LABELS[dominant])

    suppressed = part.get("suppressed_signals")
    if isinstance(suppressed, list) and len(badges) < 2:
        for sup in suppressed[:2]:
            if sup in _SIGNAL_BADGE_LABELS and sup != dominant:
                sup_val = _first_score(part, [sup])
                if sup_val is not None and sup_val >= 65:
                    _append_unique(badges, _SIGNAL_BADGE_LABELS[sup])
                    if len(badges) >= 2:
                        break

    # Ranking reason is the primary reason — already contribution-weighted from _output_ranking_reason
    ranking_reason = str(part.get("ranking_reason") or "").strip()
    if ranking_reason:
        _append_unique(reasons, ranking_reason)

    selection_reason = str(part.get("selection_reason") or "").strip()
    if selection_reason:
        _append_unique(reasons, selection_reason)

    for key in ("partial_failure_warning", "output_ranking_warning", "warning"):
        warning = str(part.get(key) or "").strip()
        if warning:
            _append_unique(warnings, warning)
    for key in ("warnings", "quality_flags"):
        values = part.get(key)
        if isinstance(values, list):
            for value in values:
                warning = str(value or "").strip()
                if warning:
                    _append_unique(warnings, warning)
    if quality_penalty is not None and quality_penalty > 0:
        _append_unique(warnings, f"Quality penalty applied: -{int(quality_penalty)}")

    summary: dict[str, Any] = {}
    if is_best and (part.get("part_no") is not None or output_score is not None or part.get("output_file")):
        summary["is_best"] = True
        summary["headline"] = "AI recommended clip"

    confidence_tier = str(part.get("confidence_tier") or "").strip()
    if confidence_tier and confidence_tier in _CONFIDENCE_LABELS:
        summary["confidence_tier"] = confidence_tier
        summary["confidence_label"] = _CONFIDENCE_LABELS[confidence_tier]

    if badges:
        summary["badges"] = badges[:2]
    if reasons:
        summary["reasons"] = reasons
    if warnings:
        summary["warnings"] = warnings
    if signals:
        summary["signals"] = signals

    return summary


def attach_ai_visibility_summaries(entries: list[dict]) -> list[dict]:
    """Return copies of output-ranking entries with additive visibility metadata."""
    output: list[dict] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        item = deepcopy(entry)
        summary = build_ai_visibility_summary(
            item,
            is_best=bool(item.get("is_best_clip") or item.get("is_best_output")),
        )
        if summary:
            item["ai_visibility_summary"] = summary
        output.append(item)
    return output
