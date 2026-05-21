"""
structure_analyzer.py — Structure-aware clip coherence analysis (S2.3).

Detects three-phase narrative structure (opening → development → payoff) within
candidate windows. Detection uses multi-signal confidence combining:
  - phrase markers       (0.40 weight — necessary but not sufficient alone)
  - position in window   (0.35 weight — each phase has an expected position range)
  - transition signals   (0.25 weight — emotion shift, density shift, natural start)

A phase is only "detected" when confidence >= 0.50.  Without a phrase marker, the
maximum achievable confidence is 0.35, so keyword-only false positives are impossible.

Set STRUCTURE_INTELLIGENCE_ENABLED=0 to disable entirely (rollback gate).

Public API:
    get_window_chunks(chunks, start, end)                    -> list[dict]
    analyze_window_structure(chunks, start, end)             -> dict
    score_structure_coherence(chunks, start, end, goal)      -> float ([0, +20])
    find_entry_point(all_chunks, current_idx, goal, ...)     -> tuple[int, float]
    STRUCTURE_INTELLIGENCE_ENABLED: bool
"""
from __future__ import annotations

import os
import re

STRUCTURE_INTELLIGENCE_ENABLED: bool = (
    os.environ.get("STRUCTURE_INTELLIGENCE_ENABLED", "1") == "1"
)

# Confidence threshold — a phase must score this to be considered "detected".
# Requires phrase marker + at least partial position or transition support.
# B2 (Calibration Sprint): externalized so casual/informal speech can use 0.42
# without a code change. Hard floor at 0.35 (below that, position-only false
# positives become likely; phrase markers lose their "necessary" status).
_DETECT_THRESHOLD: float = float(os.environ.get("S3_STRUCTURE_DETECT_THRESHOLD", "0.50"))

# ---------------------------------------------------------------------------
# Phase marker vocabulary — EN + VI
# Multi-word phrases use substring matching; single ASCII words use \b boundary.
# ---------------------------------------------------------------------------

_PHASE1_MARKERS: list[str] = [
    # Conversational openers
    "okay so", "alright", "so here's the thing", "here's the thing",
    "here is the thing", "let me tell you", "imagine", "picture this",
    "real quick", "wait a second", "you know what",
    "check this out", "listen", "i want to talk about",
    # Vietnamese
    "được rồi", "khoan đã", "hãy tưởng tượng", "nghe này",
]

_PHASE2_MARKERS: list[str] = [
    # Causal / explanatory
    "because", "here's why", "what happened was", "so what i did",
    "let me explain", "what this means is", "in other words",
    "the reason is", "what i did was",
    # Sequential / temporal
    "first", "second", "third", "then", "next", "after that",
    "as soon as", "step by step",
    # Elaborative
    "for example", "for instance", "basically", "essentially",
    "the thing is", "what i mean", "to break it down",
    # Vietnamese
    "vì", "lý do là", "ví dụ", "nghĩa là", "đầu tiên",
    "sau đó", "tiếp theo", "ví dụ như",
]

_PHASE3_MARKERS: list[str] = [
    # Conclusive
    "turns out", "in the end", "at the end of the day", "ultimately",
    "the point is", "and that's how", "which means", "so the conclusion",
    "to summarize", "long story short",
    # Result / resolution
    "the result was", "it worked", "the answer is", "i realized",
    "what i learned", "what i found", "the lesson is",
    "the key takeaway", "so what i learned",
    # Vietnamese
    "kết quả là", "cuối cùng", "điều tôi học được", "bài học là",
    "tóm lại", "nói ngắn gọn", "vì vậy cuối cùng",
]

# ---------------------------------------------------------------------------
# Goal-aware structure bonuses
# raw score [0, 20] — when multiplied by 0.15 in clip_selector gives max +3 effective.
# Levels: open_only, open_payoff (hook + close without middle), full (all 3 phases).
# ---------------------------------------------------------------------------

