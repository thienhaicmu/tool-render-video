"""
platform_adapter.py — S3.4 Platform Intelligence.

Per-clip platform-native micro-adaptation hints for TikTok / YouTube Shorts /
Instagram Reels / Podcast clips.

Advisory metadata only — NEVER affects clip selection, scoring, retry,
diversity, creator DNA, or render pipeline output.

Distinct from UP14 (_PLATFORM_PROFILES in render_pipeline.py):
  - UP14: per-job flat nudges (speed_delta, sub_bias) applied at render time
  - S3.4: per-CLIP signal-aware adaptation hints at plan assembly time,
          crossing platform context with S2 moment/hook/structure signals

Distinct from Phase 55A–57 (ai_director platform knowledge):
  - Phases 55A–57: job-level platform knowledge retrieval (advisory metadata)
  - S3.4: per-clip adaptation layer that reads plan.platform_render_strategy
          (Phase 55E output) and cross-references clip-level S2 signals

Required changes applied:
    RC1: confidence gate — segment_score < S3_PLATFORM_MIN_SCORE → null hints
    RC2: confidence bounded [0.10, 0.90] — heuristic only, never certainty=1.0
    RC3: platform conflict suppression — creator style always wins; conservative
         styles (clean/minimal/soft) cap hints at mid-scale; no hard conflict
    RC4: platform_reason list per clip (e.g. ["platform=tiktok", "moment=hook_opener"])
    RC5: S3_PLATFORM_INTELLIGENCE_ENABLED=0 → bit-identical to pre-S3.4
    RC6: advisory-only guard — return value MUST NEVER influence selection,
         retry, ranking, diversity, or creator DNA (architectural constraint)

Set S3_PLATFORM_INTELLIGENCE_ENABLED=0 for full rollback.

Public API:
    plan_platform_adaptation(selected_raw, platform_render_strategy,
                             goal, target_platform, subtitle_style) -> dict
    S3_PLATFORM_INTELLIGENCE_ENABLED: bool
    S3_PLATFORM_MIN_SCORE: float
"""
from __future__ import annotations

import os

S3_PLATFORM_INTELLIGENCE_ENABLED: bool = (
    os.environ.get("S3_PLATFORM_INTELLIGENCE_ENABLED", "1") == "1"
)
S3_PLATFORM_MIN_SCORE: float = float(os.environ.get("S3_PLATFORM_MIN_SCORE", "40"))

# Platforms with defined adaptation tables.
# Unknown platforms → {} returned immediately (no partial hints).
_KNOWN_PLATFORMS: frozenset[str] = frozenset({
    "tiktok", "youtube_shorts", "instagram_reels", "podcast",
})

# ---------------------------------------------------------------------------
# Intensity scales — used for adjacent-only shift logic (RC3 clamping).
# ---------------------------------------------------------------------------

_PACING_ORDER:  list[str] = ["calm", "standard", "punchy"]
_OPENER_ORDER:  list[str] = ["calm", "moderate", "strong"]
_DENSITY_ORDER: list[str] = ["readable", "normal", "compact"]
_POLISH_ORDER:  list[str] = ["standard", "smooth", "high"]

# ---------------------------------------------------------------------------
# Per-platform default targets.
# These are the STARTING points before per-clip signal modulation.
# ---------------------------------------------------------------------------

_PLATFORM_PACING_TARGET: dict[str, str] = {
    "tiktok":           "punchy",
    "youtube_shorts":   "standard",
    "instagram_reels":  "standard",
    "podcast":          "calm",
}

_PLATFORM_OPENER_EMPHASIS: dict[str, str] = {
    "tiktok":           "strong",
    "youtube_shorts":   "moderate",
    "instagram_reels":  "moderate",
    "podcast":          "calm",
}

_PLATFORM_SUBTITLE_DENSITY: dict[str, str] = {
    "tiktok":           "compact",
    "youtube_shorts":   "normal",
    "instagram_reels":  "compact",
    "podcast":          "readable",
}

