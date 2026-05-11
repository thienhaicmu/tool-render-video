"""
hook_quality_scorer.py — Deterministic hook quality dimension scorers. Phase 52C.

All scorers:
  - return int scores in [0, 100]
  - never raise
  - are metadata-based only (no transcript rewrite, no frame analysis, no hook rewrite)
  - tolerate None / missing inputs

Public API:
    score_first_3s_strength(edit_plan)  -> int
    score_first_5s_retention(edit_plan) -> int
    score_curiosity_strength(edit_plan) -> int
    score_open_loop_quality(edit_plan)  -> int
    score_hook_fatigue_risk(edit_plan)  -> int
    score_market_fit(edit_plan)         -> int
    score_creator_fit(edit_plan)        -> int
    compute_confidence(edit_plan)       -> float
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.hook_quality.scorer")

# Baseline when positive-dimension signal is absent
_BASELINE = 55


# ---------------------------------------------------------------------------
# First 3 seconds strength
# ---------------------------------------------------------------------------

def score_first_3s_strength(edit_plan: Any) -> int:
    """Evaluate opening hook strength from story, pacing, and emotion signals."""
    try:
        base = _BASELINE

        pacing    = _get(edit_plan, "pacing")
        story     = _get(edit_plan, "story")
        retention = _get(edit_plan, "retention")

        # Story hook segment in opening position is the strongest signal
        segments  = story.get("segments") or []
        has_hook  = any(
            str(s.get("type") or "").lower() in ("hook", "intro", "opening")
            for s in segments[:3]
            if isinstance(s, dict)
        )
        if has_hook:
            base += 16

        # Emotion drives immediate attention
        emotion = str(pacing.get("emotion") or "neutral").lower()
        if emotion in ("excitement", "happy", "energetic", "hype"):
            base += 10
        elif emotion in ("suspense", "curious", "tension"):
            base += 7
        elif emotion in ("sad", "bored", "flat"):
            base -= 6

        # High energy = strong attention capture
        energy = float(pacing.get("energy_level") or 0.0)
        if energy >= 0.75:
            base += 8
        elif energy >= 0.50:
            base += 4
        elif energy > 0 and energy < 0.30:
            base -= 5

        # Upbeat/dynamic pacing style
        pacing_style = str(pacing.get("pacing_style") or "default").lower()
        if pacing_style in ("upbeat", "dynamic", "fast"):
            base += 6
        elif pacing_style in ("slow", "relaxed"):
            base -= 4

        # Retention risk in first region reduces hook strength
        risk_regions = retention.get("risk_regions") or []
        for region in risk_regions[:5]:
            if not isinstance(region, dict):
                continue
            start = float(region.get("start") or 0.0)
            if start < 3.0:
                base -= 8
                break

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# First 5 seconds retention
# ---------------------------------------------------------------------------

def score_first_5s_retention(edit_plan: Any) -> int:
    """Evaluate first-5-second retention from pacing, content momentum, and retention signals."""
    try:
        base = _BASELINE

        pacing    = _get(edit_plan, "pacing")
        retention = _get(edit_plan, "retention")
        story     = _get(edit_plan, "story")

        # Overall retention score is the primary signal
        ret_score = float(retention.get("overall_score") or 0.0)
        if ret_score > 0:
            # Map retention score (0–100) into a delta on our baseline
            base += round((ret_score - 50) * 0.30)

        # BPM affects pacing momentum
        bpm = float(pacing.get("bpm") or 0.0)
        if bpm > 140:
            base += 8
        elif bpm > 120:
            base += 5
        elif bpm > 90:
            base += 2
        elif bpm > 0 and bpm < 80:
            base -= 4

        # Fast cut style = better retention momentum
        cut_style = str(pacing.get("suggested_cut_style") or "standard").lower()
        if cut_style in ("fast", "beat_synced"):
            base += 6
        elif cut_style in ("slow", "none"):
            base -= 3

        # High energy
        energy = float(pacing.get("energy_level") or 0.0)
        if energy >= 0.70:
            base += 6
        elif energy >= 0.40:
            base += 2

        # Story momentum: early hook followed by story segments = content continuity
        segments = story.get("segments") or []
        if len(segments) >= 2:
            base += 4

        # Retention risk regions overlapping first 5 seconds reduce score
        risk_regions = retention.get("risk_regions") or []
        early_risks = sum(
            1
            for r in risk_regions[:8]
            if isinstance(r, dict) and float(r.get("start") or 99.0) < 5.0
        )
        base -= early_risks * 6

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Curiosity strength
# ---------------------------------------------------------------------------

def score_curiosity_strength(edit_plan: Any) -> int:
    """Evaluate curiosity/tension signal from story, pacing, and market metadata."""
    try:
        base = _BASELINE

        pacing = _get(edit_plan, "pacing")
        story  = _get(edit_plan, "story")
        moi    = _get(edit_plan, "market_optimization_intelligence")

        # Story tension/curiosity segment types
        segments = story.get("segments") or []
        for seg in segments[:6]:
            if not isinstance(seg, dict):
                continue
            seg_type = str(seg.get("type") or "").lower()
            if seg_type in ("tension", "curiosity", "conflict", "question"):
                base += 12
                break

        # Suspense/curious emotion strongly correlates with curiosity
        emotion = str(pacing.get("emotion") or "neutral").lower()
        if emotion in ("suspense", "curious", "tension"):
            base += 10
        elif emotion in ("excitement", "hype"):
            base += 5

        # Fast cut style builds tension
        cut_style = str(pacing.get("suggested_cut_style") or "standard").lower()
        if cut_style in ("fast", "beat_synced"):
            base += 6

        # Market hook preference: some markets reward curiosity-driven hooks
        hook_bias = (moi.get("hook_market_bias") or {})
        hook_pref = str(hook_bias.get("preferred_style") or "").lower()
        if hook_pref in ("curiosity", "open_loop", "narrative"):
            base += 8
        elif hook_pref in ("direct", "action"):
            base -= 3

        # Subtitle market bias available = metadata is enriched
        if moi.get("available"):
            base += 3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Open loop quality
# ---------------------------------------------------------------------------

def score_open_loop_quality(edit_plan: Any) -> int:
    """Evaluate unresolved curiosity / payoff expectation signal from story metadata."""
    try:
        base = _BASELINE

        story = _get(edit_plan, "story")
        pacing = _get(edit_plan, "pacing")

        segments = story.get("segments") or []

        # Hook without early payoff = strong open loop
        has_hook    = False
        has_payoff  = False
        for i, seg in enumerate(segments[:5]):
            if not isinstance(seg, dict):
                continue
            t = str(seg.get("type") or "").lower()
            if t in ("hook", "intro", "opening", "question", "tension"):
                has_hook = True
            if t in ("payoff", "climax", "resolution") and i > 1:
                has_payoff = True

        if has_hook and not has_payoff:
            base += 16
        elif has_hook:
            base += 8

        # Narrative continuation: more story segments = richer open loop
        seg_count = len([s for s in segments if isinstance(s, dict)])
        if seg_count >= 4:
            base += 6
        elif seg_count >= 2:
            base += 3

        # Suspense/curious emotion reinforces open loop
        emotion = str(pacing.get("emotion") or "neutral").lower()
        if emotion in ("suspense", "curious", "tension"):
            base += 8

        # Story intelligence available and structured = open loop was planned
        if story.get("available"):
            base += 4

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Hook fatigue risk
# ---------------------------------------------------------------------------

def score_hook_fatigue_risk(edit_plan: Any) -> int:
    """Evaluate hook fatigue / repetitive hook risk. Lower score = better."""
    try:
        risk = 20  # moderate baseline

        pacing = _get(edit_plan, "pacing")
        aci    = _get(edit_plan, "adaptive_creator_intelligence")
        cpp    = _get(edit_plan, "creator_preference_profile")
        cpe    = _get(edit_plan, "creator_preset_evolution")
        moi    = _get(edit_plan, "market_optimization_intelligence")

        # Very high energy + high BPM over many uses = fatigue risk
        energy = float(pacing.get("energy_level") or 0.0)
        bpm    = float(pacing.get("bpm") or 0.0)

        if energy >= 0.85 and bpm > 150:
            risk += 12  # hyper-aggressive hook = high fatigue
        elif energy >= 0.75:
            risk += 6
        elif energy > 0 and energy < 0.30:
            risk -= 6   # low energy = low fatigue

        # Adaptive intelligence: repetitive export pattern = fatigue signal
        creator_profile = aci.get("creator_profile") or {}
        export_count = int(creator_profile.get("total_exports") or 0)
        style_conf   = float(creator_profile.get("style_confidence") or 0.0)
        if export_count > 20 and style_conf >= 0.7:
            risk += 8   # creator consistently uses same style → potential overuse

        # Preset evolution: mature preset reused many times = fatigue risk
        if cpe.get("available") and cpe.get("evolved_presets"):
            risk += 4

        # Creator preference profile: strong hook preference = potential overuse
        hook_pref = cpp.get("hook") or {}
        if str(hook_pref.get("strength") or "").lower() == "aggressive":
            risk += 8
        elif str(hook_pref.get("strength") or "").lower() == "moderate":
            risk += 2

        # Market saturation signal
        hook_bias = moi.get("hook_market_bias") or {}
        if str(hook_bias.get("saturation") or "").lower() == "high":
            risk += 6

        return _clamp(round(risk))
    except Exception:
        return 20


# ---------------------------------------------------------------------------
# Market hook fit
# ---------------------------------------------------------------------------

def score_market_fit(edit_plan: Any) -> int:
    """Evaluate how well hook style aligns with target market preferences."""
    try:
        base = _BASELINE

        moi    = _get(edit_plan, "market_optimization_intelligence")
        pacing = _get(edit_plan, "pacing")

        if not moi.get("available"):
            return _clamp(round(base))

        market = str(moi.get("target_market") or "").lower()

        # Market-specific hook behavior alignment
        bpm     = float(pacing.get("bpm") or 0.0)
        energy  = float(pacing.get("energy_level") or 0.0)
        emotion = str(pacing.get("emotion") or "neutral").lower()

        # US/Global: short punchy hooks with high energy
        if market in ("us", "global", "en"):
            if energy >= 0.65:
                base += 12
            if bpm > 120:
                base += 6
            if emotion in ("excitement", "hype", "happy"):
                base += 6

        # JP: narrative-driven, lower energy, story hooks
        elif market in ("jp", "ja", "japan"):
            story  = _get(edit_plan, "story")
            segs   = story.get("segments") or []
            if len(segs) >= 2:
                base += 10
            if bpm > 0 and bpm < 120:
                base += 6
            if energy < 0.70:
                base += 4

        # EU: moderate pacing, balanced hooks
        elif market in ("eu", "de", "fr", "uk", "gb"):
            if 90 <= bpm <= 140:
                base += 10
            if energy >= 0.40:
                base += 6

        # KR: dynamic, visual-heavy hooks
        elif market in ("kr", "ko", "korea"):
            if energy >= 0.70:
                base += 10
            if bpm > 130:
                base += 8

        else:
            # Unknown market: moderate boost if market data is present
            base += 4

        # Market optimization confidence
        conf = float(moi.get("confidence") or 0.0)
        if conf >= 0.7:
            base += 6
        elif conf >= 0.4:
            base += 3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Creator hook fit
# ---------------------------------------------------------------------------

def score_creator_fit(edit_plan: Any) -> int:
    """Evaluate hook style alignment with creator's established preferences."""
    try:
        base = _BASELINE

        cpp = _get(edit_plan, "creator_preference_profile")
        cpe = _get(edit_plan, "creator_preset_evolution")
        aci = _get(edit_plan, "adaptive_creator_intelligence")
        moi = _get(edit_plan, "market_optimization_intelligence")

        # Phase 50D: unified creator preference profile
        hook_pref   = cpp.get("hook") or {}
        pacing_pref = cpp.get("pacing") or {}
        cpp_conf    = float(cpp.get("confidence") or 0.0)

        if hook_pref or pacing_pref:
            if cpp_conf >= 0.7:
                base += 14
            elif cpp_conf >= 0.5:
                base += 9
            elif cpp_conf >= 0.3:
                base += 4

        # Hook style consistency
        hook_style = str(hook_pref.get("style") or "").lower()
        if hook_style in ("curiosity", "tension", "narrative"):
            base += 6
        elif hook_style in ("direct", "action"):
            base += 4

        # Pacing preference alignment
        pacing = _get(edit_plan, "pacing")
        pref_pacing = str(pacing_pref.get("style") or "").lower()
        actual_pacing = str(pacing.get("pacing_style") or "").lower()
        if pref_pacing and actual_pacing and pref_pacing == actual_pacing:
            base += 8

        # Phase 46: preset evolution maturity = creator style is well-calibrated
        if cpe.get("available") and cpe.get("evolved_presets"):
            base += 4

        # Phase 42: adaptive creator intelligence confidence
        creator_profile = aci.get("creator_profile") or {}
        style_conf = float(creator_profile.get("style_confidence") or 0.0)
        if style_conf >= 0.5:
            base += min(8, round(style_conf * 10))

        # Market and creator alignment bonus
        if moi.get("available") and cpp_conf >= 0.5:
            base += 3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def compute_confidence(edit_plan: Any) -> float:
    """Compute evaluation confidence from signal richness. 0–1."""
    try:
        signals = 0
        for attr in (
            "pacing",
            "story",
            "retention",
            "market_optimization_intelligence",
            "creator_preference_profile",
            "creator_preset_evolution",
            "adaptive_creator_intelligence",
            "subtitle_execution",
        ):
            d = _get(edit_plan, attr)
            if d and (d.get("available") or d.get("enabled") or len(d) > 1):
                signals += 1

        # AICameraPlan / AIPacingPlan are always present in an active plan
        if _get_attr(edit_plan, "camera") is not None:
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