_GOAL_STRUCTURE_BONUSES: dict[str, dict[str, float]] = {
    "viral":        {"open_only": 5.0, "open_payoff": 12.0, "full": 18.0},
    "education":    {"open_only": 2.0, "open_payoff":  8.0, "full": 20.0},
    "podcast":      {"open_only": 3.0, "open_payoff":  8.0, "full": 15.0},
    "product":      {"open_only": 4.0, "open_payoff": 12.0, "full": 18.0},
    "storytelling": {"open_only": 3.0, "open_payoff": 10.0, "full": 20.0},
}
_DEFAULT_STRUCTURE_BONUSES = {"open_only": 3.0, "open_payoff": 8.0, "full": 15.0}

# ---------------------------------------------------------------------------
# Goal-aware max backward trim (seconds) for entry-point alignment.
# Viral clips prefer tight pacing; education/storytelling allow more setup context.
# ---------------------------------------------------------------------------

_GOAL_MAX_TRIM: dict[str, float] = {
    "viral":        3.0,
    "education":    7.0,
    "podcast":      5.0,
    "product":      5.0,
    "storytelling": 8.0,
}
_DEFAULT_MAX_TRIM = 5.0

# Natural entry bonus added to hook score when a candidate chunk starts after
# sentence-final punctuation in the previous chunk.
_NATURAL_START_BONUS = 5.0

# Minimum improvement in hook+entry quality required to accept a trim.
_TRIM_DELTA_THRESHOLD = 10.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_markers(text_lower: str, markers: list[str]) -> bool:
    """Return True if any marker phrase matches in text_lower."""
    for marker in markers:
        words = marker.split()
        if len(words) == 1 and marker.isascii():
            if re.search(r"\b" + re.escape(marker) + r"\b", text_lower):
                return True
        else:
            if marker in text_lower:
                return True
    return False


def _position_score(ratio: float, peak: float, spread: float) -> float:
    """Linear ramp scoring how well `ratio` aligns with a phase's expected position."""
    return max(0.0, 1.0 - abs(ratio - peak) / spread)


def _compute_emotion_scores(chunks: list[dict]) -> list[float]:
    """Pre-compute emotion score per chunk; degrades gracefully on import failure."""
    try:
        from app.ai.analyzers.emotion_analyzer import analyze_text_emotion
        return [
            float(analyze_text_emotion(c.get("text") or "").get("score") or 0.0)
            for c in chunks
        ]
    except Exception:
        return [0.0] * len(chunks)


def _ends_sentence(chunk: dict) -> bool:
    """True if chunk text ends with sentence-final punctuation."""
    text = (chunk.get("text") or "").strip()
    return bool(text and text[-1] in ".!?")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_window_chunks(
    chunks: list[dict],
    candidate_start: float,
    candidate_end: float,
) -> list[dict]:
    """Filter transcript chunks that fall within the candidate window."""
    return [
        c for c in (chunks or [])
        if float(c.get("end") or 0.0) > candidate_start
        and float(c.get("start") or 0.0) < candidate_end
    ]


