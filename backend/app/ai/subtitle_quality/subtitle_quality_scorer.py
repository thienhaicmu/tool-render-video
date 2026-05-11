"""
subtitle_quality_scorer.py — Deterministic subtitle quality dimension scorers. Phase 52A.

All scorers:
  - return int scores in [0, 100]
  - never raise
  - are metadata-based only (no OCR, no visual frame analysis, no text rewrite)
  - tolerate None / missing inputs

Public API:
    score_mobile_readability(edit_plan) -> int
    score_subtitle_balance(edit_plan) -> int
    score_keyword_emphasis_quality(edit_plan) -> int
    score_safe_zone_fit(edit_plan) -> int
    score_creator_fit(edit_plan) -> int
    score_overload_risk(edit_plan) -> int
    score_fatigue_risk(edit_plan) -> int
    compute_confidence(edit_plan) -> float
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.subtitle_quality.scorer")

# Baseline when signal is absent
_BASELINE = 55


# ---------------------------------------------------------------------------
# Mobile readability
# ---------------------------------------------------------------------------

def score_mobile_readability(edit_plan: Any) -> int:
    """Evaluate mobile reading comfort from density, line count, complexity signals."""
    try:
        base = _BASELINE
        se   = _get(edit_plan, "subtitle_execution")
        sta  = _get(edit_plan, "subtitle_text_apply")
        csi  = _get(edit_plan, "creator_subtitle_influence")

        hint = se.get("global_hint") or {}
        density = str(hint.get("density_mode") or "normal").lower()

        # Dense subtitles are harder to read on mobile
        if density == "compact":
            base += 8
        elif density == "normal":
            base += 0
        elif density == "expressive":
            base -= 6

        # subtitle_text_apply available means optimized text was applied
        if sta.get("available") or sta.get("enabled"):
            base += 7
        if sta.get("warnings"):
            base -= 4

        # Subtitle execution warnings → potential readability issue
        se_warns = se.get("warnings") or []
        if se_warns:
            base -= 4

        # Overload detection (execution metadata or warnings string)
        se_meta = se.get("execution_metadata") or {}
        if se_meta.get("overload") or "subtitle_overload" in str(se_warns):
            base -= 12

        # Mobile readability nudge from creator influence (Phase 50C)
        mob_nudge = float(csi.get("mobile_readability_nudge") or 0.0)
        base += mob_nudge * 20  # nudge is in [-1, 1] → ±20 pts

        # Regions count: too many small regions → lower readability
        regions = se.get("regions") or []
        n_regions = len(regions)
        if n_regions > 15:
            base -= 5
        elif n_regions <= 8 and n_regions > 0:
            base += 3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Subtitle balance
# ---------------------------------------------------------------------------

def score_subtitle_balance(edit_plan: Any) -> int:
    """Evaluate line balance, pacing consistency, density consistency."""
    try:
        base = _BASELINE
        se   = _get(edit_plan, "subtitle_execution")
        pacing = _get(edit_plan, "pacing")

        hint = se.get("global_hint") or {}
        density = str(hint.get("density_mode") or "normal").lower()
        emphasis_strength = float(hint.get("emphasis_strength") or 0.0)

        # Moderate emphasis is well-balanced; extremes reduce balance
        if 0.2 <= emphasis_strength <= 0.7:
            base += 8
        elif emphasis_strength > 0.85:
            base -= 5  # over-emphasis

        # Consistent density → better balance
        if density == "normal":
            base += 5
        elif density == "compact":
            base += 3  # compact can be balanced

        # Pacing consistency: available beat + emotion signal → structured pacing
        beat_available = bool(pacing.get("beat_available"))
        if beat_available:
            bpm = float(pacing.get("bpm") or 0.0)
            if 80 <= bpm <= 160:  # readable BPM range for subtitles
                base += 6
            elif bpm > 0:
                base += 2

        # Region count consistency: regions → more temporal variety, usually balanced
        regions = se.get("regions") or []
        n_regions = len(regions)
        if 5 <= n_regions <= 15:
            base += 4

        # subtitle_execution warnings reduce balance confidence
        if se.get("warnings"):
            base -= 5

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Keyword emphasis quality
# ---------------------------------------------------------------------------

def score_keyword_emphasis_quality(edit_plan: Any) -> int:
    """Evaluate keyword highlight usage, overuse/underuse risk, visual clarity."""
    try:
        base = _BASELINE
        se    = _get(edit_plan, "subtitle_execution")
        sub   = _get_attr(edit_plan, "subtitle")  # AICameraPlan-like attr
        csi   = _get(edit_plan, "creator_subtitle_influence")

        hint = se.get("global_hint") or {}
        emphasis_strength = float(hint.get("emphasis_strength") or 0.0)
        keyword_focus     = list(hint.get("keyword_focus") or [])

        # Keyword focus available → emphasis is targeted
        n_keywords = len(keyword_focus)
        if n_keywords >= 3:
            base += 8
        elif n_keywords == 1 or n_keywords == 2:
            base += 4
        # 0 keywords → no emphasis signal, base unchanged

        # Emphasis strength sweet spot: moderate emphasis is clearest
        if 0.25 <= emphasis_strength <= 0.65:
            base += 8
        elif emphasis_strength > 0.8:
            base -= 6  # over-emphasis reduces clarity (overuse risk)
        elif emphasis_strength < 0.1 and n_keywords == 0:
            base -= 4  # underuse risk

        # AICameraPlan subtitle highlight_keywords flag (from Phase 5)
        if isinstance(sub, dict):
            highlight_kw = bool(sub.get("highlight_keywords"))
        else:
            highlight_kw = bool(getattr(sub, "highlight_keywords", False))
        if highlight_kw:
            base += 5

        # Creator influence emphasis delta
        emp_delta = float(csi.get("emphasis_delta") or 0.0)
        if abs(emp_delta) <= 0.15:
            base += 3  # conservative delta → balanced emphasis

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Safe zone fit
# ---------------------------------------------------------------------------

def score_safe_zone_fit(edit_plan: Any) -> int:
    """Evaluate subtitle margin, aspect ratio fit, TikTok/mobile UI overlap risk."""
    try:
        base = _BASELINE
        csi  = _get(edit_plan, "creator_subtitle_influence")
        moi  = _get(edit_plan, "market_optimization_intelligence")
        cpp  = _get(edit_plan, "creator_preference_profile")

        # Market target: mobile-first markets have stricter safe-zone needs
        target_market = str(moi.get("target_market") or "").lower()
        sub_bias = moi.get("subtitle_market_bias") or {}
        sub_style = str(sub_bias.get("preferred_style") or "").lower()

        # Mobile-first markets → safe-zone fit is critical
        if target_market in ("tiktok", "mobile", "short_form", "reels"):
            base += 10  # AI specifically favors safe zones for these
        elif target_market in ("youtube", "podcast", "educational"):
            base += 5

        # viral_bold / boxed_caption on TikTok: generally safe (positioned correctly)
        if sub_style in ("viral_bold", "boxed_caption"):
            base += 6
        elif sub_style == "clean_pro":
            base += 4

        # Creator subtitle preference: style aligned with safe placement
        sub_profile = cpp.get("subtitle") or {}
        prof_style = str(sub_profile.get("style") or "unknown").lower()
        if prof_style in ("viral_bold", "boxed_caption"):
            base += 4

        # Motion style bias: static is safest for safe-zone (no crop drift)
        motion_bias = str(csi.get("motion_style_bias") or "").lower()
        if motion_bias == "static":
            base += 5
        elif motion_bias in ("smooth", "dynamic"):
            base += 2

        # No strong subtitle execution warnings → safer layout
        se = _get(edit_plan, "subtitle_execution")
        if not se.get("warnings"):
            base += 4

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Creator subtitle fit
# ---------------------------------------------------------------------------

def score_creator_fit(edit_plan: Any) -> int:
    """Evaluate how well subtitle decisions align with creator's established preferences."""
    try:
        base = _BASELINE
        csp  = _get(edit_plan, "creator_subtitle_preference")
        csi  = _get(edit_plan, "creator_subtitle_influence")
        cpp  = _get(edit_plan, "creator_preference_profile")
        cpe  = _get(edit_plan, "creator_preset_evolution")

        # Phase 50A: creator subtitle preference confidence
        sub_pref = csp.get("subtitle_preference") or {}
        pref_conf = float(sub_pref.get("confidence") or 0.0)
        pref_style = str(sub_pref.get("style") or "unknown").lower()
        available_50a = bool(csp.get("available"))

        if not available_50a:
            # No creator data → moderate neutral baseline
            return _clamp(round(base))

        # Higher preference confidence → stronger creator alignment signal
        if pref_conf >= 0.7:
            base += 15
        elif pref_conf >= 0.5:
            base += 10
        elif pref_conf >= 0.3:
            base += 5

        # Phase 50C influence: if influence is applied and tier is high → great fit
        tier = str(csi.get("confidence_tier") or "low").lower()
        if tier == "high":
            base += 10
        elif tier == "medium":
            base += 5

        # Conservative preset bias strength → trustworthy alignment
        bias_strength = float(csi.get("preset_bias_strength") or 0.0)
        if 0.1 <= bias_strength <= 0.5:
            base += 4

        # Phase 50D: creator preference profile subtitle confidence
        sub_profile = cpp.get("subtitle") or {}
        prof_style  = str(sub_profile.get("style") or "unknown").lower()
        prof_conf   = float(sub_profile.get("confidence") or 0.0)

        if prof_style != "unknown" and prof_style == pref_style:
            base += 6  # 50A + 50D agree → strong alignment
        if prof_conf >= 0.6:
            base += 4

        # Phase 46: preset evolution — if evolved and available → creator style mature
        if cpe.get("available") and cpe.get("evolved_presets"):
            base += 3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Risk scores
