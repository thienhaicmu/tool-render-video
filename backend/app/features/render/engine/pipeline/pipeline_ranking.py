"""pipeline_ranking.py — Output ranking and score computation helpers.

Extracted from render_pipeline.py (lines 630–876) as part of C-1 decomposition.
All logic is identical — this is a mechanical lift, not a rewrite.

Sacred Contract: output_rank_score, is_best_output, is_best_clip must always
be present in every dict returned by _compute_output_ranking_entry.

Strategic-1c — Audit 2026-06-08 closure (UP26 structure_bias). Provides
``structure_bias`` re-weighted formulas for the output_score
computation. The operator picks one of "hook" | "balanced" | "story"
to tilt the ranking toward hook strength, retention, or a balanced
blend. The default (None / "balanced") preserves the pre-Strategic-1c
weights byte-for-byte.

All three weight sets sum to 1.0 so output_score remains a value
clamped to [0, 100]. The selected weight set is persisted into
result_json.ranking_metadata.formula by pipeline_finalize.py and
``applied_structure_bias`` records which set was used.
"""


# Strategic-1c — UP26 structure_bias weight tables. Each row sums to
# 1.0. Verified by test_strategic_1c_structure_bias_weights_sum_to_one.
STRUCTURE_BIAS_WEIGHTS: dict[str, dict[str, float]] = {
    # "hook" — bias toward strong hooks; sacrifice retention slightly.
    "hook": {
        "viral":          0.30,
        "hook":           0.30,
        "retention":      0.10,
        "speech_density": 0.10,
        "market":         0.15,
        "duration_fit":   0.05,
    },
    # "balanced" — pre-Strategic-1c default formula.
    "balanced": {
        "viral":          0.35,
        "hook":           0.20,
        "retention":      0.20,
        "speech_density": 0.10,
        "market":         0.10,
        "duration_fit":   0.05,
    },
    # "story" — bias toward retention/density (long-form storytelling).
    "story": {
        "viral":          0.30,
        "hook":           0.10,
        "retention":      0.30,
        "speech_density": 0.15,
        "market":         0.10,
        "duration_fit":   0.05,
    },
}


def resolve_structure_bias_weights(structure_bias: "str | None") -> dict[str, float]:
    """Strategic-1c — return the weight set for the given bias.

    Unknown / None / case-mismatched values default to ``balanced``
    (the pre-Strategic-1c formula). The default ensures legacy
    callers + stored payloads behave identically to pre-Strategic-1c.
    """
    if not structure_bias:
        return STRUCTURE_BIAS_WEIGHTS["balanced"]
    key = str(structure_bias).strip().lower()
    return STRUCTURE_BIAS_WEIGHTS.get(key, STRUCTURE_BIAS_WEIGHTS["balanced"])


def resolve_structure_bias_label(structure_bias: "str | None") -> str:
    """Return the canonical label used to look up the weights — useful
    for persisting the actual choice into ranking_metadata."""
    if not structure_bias:
        return "balanced"
    key = str(structure_bias).strip().lower()
    return key if key in STRUCTURE_BIAS_WEIGHTS else "balanced"


