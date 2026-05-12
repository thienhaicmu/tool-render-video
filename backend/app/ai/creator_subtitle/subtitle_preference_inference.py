"""
subtitle_preference_inference.py — Deep Subtitle Preference Intelligence Engine. Phase 50A.

Infers rich creator subtitle preferences from available AI metadata signals.
Metadata-only: no render mutation, no subtitle engine rewrite, no timing rewrite.
No executor override. No internet. No cloud AI.

Public API:
    infer_subtitle_preference(edit_plan) -> dict

Returns:
    {
        "available": bool,
        "inference_mode": "metadata_only",
        "subtitle_preference": {
            "style":               "clean_pro" | "viral_bold" | "boxed_caption" | "unknown",
            "density":             "light" | "medium" | "dense" | "unknown",
            "line_count":          int (1-3),
            "uppercase":           "uppercase" | "mixed" | "lowercase" | "unknown",
            "keyword_emphasis":    "none" | "subtle" | "moderate" | "strong" | "unknown",
            "motion_style":        "clean" | "bounce" | "karaoke" | "unknown",
            "caption_box":         "none" | "minimal" | "boxed" | "unknown",
            "readability_priority":"low" | "medium" | "high" | "unknown",
            "mobile_safe":         bool,
            "confidence":          float [0.0, 1.0],
            "signals":             [str, ...]   -- max 5, creator-facing only
        },
        "warnings": [str, ...]
    }
    or {"available": False, "inference_mode": "metadata_only",
        "subtitle_preference": <unknown_profile>, "warnings": [...]}
    on any failure.

Safety contract:
    ❌ No FFmpeg mutation
    ❌ No render pipeline changes
    ❌ No subtitle timing rewrite
    ❌ No ASS generation rewrite
    ❌ No executor override
    ❌ No autonomous execution
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.creator_subtitle.subtitle_preference_schema import (
    ALLOWED_STYLES, ALLOWED_DENSITIES, ALLOWED_UPPERCASE,
    ALLOWED_EMPHASIS, ALLOWED_MOTION, ALLOWED_CAPTION_BOX, ALLOWED_READABILITY,
    AISubtitlePreference, AISubtitlePreferencePack,
)

logger = logging.getLogger("app.ai.creator_subtitle.inference")

# Number of distinct signal domains we can draw from
_MAX_SIGNAL_DOMAINS = 8

# Max signal strings exposed to UI (creator-facing, no debug output)
_MAX_SIGNAL_ITEMS = 5

# Minimum confidence to report available=True
_MIN_CONFIDENCE_THRESHOLD = 0.0  # always available; confidence itself conveys certainty


def infer_subtitle_preference(edit_plan: Any) -> dict:
    """Infer creator subtitle preferences from AI metadata. Never raises.

    Args:
        edit_plan: AIEditPlan (or None) with Phases 17, 33, 42–48 metadata.
                   Passing None returns available=False — no data to infer from.

    Returns:
        Subtitle preference pack dict (always includes subtitle_preference key).
    """
    if edit_plan is None:
        return AISubtitlePreferencePack(
            available=False,
            warnings=["no_edit_plan"],
        ).to_dict()
    try:
        pack = _infer(edit_plan)
        return pack.to_dict()
    except Exception as exc:
        logger.debug("subtitle_preference_inference_error: %s", exc)
        return AISubtitlePreferencePack(
            available=False,
            warnings=[f"inference_error:{type(exc).__name__}"],
        ).to_dict()


# ---------------------------------------------------------------------------
# Core inference
# ---------------------------------------------------------------------------

def _infer(edit_plan: Any) -> AISubtitlePreferencePack:
    warnings: list[str] = []

    # Collect all signal source dicts
    subtitle_apply  = _get_dict(edit_plan, "subtitle_text_apply")
    subtitle_exec   = _get_dict(edit_plan, "subtitle_execution")
    adaptive        = _get_dict(edit_plan, "adaptive_creator_intelligence")
    feedback        = _get_dict(edit_plan, "creator_feedback_intelligence")
    market          = _get_dict(edit_plan, "market_optimization_intelligence")
    quality         = _get_dict(edit_plan, "render_quality_evaluation")
    preset_ev       = _get_dict(edit_plan, "creator_preset_evolution")
    influence       = _get_dict(edit_plan, "safe_influence_pack")
    orchestration   = _get_dict(edit_plan, "multi_signal_orchestration")

    signals: list[str] = []
    active_domains = 0

    # ── Style ────────────────────────────────────────────────────────────────
    style, style_sig = _infer_style(
        subtitle_apply, feedback, influence, orchestration, market, preset_ev
    )
    if style_sig:
        signals.append(style_sig)
        active_domains += 1

    # ── Density ──────────────────────────────────────────────────────────────
    density, density_sig = _infer_density(
        subtitle_exec, influence, orchestration, market
    )
    if density_sig:
        signals.append(density_sig)
        active_domains += 1

    # ── Line count ───────────────────────────────────────────────────────────
    line_count, line_sig = _infer_line_count(subtitle_exec, subtitle_apply, density)
    if line_sig:
        signals.append(line_sig)
        active_domains += 1

    # ── Uppercase ────────────────────────────────────────────────────────────
    uppercase, uc_sig = _infer_uppercase(style, market, feedback)
    if uc_sig:
        signals.append(uc_sig)
        active_domains += 1

    # ── Keyword emphasis ─────────────────────────────────────────────────────
    keyword_emphasis, ke_sig = _infer_keyword_emphasis(
        subtitle_apply, subtitle_exec, market, style
    )
    if ke_sig:
        signals.append(ke_sig)
        active_domains += 1

    # ── Motion style ─────────────────────────────────────────────────────────
    motion_style, ms_sig = _infer_motion_style(feedback, market)
    if ms_sig:
        signals.append(ms_sig)
        active_domains += 1

    # ── Caption box (derived from style — no separate signal) ────────────────
    caption_box = _infer_caption_box(style)

    # ── Readability priority ─────────────────────────────────────────────────
    readability_priority, rp_sig = _infer_readability_priority(quality, market)
    if rp_sig:
        signals.append(rp_sig)
        active_domains += 1

    # ── Mobile safe ──────────────────────────────────────────────────────────
    mobile_safe = _infer_mobile_safe(market)

    # ── Confidence ───────────────────────────────────────────────────────────
    confidence = _compute_confidence(active_domains, adaptive, feedback)

    # Phase 53B: optional knowledge-aware signal enrichment
    # Guard: only enrich when style is known and at least one domain was active.
    # Empty / no-signal plans are not enriched to preserve existing fallback behaviour.
    if len(signals) < _MAX_SIGNAL_ITEMS and style != "unknown" and active_domains > 0:
        k_signal = _get_knowledge_signal(style, mobile_safe)
        if k_signal:
            signals.append(k_signal)

    preference = AISubtitlePreference(
        style=style,
        density=density,
        line_count=line_count,
        uppercase=uppercase,
        keyword_emphasis=keyword_emphasis,
        motion_style=motion_style,
        caption_box=caption_box,
        readability_priority=readability_priority,
        mobile_safe=mobile_safe,
        confidence=confidence,
        signals=signals[:_MAX_SIGNAL_ITEMS],
    )

    return AISubtitlePreferencePack(
        available=True,
        inference_mode="metadata_only",
        subtitle_preference=preference,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Style inference
# ---------------------------------------------------------------------------

def _infer_style(subtitle_apply, feedback, influence, orchestration, market, preset_ev):
    """Infer subtitle style. Returns (style, signal_str)."""

    # 1. Creator feedback — highest priority (reflects actual creator choices)
    fb_patterns = feedback.get("learned_patterns") or {}
    fb_style = str(fb_patterns.get("subtitle_style_pattern") or "").lower()
    mapped = _map_style(fb_style)
    if mapped != "unknown":
        return mapped, f"Creator historically preferred {mapped} subtitle style"

    # 2. Phase 48 safe influence bias
    si = influence.get("safe_influence") or {}
    style_bias = str(si.get("subtitle_style_bias") or "").lower()
    if style_bias and style_bias in ALLOWED_STYLES and style_bias != "unknown":
        return style_bias, f"AI influence recommended {style_bias} subtitle style"

    # 3. Phase 47 orchestration recommended strategy
    rec = orchestration.get("recommended_strategy") or {}
    orc_style = _map_style(str(rec.get("subtitle_style") or ""))
    if orc_style != "unknown":
        return orc_style, f"Multi-signal orchestration recommended {orc_style} subtitle style"

    # 4. Phase 33 subtitle apply metadata
    apply_style = _map_style(str(subtitle_apply.get("subtitle_style") or ""))
    if apply_style != "unknown":
        return apply_style, f"Prior subtitle apply metadata preferred {apply_style} style"

    # 5. Phase 46 preset evolution
    best_preset = preset_ev.get("recommended_preset") or {}
    preset_style = _map_style(str(best_preset.get("subtitle_style") or ""))
    if preset_style != "unknown":
        return preset_style, f"Preset evolution recommended {preset_style} subtitle style"

    # 6. Phase 44 market profile
    mp = market.get("market_profile") or {}
    mkt_style = _map_style(str(mp.get("subtitle_style") or ""))
    if mkt_style != "unknown":
        return mkt_style, f"Market profile suggests {mkt_style} subtitle style"

    return "unknown", ""


def _map_style(raw: str) -> str:
    if not raw:
        return "unknown"
    s = raw.lower().strip()
    if s in ("viral_bold", "viral", "bold"):
        return "viral_bold"
    if s in ("clean_pro", "clean", "compact", "clean_readable",
             "compact_viral", "clean_compact", "readable"):
        return "clean_pro"
    if s in ("boxed_caption", "boxed", "caption", "caption_box"):
        return "boxed_caption"
    if s in ALLOWED_STYLES and s != "unknown":
        return s
    return "unknown"


# ---------------------------------------------------------------------------
# Density inference
# ---------------------------------------------------------------------------

def _infer_density(subtitle_exec, influence, orchestration, market):
    """Infer subtitle density. Returns (density, signal_str)."""

    # 1. Phase 48 density bias
    si = influence.get("safe_influence") or {}
    density_bias = str(si.get("subtitle_density_bias") or "").lower()
    if density_bias == "lighter":
        return "light", "AI influence recommended lighter subtitle density"

    # 2. Phase 17 subtitle execution density
    exec_density = _map_density(str(subtitle_exec.get("density") or ""))
    if exec_density != "unknown":
        return exec_density, f"Subtitle execution metadata shows {exec_density} density preference"

    # 3. Phase 47 orchestration
    rec = orchestration.get("recommended_strategy") or {}
    orc_density = _map_density(str(rec.get("subtitle_density") or ""))
    if orc_density != "unknown":
        return orc_density, f"Orchestration recommended {orc_density} subtitle density"

    # 4. Phase 44 market profile
    mp = market.get("market_profile") or {}
    # market_optimizer stores subtitle density bias as a numeric weight; try label fields
    mkt_label = str(mp.get("density") or mp.get("subtitle_density_label") or "")
    mkt_density = _map_density(mkt_label)
    if mkt_density != "unknown":
        return mkt_density, f"Market profile indicates {mkt_density} subtitle density"

    return "unknown", ""


def _map_density(raw: str) -> str:
    if not raw:
        return "unknown"
    s = raw.lower().strip()
    if s in ("light", "low", "sparse", "minimal"):
        return "light"
    if s in ("medium", "normal", "balanced", "moderate", "medium_density"):
        return "medium"
    if s in ("dense", "high", "heavy", "compact"):
        return "dense"
    if s in ALLOWED_DENSITIES and s != "unknown":
        return s
    return "unknown"


# ---------------------------------------------------------------------------
# Line count inference
# ---------------------------------------------------------------------------

def _infer_line_count(subtitle_exec, subtitle_apply, density: str):
    """Infer preferred subtitle line count. Returns (line_count, signal_str)."""
    max_words = (
        subtitle_exec.get("max_words_per_line")
        or subtitle_apply.get("max_words_per_line")
    )
    try:
        mw = int(max_words)
        if mw <= 4:
            return 1, "Short max-words-per-line suggests single-line subtitle preference"
        elif mw <= 8:
            return 2, "Medium max-words-per-line suggests two-line subtitle preference"
        else:
            return 3, "Wide max-words-per-line supports three-line subtitle layout"
    except (TypeError, ValueError):
        pass

    # Derive conservatively from density
    if density == "light":
        return 1, ""
    return 2, ""


# ---------------------------------------------------------------------------
# Uppercase inference
# ---------------------------------------------------------------------------

def _infer_uppercase(style: str, market, feedback):
    """Infer uppercase preference. Returns (uppercase, signal_str)."""

    # 1. Creator feedback explicit pattern
    fb_patterns = feedback.get("learned_patterns") or {}
    fb_uc = str(fb_patterns.get("uppercase_pattern") or "").lower()
    if fb_uc in ALLOWED_UPPERCASE and fb_uc != "unknown":
        return fb_uc, f"Creator feedback shows {fb_uc} text casing preference"

    # 2. Infer from style
    if style == "viral_bold":
        return "uppercase", "Viral bold style typically uses uppercase text"
    if style in ("clean_pro", "boxed_caption"):
        return "mixed", f"{style} style uses mixed case for readability"

    # 3. Infer from market
    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or mp.get("platform_name") or "").lower()
    if "tiktok" in target:
        return "uppercase", "TikTok market favors uppercase subtitle text"
    if "podcast" in target or "educational" in target:
        return "mixed", f"{target} market uses mixed case for readability"
    if "shorts" in target or "youtube" in target:
        return "mixed", "YouTube Shorts market uses mixed case subtitles"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Keyword emphasis inference
# ---------------------------------------------------------------------------

def _infer_keyword_emphasis(subtitle_apply, subtitle_exec, market, style: str):
    """Infer keyword emphasis. Returns (emphasis, signal_str)."""

    # 1. Phase 33 subtitle apply emphasis_style
    apply_emphasis = str(subtitle_apply.get("emphasis_style") or "").lower()
    if apply_emphasis and apply_emphasis not in ("none", ""):
        mapped = _map_emphasis(apply_emphasis)
        if mapped != "unknown":
            return mapped, f"Subtitle apply metadata shows {mapped} keyword emphasis"

    # 2. Phase 17 subtitle execution emphasis flag
    has_emphasis = (
        subtitle_exec.get("has_emphasis")
        or subtitle_exec.get("emphasis_enabled")
    )
    if has_emphasis is True:
        return "moderate", "Subtitle execution metadata shows keyword emphasis active"
    if has_emphasis is False:
        return "none", "Subtitle execution metadata shows no keyword emphasis"

    # 3. Infer from style + market
    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()
    if style == "viral_bold" or "tiktok" in target:
        return "strong", "Viral style typically uses strong keyword emphasis"
    if style == "clean_pro":
        return "subtle", "Clean Pro style uses subtle keyword emphasis"
    if "podcast" in target or "educational" in target:
        return "none", f"{target} market prefers no keyword emphasis"

    return "unknown", ""


def _map_emphasis(raw: str) -> str:
    if not raw:
        return "unknown"
    s = raw.lower().strip()
    if s in ("none", "off", "disabled"):
        return "none"
    if s in ("subtle", "light", "soft", "minimal"):
        return "subtle"
    if s in ("moderate", "medium", "normal", "bold", "standard"):
        return "moderate"
    if s in ("strong", "heavy", "aggressive", "vibrant", "intense"):
        return "strong"
    return "unknown"


# ---------------------------------------------------------------------------
# Motion style inference
# ---------------------------------------------------------------------------

def _infer_motion_style(feedback, market):
    """Infer subtitle motion/animation style. Returns (motion_style, signal_str)."""

    # 1. Creator feedback pattern
    fb_patterns = feedback.get("learned_patterns") or {}
    fb_motion = str(fb_patterns.get("motion_style_pattern") or "").lower()
    if fb_motion in ALLOWED_MOTION and fb_motion != "unknown":
        return fb_motion, f"Creator feedback shows preference for {fb_motion} subtitle motion"

    # 2. Market profile
    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()
    if "tiktok" in target:
        return "bounce", "TikTok market typically prefers bounce subtitle motion"
    if "podcast" in target or "educational" in target:
        return "clean", f"{target} market favors clean subtitle motion"
    if "shorts" in target or "youtube" in target:
        return "clean", "YouTube Shorts market prefers clean subtitle motion"
    if "reels" in target or "facebook" in target:
        return "clean", "Facebook Reels market uses clean subtitle motion"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Caption box inference
# ---------------------------------------------------------------------------

def _infer_caption_box(style: str) -> str:
    """Infer caption box preference from style. Always returns allowed value."""
    if style == "boxed_caption":
        return "boxed"
    if style == "clean_pro":
        return "minimal"
    if style == "viral_bold":
        return "none"
    return "unknown"


# ---------------------------------------------------------------------------
# Readability priority inference
# ---------------------------------------------------------------------------

def _infer_readability_priority(quality, market):
    """Infer readability priority. Returns (readability_priority, signal_str)."""

    # 1. Quality evaluation subtitle_readability scores
    output_scores = quality.get("output_scores") or []
    if output_scores:
        try:
            scores = [
                float(s.get("subtitle_readability") or 0.0)
                for s in output_scores
                if isinstance(s, dict)
            ]
            if scores:
                avg = sum(scores) / len(scores)
                if avg >= 0.70:
                    return "high", f"Subtitle readability score consistently high (avg={avg:.2f})"
                elif avg >= 0.40:
                    return "medium", f"Subtitle readability score moderate (avg={avg:.2f})"
                else:
                    return "low", f"Subtitle readability score low (avg={avg:.2f})"
        except Exception:
            pass

    # 2. Market profile
    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()
    if "podcast" in target or "educational" in target:
        return "high", f"{target} market prioritizes subtitle readability"
    if "tiktok" in target:
        return "medium", "TikTok market balances readability with visual impact"
    if "shorts" in target or "youtube" in target:
        return "medium", "YouTube Shorts market prioritizes moderate readability"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Mobile safe inference
# ---------------------------------------------------------------------------

def _infer_mobile_safe(market) -> bool:
    """Infer mobile-safe flag. Defaults True (conservative)."""
    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()
    platform = str(mp.get("platform_name") or "").lower()
    combined = target + " " + platform

    if "podcast" in combined:
        return False  # podcast is primarily desktop/audio
    if any(k in combined for k in ("tiktok", "shorts", "reels", "mobile", "instagram")):
        return True

    # Conservative default: assume mobile-safe
    return True


# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------

def _compute_confidence(active_domains: int, adaptive, feedback) -> float:
    """Compute inference confidence. Clamped to [0.0, 1.0]."""
    base = min(active_domains / _MAX_SIGNAL_DOMAINS, 1.0)

    # Amplify when adaptive profile has subtitle confidence
    adaptive_influences = adaptive.get("adaptive_influences") or {}
    sub_weight = _safe_float(
        adaptive_influences.get("subtitle_enhancement_weight")
        or (adaptive.get("creator_profile") or {}).get("subtitle_confidence")
    )

    # Amplify when feedback has subtitle signal history
    fb_patterns = feedback.get("learned_patterns") or {}
    fb_count = _safe_int(
        fb_patterns.get("subtitle_style_count")
        or feedback.get("subtitle_signal_count")
        or feedback.get("total_exports")  # conservative proxy
    )

    amplifier = 0.0
    if sub_weight > 0.20:
        amplifier += sub_weight * 0.10
    if fb_count >= 3:
        amplifier += min(fb_count * 0.02, 0.10)

    raw = base + amplifier
    return round(max(0.0, min(1.0, raw)), 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(val) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Phase 53B — optional knowledge signal enrichment
# ---------------------------------------------------------------------------

def _get_knowledge_signal(style: str, mobile_safe: bool) -> str:
    """Return an optional subtitle knowledge signal. Never raises. Phase 53B.

    Enriches the inference signals list with curated subtitle knowledge guidance.
    Metadata-only — does not change inferred values, weights, or confidence.
    """
    try:
        from app.ai.knowledge.subtitle_knowledge_retriever import (
            retrieve_knowledge,
            build_subtitle_reasoning,
        )
        tags: list = []
        if style == "clean_pro":
            tags.append("podcast")
        elif style == "viral_bold":
            tags.append("tiktok")
        if mobile_safe:
            tags.append("mobile")
        if not tags:
            return ""
        pack = retrieve_knowledge(domain="subtitle", tags=tags, max_results=1)
        hints = build_subtitle_reasoning(pack, creator_style=None, subtitle_style=style)
        if hints:
            raw = hints[0]
            # Truncate to keep signal concise (max 100 chars for UI display)
            return raw[:100] if raw else ""
        return ""
    except Exception:
        return ""