# ---------------------------------------------------------------------------

def score_overload_risk(edit_plan: Any) -> int:
    """Evaluate subtitle overload risk. Lower is better (0 = no risk)."""
    try:
        risk = 0
        se = _get(edit_plan, "subtitle_execution")

        hint = se.get("global_hint") or {}
        density = str(hint.get("density_mode") or "normal").lower()
        emphasis_strength = float(hint.get("emphasis_strength") or 0.0)
        n_keywords = len(list(hint.get("keyword_focus") or []))

        # Dense subtitles increase overload risk
        if density == "expressive":
            risk += 25
        elif density == "normal":
            risk += 8
        elif density == "compact":
            risk += 3

        # High emphasis + many keywords → overload
        if emphasis_strength > 0.8:
            risk += 15
        if n_keywords > 8:
            risk += 10
        elif n_keywords > 5:
            risk += 5

        # Execution metadata overload flag
        se_meta = se.get("execution_metadata") or {}
        se_warns = se.get("warnings") or []
        if se_meta.get("overload") or "subtitle_overload" in str(se_warns):
            risk += 30

        # Many regions → more subtitle events → higher overload potential
        regions = se.get("regions") or []
        n_regions = len(regions)
        if n_regions > 18:
            risk += 10
        elif n_regions > 12:
            risk += 5

        return _clamp(round(risk))
    except Exception:
        return 0