_PLATFORM_VISUAL_POLISH: dict[str, str] = {
    "tiktok":           "standard",
    "youtube_shorts":   "standard",
    "instagram_reels":  "high",
    "podcast":          "standard",
}

# ---------------------------------------------------------------------------
# Hook type sets for per-clip modulation.
# ---------------------------------------------------------------------------

# Strong hooks amplify opener emphasis (+1 step toward aggressive).
_STRONG_HOOK_TYPES: frozenset[str] = frozenset({
    "surprise", "warning", "result_first",
})

# Soft hooks soften opener emphasis (−1 step toward calm).
_SOFT_HOOK_TYPES: frozenset[str] = frozenset({
    "story", "authority",
})

# ---------------------------------------------------------------------------
# RC3: Creator style → conflict suppression.
# Conservative styles cap hints at mid-scale.
# Aggressive styles allow full platform target.
# Neutral styles (default) allow platform target.
# ---------------------------------------------------------------------------

# Conservative styles: creator intentionally chose calm/clean — never push
# to aggressive end of any scale even on aggressive platforms (e.g. TikTok).
_CONSERVATIVE_STYLES: frozenset[str] = frozenset({
    "minimal", "clean", "soft",
})

# Aggressive styles: creator chose high-energy — full platform target allowed.
_AGGRESSIVE_STYLES: frozenset[str] = frozenset({
    "punch", "viral", "gaming", "pro_karaoke",
})

# Base confidence before per-signal contributions (RC2 bounded to 0.10–0.90).
# All externalized to env vars for calibration without code changes.
_BASE_CONFIDENCE:      float = float(os.environ.get("S3_PLATFORM_CONF_BASE",      "0.20"))
_CONF_PLATFORM_KNOWN:  float = float(os.environ.get("S3_PLATFORM_CONF_PLATFORM",  "0.20"))
_CONF_STRATEGY_AVAIL:  float = float(os.environ.get("S3_PLATFORM_CONF_STRATEGY",  "0.15"))
_CONF_MOMENT_KNOWN:    float = float(os.environ.get("S3_PLATFORM_CONF_MOMENT",    "0.20"))
_CONF_HOOK_KNOWN:      float = float(os.environ.get("S3_PLATFORM_CONF_HOOK",      "0.10"))
_CONF_RETENTION_AVAIL: float = float(os.environ.get("S3_PLATFORM_CONF_RETENTION", "0.10"))

