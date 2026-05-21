"""
clip_debug_aggregator.py — S3 Stabilization: unified per-clip debug layer.

Aggregates S3.1–S3.4 advisory signals into a single per-clip debug dict.
Gated by S3_DEBUG_ENABLED (default OFF) — must not leak to production API.

RC1: S3_DEBUG_ENABLED=0 (default) → aggregate_clip_debug() returns {} immediately.
     Debug output is advisory metadata only. NEVER affects selection, retry,
     ranking, diversity, creator DNA, or render pipeline.

RC3 (dominance check): fires a warning in the output when any single signal
     accounts for > S3_DEBUG_DOMINANCE_THRESHOLD (default 55%) of total
     confidence-proxy weight for a clip. Warning is informational only.

Advisory-only architectural constraint:
    The returned debug dict MUST NEVER influence:
      - clip selection (clip_selector.py, segment_builder.py)
      - selection ordering or reranking
      - retry logic (retry_analyzer.py)
      - diversity penalty (diversity_analyzer.py)
      - creator DNA adjustments (dna_engine.py)
      - render pipeline parameters (render_pipeline.py, render_engine.py)

Set S3_DEBUG_ENABLED=1 to activate debug output (dev/staging only).
Set S3_DEBUG_DOMINANCE_THRESHOLD to adjust the dominance warning threshold.

Public API:
    aggregate_clip_debug(selected_segments, clip_packaging, clip_retention_prediction,
                         clip_cover_hints, clip_platform_adaptation) -> dict
    S3_DEBUG_ENABLED: bool
    S3_DEBUG_DOMINANCE_THRESHOLD: float
"""
from __future__ import annotations

import os

S3_DEBUG_ENABLED: bool = os.environ.get("S3_DEBUG_ENABLED", "0") == "1"
S3_DEBUG_DOMINANCE_THRESHOLD: float = float(
    os.environ.get("S3_DEBUG_DOMINANCE_THRESHOLD", "0.55")
)

