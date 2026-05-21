"""
retry_analyzer.py — S2.5 Retry Intelligence (single bounded retry).

Evaluates first-pass clip selection confidence, triggers one optional retry
when quality is below threshold, and keeps the better result only when it
improves by the minimum required margin.

Constraints:
  - Maximum 1 retry only. No recursion, no loops.
  - Retry triggers ONLY when confidence < RETRY_CONFIDENCE_THRESHOLD (60).
  - Keep retry result ONLY when improvement >= MIN_IMPROVEMENT_THRESHOLD (8).
  - All weight adjustments bounded to max multiplier 1.20 above original.
  - clip_count = 1 applies 0.5× aggressiveness to all adjustments.
  - RETRY_INTELLIGENCE_ENABLED=0 disables entirely (rollback gate).

Public API:
    evaluate_selection_confidence(selected_raw) -> float
    should_retry(confidence, clip_count) -> bool
    build_retry_config(mode_config, selected_raw, goal, clip_count) -> dict
    RETRY_INTELLIGENCE_ENABLED: bool
    RETRY_CONFIDENCE_THRESHOLD: float
    MIN_IMPROVEMENT_THRESHOLD: float
"""
from __future__ import annotations

import os

RETRY_INTELLIGENCE_ENABLED: bool = (
    os.environ.get("RETRY_INTELLIGENCE_ENABLED", "1") == "1"
)

RETRY_CONFIDENCE_THRESHOLD: float = 60.0
MIN_IMPROVEMENT_THRESHOLD: float = 8.0
_MAX_WEIGHT_MULTIPLIER: float = 1.20
_SINGLE_CLIP_AGGRESSIVENESS: float = 0.5


def evaluate_selection_confidence(selected_raw: list[dict]) -> float:
    """Quick confidence estimate from raw selection dicts before plan assembly.

    Mirrors _clip_confidence() in confidence.py but operates on raw selection
    dicts (not AIClipPlan objects) so it can run before plan assembly.

    Returns float [0, 100].
    """
    if not selected_raw:
        return 20.0

    scores = [float(s.get("score", 50.0)) for s in selected_raw]
    avg_score = sum(scores) / len(scores)
    fallback_used = any(s.get("source", "") == "scene_fallback" for s in selected_raw)

    base = 70.0
    if avg_score >= 75:
        base += 20.0
    elif avg_score >= 60:
        base += 10.0
    elif avg_score < 40:
        base -= 15.0

    if fallback_used:
        base -= 15.0

    return max(0.0, min(100.0, base))


def should_retry(confidence: float, clip_count: int) -> bool:
    """Return True when a retry pass is warranted.

    Retry fires only when RETRY_INTELLIGENCE_ENABLED and confidence is below
    the threshold. clip_count is accepted for API completeness; the threshold
    does not vary by count since a weak single clip is equally worth retrying.
    """
    if not RETRY_INTELLIGENCE_ENABLED:
        return False
    return confidence < RETRY_CONFIDENCE_THRESHOLD


def build_retry_config(
    mode_config: dict,
    selected_raw: list[dict],
    goal: str = "",
    clip_count: int = 1,
) -> dict:
    """Build a mode_config variant with conservative bounded strategy shifts.

    Detects weakness from reason annotations on selected_raw and applies
    targeted multipliers (max 1.20) to the relevant dimension weights.

    Signals detected from reason strings:
      weak_hook      — no segment annotated "hook=N" (hook_s was < 60 on all)
      weak_moment    — no segment annotated "moment=N" (moment_raw < 5 on all)
      weak_structure — no segment annotated "structure=N" (structure_raw < 5 on all)
      low_diversity  — 2+ segments with narrow score spread and no structure variety

    All deltas are scaled by 0.5 when clip_count = 1 for conservative retry.
    Returns a fresh dict copy — never mutates the original mode_config.
    """
    retry_config = dict(mode_config)
    aggressiveness = _SINGLE_CLIP_AGGRESSIVENESS if clip_count <= 1 else 1.0
    signals = _detect_weakness_signals(selected_raw)

    if signals["weak_hook"]:
        delta = 0.15 * aggressiveness
        orig = float(retry_config.get("hook_weight", 0.35))
        retry_config["hook_weight"] = min(orig * _MAX_WEIGHT_MULTIPLIER, orig * (1.0 + delta))

    if signals["weak_moment"]:
        delta = 0.15 * aggressiveness
        orig = float(retry_config.get("retry_moment_scale", 1.0))
        retry_config["retry_moment_scale"] = min(orig * _MAX_WEIGHT_MULTIPLIER, orig * (1.0 + delta))

    if signals["weak_structure"]:
        delta = 0.10 * aggressiveness
        orig = float(retry_config.get("retry_structure_scale", 1.0))
        retry_config["retry_structure_scale"] = min(orig * _MAX_WEIGHT_MULTIPLIER, orig * (1.0 + delta))

    if signals["low_diversity"]:
        delta = 0.10 * aggressiveness
        orig = float(retry_config.get("retry_diversity_scale", 1.0))
        retry_config["retry_diversity_scale"] = min(orig * _MAX_WEIGHT_MULTIPLIER, orig * (1.0 + delta))

    return retry_config


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_weakness_signals(selected_raw: list[dict]) -> dict[str, bool]:
    """Detect weakness signals from segment reason annotations."""
    if not selected_raw:
        return {"weak_hook": True, "weak_moment": True, "weak_structure": True, "low_diversity": False}

    has_hook = False
    has_moment = False
    has_structure = False

    for s in selected_raw:
        reason = str(s.get("reason", ""))
        for part in reason.split(","):
            part = part.strip()
            if part.startswith("hook="):
                has_hook = True
            elif part.startswith("moment="):
                has_moment = True
            elif part.startswith("structure="):
                has_structure = True

    # Low diversity: 2+ clips, narrow score spread, no structure variety detected.
    low_diversity = False
    if len(selected_raw) >= 2:
        scores = [float(s.get("score", 50.0)) for s in selected_raw]
        score_range = max(scores) - min(scores)
        low_diversity = score_range < 5.0 and not has_structure

    return {
        "weak_hook": not has_hook,
        "weak_moment": not has_moment,
        "weak_structure": not has_structure,
        "low_diversity": low_diversity,
    }
