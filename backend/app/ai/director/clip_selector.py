"""
clip_selector.py — Transcript-driven clip selection for the AI Director.

Scores candidate transcript windows and selects non-overlapping segments
that best fit the target mode duration and hook/density requirements.

Public API:
    select_ai_segments(chunks, scenes, duration, mode_config, target_duration) -> list[dict]
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.analysis.signals import AnalysisSignals

from app.ai.analyzers.hook_analyzer import (
    score_hook_text,
    score_hook_intelligence,
    get_opening_window_text,
    detect_hook_type,
)
from app.ai.analyzers.moment_analyzer import score_best_moment
from app.ai.analyzers.silence_analyzer import estimate_silence_penalty, score_speech_density
from app.ai.analyzers.audio_energy_analyzer import score_audio_energy
from app.ai.analyzers.feedback_scorer import apply_feedback_bias

try:
    from app.ai.analyzers.structure_analyzer import (
        score_structure_coherence as _struct_score,
        find_entry_point as _struct_find_entry,
        analyze_window_structure as _struct_analyze,
        STRUCTURE_INTELLIGENCE_ENABLED as _STRUCTURE_ENABLED,
    )
    _STRUCTURE_AVAILABLE = True
except ImportError:
    _STRUCTURE_AVAILABLE = False
    _STRUCTURE_ENABLED = False

    def _struct_score(*a, **kw) -> float: return 0.0           # type: ignore[misc]
    def _struct_find_entry(all_chunks, current_idx, *a, **kw):  # type: ignore[misc]
        return current_idx, 0.0
    def _struct_analyze(*a, **kw) -> dict:                      # type: ignore[misc]
        return {"phases_detected": []}

try:
    from app.ai.analyzers.diversity_analyzer import (
        build_candidate_context as _div_build_ctx,
        compute_diversity_penalty as _div_penalty,
        DIVERSITY_INTELLIGENCE_ENABLED as _DIVERSITY_ENABLED,
    )
    _DIVERSITY_AVAILABLE = True
except ImportError:
    _DIVERSITY_AVAILABLE = False
    _DIVERSITY_ENABLED = False

    def _div_build_ctx(*a, **kw) -> dict: return {}             # type: ignore[misc]
    def _div_penalty(*a, **kw) -> float: return 0.0             # type: ignore[misc]

_DEFAULT_WEIGHTS: dict[str, float] = {
    "hook_weight": 0.35,
    "speech_density_weight": 0.35,
    "silence_penalty_weight": 0.20,
    "duration_weight": 0.10,
}

# Cap returned segments per plan to keep downstream logic manageable.
_MAX_SEGMENTS = 5

# Fine-scan parameters (Phase 4)
_FINE_SCAN_RADIUS_SEC = 15.0   # scan ±N seconds around each top coarse candidate
_FINE_SCAN_TOP_N      = 3      # fine-scan around the top N coarse results
_FINE_SCAN_DEDUP_SEC  = 5.0    # candidates within this distance treated as duplicates
_FINE_SCAN_MIN_CHUNKS = 15     # only worth running when transcript has enough chunks


def select_ai_segments(
    chunks: list[dict],
    scenes: list[dict] | None,
    duration: float,
    mode_config: dict,
    target_duration: float | None = None,
    memory_context: dict | None = None,
    content_analysis=None,
    enrichment: "AnalysisSignals | None" = None,
    max_segments: int = _MAX_SEGMENTS,
    feedback_context: dict | None = None,
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
    # S2.5: retry scales — optional keys set by retry_analyzer for a second pass.
    # Absent on normal passes (defaults to 1.0 = no change).
    retry_scales = {
        "moment":    float(mode_config.get("retry_moment_scale", 1.0)),
        "structure": float(mode_config.get("retry_structure_scale", 1.0)),
        "diversity": float(mode_config.get("retry_diversity_scale", 1.0)),
    }
    candidates = _build_and_score_candidates(
        chunks, target_min, target_max, weights, goal=goal, retry_scales=retry_scales,
    )

    if not candidates:
        return _select_from_scenes(scenes or [], target_min, target_max)

    # Phase 4: Fine-scan ±_FINE_SCAN_RADIUS_SEC around top coarse candidates.
    # Only runs when transcript is long enough for coarse sampling to have skipped chunks.
    if len(chunks) >= _FINE_SCAN_MIN_CHUNKS:
        fine = _fine_scan_around(
            chunks, candidates[:_FINE_SCAN_TOP_N],
            target_min, target_max, weights, goal, retry_scales,
        )
        if fine:
            merged = candidates + fine
            merged.sort(key=lambda c: c["score"], reverse=True)
            candidates = _deduplicate_by_proximity(merged, _FINE_SCAN_DEDUP_SEC)

    if enrichment is not None:
        candidates = _apply_cloud_enrichment(candidates, enrichment)

    if feedback_context is not None:
        candidates = apply_feedback_bias(candidates, feedback_context)

    candidates = _apply_hook_proximity_boost(candidates, content_analysis)

    selected = _select_diverse(candidates, goal, max_segments, diversity_scale=retry_scales["diversity"])
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
    retry_scales: dict | None = None,
) -> list[dict]:
    candidates: list[dict] = []
    # Sample starting points to avoid O(n²) on long transcripts.
    step = max(1, len(chunks) // 12)
    # Total duration estimate for position_ratio used in diversity context.
    total_duration = float(chunks[-1].get("end") or 1.0) if chunks else 1.0
    moment_scale   = retry_scales.get("moment",    1.0) if retry_scales else 1.0
    structure_scale = retry_scales.get("structure", 1.0) if retry_scales else 1.0

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
        # Detect hook type and structure phases for diversity context (S2.4).
        hook_type = detect_hook_type(opening_text) if opening_text else "none"
        phases_detected = (
            _struct_analyze(win_chunks, win["start"], win["end"]).get("phases_detected", [])
            if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED else []
        )
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
        # S2.5: moment_scale (default 1.0) applied during retry pass only.
        moment_raw = score_best_moment(win_chunks, win["start"], win["end"], goal)
        final = min(100.0, final + moment_raw * 0.25 * moment_scale)

        # S2.3: structure coherence bonus — separate additive, max +3 effective.
        # score_structure_coherence returns [0,20]; scale by 0.15 → max +3.
        # S2.5: structure_scale (default 1.0) applied during retry pass only.
        structure_raw = (
            _struct_score(win_chunks, win["start"], win["end"], goal)
            if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED else 0.0
        )
        final = round(min(100.0, final + structure_raw * 0.15 * structure_scale), 2)

        # Phase 5: audio energy proxy bonus — max +4 effective ([0,20] * 0.20).
        # Detects high-energy windows via exclamation density, caps, energy
        # keywords, and speech acceleration — no audio file required.
        energy_raw = score_audio_energy(win_chunks, win["start"], win["end"], goal)
        final = round(min(100.0, final + energy_raw * 0.20), 2)

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
        if energy_raw >= 5.0:
            parts.append(f"energy={energy_raw:.0f}")

        candidates.append({
            "start":          win["start"],
            "end":            win["end"],
            "score":          final,
            "reason":         ", ".join(parts) or "ai_scored",
            "source":         "local_ai",
            "duration":       win["duration"],
            # Diversity context fields (S2.4) — used by _select_diverse, not
            # part of the external contract; stripped before returning to callers.
            "_hook_type":     hook_type,
            "_phases":        phases_detected,
            "_position_ratio": win["start"] / max(total_duration, 1.0),
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def _select_diverse(
    candidates: list[dict],
    goal: str,
    clip_count: int,
    diversity_scale: float = 1.0,
) -> list[dict]:
    """Select up to clip_count non-overlapping candidates with diversity awareness.

    Candidates must be pre-sorted by score descending.

    Algorithm (O(n²) over ~12 candidates — negligible cost):
      For each selection round, compute a diversity-adjusted comparison score
      for every remaining candidate.  Pick the highest adjusted-score candidate
      that doesn't overlap already-selected windows.  Repeat until clip_count
      is reached or no non-overlapping candidates remain.

    Diversity penalty is for ORDERING ONLY.  Output dicts carry the original
    pre-penalty score.  Internal diversity context fields (_hook_type, _phases,
    _position_ratio) are stripped before returning.

    diversity_scale (default 1.0): S2.5 retry multiplier — set > 1.0 during a
    retry pass to enforce stronger diversity on low-variety first-pass results.
    """
    if not candidates:
        return []

    top_score  = candidates[0]["score"]
    selected:       list[dict] = []
    selected_ctxs:  list[dict] = []

    remaining = list(candidates)

    while remaining and len(selected) < clip_count:
        best: dict | None = None
        best_adj = -1.0

        for c in remaining:
            # Temporal overlap check (binary, unchanged from original _deduplicate).
            if any(not (c["end"] <= s["start"] or c["start"] >= s["end"]) for s in selected):
                continue

            # Diversity-adjusted comparison score (never stored in output).
            # S2.5: diversity_scale multiplies the penalty during retry passes
            # where low variety was detected (scale > 1.0 = more enforcement).
            if _DIVERSITY_AVAILABLE and _DIVERSITY_ENABLED and selected_ctxs:
                ctx = _div_build_ctx(
                    hook_type=c.get("_hook_type", "none"),
                    phases=c.get("_phases", []),
                    position_ratio=c.get("_position_ratio", 0.5),
                )
                penalty = _div_penalty(
                    ctx, selected_ctxs, goal,
                    top_score=top_score,
                    candidate_score=c["score"],
                    clip_count=clip_count,
                ) * diversity_scale
            else:
                penalty = 0.0

            # Phase 2: clip_type diversity — penalise repeating the same clip_type
            cand_clip_type = c.get("clip_type", "unknown")
            if cand_clip_type != "unknown" and selected:
                same_type_count = sum(
                    1 for s in selected if s.get("clip_type") == cand_clip_type
                )
                penalty += same_type_count * 3.0 * diversity_scale

            adj = c["score"] - penalty
            if adj > best_adj:
                best_adj = adj
                best = c

        if best is None:
            break

        remaining.remove(best)
        # Build diversity context from the chosen candidate's internal fields,
        # then strip those fields before adding to output.
        ctx_for_tracking = _div_build_ctx(
            hook_type=best.get("_hook_type", "none"),
            phases=best.get("_phases", []),
            position_ratio=best.get("_position_ratio", 0.5),
        )
        selected_ctxs.append(ctx_for_tracking)
        out = {k: v for k, v in best.items() if not k.startswith("_")}
        # S3.1: expose S2 signal context before internal fields are stripped.
        out["hook_intelligence_type"] = best.get("_hook_type", "none")
        out["structure_phases"]       = list(best.get("_phases", []))
        out["moment_type"]            = str(ctx_for_tracking.get("moment_type", "unknown"))
        selected.append(out)

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


def _apply_hook_proximity_boost(
    candidates: list[dict],
    content_analysis,
) -> list[dict]:
    """Boost candidate scores when they start near a pre-identified hook position.

    Max boost: +5.0 (same magnitude as memory bonus to keep relative influence balanced).
    Formula: boost = proximity_factor * (hook_score / 100) * 5.0
      - proximity_factor = max(0, 1 - dist / 8.0)  [falls to zero at 8s distance]
      - hook_score = score field from ContentAnalysisResult.hook_positions (0–100)

    Candidates are re-sorted after boosting. Never raises.
    """
    hook_positions = getattr(content_analysis, "hook_positions", None) or []
    if not hook_positions:
        return candidates

    try:
        for c in candidates:
            best_boost = 0.0
            c_start = float(c.get("start", 0))
            for h in hook_positions:
                dist = abs(c_start - float(h.get("time", 0)))
                if dist >= 8.0:
                    continue
                h_score = float(h.get("score", 0))
                if h_score <= 0:
                    continue
                boost = max(0.0, 1.0 - dist / 8.0) * (h_score / 100.0) * 5.0
                best_boost = max(best_boost, boost)
            if best_boost > 0:
                c["score"] = round(min(100.0, c["score"] + best_boost), 2)
                reason = c.get("reason", "ai_scored")
                c["reason"] = f"{reason}, hook_proximity" if reason else "hook_proximity"
        candidates.sort(key=lambda x: x["score"], reverse=True)
    except Exception:
        pass  # never block clip selection on boost failure

    return candidates


def _apply_cloud_enrichment(
    candidates: list[dict],
    enrichment: "AnalysisSignals",
) -> list[dict]:
    """Blend cloud clip scores into local candidate scores.

    For each local candidate, finds the closest cloud ClipSignal within
    _CLOUD_MATCH_TOLERANCE seconds. Blends scores and overrides hook_type
    when the cloud signal is more specific. Re-sorts by score after blending.
    Never raises — returns candidates unchanged on any error.
    """
    _CLOUD_MATCH_TOLERANCE = 8.0
    _CLOUD_WEIGHT = 0.70
    _LOCAL_WEIGHT = 0.30

    if not enrichment.clip_signals:
        return candidates
    try:
        for cand in candidates:
            c_start = float(cand.get("start", 0.0))
            best_match = None
            best_dist = float("inf")
            for cs in enrichment.clip_signals:
                dist = abs(cs.start - c_start)
                if dist < best_dist and dist <= _CLOUD_MATCH_TOLERANCE:
                    best_dist = dist
                    best_match = cs
            if best_match is not None:
                orig = float(cand.get("score", 50.0))
                blended = orig * _LOCAL_WEIGHT + best_match.hook_score * _CLOUD_WEIGHT
                cand["score"] = round(max(0.0, min(100.0, blended)), 2)
                if best_match.hook_type and best_match.hook_type != "none":
                    cand["hook_intelligence_type"] = best_match.hook_type
                if best_match.reason:
                    cand["reason"] = f"[hybrid] {best_match.reason}"
                if best_match.clip_type and best_match.clip_type != "unknown":
                    cand["clip_type"] = best_match.clip_type
                if best_match.thumbnail_sec is not None:
                    cand["thumbnail_sec"] = best_match.thumbnail_sec
        candidates.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    except Exception:
        pass  # never block clip selection on enrichment failure
    return candidates


def _fine_scan_around(
    chunks: list[dict],
    top_candidates: list[dict],
    t_min: float,
    t_max: float,
    weights: dict[str, float],
    goal: str,
    retry_scales: dict | None,
) -> list[dict]:
    """Step-1 scan in ±_FINE_SCAN_RADIUS_SEC around each top coarse candidate.

    The coarse pass uses step=len(chunks)//12, which may skip over the optimal
    entry point by several chunks. This pass closes that gap by evaluating every
    chunk start within the radius, producing more precisely aligned candidates.

    Returns scored candidate dicts (same schema as _build_and_score_candidates).
    Never raises — returns [] on any error.
    """
    if not chunks or not top_candidates:
        return []
    try:
        moment_scale   = retry_scales.get("moment",    1.0) if retry_scales else 1.0
        structure_scale = retry_scales.get("structure", 1.0) if retry_scales else 1.0
        total_duration  = float(chunks[-1].get("end") or 1.0)

        scanned_indices: set[int] = set()
        fine_candidates: list[dict] = []

        for c in top_candidates:
            center = float(c.get("start", 0.0))
            lo = center - _FINE_SCAN_RADIUS_SEC
            hi = center + _FINE_SCAN_RADIUS_SEC

            for idx, chunk in enumerate(chunks):
                chunk_start = float(chunk.get("start") or 0.0)
                if chunk_start < lo:
                    continue
                if chunk_start > hi:
                    break
                if idx in scanned_indices:
                    continue
                scanned_indices.add(idx)

                win = _build_window(chunks, idx, t_max)
                if not win or win["duration"] < t_min * 0.4:
                    continue

                if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED:
                    new_idx, _ = _struct_find_entry(chunks, idx, goal, t_min * 0.4, win["end"])
                    if new_idx != idx:
                        trimmed = _build_window(chunks, new_idx, t_max)
                        if trimmed and trimmed["duration"] >= t_min * 0.4:
                            win = trimmed

                win_chunks = win["chunks"]
                opening_text = get_opening_window_text(win_chunks, win["start"])
                base_hook    = score_hook_text(opening_text)
                intel_bonus  = score_hook_intelligence(opening_text, goal)
                hook_s       = min(100.0, base_hook + intel_bonus)
                hook_type    = detect_hook_type(opening_text) if opening_text else "none"
                phases       = (
                    _struct_analyze(win_chunks, win["start"], win["end"]).get("phases_detected", [])
                    if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED else []
                )
                density_s  = (
                    sum(score_speech_density(ch) for ch in win_chunks) / len(win_chunks)
                    if win_chunks else 0.0
                )
                silence_pen = estimate_silence_penalty(win_chunks)
                dur_s       = _duration_fit_score(win["duration"], t_min, t_max)

                final = (
                    hook_s   * weights["hook"]
                    + density_s * weights["density"]
                    + dur_s     * weights["duration"]
                    - silence_pen * weights["silence"]
                )
                final = max(0.0, min(100.0, final))

                moment_raw = score_best_moment(win_chunks, win["start"], win["end"], goal)
                final = min(100.0, final + moment_raw * 0.25 * moment_scale)

                structure_raw = (
                    _struct_score(win_chunks, win["start"], win["end"], goal)
                    if _STRUCTURE_AVAILABLE and _STRUCTURE_ENABLED else 0.0
                )
                final = round(min(100.0, final + structure_raw * 0.15 * structure_scale), 2)

                parts: list[str] = ["fine_scan"]
                if hook_s >= 60:
                    parts.append(f"hook={hook_s:.0f}")
                if density_s >= 60:
                    parts.append(f"density={density_s:.0f}")

                fine_candidates.append({
                    "start":           win["start"],
                    "end":             win["end"],
                    "score":           final,
                    "reason":          ", ".join(parts),
                    "source":          "local_ai_fine",
                    "duration":        win["duration"],
                    "_hook_type":      hook_type,
                    "_phases":         phases,
                    "_position_ratio": win["start"] / max(total_duration, 1.0),
                })

        return fine_candidates
    except Exception:
        return []


def _deduplicate_by_proximity(
    candidates: list[dict],
    tolerance_sec: float,
) -> list[dict]:
    """Remove candidates whose start is within tolerance_sec of a higher-scored one.

    Assumes candidates are sorted descending by score (highest first).
    Preserves the original score — proximity dedup is for ordering only.
    """
    result: list[dict] = []
    for c in candidates:
        c_start = float(c.get("start", 0.0))
        if any(abs(c_start - float(r.get("start", 0.0))) < tolerance_sec for r in result):
            continue
        result.append(c)
    return result


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