# Confidence-proxy weights per S3 module.
# Used by RC3 dominance check: proportion of total weight for a clip.
_MODULE_WEIGHTS: dict[str, float] = {
    "packaging":  0.25,
    "retention":  0.35,
    "thumbnail":  0.20,
    "platform":   0.20,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def aggregate_clip_debug(
    selected_segments: list,           # list of AIClipPlan objects
    clip_packaging: dict,              # S3.1 {idx: packaging_dict}
    clip_retention_prediction: dict,   # S3.2 {idx: retention_dict}
    clip_cover_hints: dict,            # S3.3 {idx: cover_hint_dict}
    clip_platform_adaptation: dict,    # S3.4 {idx: adaptation_dict}
) -> dict:
    """Aggregate S3 per-clip debug info.

    Returns {clip_index (int): clip_debug_dict} or {} if S3_DEBUG_ENABLED=0.

    clip_debug_dict fields:
        packaging_summary     dict  — S3.1 signal summary
        retention_summary     dict  — S3.2 score + risks
        thumbnail_summary     dict  — S3.3 ratio + confidence
        platform_summary      dict  — S3.4 hints + platform
        dominance             dict  — RC3 signal balance check
        warnings              list  — dominance or missing-signal warnings

    RC1: S3_DEBUG_ENABLED=0 → {} immediately (production safe).
    RC3: dominance warning when any signal > S3_DEBUG_DOMINANCE_THRESHOLD.
    """
    if not S3_DEBUG_ENABLED:
        return {}  # RC1: hard gate — no debug in production

    result: dict = {}

    for idx, seg_plan in enumerate(selected_segments or []):
        try:
            pkg        = dict(clip_packaging.get(idx) or {})
            retention  = dict(clip_retention_prediction.get(idx) or {})
            cover      = dict(clip_cover_hints.get(idx) or {})
            platform   = dict(clip_platform_adaptation.get(idx) or {})

            pkg_summary       = _summarise_packaging(pkg)
            retention_summary = _summarise_retention(retention)
            thumbnail_summary = _summarise_thumbnail(cover)
            platform_summary  = _summarise_platform(platform)

            dominance_result  = _compute_dominance(pkg, retention, cover, platform)
            warnings: list[str] = []
            if dominance_result.get("dominant_signal"):
                warnings.append(
                    f"dominance_warning:{dominance_result['dominant_signal']}"
                    f"={dominance_result['dominant_pct']:.0%}"
                )

            result[idx] = {
                "packaging_summary":  pkg_summary,
                "retention_summary":  retention_summary,
                "thumbnail_summary":  thumbnail_summary,
                "platform_summary":   platform_summary,
                "dominance":          dominance_result,
                "warnings":           warnings,
            }
        except Exception:
            # Per-clip failure swallowed — never propagates.
            pass

    return result


# ---------------------------------------------------------------------------
# Internal — per-module summarisers
# ---------------------------------------------------------------------------

def _summarise_packaging(pkg: dict) -> dict:
    if not pkg:
        return {"applied": False}
    return {
        "applied":           True,
        "subtitle_intensity": pkg.get("subtitle_intensity"),
        "reason_count":      len(pkg.get("reason") or []),
        "reason":            list(pkg.get("reason") or []),
    }


def _summarise_retention(retention: dict) -> dict:
    if not retention:
        return {"available": False}
    return {
        "available":   bool(retention.get("retention_available", False)),
        "score":       retention.get("retention_score"),
        "risk_level":  retention.get("risk_level"),
        "confidence":  retention.get("prediction_confidence"),
        "risks":       list((retention.get("retention_explanation") or {}).get("risks", [])),
        "strengths":   list((retention.get("retention_explanation") or {}).get("strengths", [])),
    }


def _summarise_thumbnail(cover: dict) -> dict:
    if not cover:
        return {"available": False}
    return {
        "available":            True,
        "offset_ratio":         cover.get("preferred_offset_ratio"),
        "confidence":           cover.get("confidence"),
        "reason":               list(cover.get("reason") or []),
        "risks":                list(cover.get("thumbnail_risks") or []),
    }


def _summarise_platform(platform: dict) -> dict:
    if not platform:
        return {"available": False}
    return {
        "available":       True,
        "platform":        platform.get("platform"),
        "pacing_hint":     platform.get("pacing_hint"),
        "opener_emphasis": platform.get("opener_emphasis"),
        "confidence":      platform.get("confidence"),
        "risks":           list(platform.get("platform_risks") or []),
        "reason":          list(platform.get("platform_reason") or []),
    }


# ---------------------------------------------------------------------------
# RC3: Dominance check
# ---------------------------------------------------------------------------

def _compute_dominance(
    pkg: dict,
    retention: dict,
    cover: dict,
    platform: dict,
) -> dict:
    """RC3: Check if any single S3 module dominates signal weight for this clip.

    Returns dominance dict:
        weights           {module: effective_weight}
        total_weight      float
        dominant_signal   str | None  — module name if > threshold
        dominant_pct      float       — fraction of total weight
        balanced          bool        — True when no single module dominates
    """
    # Compute per-module effective weight (proxy = module weight × signal depth).
    # Signal depth: 1.0 if module produced non-empty output, 0.0 otherwise.
    weights: dict[str, float] = {}

    weights["packaging"] = (
        _MODULE_WEIGHTS["packaging"] if pkg and pkg.get("applied") is not False
        else 0.0
    )

    ret_conf = float(retention.get("prediction_confidence") or 0.0) if retention else 0.0
    weights["retention"] = _MODULE_WEIGHTS["retention"] * ret_conf

    cover_conf = float(cover.get("confidence") or 0.0) if cover and cover.get("preferred_offset_ratio") is not None else 0.0
    weights["thumbnail"] = _MODULE_WEIGHTS["thumbnail"] * cover_conf

    plat_conf = float(platform.get("confidence") or 0.0) if platform and platform.get("pacing_hint") is not None else 0.0
    weights["platform"] = _MODULE_WEIGHTS["platform"] * plat_conf

    total = sum(weights.values())
    if total <= 0.0:
        return {
            "weights":         weights,
            "total_weight":    0.0,
            "dominant_signal": None,
            "dominant_pct":    0.0,
            "balanced":        True,
        }

    dominant_module = max(weights, key=lambda k: weights[k])
    dominant_pct    = weights[dominant_module] / total

    return {
        "weights":         {k: round(v, 4) for k, v in weights.items()},
        "total_weight":    round(total, 4),
        "dominant_signal": dominant_module if dominant_pct > S3_DEBUG_DOMINANCE_THRESHOLD else None,
        "dominant_pct":    round(dominant_pct, 4),
        "balanced":        dominant_pct <= S3_DEBUG_DOMINANCE_THRESHOLD,
    }
