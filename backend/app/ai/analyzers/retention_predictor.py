"""
retention_predictor.py — S3.2 Retention Prediction.

Per-clip retention likelihood estimation before export.
Advisory metadata only — NEVER affects selection, retry, ranking,
diversity, or creator DNA. No feedback loops (required change 1).

Distinct from Phase 16 retention_analyzer (whole-video analysis):
  - Phase 16: operates on full video transcript + story + pacing context
  - S3.2: operates on per-clip window using S2 signals from S3.1 carry-through

Signal sources:
    hook_intelligence_type — S2.1 (carried through via S3.1)
    moment_type            — S2.4 context (carried through via S3.1)
    structure_phases       — S2.3 (carried through via S3.1)
    clip window chunks     — re-sliced from full transcript by start/end

Retention factors:
    hook_weakness          — hook absent or too weak to engage
    payoff_absence         — opening present, payoff absent (broken promise)
    unfulfilled_hook_promise — promise-type hook (result_first/challenge/…) with no payoff
    flat_emotion           — emotion variance below threshold (monotone content)
    dead_zone_risk         — RC4: ≥22% of clip duration is flat (conservative)
    structural_gap         — opening-only structure mismatched to goal
    density_falloff        — speech density declining in second half

Required changes applied:
    RC1: hard advisory-only — score NEVER feeds back into selection, retry,
         ranking, diversity, or creator DNA (architectural constraint)
    RC2: prediction_confidence field per clip [0, 1] — heuristic ≠ truth
    RC3: hook→payoff coherence penalty −12 (generic) to −18 (promise hooks)
    RC4: dead-zone only fires when ≥22% of clip duration is flat (conservative)
    RC5: retention_explanation with strengths + risks lists (explainability)
    RC6: S3_RETENTION_ENABLED=0 produces bit-identical behavior

Stabilization changes (S3 Sprint):
    - All threshold/penalty constants externalized to env vars
    - RC2 goal-aware emotion stacking cap: flat_emotion + dead_zone + density_falloff
      capped at viral=30, storytelling=26, education=22, podcast=20, fallback=25
    - Override all caps via S3_RETENTION_MAX_EMOTION_PENALTY

Set S3_RETENTION_ENABLED=0 for full rollback.

Public API:
    predict_clip_retention(selected_raw, chunks, goal) -> dict
    S3_RETENTION_ENABLED: bool
    S3_RETENTION_MIN_SCORE: float
    S3_RETENTION_MAX_EMOTION_PENALTY: float | None
"""
from __future__ import annotations

import os

S3_RETENTION_ENABLED: bool = os.environ.get("S3_RETENTION_ENABLED", "1") == "1"
S3_RETENTION_MIN_SCORE: float = float(os.environ.get("S3_RETENTION_MIN_SCORE", "50"))

# Base retention score before adjustments.
_BASE_SCORE: float = float(os.environ.get("S3_RETENTION_BASE_SCORE", "65.0"))

# RC4: Dead-zone only fires when flat fraction >= this threshold.
# Used as the fallback for unknown goals in _get_dead_zone_threshold().
_DEAD_ZONE_FLAT_THRESHOLD: float = float(os.environ.get("S3_RETENTION_DEAD_ZONE_THRESHOLD", "0.22"))

# Dead-zone penalty multiplier: penalty = min(max_penalty, dead_ratio * multiplier).
_DEAD_ZONE_PENALTY_MULTIPLIER: float = float(os.environ.get("S3_RETENTION_DEAD_ZONE_MULTIPLIER", "45.0"))

# B3 (Calibration Sprint): goal-aware dead zone threshold.
# "calm ≠ boring" — podcast/education allow more natural flat spans before flagging.
# Hard cap ≤ 0.30 per spec (boring podcast still exists).
# Unknown goals fall back to _DEAD_ZONE_FLAT_THRESHOLD (env-var controlled).
_GOAL_DEAD_ZONE_THRESHOLDS: dict[str, float] = {
    "viral":        0.18,
    "storytelling": 0.22,
    "education":    0.24,
    "podcast":      0.28,
}


