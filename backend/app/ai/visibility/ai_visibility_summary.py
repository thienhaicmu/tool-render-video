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

    if hook_score is not None and hook_score >= 70:
        _append_unique(badges, "Strong hook")
        _append_unique(reasons, "High hook score")
    if retention_score is not None and retention_score >= 70:
        _append_unique(badges, "Good retention")
        _append_unique(reasons, "Good retention score")
    if market_score is not None and market_score >= 65:
        _append_unique(badges, "Market fit")
        _append_unique(reasons, "Good market score")
    if duration_fit_score is not None and duration_fit_score >= 75:
        _append_unique(badges, "Good duration")
        _append_unique(reasons, "Good duration fit")
    if output_score is not None and output_score >= 70:
        _append_unique(badges, "Strong output rank")
        _append_unique(reasons, "Strong output score")

    rank = _as_int(part.get("output_rank"))
    if is_best or rank == 1 or bool(part.get("is_best_clip")) or bool(part.get("is_best_output")):
        if part.get("part_no") is not None or output_score is not None or part.get("output_file"):
            _append_unique(reasons, "Top ranked output")

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

    if badges:
        summary["badges"] = badges
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
