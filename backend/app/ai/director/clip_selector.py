"""
clip_selector.py — Transcript-driven clip selection for the AI Director.

Scores candidate transcript windows and selects non-overlapping segments
that best fit the target mode duration and hook/density requirements.

Public API:
    select_ai_segments(chunks, scenes, duration, mode_config, target_duration) -> list[dict]
"""
from __future__ import annotations

from app.ai.analyzers.hook_analyzer import (
    score_hook_text,
    score_hook_intelligence,
    get_opening_window_text,
)
from app.ai.analyzers.moment_analyzer import score_best_moment
from app.ai.analyzers.silence_analyzer import estimate_silence_penalty, score_speech_density

try:
    from app.ai.analyzers.structure_analyzer import (
        score_structure_coherence as _struct_score,
        find_entry_point as _struct_find_entry,
        STRUCTURE_INTELLIGENCE_ENABLED as _STRUCTURE_ENABLED,
    )
    _STRUCTURE_AVAILABLE = True
except ImportError:
    _STRUCTURE_AVAILABLE = False
    _STRUCTURE_ENABLED = False

    def _struct_score(*a, **kw) -> float: return 0.0           # type: ignore[misc]
    def _struct_find_entry(all_chunks, current_idx, *a, **kw):  # type: ignore[misc]
        return current_idx, 0.0

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
    memory_context: dict | None = None,
) -> list[dict]:
    """Select the best transcript windows using hook + density + duration scoring.

    Falls back to scenes if no transcript data is available.
    Returns [] if neither transcript nor scenes are usable.

    Result dicts contain: start, end, score, reason, source.

    memory_context: optional RAG result dict (from retrieve_ai_context). When
    results with score > 0.7 are present a small bonus is added to the top
    candidate and the reason is annotated with "rag_match".
    """
    target_min, target_max = _resolve_targets(mode_config, target_duration)

    weights = _resolve_weights(mode_config)

    if not chunks:
        return _select_from_scenes(scenes or [], target_min, target_max)

    goal = mode_config.get("goal", "")
    candidates = _build_and_score_candidates(chunks, target_min, target_max, weights, goal=goal)

    if not candidates:
        return _select_from_scenes(scenes or [], target_min, target_max)

    selected = _deduplicate(candidates)[:_MAX_SEGMENTS]
    return _apply_memory_bonus(selected, memory_context)


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
    goal: str = "",
) -> list[dict]:
    candidates: list[dict] = []
    # Sample starting points to avoid O(n²) on long transcripts.
    step = max(1, len(chunks) // 12)

    for i in range(0, len(chunks), step):
        win = _build_window(chunks, i, t_max)
        if not win or win["duration"] < t_min * 0.4:
            continue

        # S2.3: Micro-trim entry-point alignment BEFORE any scoring (required change 3).
        # Scans backward up to goal-aware max (3–8s) for a cleaner hook entry.
        # Only accepts the trim when hook quality improves by >= +10 raw delta.
        # All signals below are computed on the final (possibly trimmed) window.
        if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED:
            new_idx, _delta = _struct_find_entry(
                chunks, i, goal, t_min * 0.4, win["end"]
            )
            if new_idx != i:
                trimmed = _build_window(chunks, new_idx, t_max)
                if trimmed and trimmed["duration"] >= t_min * 0.4:
                    win = trimmed

        win_chunks = win["chunks"]

        # Score hook on the opening window of this candidate (first ~10s from
        # candidate start), not the head of the source video — critical for
        # long-form content where strong hooks appear deep into the file.
        opening_text = get_opening_window_text(win_chunks, win["start"])
        base_hook = score_hook_text(opening_text)
        intel_bonus = score_hook_intelligence(opening_text, goal)
        hook_s = min(100.0, base_hook + intel_bonus)
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
        final = max(0.0, min(100.0, final))

        # S2.2: best-moment bonus — separate additive signal, not blended into
        # existing weights. score_best_moment returns [0,20]; scale to [0,5]
        # to keep effective influence modest relative to the main formula.
        moment_raw = score_best_moment(win_chunks, win["start"], win["end"], goal)
        final = min(100.0, final + moment_raw * 0.25)

        # S2.3: structure coherence bonus — separate additive, max +3 effective.
        # score_structure_coherence returns [0,20]; scale by 0.15 → max +3.
        structure_raw = (
            _struct_score(win_chunks, win["start"], win["end"], goal)
            if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED else 0.0
        )
        final = round(min(100.0, final + structure_raw * 0.15), 2)

        parts: list[str] = []
        if hook_s >= 60:
            parts.append(f"hook={hook_s:.0f}")
        if density_s >= 60:
            parts.append(f"density={density_s:.0f}")
        if silence_pen > 30:
            parts.append(f"silence_penalty={silence_pen:.0f}")
        if moment_raw >= 5.0:
            parts.append(f"moment={moment_raw:.0f}")
        if structure_raw >= 5.0:
            parts.append(f"structure={structure_raw:.0f}")

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


def _apply_memory_bonus(
    segments: list[dict],
    memory_context: dict | None,
) -> list[dict]:
    """Boost the top segment score by up to +5 when strong RAG hits exist."""
    if not segments or not memory_context:
        return segments
    results = memory_context.get("results") or []
    high_score_hits = [r for r in results if float(r.get("score") or 0.0) > 0.7]
    if not high_score_hits:
        return segments
    bonus = min(5.0, len(high_score_hits) * 2.0)
    top = dict(segments[0])
    top["score"] = round(min(100.0, top["score"] + bonus), 2)
    reason = top.get("reason", "ai_scored")
    top["reason"] = f"{reason}, rag_match" if reason else "rag_match"
    return [top] + segments[1:]


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
