import math
from typing import List, Dict


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _score_scene(scene: Dict, idx: int, total: int) -> float:
    duration = float(scene["end"]) - float(scene["start"])
    if duration <= 0:
        return 0.0

    # Scene quality heuristic:
    # - scenes too short/too long are usually weak for short-video rhythm
    # - early parts get slight hook bias
    duration_score = max(0.0, 100.0 - abs(duration - 4.5) * 12.0)
    transition_raw = float(scene.get("transition_score", 1.0))
    transition_score = _clamp(transition_raw * 60.0, 20.0, 100.0)
    early_bonus = 8.0 if float(scene["start"]) < 90.0 else (4.0 if float(scene["start"]) < 180.0 else 0.0)
    position_stability = 100.0 - (idx / max(total, 1)) * 15.0

    return (duration_score * 0.45) + (transition_score * 0.35) + (position_stability * 0.20) + early_bonus


def _normalize_scenes(scenes: List[Dict], total_duration: float) -> List[Dict]:
    normalized = []
    for i, s in enumerate(sorted(scenes or [], key=lambda x: float(x.get("start", 0.0)))):
        st = max(0.0, float(s.get("start", 0.0)))
        ed = min(total_duration, float(s.get("end", st)))
        if ed <= st:
            continue
        normalized.append({"start": st, "end": ed, "transition_score": float(s.get("transition_score", 1.0)), "_idx": i})
    if not normalized:
        normalized = [{"start": 0.0, "end": total_duration, "transition_score": 0.0, "_idx": 0}]
    return normalized