def _get_dead_zone_threshold(goal: str) -> float:
    """B3: Goal-aware dead zone threshold. Hard cap ≤ 0.30 per spec."""
    raw = _GOAL_DEAD_ZONE_THRESHOLDS.get(goal, _DEAD_ZONE_FLAT_THRESHOLD)
    return min(0.30, raw)

# Emotion score (0-100) below this = "flat chunk" for dead-zone purposes.
_FLAT_CHUNK_SCORE: float = 8.0

# Minimum consecutive flat chunks required to start counting a dead zone.
_MIN_CONSECUTIVE_FLAT: int = 3

# Emotion variance minimum to qualify as an engaging arc.
_ARC_VARIANCE_MIN: float = float(os.environ.get("S3_RETENTION_ARC_VARIANCE_MIN", "15.0"))

# Density falloff — second half avg / first half avg below this = declining.
_DENSITY_FALLOFF_RATIO: float = float(os.environ.get("S3_RETENTION_DENSITY_FALLOFF_RATIO", "0.60"))

# Minimum clip duration (seconds) to run payoff-absence checks.
_MIN_PAYOFF_DURATION: float = 20.0

# Minimum emotion chunks needed to compute variance / dead zones reliably.
_MIN_EMOTION_CHUNKS: int = 4

# Penalty constants — externalized for calibration without code changes.
# _HOOK_ABSENCE_PENALTY remains for backward-compat / env-var docs; _predict_one
# now calls _get_hook_absence_penalty(goal) which uses the goal-aware table (B1).
_HOOK_ABSENCE_PENALTY: float = float(os.environ.get("S3_RETENTION_HOOK_PENALTY", "20.0"))
_PROMISE_HOOK_PENALTY: float = float(os.environ.get("S3_RETENTION_PROMISE_PENALTY", "18.0"))
_GENERIC_PAYOFF_PENALTY: float = float(os.environ.get("S3_RETENTION_GENERIC_PENALTY", "12.0"))

# B1 (Calibration Sprint): goal-aware hook absence penalty.
# "calm ≠ bad content" — podcast/education creators penalized less for indirect openings.
# Conservative spread per spec: viral=20, storytelling=16, education=14, podcast=12.
# Unknown goals fall back to _DEFAULT_HOOK_ABSENCE_PENALTY.
_GOAL_HOOK_ABSENCE_PENALTIES: dict[str, float] = {
    "viral":        20.0,
    "storytelling": 16.0,
    "education":    14.0,
    "podcast":      12.0,
}
_DEFAULT_HOOK_ABSENCE_PENALTY: float = 16.0


def _get_hook_absence_penalty(goal: str) -> float:
    """B1: Goal-aware hook absence penalty. calm≠bad — podcast/edu penalized less."""
    return _GOAL_HOOK_ABSENCE_PENALTIES.get(goal, _DEFAULT_HOOK_ABSENCE_PENALTY)

# RC2: Goal-aware emotion stacking cap — "calm ≠ boring" for podcast/education.
# Prevents flat_emotion + dead_zone + density_falloff from over-penalising
# naturally low-intensity content where calm pacing is expected.
# Override all caps via S3_RETENTION_MAX_EMOTION_PENALTY (int, ≥0).
_GOAL_EMOTION_CAPS: dict[str, float] = {
    "viral":        30.0,
    "storytelling": 26.0,
    "education":    22.0,
    "podcast":      20.0,
}
_DEFAULT_EMOTION_CAP: float = 25.0

# Env override — applies to ALL goals when set (must be ≥ 0).
_S3_RETENTION_MAX_EMOTION_PENALTY_ENV: str = os.environ.get("S3_RETENTION_MAX_EMOTION_PENALTY", "")
S3_RETENTION_MAX_EMOTION_PENALTY: float | None = (
    float(_S3_RETENTION_MAX_EMOTION_PENALTY_ENV)
    if _S3_RETENTION_MAX_EMOTION_PENALTY_ENV.strip().lstrip("-").replace(".", "", 1).isdigit()
    else None
)


