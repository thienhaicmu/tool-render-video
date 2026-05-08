"""
clip_selector.py — Transcript-driven clip selection for the AI Director.

Scores candidate transcript windows and selects non-overlapping segments
that best fit the target mode duration and hook/density requirements.

Public API:
    select_ai_segments(chunks, scenes, duration, mode_config, target_duration) -> list[dict]
"""
from __future__ import annotations

from app.ai.analyzers.hook_analyzer import score_hook_text
from app.ai.analyzers.silence_analyzer import estimate_silence_penalty, score_speech_density

_DEFAULT_WEIGHTS: dict[str, float] = {
    "hook_weight": 0.35,
    "speech_density_weight": 0.35,
    "silence_penalty_weight": 0.20,
    "duration_weight": 0.10,
}

# Cap returned segments per plan to keep downstream logic manageable.
_MAX_SEGMENTS = 5


def select_ai_segments(
    chunks: list[dict],
    scenes: list[dict] | None,
    duration: float,
    mode_config: dict,
    target_duration: float | None = None,
) -> list[dict]:
    """Select the best transcript windows using hook + density + duration scoring.

    Falls back to scenes if no transcript data is available.
    Returns [] if neither transcript nor scenes are usable.

    Result dicts contain: start, end, score, reason, source.
    """
    target_min, target_max = _resolve_targets(mode_config, target_duration)

    weights = _resolve_weights(mode_config)

    if not chunks:
        return _select_from_scenes(scenes or [], target_min, target_max)

    candidates = _build_and_score_candidates(chunks, target_min, target_max, weights)

    if not candidates:
        return _select_from_scenes(scenes or [], target_min, target_max)

    return _deduplicate(candidates)[:_MAX_SEGMENTS]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_targets(mode_config: dict, target_duration: float | None) -> tuple[float, float]:
    t_min = float(mode_config.get("preferred_duration_min", 60))
    t_max = float(mode_config.get("preferred_duration_max", 90))
    if target_duration and target_duration > 0:
        half = target_duration * 0.15
        t_min = max(10.0, target_duration - half)
        t_max = target_duration + half
    return t_min, t_max


def _resolve_weights(mode_config: dict) -> dict[str, float]:
    return {
        "hook": float(mode_config.get("hook_weight", _DEFAULT_WEIGHTS["hook_weight"])),
        "density": float(mode_config.get("speech_density_weight", _DEFAULT_WEIGHTS["speech_density_weight"])),
        "silence": float(mode_config.get("silence_penalty_weight", _DEFAULT_WEIGHTS["silence_penalty_weight"])),
        "duration": float(mode_config.get("duration_weight", _DEFAULT_WEIGHTS["duration_weight"])),
    }


def _duration_fit_score(dur: float, t_min: float, t_max: float) -> float:
    if t_min <= dur <= t_max:
        return 100.0
    if dur < t_min:
        return max(0.0, (dur / max(1.0, t_min)) * 100.0)
    return max(0.0, (t_max / max(1.0, dur)) * 100.0)


def _build_window(chunks: list[dict], start_idx: int, t_max: float) -> dict | None:
    if start_idx >= len(chunks):
        return None
    origin = float(chunks[start_idx].get("start") or 0.0)
    window: list[dict] = []
    for chunk in chunks[start_idx:]:
        if float(chunk.get("end") or 0.0) - origin > t_max:
            break
        window.append(chunk)
    if not window:
        return None
    end = float(window[-1].get("end") or origin)
    return {"start": origin, "end": end, "duration": end - origin, "chunks": window}


def _build_and_score_candidates(
    chunks: list[dict],
    t_min: float,
    t_max: float,
    weights: dict[str, float],
) -> list[dict]:
    candidates: list[dict] = []
    # Sample starting points to avoid O(n²) on long transcripts.
    step = max(1, len(chunks) // 12)

    for i in range(0, len(chunks), step):
        win = _build_window(chunks, i, t_max)
        if not win or win["duration"] < t_min * 0.4:
            continue

        win_chunks = win["chunks"]
        first_text = win_chunks[0].get("text", "") if win_chunks else ""

        hook_s = score_hook_text(first_text)
        density_s = (
            sum(score_speech_density(c) for c in win_chunks) / len(win_chunks)
            if win_chunks else 0.0
        )
        silence_pen = estimate_silence_penalty(win_chunks)
        dur_s = _duration_fit_score(win["duration"], t_min, t_max)

        final = (
            hook_s * weights["hook"]
            + density_s * weights["density"]
            + dur_s * weights["duration"]
            - silence_pen * weights["silence"]
        )
        final = round(max(0.0, min(100.0, final)), 2)

        parts: list[str] = []
        if hook_s >= 60:
            parts.append(f"hook={hook_s:.0f}")
        if density_s >= 60:
            parts.append(f"density={density_s:.0f}")
        if silence_pen > 30:
            parts.append(f"silence_penalty={silence_pen:.0f}")

        candidates.append({
            "start": win["start"],
            "end": win["end"],
            "score": final,
            "reason": ", ".join(parts) or "ai_scored",
            "source": "local_ai",
            "duration": win["duration"],
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def _deduplicate(candidates: list[dict]) -> list[dict]:
    """Keep highest-scoring non-overlapping windows."""
    selected: list[dict] = []
    for c in candidates:
        overlaps = any(
            not (c["end"] <= s["start"] or c["start"] >= s["end"])
            for s in selected
        )
        if not overlaps:
            selected.append(c)
    return selected


def _select_from_scenes(scenes: list[dict], t_min: float, t_max: float) -> list[dict]:
    if not scenes:
        return []
    best = max(
        scenes,
        key=lambda s: float(s.get("motion_score") or s.get("viral_score") or 0),
    )
    start = float(best.get("start") or 0.0)
    end = float(best.get("end") or start + t_min)
    return [{
        "start": start,
        "end": end,
        "score": 50.0,
        "reason": "scene_fallback",
        "source": "scene_score",
    }]