def analyze_window_structure(
    chunks: list[dict],
    start: float,
    end: float,
) -> dict:
    """Analyse three-phase structure within the candidate window.

    Multi-signal confidence per chunk:
      marker_hit  × 0.40  (necessary contributor — alone stays below threshold)
      position    × 0.35  (does this chunk appear where the phase is expected?)
      transition  × 0.25  (emotion shift + density shift + natural start)

    A phase is detected only when confidence >= 0.50, ensuring no single signal
    can trigger a false positive alone.

    Returns:
        opening_confidence     float [0, 1]
        development_confidence float [0, 1]
        payoff_confidence      float [0, 1]
        phases_detected        list[str]
    """
    window = get_window_chunks(chunks, start, end)
    if len(window) < 2:
        return {
            "opening_confidence": 0.0,
            "development_confidence": 0.0,
            "payoff_confidence": 0.0,
            "phases_detected": [],
        }

    w_start = float(window[0].get("start") or start)
    w_end   = float(window[-1].get("end") or end)
    w_dur   = max(w_end - w_start, 1.0)

    emotion_scores = _compute_emotion_scores(window)

    best_p1 = best_p2 = best_p3 = 0.0

    for i, chunk in enumerate(window):
        t = float(chunk.get("start") or w_start)
        ratio = max(0.0, min(1.0, (t - w_start) / w_dur))
        text_lower = (chunk.get("text") or "").lower()

        # ── Signal 1: phrase markers ────────────────────────────────────────
        hit_p1 = _check_markers(text_lower, _PHASE1_MARKERS)
        hit_p2 = _check_markers(text_lower, _PHASE2_MARKERS)
        hit_p3 = _check_markers(text_lower, _PHASE3_MARKERS)

        # ── Signal 2: position fit ──────────────────────────────────────────
        # Phase 1 peaks at 10%, Phase 2 at 45%, Phase 3 at 88%
        pos_p1 = _position_score(ratio, peak=0.10, spread=0.25)
        pos_p2 = _position_score(ratio, peak=0.45, spread=0.35)
        pos_p3 = _position_score(ratio, peak=0.88, spread=0.25)

        # ── Signal 3: transition (emotion shift + density shift + context) ──
        if i > 0:
            em_delta = abs(emotion_scores[i] - emotion_scores[i - 1]) / 100.0
            prev_density = float(window[i - 1].get("speech_density") or 0.0)
            cur_density  = float(chunk.get("speech_density") or 0.0)
            dens_delta   = min(1.0, abs(cur_density - prev_density) * 3.0)
            nat_start    = 0.20 if _ends_sentence(window[i - 1]) else 0.0
        else:
            em_delta = dens_delta = 0.0
            nat_start = 0.20  # first chunk always treated as a clean start

        transition = min(1.0, em_delta * 0.50 + dens_delta * 0.30 + nat_start)

        # ── Combine: marker required to exceed threshold ────────────────────
        if hit_p1:
            c1 = 0.40 + pos_p1 * 0.35 + transition * 0.25
        else:
            c1 = pos_p1 * 0.20 + transition * 0.15

        if hit_p2:
            c2 = 0.40 + pos_p2 * 0.35 + transition * 0.25
        else:
            c2 = pos_p2 * 0.20 + transition * 0.15

        if hit_p3:
            c3 = 0.40 + pos_p3 * 0.35 + transition * 0.25
        else:
            c3 = pos_p3 * 0.20 + transition * 0.15

        if c1 > best_p1: best_p1 = min(1.0, c1)
        if c2 > best_p2: best_p2 = min(1.0, c2)
        if c3 > best_p3: best_p3 = min(1.0, c3)

    phases_detected = []
    if best_p1 >= _DETECT_THRESHOLD: phases_detected.append("opening")
    if best_p2 >= _DETECT_THRESHOLD: phases_detected.append("development")
    if best_p3 >= _DETECT_THRESHOLD: phases_detected.append("payoff")

    return {
        "opening_confidence":     round(best_p1, 3),
        "development_confidence": round(best_p2, 3),
        "payoff_confidence":      round(best_p3, 3),
        "phases_detected":        phases_detected,
    }