def _normalize_segment_durations(segments: List[Dict], min_len: float, max_len: float) -> List[Dict]:
    """
    Final normalization pass: clamp each segment so that:
      - end - start <= max_len   (hard upper bound, enforces UI max_part_sec)
      - duration_hint always equals end - start (no stale hints)
    """
    result = []
    for seg in segments:
        start = float(seg["start"])
        end   = float(seg["end"])

        if (end - start) > max_len:
            end = round(start + max_len, 3)

        duration_hint = round(end - start, 3)
        result.append({
            **seg,
            "end":           round(end, 3),
            "duration_hint": duration_hint,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Candidate generation (sliding window)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_candidates(scored_scenes: List[Dict], min_len: float, max_len: float) -> List[List[Dict]]:
    """Sliding-window candidate generation.

    For each scene as the segment start, expand forward adding scenes until the
    accumulated duration exceeds max_len.  A candidate is emitted at every step
    where duration >= min_len, giving multiple valid extents per start position.

    Returns a list of scene-lists; each inner list defines one candidate segment.
    """
    candidates: List[List[Dict]] = []
    n = len(scored_scenes)

    for start_i in range(n):
        window: List[Dict] = []
        seg_start = float(scored_scenes[start_i]["start"])
        seg_end   = seg_start

        for j in range(start_i, n):
            sc = scored_scenes[j]
            sc_end = float(sc["end"])
            if sc_end - seg_start > max_len:
                break
            window.append(sc)
            seg_end = sc_end
            if seg_end - seg_start >= min_len:
                candidates.append(list(window))

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# Segment-level viral_score v2
# ─────────────────────────────────────────────────────────────────────────────

def _score_candidate(scene_window: List[Dict], min_len: float, max_len: float) -> Dict:
    """Compute viral_score v2 for a candidate segment defined by scene_window.

    Returns a fully-annotated segment dict, or {} on degenerate input.
    """
    if not scene_window:
        return {}

    seg_start = float(scene_window[0]["start"])
    seg_end   = float(scene_window[-1]["end"])
    duration  = seg_end - seg_start
    if duration <= 0:
        return {}

    scene_qualities = [float(s["scene_quality"]) for s in scene_window]
    scene_durs      = [max(0.01, float(s["end"]) - float(s["start"])) for s in scene_window]

    # ── hook_opening_score ───────────────────────────────────────────────────
    first       = scene_window[0]
    first_q     = float(first["scene_quality"])
    first_trans = _clamp(float(first.get("transition_score", 1.0)) * 60.0, 20.0, 100.0)
    hook_opening_score = _clamp((first_q + first_trans) / 2.0, 0.0, 100.0)

    # ── avg_scene_quality ────────────────────────────────────────────────────
    avg_scene_quality = sum(scene_qualities) / len(scene_qualities)

    # ── scene_density [0,100] ────────────────────────────────────────────────
    # ~0.125 cuts/s normalises to 1.0; multiply *8 then scale to 100
    scene_density = _clamp(len(scene_window) / duration * 8.0, 0.0, 1.0) * 100.0

    # ── pacing_stability [0,100] ─────────────────────────────────────────────
    # Low standard deviation relative to mean = stable pacing
    mean_dur = sum(scene_durs) / len(scene_durs)
    variance = sum((d - mean_dur) ** 2 for d in scene_durs) / max(len(scene_durs), 1)
    pacing_stability = _clamp(1.0 - math.sqrt(variance) / max(mean_dur, 0.5), 0.0, 1.0) * 100.0

    # ── ending_strength ──────────────────────────────────────────────────────
    ending_strength = float(scene_window[-1]["scene_quality"])

    # ── gap_penalty [0,100] ──────────────────────────────────────────────────
    # Ratio of total timeline gaps to total segment duration, scaled to 100
    total_gap = 0.0
    for k in range(1, len(scene_window)):
        gap = float(scene_window[k]["start"]) - float(scene_window[k - 1]["end"])
        if gap > 0.0:
            total_gap += gap
    gap_ratio    = total_gap / max(duration, 1.0)
    gap_penalty  = _clamp(gap_ratio * 100.0, 0.0, 100.0)

    # ── penalties ────────────────────────────────────────────────────────────
    weak_open_penalty = 1.0 if hook_opening_score < 40.0 else 0.0
    overlong_penalty  = (
        _clamp((duration - max_len) / max(max_len, 1.0) * 100.0, 0.0, 100.0)
        if duration > max_len else 0.0
    )

    # ── retention_score [0,100] ──────────────────────────────────────────────
    retention_score = _clamp(
        pacing_stability * 0.6 + max(0.0, 100.0 - gap_penalty) * 0.4,
        0.0, 100.0,
    )

    # ── viral_score [0,100] ──────────────────────────────────────────────────
    raw_score = (
        hook_opening_score * 0.25
        + avg_scene_quality * 0.20
        + scene_density     * 0.15
        + pacing_stability  * 0.10
        + ending_strength   * 0.15
        + retention_score   * 0.15
    ) - (
        weak_open_penalty * 0.5
        + overlong_penalty  * 0.7
        + gap_penalty       * 0.3
    )
    viral_score = _clamp(raw_score, 0.0, 100.0)

    return {
        "start":             round(seg_start, 3),
        "end":               round(seg_end, 3),
        "duration_hint":     round(duration, 3),
        "scene_count":       len(scene_window),
        "scene_quality_avg": round(avg_scene_quality, 3),
        "hook_opening_score": round(hook_opening_score, 3),
        "momentum_score":    round(scene_density, 3),
        "payoff_score":      round(ending_strength, 3),
        "retention_score":   round(retention_score, 3),
        "viral_score":       round(viral_score, 3),
        "gap_penalty":       round(gap_penalty, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Non-overlapping selection
# ─────────────────────────────────────────────────────────────────────────────

def _select_non_overlapping(
    scored_candidates: List[Dict],
    max_overlap_ratio: float = 0.45,
) -> List[Dict]:
    """Greedy selection of best non-overlapping candidates.

    Sort descending by (viral_score, hook_opening_score, scene_quality_avg).
    Accept a candidate only when its overlap with every already-selected
    segment is below max_overlap_ratio (= overlap / shorter segment duration).
    Returns segments sorted by start time.
    """
    sorted_cands = sorted(
        scored_candidates,
        key=lambda x: (x["viral_score"], x["hook_opening_score"], x["scene_quality_avg"]),
        reverse=True,
    )

    selected: List[Dict] = []
    for cand in sorted_cands:
        c_start = cand["start"]
        c_end   = cand["end"]
        c_dur   = max(c_end - c_start, 0.001)

        ok = True
        for sel in selected:
            overlap = max(0.0, min(c_end, sel["end"]) - max(c_start, sel["start"]))
            ratio   = overlap / min(c_dur, max(sel["end"] - sel["start"], 0.001))
            if ratio >= max_overlap_ratio:
                ok = False
                break

        if ok:
            selected.append(cand)

    return sorted(selected, key=lambda x: x["start"])


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_FIELDS = {
    "scene_count":       1,
    "scene_quality_avg": 50.0,
    "hook_opening_score": 50.0,
    "momentum_score":    50.0,
    "payoff_score":      50.0,
    "retention_score":   50.0,
    "viral_score":       50.0,
    "gap_penalty":       0.0,
}


def build_segments_from_scenes(
    scenes: List[Dict],
    total_duration: int,
    min_part_sec: int = 70,
    max_part_sec: int = 180,
) -> List[Dict]:
    total = max(float(total_duration or 0), 0.0)
    if total <= 0:
        return []

    if min_part_sec > max_part_sec:
        min_part_sec, max_part_sec = max_part_sec, min_part_sec

    min_len = max(10.0, float(min_part_sec))
    max_len = max(min_len, float(max_part_sec))

    # ── 1. Normalize scenes and compute per-scene quality ────────────────────
    scenes_norm = _normalize_scenes(scenes, total)
    scored_scenes: List[Dict] = []
    for i, s in enumerate(scenes_norm):
        q = _score_scene(s, i, len(scenes_norm))
        scored_scenes.append({**s, "scene_quality": q})

    # ── 2. Sliding-window candidate generation ───────────────────────────────
    candidate_windows = _generate_candidates(scored_scenes, min_len, max_len)

    # ── 3. Score every candidate (viral_score v2) ────────────────────────────
    scored_candidates: List[Dict] = []
    for window in candidate_windows:
        result = _score_candidate(window, min_len, max_len)
        if result:
            scored_candidates.append(result)

    # ── 4. Select best non-overlapping segments ──────────────────────────────
    selected = _select_non_overlapping(scored_candidates) if scored_candidates else []

    # ── 5. Hard min/max enforcement (strict — no soft fractions) ────────────
    # Drop any segment that still falls below min_len (degenerate edge case).
    valid = [s for s in selected if (s["end"] - s["start"]) >= min_len]
    # Hard-clamp upper bound via existing normalizer.
    valid = _normalize_segment_durations(valid, min_len, max_len)

    # ── 6. Fallback ──────────────────────────────────────────────────────────
    if not valid:
        fallback_end = round(min(total, max_len), 3)
        valid = [{
            "start":         0.0,
            "end":           fallback_end,
            "duration_hint": fallback_end,
            **_FALLBACK_FIELDS,
        }]

    return valid