def _get_emotion_cap(goal: str) -> float:
    """Return goal-aware emotion stacking cap. Env override takes precedence."""
    if S3_RETENTION_MAX_EMOTION_PENALTY is not None:
        return max(0.0, S3_RETENTION_MAX_EMOTION_PENALTY)
    return _GOAL_EMOTION_CAPS.get(goal, _DEFAULT_EMOTION_CAP)


# RC3: "Promise" hooks make an explicit content promise to the viewer.
# Unfulfilled promise → strong retention killer (penalty −18).
_PROMISE_HOOK_TYPES: frozenset[str] = frozenset({
    "result_first", "challenge", "surprise", "warning", "authority",
})

# High-retention hook types — strongly engaging opening styles.
_HIGH_RETENTION_HOOKS: frozenset[str] = frozenset({
    "surprise", "result_first", "warning", "curiosity", "problem",
})

# Goals where opening-only structure (no development/payoff) is a risk.
_STRUCTURAL_GAP_GOALS: frozenset[str] = frozenset({
    "education", "podcast", "storytelling",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict_clip_retention(
    selected_raw: list[dict],
    chunks: list[dict],
    goal: str = "",
) -> dict:
    """Predict per-clip retention likelihood before export.

    Returns {clip_index (int): retention_dict}.
    Clips scoring below S3_RETENTION_MIN_SCORE or using scene fallback still
    receive a prediction entry with retention_available=False.

    IMPORTANT — RC1 (hard advisory-only):
    This function is READ-ONLY with respect to the selection pipeline.
    The returned retention_score and risk factors MUST NEVER influence:
      - clip selection (clip_selector.py, segment_builder.py)
      - selection ordering or reranking
      - retry logic (retry_analyzer.py)
      - diversity penalty (diversity_analyzer.py)
      - creator DNA adjustments (dna_engine.py)
    This constraint must be preserved across all future changes.

    Graceful degradation:
      S3_RETENTION_ENABLED=0 → returns {} (bit-identical to pre-S3.2)
      No transcript for clip window → retention_available=False, low confidence
      emotion_analyzer import fails → returns {} (warning in caller)
    """
    if not S3_RETENTION_ENABLED:
        return {}

    result: dict = {}
    goal_key = str(goal or "").lower().strip()

    for idx, seg in enumerate(selected_raw):
        score = float(seg.get("score", 0.0) or 0.0)
        if score < S3_RETENTION_MIN_SCORE:
            continue
        try:
            retention = _predict_one(seg, chunks, goal_key)
            result[idx] = retention
        except Exception:
            # Per-clip failure is silently swallowed — never propagates.
            pass

    return result


# ---------------------------------------------------------------------------
# Internal — per-clip prediction
# ---------------------------------------------------------------------------

def _predict_one(seg: dict, all_chunks: list[dict], goal: str) -> dict:
    """Predict retention for a single clip segment.

    Returns a complete retention_dict regardless of signal availability.
    retention_available=False signals to consumers that the prediction
    is unreliable (no transcript for this window).
    """
    start = float(seg.get("start", 0.0) or 0.0)
    end   = float(seg.get("end", 0.0) or 0.0)
    hook_type        = str(seg.get("hook_intelligence_type", "none") or "none").lower()
    moment_type      = str(seg.get("moment_type", "unknown") or "unknown").lower()
    structure_phases = list(seg.get("structure_phases", []) or [])

    win_chunks    = _get_window_chunks(all_chunks, start, end)
    clip_duration = max(0.1, end - start)

    # No transcript for this window — return minimal advisory prediction.
    if not win_chunks:
        return {
            "retention_score":       round(_BASE_SCORE, 1),
            "prediction_confidence": 0.15,
            "risk_level":            "medium",
            "retention_explanation": {"strengths": [], "risks": []},
            "retention_available":   False,
        }

    strengths: list[str] = []
    risks: list[str]     = []
    score: float         = _BASE_SCORE
    conf_parts: list[float] = [0.25]  # base from transcript presence

    # ── Hook strength ──────────────────────────────────────────────────────
    if hook_type != "none":
        conf_parts.append(0.20)
        if hook_type in _HIGH_RETENTION_HOOKS:
            score += 15.0
            strengths.append("strong_hook")
        else:
            score += 8.0
            strengths.append("hook_present")
    else:
        score -= _get_hook_absence_penalty(goal)   # B1: goal-aware
        risks.append("hook_weakness")

    # ── RC3: Hook → payoff coherence ───────────────────────────────────────
    # Checks whether the clip delivers on its opening promise.
    # Promise hooks (result_first / challenge / surprise / warning / authority)
    # get the strong −18 penalty; generic opening-only clips get −12.
    has_payoff  = "payoff" in structure_phases
    has_opening = "opening" in structure_phases

    if has_payoff:
        conf_parts.append(0.10)
        if "development" in structure_phases:
            score += 12.0
            strengths.append("strong_payoff")
        else:
            score += 7.0
            strengths.append("payoff_present")
    elif has_opening and clip_duration >= _MIN_PAYOFF_DURATION:
        if hook_type in _PROMISE_HOOK_TYPES:
            score -= _PROMISE_HOOK_PENALTY    # RC3: strong penalty for broken promise
            risks.append("unfulfilled_hook_promise")
        else:
            score -= _GENERIC_PAYOFF_PENALTY  # RC3: moderate penalty for unresolved open
            risks.append("payoff_absence")

    # ── Full structure bonus ───────────────────────────────────────────────
    if structure_phases:
        conf_parts.append(0.12)
        if set(structure_phases) >= {"opening", "development", "payoff"}:
            score += 5.0
            strengths.append("full_structure")

    # ── Structural gap — goal-aware ────────────────────────────────────────
    if moment_type == "hook_opener" and goal in _STRUCTURAL_GAP_GOALS:
        score -= 8.0
        risks.append("structural_gap")

    # ── Emotion signals ────────────────────────────────────────────────────
    emotion_scores = _compute_emotion_scores(win_chunks)

    # RC2: accumulate emotion-family penalties, then apply goal-aware cap.
    # This prevents flat_emotion + dead_zone + density_falloff from stacking
    # to −33 and over-penalising naturally calm content (podcast/education).
    _emotion_penalty_raw: float = 0.0

    if len(emotion_scores) >= _MIN_EMOTION_CHUNKS:
        conf_parts.append(0.15)
        variance  = max(emotion_scores) - min(emotion_scores)
        avg_score = sum(emotion_scores) / len(emotion_scores)

        # Rising emotional arc
        if variance >= _ARC_VARIANCE_MIN:
            mid = len(emotion_scores) // 2
            first_avg  = sum(emotion_scores[:mid])  / max(1, mid)
            second_avg = sum(emotion_scores[mid:])  / max(1, len(emotion_scores) - mid)
            if second_avg > first_avg:
                score += 8.0
                strengths.append("emotion_arc")
            else:
                score += 3.0
                strengths.append("emotion_variance")

        # Flat emotion (monotone content throughout)
        if variance < 5.0 and avg_score < 10.0:
            _emotion_penalty_raw += 10.0
            risks.append("flat_emotion")

        # RC4: Dead-zone detection — goal-aware threshold (B3: calm≠boring).
        dead_ratio = _compute_dead_zone_ratio(win_chunks, emotion_scores, clip_duration)
        if dead_ratio >= _get_dead_zone_threshold(goal):
            # Scale penalty with dead ratio (max −15 at 100% flat).
            _emotion_penalty_raw += min(15.0, round(dead_ratio * _DEAD_ZONE_PENALTY_MULTIPLIER, 1))
            risks.append("dead_zone_risk")

    # ── Density falloff (part of emotion-family stacking pool) ────────────
    falloff = _compute_density_falloff(win_chunks)
    if falloff is not None:
        if falloff < _DENSITY_FALLOFF_RATIO:
            _emotion_penalty_raw += 8.0
            risks.append("density_falloff")
        elif falloff >= 1.0:
            score += 3.0
            strengths.append("density_maintained")

    # Apply emotion-family penalty with goal-aware cap (RC2).
    if _emotion_penalty_raw > 0.0:
        score -= min(_emotion_penalty_raw, _get_emotion_cap(goal))

    # ── Duration confidence factor ─────────────────────────────────────────
    if clip_duration >= 30.0:
        conf_parts.append(0.12)
    elif clip_duration >= 20.0:
        conf_parts.append(0.06)

    # ── Chunk depth confidence ─────────────────────────────────────────────
    if len(win_chunks) >= 8:
        conf_parts.append(0.10)
    elif len(win_chunks) >= 4:
        conf_parts.append(0.05)

    # ── Finalise ───────────────────────────────────────────────────────────
    retention_score       = max(0.0, min(100.0, round(score, 1)))
    prediction_confidence = round(max(0.10, min(1.0, sum(conf_parts))), 3)

    if retention_score >= 70:
        risk_level = "low"
    elif retention_score >= 50:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {
        "retention_score":       retention_score,
        "prediction_confidence": prediction_confidence,   # RC2
        "risk_level":            risk_level,
        "retention_explanation": {                        # RC5
            "strengths": strengths,
            "risks":     risks,
        },
        "retention_available":   True,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_window_chunks(
    chunks: list[dict],
    start: float,
    end: float,
) -> list[dict]:
    """Filter transcript chunks that fall within [start, end]."""
    return [
        c for c in (chunks or [])
        if float(c.get("end") or 0.0) > start
        and float(c.get("start") or 0.0) < end
    ]


def _compute_emotion_scores(chunks: list[dict]) -> list[float]:
    """Score per-chunk emotional intensity. Returns [] on import failure."""
    try:
        from app.ai.analyzers.emotion_analyzer import analyze_text_emotion
        scores: list[float] = []
        for c in chunks:
            text = str(c.get("text") or "").strip()
            if not text:
                scores.append(0.0)
                continue
            result = analyze_text_emotion(text)
            scores.append(float(result.get("score") or 0.0))
        return scores
    except Exception:
        return []


def _compute_dead_zone_ratio(
    chunks: list[dict],
    emotion_scores: list[float],
    clip_duration: float,
) -> float:
    """Compute fraction of clip duration occupied by contiguous flat zones.

    RC4 guard: only counts spans of >= _MIN_CONSECUTIVE_FLAT flat chunks.
    Returns [0.0, 1.0].
    """
    if not chunks or not emotion_scores or clip_duration <= 0.0:
        return 0.0
    if len(chunks) != len(emotion_scores):
        return 0.0

    total_flat = 0.0
    run_start: float | None = None
    run_count: int = 0

    for i, (chunk, escore) in enumerate(zip(chunks, emotion_scores)):
        c_start = float(chunk.get("start") or 0.0)
        c_end   = float(chunk.get("end") or c_start)

        if escore < _FLAT_CHUNK_SCORE:
            if run_start is None:
                run_start = c_start
            run_count += 1
        else:
            if run_count >= _MIN_CONSECUTIVE_FLAT and run_start is not None:
                prev = chunks[i - 1]
                run_end = float(prev.get("end") or prev.get("start") or run_start)
                total_flat += max(0.0, run_end - run_start)
            run_start = None
            run_count = 0

    # Flush trailing flat run.
    if run_count >= _MIN_CONSECUTIVE_FLAT and run_start is not None:
        last = chunks[-1]
        run_end = float(last.get("end") or last.get("start") or run_start)
        total_flat += max(0.0, run_end - run_start)

    return min(1.0, total_flat / clip_duration)


def _compute_density_falloff(chunks: list[dict]) -> float | None:
    """Compute speech density ratio: second_half_avg / first_half_avg.

    Returns None when insufficient chunks.
    < 1.0 = density declining (risk); >= 1.0 = maintained or rising (strength).
    """
    if len(chunks) < 4:
        return None
    try:
        from app.ai.analyzers.silence_analyzer import score_speech_density
        mid    = len(chunks) // 2
        first  = [score_speech_density(c) for c in chunks[:mid]]
        second = [score_speech_density(c) for c in chunks[mid:]]
        first_avg  = sum(first)  / max(1, len(first))
        second_avg = sum(second) / max(1, len(second))
        if first_avg <= 0.0:
            return None
        return round(second_avg / first_avg, 3)
    except Exception:
        return None