def resolve_combined_score_weights(
    target_market: "str | None",
    has_market_score: bool,
    has_hook_score: bool,
    duration: "float | None",
    adaptive_enabled: bool,
) -> dict:
    """Return combined-score weights that always sum to 1.0.

    When adaptive_enabled=False returns fixed P3-2 defaults.
    When True applies market/availability/duration adjustments then normalizes.
    """
    BASE_VIRAL  = 0.50
    BASE_MARKET = 0.30
    BASE_HOOK   = 0.20

    if not adaptive_enabled:
        return {
            "viral_weight":  BASE_VIRAL,
            "market_weight": BASE_MARKET,
            "hook_weight":   BASE_HOOK,
            "reason":        "fixed",
        }

    w_v = BASE_VIRAL
    w_m = BASE_MARKET
    w_h = BASE_HOOK
    reasons: list[str] = []

    # ── Market adjustment ──────────────────────────────────────────────────
    market = (target_market or "US").upper()
    if market == "US":
        w_h += 0.05; w_v += 0.05; w_m -= 0.10
        reasons.append("US:hook+viral")
    elif market == "EU":
        w_m += 0.10; w_h -= 0.05; w_v -= 0.05
        reasons.append("EU:market+")
    elif market == "JP":
        w_m += 0.05; w_h += 0.05; w_v -= 0.10
        reasons.append("JP:market+hook")

    # ── Missing score redistribution ───────────────────────────────────────
    if not has_market_score:
        half = w_m / 2.0
        w_v += half; w_h += half; w_m = 0.0
        reasons.append("no_mv:redistribute")

    if not has_hook_score:
        half = w_h / 2.0
        w_v += half; w_m += half; w_h = 0.0
        reasons.append("no_hook:redistribute")

    # ── Duration adjustment ────────────────────────────────────────────────
    dur = float(duration or 0)
    if dur > 90:
        w_v += 0.05; w_h -= 0.05
        reasons.append("long:viral+")
    elif 0 < dur < 10:
        w_h += 0.05; w_m -= 0.05
        reasons.append("short:hook+")
    # 10–90 s: no change

    # ── Clamp each active weight to [0.10, 0.70] ──────────────────────────
    W_MIN, W_MAX = 0.10, 0.70
    w_v = max(W_MIN, min(W_MAX, w_v))
    if has_market_score and w_m > 0:
        w_m = max(W_MIN, min(W_MAX, w_m))
    if has_hook_score and w_h > 0:
        w_h = max(W_MIN, min(W_MAX, w_h))

    # ── Normalize → sum = 1.0 ─────────────────────────────────────────────
    total = w_v + w_m + w_h
    if total > 0:
        w_v /= total; w_m /= total; w_h /= total
    else:
        w_v, w_m, w_h = 1.0, 0.0, 0.0

    return {
        "viral_weight":  round(w_v, 4),
        "market_weight": round(w_m, 4),
        "hook_weight":   round(w_h, 4),
        "reason":        ";".join(reasons) or "adaptive_default",
    }


def _score_component(value, default: float = 50.0) -> float:
    """Return a clamped 0-100 score, using neutral default only when missing."""
    if value is None or value == "":
        return default
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return default


def _first_score(seg: dict, names: list[str], default: float = 50.0) -> float:
    for name in names:
        if name in seg and seg.get(name) not in (None, ""):
            return _score_component(seg.get(name), default=default)
    return default


_RANKING_WEIGHTS: dict[str, float] = {
    "segment_viral_score":  0.35,
    "hook_score":           0.20,
    "retention_score":      0.20,
    "speech_density_score": 0.10,
    "market_score":         0.10,
    "duration_fit_score":   0.05,
}


def _output_ranking_detail(components: dict) -> dict:
    contribs = {k: components.get(k, 50.0) * w for k, w in _RANKING_WEIGHTS.items()}
    total = sum(contribs.values()) or 1.0
    ranked = sorted(contribs.items(), key=lambda x: x[1], reverse=True)
    top_signal, top_contrib = ranked[0]
    material = [s for s, c in ranked if c >= top_contrib * 0.60]
    suppressed = [s for s, c in ranked[1:] if c < top_contrib * 0.60 and components.get(s, 50.0) >= 65]
    return {
        "dominant_signal": top_signal,
        "dominant_pct": round(top_contrib / total * 100, 1),
        "material_signals": material,
        "suppressed_signals": suppressed,
    }


def _output_ranking_reason(components: dict) -> str:
    content_type = str(components.get("content_type_hint") or "")
    detail = _output_ranking_detail(components)

    def _label(signal: str, raw: float) -> "str | None":
        if signal == "segment_viral_score":
            if raw >= 65:
                if content_type == "montage":
                    return "High visual energy"
                if content_type in ("interview", "tutorial"):
                    return "Strong spoken segment"
                return "Strong segment"
        elif signal == "hook_score":
            if raw >= 60:
                return ("Strong spoken hook" if content_type in ("interview", "commentary", "tutorial", "podcast")
                        else "Strong opening hook")
            if raw < 40:
                return "Weak opening"
        elif signal == "retention_score":
            if raw >= 65:
                return ("High engagement energy" if content_type in ("interview", "tutorial") else "Good retention")
        elif signal == "speech_density_score":
            if raw >= 60 and content_type in ("interview", "commentary", "tutorial", "podcast"):
                return "Dense spoken content"
            if raw < 20 and content_type == "montage":
                return "Pure visual"
        elif signal == "market_score":
            if raw >= 65:
                return "Good market match"
        elif signal == "duration_fit_score":
            if raw >= 75:
                return "Ideal duration"
        return None

    reasons: list[str] = []
    for sig in detail["material_signals"]:
        if len(reasons) >= 2:
            break
        label = _label(sig, components.get(sig, 50.0))
        if label and label not in reasons:
            reasons.append(label)

    if not reasons:
        if content_type == "montage":
            reasons.append("High-energy montage")
        elif content_type in ("interview", "commentary", "tutorial"):
            reasons.append("Quality spoken content")
        else:
            reasons.append("Balanced clip signals")

    return ", ".join(reasons[:2])