# RC2 confidence floor — never below this even for weak clips.
S3_PLATFORM_CONFIDENCE_MIN: float = float(os.environ.get("S3_PLATFORM_CONFIDENCE_MIN", "0.10"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_platform_adaptation(
    selected_raw: list[dict],
    platform_render_strategy: dict,
    goal: str = "",
    target_platform: str = "",
    subtitle_style: str = "",
) -> dict:
    """Compute per-clip platform micro-adaptation hints at plan assembly time.

    Returns {clip_index (int): platform_adaptation_dict}.

    platform_adaptation_dict:
        platform              str        — normalised platform key
        pacing_hint           str | None — "calm" | "standard" | "punchy"
        opener_emphasis       str | None — "calm" | "moderate" | "strong"
        subtitle_density_hint str | None — "readable" | "normal" | "compact"
        visual_polish_hint    str | None — "standard" | "smooth" | "high"
        confidence            float      — [0.10, 0.90] heuristic (RC2)
        platform_reason       list[str]  — explainability (RC4)
        platform_risks        list[str]  — risk signals

    RC6 — FUTURE CONSUMER GUARD (architectural constraint):
    This function is READ-ONLY with respect to the selection pipeline.
    The returned hints MUST NEVER influence:
      - clip selection (clip_selector.py, segment_builder.py)
      - selection ordering or reranking
      - retry logic (retry_analyzer.py)
      - diversity penalty (diversity_analyzer.py)
      - creator DNA adjustments (dna_engine.py)
      - render pipeline parameters (render_pipeline.py, render_engine.py)
    This constraint must be preserved across all future changes.

    RC5 (exact no-op): S3_PLATFORM_INTELLIGENCE_ENABLED=0 → {} → bit-identical.
    RC1 (confidence gate): segment_score < S3_PLATFORM_MIN_SCORE → null hints.
    RC2 (confidence bound): confidence clamped to [0.10, 0.90], never 1.0.
    RC3 (conflict suppression): conservative creator styles cap mid-scale.
    RC4 (platform_reason): ["platform=tiktok", "moment=hook_opener", ...].
    """
    if not S3_PLATFORM_INTELLIGENCE_ENABLED:
        return {}  # RC5: exact no-op

    platform = str(target_platform or "").lower().strip()
    if platform not in _KNOWN_PLATFORMS:
        return {}  # No partial hints on unrecognised platforms.

    style        = str(subtitle_style or "").lower().strip()
    strategy_ctx = dict(platform_render_strategy or {})
    result: dict = {}

    for idx, seg in enumerate(selected_raw):
        try:
            adaptation = _adapt_one(seg, platform, style, strategy_ctx)
            result[idx] = adaptation
        except Exception:
            # Per-clip failure swallowed — never propagates.
            pass

    return result


# ---------------------------------------------------------------------------
# Internal — per-clip adaptation
# ---------------------------------------------------------------------------

def _adapt_one(
    seg: dict,
    platform: str,
    subtitle_style: str,
    strategy_ctx: dict,
) -> dict:
    """Compute platform adaptation dict for one clip segment."""
    score = float(seg.get("score", 0.0) or 0.0)

    # RC1: confidence gate — weak clips get null hints.
    if score < S3_PLATFORM_MIN_SCORE:
        return {
            "platform":              platform,
            "pacing_hint":           None,
            "opener_emphasis":       None,
            "subtitle_density_hint": None,
            "visual_polish_hint":    None,
            "confidence":            S3_PLATFORM_CONFIDENCE_MIN,
            "platform_reason":       ["weak_clip_score"],
            "platform_risks":        ["low_signal"],
        }

    hook_type     = str(seg.get("hook_intelligence_type", "none") or "none").lower()
    moment_type   = str(seg.get("moment_type", "unknown") or "unknown").lower()
    struct_phases = list(seg.get("structure_phases", []) or [])

    retention: dict = seg.get("retention_prediction") or {}
    retention_available = bool(retention.get("retention_available", False))
    retention_level     = str(retention.get("risk_level") or "").lower()

    # ── Platform base targets ──────────────────────────────────────────────
    pacing_raw   = _PLATFORM_PACING_TARGET[platform]
    opener_raw   = _PLATFORM_OPENER_EMPHASIS[platform]
    density_raw  = _PLATFORM_SUBTITLE_DENSITY[platform]
    polish_raw   = _PLATFORM_VISUAL_POLISH[platform]

    # ── Per-clip signal modulation (before style clamping) ────────────────
    # pacing: payoff moment pushes +1 step faster; soft hook pulls -1 step calmer.
    if moment_type == "payoff":
        pacing_raw = _step(pacing_raw, +1, _PACING_ORDER)
    elif hook_type in _SOFT_HOOK_TYPES:
        pacing_raw = _step(pacing_raw, -1, _PACING_ORDER)

    # opener_emphasis: strong hooks amplify; soft hooks soften.
    if hook_type in _STRONG_HOOK_TYPES:
        opener_raw = _step(opener_raw, +1, _OPENER_ORDER)
    elif hook_type in _SOFT_HOOK_TYPES:
        opener_raw = _step(opener_raw, -1, _OPENER_ORDER)

    # density: no clip-level modulation (platform base is correct).
    # polish: full_story + Reels gets an extra polish nudge.
    if moment_type in ("full_story", "narrative") and platform == "instagram_reels":
        polish_raw = _step(polish_raw, +1, _POLISH_ORDER)

    # ── RC3: Creator style conflict suppression ───────────────────────────
    # Conservative styles cap all hints at mid-scale (never aggressive end).
    pacing_hint   = _clamp_for_style(pacing_raw,  subtitle_style, _PACING_ORDER)
    opener_hint   = _clamp_for_style(opener_raw,  subtitle_style, _OPENER_ORDER)
    density_hint  = _clamp_for_style(density_raw, subtitle_style, _DENSITY_ORDER)
    polish_hint   = _clamp_for_style(polish_raw,  subtitle_style, _POLISH_ORDER)

    style_clamped = (
        subtitle_style in _CONSERVATIVE_STYLES
        and (
            pacing_hint   != pacing_raw
            or opener_hint  != opener_raw
            or density_hint != density_raw
        )
    )

    # ── RC2: Confidence [0.10, 0.90] — heuristic only, never certainty ────
    conf = _BASE_CONFIDENCE + _CONF_PLATFORM_KNOWN  # platform always known here
    if strategy_ctx:
        conf += _CONF_STRATEGY_AVAIL
    if moment_type not in ("unknown", ""):
        conf += _CONF_MOMENT_KNOWN
    if hook_type != "none":
        conf += _CONF_HOOK_KNOWN
    if retention_available:
        conf += _CONF_RETENTION_AVAIL
    confidence = round(max(S3_PLATFORM_CONFIDENCE_MIN, min(0.90, conf)), 3)  # RC2

    # ── RC4: platform_reason list ─────────────────────────────────────────
    platform_reason: list[str] = [f"platform={platform}"]
    if moment_type not in ("unknown", ""):
        platform_reason.append(f"moment={moment_type}")
    if hook_type != "none":
        platform_reason.append(f"hook={hook_type}")
    if retention_available and retention_level:
        platform_reason.append(f"retention={retention_level}")
    if style_clamped:
        platform_reason.append(f"style_clamped={subtitle_style}")

    # ── platform_risks ────────────────────────────────────────────────────
    platform_risks: list[str] = []

    # hook_too_slow: slow/authority opener on fast-paced platform.
    if platform == "tiktok" and hook_type in _SOFT_HOOK_TYPES:
        platform_risks.append("hook_too_slow")

    # payoff_unclear: Shorts clip likely exits before payoff.
    if (
        platform == "youtube_shorts"
        and "payoff" not in struct_phases
        and moment_type not in ("payoff", "hook_payoff", "full_story")
    ):
        platform_risks.append("payoff_unclear")

    # subtitle_crowded: no hook to carry attention → subtitle must do all the work.
    if platform == "tiktok" and hook_type == "none":
        platform_risks.append("subtitle_crowded")

    # style_conflict: informational — conservative style on aggressive platform.
    if style_clamped:
        platform_risks.append("style_conflict")

    # low_signal: overall confidence below reliable threshold.
    if confidence < 0.30:
        platform_risks.append("low_signal")

    return {
        "platform":              platform,
        "pacing_hint":           pacing_hint,
        "opener_emphasis":       opener_hint,
        "subtitle_density_hint": density_hint,
        "visual_polish_hint":    polish_hint,
        "confidence":            confidence,
        "platform_reason":       platform_reason,  # RC4
        "platform_risks":        platform_risks,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _step(current: str, delta: int, order: list[str]) -> str:
    """Move current value by delta steps in order. Clamps to bounds."""
    try:
        idx = order.index(current)
    except ValueError:
        idx = len(order) // 2
    return order[max(0, min(len(order) - 1, idx + delta))]


def _clamp_for_style(target: str, subtitle_style: str, order: list[str]) -> str:
    """RC3: Apply creator style conflict suppression.

    Conservative styles (clean/minimal/soft) cap output at the middle of
    the scale — never push to the aggressive end regardless of platform target.
    Example: clean + TikTok strong opener → clamped to moderate.

    Neutral or aggressive styles: full platform target allowed.
    """
    if subtitle_style not in _CONSERVATIVE_STYLES:
        return target  # neutral or aggressive: no cap
    try:
        target_idx = order.index(target)
    except ValueError:
        return target
    mid_idx = len(order) // 2
    return order[min(target_idx, mid_idx)]