def score_fatigue_risk(edit_plan: Any) -> int:
    """Evaluate subtitle reading fatigue risk. Lower is better."""
    try:
        risk = 0
        se     = _get(edit_plan, "subtitle_execution")
        pacing = _get(edit_plan, "pacing")

        hint = se.get("global_hint") or {}
        density = str(hint.get("density_mode") or "normal").lower()
        beat_sync = float(hint.get("beat_sync_strength") or 0.0)
        emphasis_strength = float(hint.get("emphasis_strength") or 0.0)

        # High density + high beat sync → rapid reading → fatigue
        if density == "expressive" and beat_sync > 0.6:
            risk += 20
        elif density == "expressive":
            risk += 12

        # Very high emphasis throughout → cognitive load
        if emphasis_strength > 0.75:
            risk += 10

        # Fast BPM with subtitles → fatigue
        bpm = float(pacing.get("bpm") or 0.0)
        if bpm > 180:
            risk += 15
        elif bpm > 140:
            risk += 8
        elif bpm > 120:
            risk += 4

        # High energy level → stimulating content, fatigue possible
        energy = float(pacing.get("energy_level") or 0.0)
        if energy > 0.85:
            risk += 8
        elif energy > 0.65:
            risk += 4

        # Many regions → reading many subtitle events → fatigue
        regions = se.get("regions") or []
        n_regions = len(regions)
        if n_regions > 18:
            risk += 8
        elif n_regions > 12:
            risk += 4

        return _clamp(round(risk))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def compute_confidence(edit_plan: Any) -> float:
    """Compute evaluation confidence from signal richness. 0–1."""
    try:
        signals = 0
        for attr in (
            "subtitle_execution",
            "subtitle_text_apply",
            "creator_subtitle_preference",
            "creator_subtitle_influence",
            "creator_preference_profile",
            "market_optimization_intelligence",
            "creator_preset_evolution",
            "pacing",
        ):
            d = _get(edit_plan, attr)
            if d and (d.get("available") or d.get("enabled") or len(d) > 1):
                signals += 1

        # AICameraPlan subtitle plan is always present
        sub = _get_attr(edit_plan, "subtitle")
        if sub is not None:
            signals += 1

        raw = signals / 9.0
        return round(max(0.0, min(1.0, raw)), 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(edit_plan: Any, attr: str) -> dict:
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _get_attr(edit_plan: Any, attr: str) -> Any:
    try:
        return getattr(edit_plan, attr, None)
    except Exception:
        return None


def _clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(v)))