def score_structure_coherence(
    chunks: list[dict],
    start: float,
    end: float,
    goal: str = "",
) -> float:
    """Score narrative structure coherence for a candidate window.

    Returns an additive bonus in [0, +20]. When multiplied by 0.15 in
    clip_selector the effective contribution to final score is max +3.

    Returns 0.0 when:
      - STRUCTURE_INTELLIGENCE_ENABLED is False (env gate)
      - chunks is empty (graceful degradation)
      - no phases are reliably detected (multi-signal threshold not met)

    Goal-aware: different goals reward different structural completeness levels.
    """
    if not STRUCTURE_INTELLIGENCE_ENABLED or not chunks:
        return 0.0

    analysis = analyze_window_structure(chunks, start, end)
    phases = analysis["phases_detected"]
    if not phases:
        return 0.0

    goal_key = str(goal or "").lower().strip()
    bonuses = _GOAL_STRUCTURE_BONUSES.get(goal_key, _DEFAULT_STRUCTURE_BONUSES)

    if "opening" in phases and "development" in phases and "payoff" in phases:
        raw = bonuses["full"]
    elif "opening" in phases and "payoff" in phases:
        raw = bonuses["open_payoff"]
    elif "opening" in phases:
        raw = bonuses["open_only"]
    else:
        raw = 0.0

    if raw <= 0.0:
        return 0.0

    # Scale by average confidence of detected phases to reward conviction.
    total_conf = (
        analysis["opening_confidence"]
        + analysis["development_confidence"]
        + analysis["payoff_confidence"]
    )
    avg_conf = total_conf / 3.0
    return max(0.0, min(20.0, raw * avg_conf))


def find_entry_point(
    all_chunks: list[dict],
    current_idx: int,
    goal: str = "",
    min_duration: float = 0.0,
    candidate_end: float = None,
) -> tuple[int, float]:
    """Scan backward from current_idx to find a better hook entry point.

    For each candidate chunk within max_trim_sec before the current start,
    computes entry quality using S2.1 hook scoring plus a natural-start bonus.
    A natural start (previous chunk ends with sentence-final punctuation) earns
    +5 raw points — incentivising clean, contextually appropriate entry points.

    Returns (new_idx, delta) where delta is the score improvement.
    Only returns a new index when delta >= _TRIM_DELTA_THRESHOLD (+10).
    Returns (current_idx, 0.0) if no meaningful improvement is found.

    Required change 4 is enforced here: trim only when improvement is meaningful.
    """
    if not STRUCTURE_INTELLIGENCE_ENABLED or current_idx <= 0 or not all_chunks:
        return current_idx, 0.0

    try:
        from app.ai.analyzers.hook_analyzer import score_hook_text, score_hook_intelligence
    except ImportError:
        return current_idx, 0.0

    goal_key = str(goal or "").lower().strip()
    max_trim = _GOAL_MAX_TRIM.get(goal_key, _DEFAULT_MAX_TRIM)

    current_start = float(all_chunks[current_idx].get("start") or 0.0)
    lookback_cutoff = current_start - max_trim

    # Score the current entry for comparison baseline.
    current_text = all_chunks[current_idx].get("text") or ""
    current_score = (
        score_hook_text(current_text)
        + score_hook_intelligence(current_text, goal_key)
    )
    # Natural-start bonus for current entry.
    if current_idx > 0 and _ends_sentence(all_chunks[current_idx - 1]):
        current_score += _NATURAL_START_BONUS

    best_idx   = current_idx
    best_delta = 0.0

    # Scan backward within the lookback window.
    for j in range(current_idx - 1, -1, -1):
        chunk_start = float(all_chunks[j].get("start") or 0.0)
        if chunk_start < lookback_cutoff:
            break

        # Duration guard: resulting clip must meet minimum length.
        if candidate_end is not None:
            new_dur = candidate_end - chunk_start
            if new_dur < min_duration:
                continue

        # Entry quality: hook score + natural-start context.
        text = all_chunks[j].get("text") or ""
        entry_score = (
            score_hook_text(text)
            + score_hook_intelligence(text, goal_key)
        )
        # Natural-start: does the preceding chunk end a sentence?
        if j > 0 and _ends_sentence(all_chunks[j - 1]):
            entry_score += _NATURAL_START_BONUS

        delta = entry_score - current_score
        if delta > best_delta:
            best_delta = delta
            best_idx = j

    # Required change 4: only accept when improvement is meaningful.
    if best_delta >= _TRIM_DELTA_THRESHOLD:
        return best_idx, best_delta
    return current_idx, 0.0
