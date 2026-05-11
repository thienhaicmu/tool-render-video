"""
unified_quality_scorer.py — Deterministic unified quality dimension scorers. Phase 52D.

All scorers:
  - return int scores in [0, 100]
  - never raise
  - are metadata-based only (fuse Phase 52A/B/C outputs + creator/market/strategy signals)
  - tolerate None / missing / empty inputs

Public API:
    score_subtitle(edit_plan)      -> int
    score_camera(edit_plan)        -> int
    score_hook(edit_plan)          -> int
    score_creator_fit(edit_plan)   -> int
    score_market_fit(edit_plan)    -> int
    score_strategy_fit(edit_plan)  -> int
    compute_confidence(edit_plan)  -> float
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.unified_quality.scorer")


# ---------------------------------------------------------------------------
# Subsystem score pass-throughs
# ---------------------------------------------------------------------------

def score_subtitle(edit_plan: Any) -> int:
    """Read subtitle_quality_v2.overall from Phase 52A. Returns 0 if unavailable."""
    try:
        sqv2 = _get(edit_plan, "subtitle_quality_v2")
        return _clamp(int(sqv2.get("overall") or 0))
    except Exception:
        return 0


def score_camera(edit_plan: Any) -> int:
    """Read camera_quality_v2.overall from Phase 52B. Returns 0 if unavailable."""
    try:
        cqv2 = _get(edit_plan, "camera_quality_v2")
        return _clamp(int(cqv2.get("overall") or 0))
    except Exception:
        return 0


def score_hook(edit_plan: Any) -> int:
    """Read hook_quality_v2.overall from Phase 52C. Returns 0 if unavailable."""
    try:
        hqv2 = _get(edit_plan, "hook_quality_v2")
        return _clamp(int(hqv2.get("overall") or 0))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Creator fit
# ---------------------------------------------------------------------------

def score_creator_fit(edit_plan: Any) -> int:
    """Aggregate creator fit across subtitle, camera, and hook subsystems + creator profile."""
    try:
        sqv2 = _get(edit_plan, "subtitle_quality_v2")
        cqv2 = _get(edit_plan, "camera_quality_v2")
        hqv2 = _get(edit_plan, "hook_quality_v2")
        cpp  = _get(edit_plan, "creator_preference_profile")
        cpe  = _get(edit_plan, "creator_preset_evolution")

        sub_cf  = int(sqv2.get("creator_fit") or 0)
        cam_cf  = int(cqv2.get("creator_fit") or 0)
        hook_cf = int(hqv2.get("creator_fit") or 0)

        # Only average non-zero available scores
        available = [v for v in (sub_cf, cam_cf, hook_cf) if v > 0]
        if not available:
            return 0

        base = round(sum(available) / len(available))

        # creator_preference_profile confidence → small supplement
        cpp_conf = float(cpp.get("confidence") or 0.0)
        if cpp_conf >= 0.7:
            base += 5
        elif cpp_conf >= 0.5:
            base += 3
        elif cpp_conf >= 0.3:
            base += 1

        # Preset evolution maturity enriches creator model calibration
        if cpe.get("available") and cpe.get("evolved_presets"):
            base += 2

        return _clamp(round(base))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Market fit
# ---------------------------------------------------------------------------

def score_market_fit(edit_plan: Any) -> int:
    """Aggregate market fit from hook market score + subtitle safe-zone + market confidence."""
    try:
        hqv2 = _get(edit_plan, "hook_quality_v2")
        sqv2 = _get(edit_plan, "subtitle_quality_v2")
        moi  = _get(edit_plan, "market_optimization_intelligence")

        hook_mf = int(hqv2.get("market_fit") or 0)
        # subtitle safe_zone_fit is a partial market-fit proxy (placement safety)
        sub_szf = int(sqv2.get("safe_zone_fit") or 0)

        signals = [v for v in (hook_mf, sub_szf) if v > 0]
        if not signals:
            return 0

        # Weighted: hook market fit carries more weight (direct market signal)
        if len(signals) == 2:
            base = round(hook_mf * 0.70 + sub_szf * 0.30)
        else:
            base = signals[0]

        # Market optimization confidence boost
        if moi.get("available"):
            moi_conf = float(moi.get("confidence") or 0.0)
            if moi_conf >= 0.7:
                base += 5
            elif moi_conf >= 0.5:
                base += 3

        return _clamp(round(base))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Strategy fit
# ---------------------------------------------------------------------------

def score_strategy_fit(edit_plan: Any) -> int:
    """Score strategy quality from Phase 51B variant evaluation + Phase 51C reasoning."""
    try:
        ve  = _get(edit_plan, "variant_evaluation")
        bsr = _get(edit_plan, "best_strategy_reasoning")

        ve_avail = bool(ve.get("available"))
        ve_conf  = float(ve.get("confidence") or 0.0)
        bsr_conf = float(bsr.get("confidence") or 0.0)

        if not ve_avail and bsr_conf == 0.0:
            return 0

        base = 0

        # Variant evaluation confidence → core signal
        if ve_avail:
            base = round(ve_conf * 100)
            # Best variant ID exists → strategy is resolved
            if ve.get("best_variant_id"):
                base += 5

        # Best strategy reasoning recommendation strength
        strength = str(bsr.get("recommendation_strength") or "none").lower()
        if strength == "strong":
            base += 10
        elif strength == "moderate":
            base += 5
        elif strength == "weak":
            base += 2

        # Blend with BSR confidence when available
        if bsr_conf > 0.0:
            base = round(base * 0.70 + bsr_conf * 100 * 0.30)

        return _clamp(round(base))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def compute_confidence(edit_plan: Any) -> float:
    """Compute unified confidence from subsystem signal richness. 0–1."""
    try:
        signals = 0

        # Subsystem quality scores
        for attr in ("subtitle_quality_v2", "camera_quality_v2", "hook_quality_v2"):
            d = _get(edit_plan, attr)
            if int(d.get("overall") or 0) > 0 or float(d.get("confidence") or 0.0) > 0.0:
                signals += 1

        # Creator profile
        cpp = _get(edit_plan, "creator_preference_profile")
        if float(cpp.get("confidence") or 0.0) > 0.0:
            signals += 1

        # Market intelligence
        moi = _get(edit_plan, "market_optimization_intelligence")
        if moi.get("available"):
            signals += 1

        # Strategy evaluation
        ve = _get(edit_plan, "variant_evaluation")
        if ve.get("available"):
            signals += 1

        raw = signals / 6.0
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


def _clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(v)))