def _compute_output_ranking_entry(
    part_no: int,
    seg: dict,
    output_file: str,
    payload_hook_score=None,
    structure_bias: "str | None" = None,
) -> dict:
    """Compute one ranking entry.

    Strategic-1c — Audit 2026-06-08 closure (UP26 structure_bias). The
    optional ``structure_bias`` kwarg ('hook' | 'balanced' | 'story')
    selects one of the canonical weight sets in
    ``STRUCTURE_BIAS_WEIGHTS``. None / unknown values default to the
    'balanced' set (pre-Strategic-1c formula — byte-for-byte
    backward compat).
    """
    segment_viral_score = _first_score(seg, ["viral_score"], default=50.0)
    hook_score = _first_score(
        seg,
        ["hook_text_score", "hook_timing_score", "hook_score", "hook_opening_score"],
        default=_score_component(payload_hook_score, default=50.0),
    )
    retention_score = _first_score(seg, ["retention_score"], default=50.0)
    speech_density_score = _first_score(seg, ["speech_density_score"], default=50.0)
    market_score = _first_score(seg, ["mv_viral_score", "market_viral_score"], default=50.0)
    duration_fit_score = _first_score(seg, ["duration_fit_score"], default=50.0)
    continuity_score = _first_score(seg, ["continuity_score"], default=50.0)

    # Strategic-1c — pick the formula weights based on structure_bias.
    weights = resolve_structure_bias_weights(structure_bias)
    raw_score = (
        segment_viral_score * weights["viral"]
        + hook_score * weights["hook"]
        + retention_score * weights["retention"]
        + speech_density_score * weights["speech_density"]
        + market_score * weights["market"]
        + duration_fit_score * weights["duration_fit"]
    )
    output_score = round(max(0.0, min(100.0, raw_score)), 1)
    components = {
        "segment_viral_score": round(segment_viral_score, 1),
        "hook_score": round(hook_score, 1),
        "retention_score": round(retention_score, 1),
        "speech_density_score": round(speech_density_score, 1),
        "market_score": round(market_score, 1),
        "duration_fit_score": round(duration_fit_score, 1),
        "continuity_score": round(continuity_score, 1),
        "content_type_hint": str(seg.get("content_type_hint") or ""),
    }

    _detail = _output_ranking_detail(components)
    return {
        "part_no": part_no,
        "output_file": output_file,
        "output_rank": 0,
        "output_score": output_score,
        "is_best_clip": False,
        "ranking_reason": _output_ranking_reason(components),
        "ranking_components": components,
        "dominant_signal": _detail["dominant_signal"],
        "suppressed_signals": _detail["suppressed_signals"],
        "selection_reason": seg.get("selection_reason", ""),
        # Backward-compatible aliases consumed by existing render UI.
        "output_rank_score": output_score,
        "is_best_output": False,
        "reasons": [
            f"segment_viral={components['segment_viral_score']}",
            f"hook={components['hook_score']}",
            f"retention={components['retention_score']}",
            f"speech_density={components['speech_density_score']}",
            f"market={components['market_score']}",
            f"duration_fit={components['duration_fit_score']}",
        ],
    }


