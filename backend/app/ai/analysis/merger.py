"""
merger.py — Merge strategy for combining local and cloud AnalysisSignals.

Configurable weights per signal type. Cloud generally wins on semantic signals;
local wins on technical signals. If cloud is None, local is returned unchanged.
"""
from __future__ import annotations

from app.ai.analysis.signals import (
    AnalysisSignals, ClipSignal, EmotionSignal,
)

# ── Blend weights ─────────────────────────────────────────────────────────────
# cloud=1.0 → use cloud exclusively; cloud=0.0 → use local exclusively
_WEIGHTS: dict[str, float] = {
    "clip_hook_score":  0.70,   # cloud better at semantic hook detection
    "clip_relevance":   0.70,
    "emotion_score":    0.65,
    "confidence":       0.60,   # how much cloud confidence contributes
}

# Fuzzy match window: cloud (start, end) matches local candidate within ±N seconds
_WINDOW_MATCH_TOLERANCE = 8.0


def merge(local: AnalysisSignals, cloud: AnalysisSignals | None) -> AnalysisSignals:
    """Return merged AnalysisSignals. If cloud is None, returns local unchanged."""
    if cloud is None:
        return local

    return AnalysisSignals(
        clip_signals=_merge_clips(local.clip_signals, cloud.clip_signals),
        emotion=_merge_emotion(local.emotion, cloud.emotion),
        subtitle_hints=cloud.subtitle_hints or local.subtitle_hints,
        camera_hints=cloud.camera_hints or local.camera_hints,
        confidence=round(
            local.confidence * (1 - _WEIGHTS["confidence"])
            + cloud.confidence * _WEIGHTS["confidence"],
            3,
        ),
        source="hybrid",
        warnings=list(local.warnings) + [f"cloud:{w}" for w in cloud.warnings],
    )


# ── Clip merging ───────────────────────────────────────────────────────────────

def _merge_clips(
    local: list[ClipSignal],
    cloud: list[ClipSignal],
) -> list[ClipSignal]:
    if not cloud:
        return local
    if not local:
        return cloud

    cw = _WEIGHTS["clip_hook_score"]
    lw = 1.0 - cw
    result: list[ClipSignal] = []

    for ls in local:
        match = _closest_cloud(ls, cloud)
        if match:
            blended_hook = round(ls.hook_score * lw + match.hook_score * cw, 2)
            blended_rel = round(ls.relevance_score * lw + match.relevance_score * cw, 2)
            hook_type = match.hook_type if match.hook_type != "none" else ls.hook_type
            result.append(ClipSignal(
                start=ls.start,
                end=ls.end,
                hook_score=max(0.0, min(100.0, blended_hook)),
                hook_type=hook_type,
                relevance_score=max(0.0, min(100.0, blended_rel)),
                reason=match.reason or ls.reason,
                source="hybrid",
            ))
        else:
            result.append(ls)

    # Include cloud-only windows that have no local counterpart
    matched_starts = {c.start for c in result}
    for cs in cloud:
        if not any(abs(cs.start - ms) <= _WINDOW_MATCH_TOLERANCE for ms in matched_starts):
            result.append(cs)

    return result


def _merge_emotion(local: EmotionSignal, cloud: EmotionSignal) -> EmotionSignal:
    cw = _WEIGHTS["emotion_score"]
    lw = 1.0 - cw
    dominant = cloud.dominant if cloud.score >= 40.0 else local.dominant
    blended = round(local.score * lw + cloud.score * cw, 2)
    return EmotionSignal(dominant=dominant, score=blended, source="hybrid")


def _closest_cloud(target: ClipSignal, pool: list[ClipSignal]) -> ClipSignal | None:
    best: ClipSignal | None = None
    best_dist = float("inf")
    for c in pool:
        d = abs(c.start - target.start)
        if d < best_dist and d <= _WINDOW_MATCH_TOLERANCE:
            best_dist = d
            best = c
    return best