# ────────────────────────────────────────────────────────────────────
# Sprint 4.G — RenderPlan rank consume helper.
#
# When the orchestrator is permitted to consume AI-emitted ranks
# (LLM_EMIT_RENDER_PLAN env flag == "1") AND the plan carries a valid
# permutation of ranks 1..N across the successful parts, the per-part
# `output_rank` / `is_best_clip` / `is_best_output` flags are derived
# from the plan instead of the legacy score-descending sort.
#
# When the env flag is OFF (the Sprint 4.D default), this helper
# ALWAYS returns (None, "fallback") so the Sprint 2.2 builder shim's
# rank values cannot leak into the live render path — Sacred Contract
# #2 baseline behaviour preservation. The legacy score-descending sort
# (render_pipeline.py L1037) stays the sole authority in that case.
#
# Mapping strategy: BY POSITION. render_plan.clips[i] is taken to
# correspond to scored[i] — the Sprint 4.D shim guarantees this
# alignment; AI providers wire their emission to the same ordering.
# clip_name is NOT used as the join key (it may be empty, duplicated,
# or sanitised).
#
# Invalid-plan branches return (None, "fallback_*") with a tag so the
# orchestrator can surface the reason in the existing
# `output_rank_computed` / `output_ranking_completed` events. The
# Sacred Contract #1 keys (`output_rank_score`, `is_best_output`,
# `is_best_clip`) are NEVER dropped by either path — only their
# VALUES differ.
# ────────────────────────────────────────────────────────────────────

import os as _os  # noqa: E402 (kept local to helper section)
from typing import Optional as _Optional  # noqa: E402


_RENDER_PLAN_RANK_SOURCES: frozenset[str] = frozenset({
    "render_plan",
    "fallback",
    "fallback_no_plan_rank",
    "fallback_rank_collision",
    "fallback_rank_invalid",
})


def _resolve_rank_from_plan(
    render_plan,
    scored: list,
    failed_idx_set: set,
) -> tuple[_Optional[dict], str]:
    """Return ``(mapping_part_no_to_rank, source_tag)`` or ``(None, tag)``.

    The mapping covers exactly the successful parts (the same set the
    orchestrator builds `_rank_entries` for). When the helper returns
    None the orchestrator falls back to the legacy score-descending
    sort. See module-level comment block for the consume gate rules.

    Never raises — any attribute lookup or comparison failure surfaces
    as a fallback tag.
    """
    # F.5 Option C — consume only when the feature flag is "1".
    # Reading the env var per call (rather than once at module load)
    # lets tests monkeypatch the flag without reload gymnastics.
    # Sprint 7.6a (2026-06-05): default flipped "0" → "1" to match
    # render_pipeline.py:134. Operators set LLM_EMIT_RENDER_PLAN=0 to revert.
    # See docs/review/SPRINT_7_6a_LLM_FLAG_FLIP_2026-06-05.md.
    if _os.getenv("LLM_EMIT_RENDER_PLAN", "1") != "1":
        return None, "fallback"
    if render_plan is None:
        return None, "fallback"
    try:
        clips = list(getattr(render_plan, "clips", None) or [])
    except Exception:
        return None, "fallback"
    if not clips:
        return None, "fallback_no_plan_rank"

    # part_no values for the successful entries in the same order the
    # orchestrator iterates `scored` (1-based, failed parts excluded).
    success_part_nos: list[int] = []
    for _idx in range(len(scored)):
        _pn = _idx + 1
        if _pn in failed_idx_set:
            continue
        success_part_nos.append(_pn)

    if len(clips) < len(success_part_nos):
        return None, "fallback_no_plan_rank"

    mapping: dict[int, int] = {}
    seen_ranks: set[int] = set()
    for _pn, _clip in zip(success_part_nos, clips):
        try:
            _r = int(getattr(_clip, "rank", 0) or 0)
        except (TypeError, ValueError):
            return None, "fallback_rank_invalid"
        if _r <= 0:
            return None, "fallback_no_plan_rank"
        if _r in seen_ranks:
            return None, "fallback_rank_collision"
        seen_ranks.add(_r)
        mapping[_pn] = _r

    # Validate the rank set is exactly {1, 2, ..., N}. Reject
    # non-sequential AI emissions (e.g. [1, 3, 5]) rather than
    # silently re-numbering them.
    expected_set = set(range(1, len(mapping) + 1))
    if seen_ranks != expected_set:
        return None, "fallback_rank_invalid"

    return mapping, "render_plan"
