"""
subtitle_promotion_engine.py — Phase 59A Subtitle Influence Promotion.

Promotes advisory subtitle influence metadata into actual subtitle render
configuration on the payload. This is the first safe execution promotion
layer for AI subtitle intelligence.

Promoted fields:
    payload.subtitle_style        (preset selection)
    payload.highlight_per_word    (keyword emphasis)

Design rules:
  - Never raises — returns safe fallback on any error.
  - User explicit style wins: only promotes FROM the AI-neutral default.
  - Preset must be in ALLOWED_PROMOTION_PRESETS.
  - Confidence thresholds block low-quality promotions.
  - AI only enables highlight_per_word — never disables it.
  - No subtitle timing rewrite.
  - No ASS generation rewrite.
  - No segmentation rewrite.
  - No transcript mutation.
  - No new preset generation.
  - Executor remains authority.

Public API:
    promote_subtitle_influence(payload, edit_plan, context=None)
        -> tuple[payload, dict]

Promotion report shape:
    {
        "subtitle_execution_promotion": {
            "applied": bool,
            "preset_applied": str | None,
            "density_applied": str | None,   # advisory only — no field mutation
            "keyword_emphasis_applied": bool,
            "confidence": float,
            "reason": str,
            "reasoning": list[str],
        }
    }

Safety contract:
    ❌ No subtitle timing rewrite
    ❌ No ASS generation rewrite
    ❌ No segmentation rewrite
    ❌ No transcript mutation
    ❌ No new subtitle preset generation
    ❌ No FFmpeg mutation
    ❌ No render pipeline rewrite
    ❌ No playback_speed mutation
    ❌ No executor override
    ✅ Only promotes from AI-neutral default style
    ✅ Preset validated against ALLOWED_PROMOTION_PRESETS
    ✅ Confidence gates enforced before any mutation
    ✅ Deterministic: same inputs → same output
    ✅ User override respected (subtitle_style not in neutral set → no change)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.subtitle_promotion")

# ---------------------------------------------------------------------------
# Allowed promotion targets — must exist as real presets in subtitle_engine.py
# ---------------------------------------------------------------------------
ALLOWED_PROMOTION_PRESETS: frozenset = frozenset({
    "viral_bold",
    "clean_pro",
    "boxed_caption",
})

# Styles that mean "user has no explicit preference" — AI may promote from these.
# "pro_karaoke" is the legacy schema default. None covers unset/null.
_AI_NEUTRAL_STYLES: frozenset = frozenset({"pro_karaoke", None, ""})

# Confidence thresholds (conservative — err on the side of doing nothing)
_CONF_THRESHOLD_PRESET:    float = 0.80
_CONF_THRESHOLD_EMPHASIS:  float = 0.78

# Emphasis delta minimum to trigger highlight_per_word promotion
_EMPHASIS_DELTA_ENABLE_THRESHOLD: float = 0.10

# Emphasis values from Phase 50A that justify enabling highlight_per_word
_EMPHASIS_ENABLE_VALUES: frozenset = frozenset({"moderate", "strong"})

# Platform keyword emphasis values that justify enabling highlight_per_word
_PLATFORM_EMPHASIS_ENABLE_VALUES: frozenset = frozenset({"high", "moderate"})

# Preset → whether to also enable highlight_per_word when promoting
_PRESET_IMPLIES_HIGHLIGHT: dict = {
    "viral_bold":    True,   # viral_bold is designed for word-level bounce
    "clean_pro":     None,   # keep existing value (no change either way)
    "boxed_caption": False,  # opaque box works better with block subtitles
}

# Max reasoning lines in the promotion report
_MAX_REASONING = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def promote_subtitle_influence(
    payload: Any,
    edit_plan: Any,
    context: Optional[dict] = None,
) -> tuple[Any, dict]:
    """Promote advisory subtitle influence metadata to actual render configuration.

    Mutates payload.subtitle_style and/or payload.highlight_per_word in-place
    when promotion conditions are met. Returns (payload, promotion_report).

    Args:
        payload:   RenderRequest-compatible object with subtitle config fields.
        edit_plan: AIEditPlan (or None/dict) with Phase 50–56 metadata.
        context:   Optional dict with "job_id" etc. for logging.

    Returns:
        (payload, {"subtitle_execution_promotion": {...}})
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        report = _promote(payload, edit_plan, job_id)
        return payload, report
    except Exception as exc:
        logger.warning("subtitle_promotion_unexpected_error job_id=%s: %s", job_id, exc)
        return payload, _fallback_report("promotion_error")


# ---------------------------------------------------------------------------
# Core promotion
# ---------------------------------------------------------------------------

def _promote(payload: Any, edit_plan: Any, job_id: str) -> dict:
    """Core promotion logic. May raise — caller wraps in try/except."""

    # ── Gate 1: basic eligibility ──────────────────────────────────────────
    if not bool(getattr(payload, "add_subtitle", False)):
        return _fallback_report("subtitles_disabled")

    if edit_plan is None:
        return _fallback_report("no_edit_plan")

    # ── Gate 2: user override detection ───────────────────────────────────
    current_style = getattr(payload, "subtitle_style", None)
    user_locked = bool(getattr(payload, "subtitle_ai_style_lock", False))

    if user_locked:
        logger.debug("subtitle_promotion_skipped job_id=%s reason=user_locked", job_id)
        return _fallback_report("user_override", note="subtitle_ai_style_lock=true")

    if current_style not in _AI_NEUTRAL_STYLES:
        logger.debug(
            "subtitle_promotion_skipped job_id=%s reason=user_set_style style=%r",
            job_id, current_style,
        )
        return _fallback_report("user_override", note=f"style={current_style!r}")

    # ── Read signal sources ────────────────────────────────────────────────
    sub_influence = _get_dict(edit_plan, "creator_subtitle_influence")
    sub_pref      = _get_dict(edit_plan, "creator_subtitle_preference")
    prs           = _get_dict(edit_plan, "platform_render_strategy")
    psi           = _get_dict(edit_plan, "platform_strategy_influence")
    # Phase 61B: archetype-derived style (lowest-priority fallback)
    css_promo     = _get_dict(edit_plan, "creator_subtitle_style_promotion")

    # Primary confidence: Phase 50A inference confidence
    pref_inner  = (sub_pref.get("subtitle_preference") or {}) if sub_pref else {}
    pref_conf = _safe_float(pref_inner.get("confidence"))
    # Only trust platform_render_strategy confidence when the signal is available
    prs_conf  = _safe_float(prs.get("confidence")) if (prs and prs.get("available")) else 0.0
    # Use the higher of the two available confidence signals
    effective_conf = max(pref_conf, prs_conf)

    reasoning: list[str] = []
    applied_any = False

    # ── Preset promotion ───────────────────────────────────────────────────
    preset_applied: Optional[str] = None
    if effective_conf >= _CONF_THRESHOLD_PRESET:
        preset_candidate, preset_reason = _resolve_preset(
            sub_influence, pref_inner, prs, psi, css_promo
        )
        if preset_candidate and preset_candidate in ALLOWED_PROMOTION_PRESETS:
            try:
                payload.subtitle_style = preset_candidate
                preset_applied = preset_candidate
                applied_any = True
                reasoning.append(preset_reason)
                logger.info(
                    "subtitle_preset_promoted job_id=%s preset=%r conf=%.3f",
                    job_id, preset_candidate, effective_conf,
                )
            except Exception as exc:
                logger.debug(
                    "subtitle_preset_set_failed job_id=%s: %s", job_id, exc
                )

    # ── highlight_per_word promotion ──────────────────────────────────────
    # Never disable; only enable.
    keyword_emphasis_applied = False
    existing_highlight = bool(getattr(payload, "highlight_per_word", False))

    if not existing_highlight and effective_conf >= _CONF_THRESHOLD_EMPHASIS:
        should_enable, emph_reason = _resolve_emphasis(
            sub_influence, pref_inner, prs, preset_applied
        )
        if should_enable:
            try:
                payload.highlight_per_word = True
                keyword_emphasis_applied = True
                applied_any = True
                reasoning.append(emph_reason)
                logger.info(
                    "subtitle_keyword_emphasis_promoted job_id=%s conf=%.3f",
                    job_id, effective_conf,
                )
            except Exception as exc:
                logger.debug(
                    "subtitle_emphasis_set_failed job_id=%s: %s", job_id, exc
                )

    # ── Density (advisory only — no field to mutate) ───────────────────────
    density_applied: Optional[str] = _resolve_density_advisory(sub_influence, pref_inner)

    if not applied_any:
        return _fallback_report(
            "no_eligible_promotion",
            confidence=effective_conf,
            reasoning=reasoning,
        )

    logger.info(
        "subtitle_promotion_applied job_id=%s preset=%r emphasis=%s density_advisory=%r conf=%.3f",
        job_id, preset_applied, keyword_emphasis_applied, density_applied, effective_conf,
    )

    return {
        "subtitle_execution_promotion": {
            "applied":                   True,
            "preset_applied":            preset_applied,
            "density_applied":           density_applied,   # advisory only
            "keyword_emphasis_applied":  keyword_emphasis_applied,
            "confidence":                round(effective_conf, 4),
            "reason":                    "promotion_applied",
            "reasoning":                 reasoning[:_MAX_REASONING],
        }
    }


# ---------------------------------------------------------------------------
# Signal resolvers
# ---------------------------------------------------------------------------

def _resolve_preset(
    sub_influence: dict,
    pref_inner: dict,
    prs: dict,
    psi: dict,
    css_promo: Optional[dict] = None,
) -> tuple[Optional[str], str]:
    """Priority-ordered preset resolution. Returns (preset_id | None, reason)."""

    # 1. Phase 50C creator subtitle influence (most creator-specific signal)
    if sub_influence and sub_influence.get("available"):
        bias = str(sub_influence.get("preset_bias") or "").strip().lower()
        if bias in ALLOWED_PROMOTION_PRESETS:
            return bias, f"Creator subtitle influence recommended {bias!r} style"

    # 2. Phase 55E platform render strategy
    if prs and prs.get("available"):
        prs_sub = (prs.get("strategy") or {}).get("subtitle") or {}
        style_bias = str(prs_sub.get("style_bias") or "").strip().lower()
        if style_bias in ALLOWED_PROMOTION_PRESETS:
            platform = str(prs.get("platform") or "")
            return style_bias, f"Platform strategy ({platform}) recommended {style_bias!r} style"

    # 3. Phase 56 platform strategy influence
    if psi and psi.get("available"):
        psi_sub = (psi.get("subtitle") or {})
        if psi_sub.get("supported"):
            psi_bias = (psi_sub.get("bias") or {})
            psi_style = str(psi_bias.get("style") or "").strip().lower()
            if psi_style in ALLOWED_PROMOTION_PRESETS:
                return psi_style, f"Platform strategy influence supported {psi_style!r} style"

    # 4. Phase 50A creator subtitle preference (broadest signal)
    pref_style = str(pref_inner.get("style") or "").strip().lower()
    if pref_style in ALLOWED_PROMOTION_PRESETS:
        return pref_style, f"Creator subtitle preference inferred {pref_style!r} style"

    # 5. Phase 61B creator archetype style (lowest-priority fallback)
    if css_promo and css_promo.get("available"):
        arch_preset = str(css_promo.get("recommended_preset") or "").strip().lower()
        if arch_preset in ALLOWED_PROMOTION_PRESETS:
            creator = str(css_promo.get("creator_type") or "unknown")
            return arch_preset, f"Creator archetype ({creator!r}) style recommended {arch_preset!r}"

    return None, ""


def _resolve_emphasis(
    sub_influence: dict,
    pref_inner: dict,
    prs: dict,
    promoted_preset: Optional[str],
) -> tuple[bool, str]:
    """Determine whether to enable highlight_per_word. Returns (enable, reason)."""

    # 1. Phase 50C emphasis delta >= threshold
    if sub_influence and sub_influence.get("available"):
        delta = _safe_float(sub_influence.get("emphasis_delta"))
        if delta >= _EMPHASIS_DELTA_ENABLE_THRESHOLD:
            return True, f"Subtitle influence emphasis delta {delta:+.2f} exceeds enable threshold"

    # 2. Phase 50A keyword_emphasis field
    emphasis = str(pref_inner.get("keyword_emphasis") or "").strip().lower()
    if emphasis in _EMPHASIS_ENABLE_VALUES:
        return True, f"Creator subtitle preference shows {emphasis!r} keyword emphasis"

    # 3. Phase 55E platform keyword emphasis
    if prs and prs.get("available"):
        prs_sub = (prs.get("strategy") or {}).get("subtitle") or {}
        plat_emphasis = str(prs_sub.get("keyword_emphasis") or "").strip().lower()
        if plat_emphasis in _PLATFORM_EMPHASIS_ENABLE_VALUES:
            platform = str(prs.get("platform") or "")
            return True, f"Platform strategy ({platform}) recommends {plat_emphasis!r} keyword emphasis"

    # 4. Promoted preset implies highlight_per_word
    if promoted_preset and _PRESET_IMPLIES_HIGHLIGHT.get(promoted_preset) is True:
        return True, f"Promoted preset {promoted_preset!r} is designed for word-level highlighting"

    return False, ""


def _resolve_density_advisory(
    sub_influence: dict,
    pref_inner: dict,
) -> Optional[str]:
    """Return an advisory density recommendation (no field is mutated)."""
    if sub_influence and sub_influence.get("available"):
        nudge = str(sub_influence.get("density_nudge") or "none").strip().lower()
        if nudge == "reduce":
            return "medium"

    density = str(pref_inner.get("density") or "").strip().lower()
    if density in ("medium", "light"):
        return density

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fallback_report(
    reason: str,
    note: str = "",
    confidence: float = 0.0,
    reasoning: Optional[list] = None,
) -> dict:
    full_reason = f"{reason}:{note}" if note else reason
    return {
        "subtitle_execution_promotion": {
            "applied":                  False,
            "preset_applied":           None,
            "density_applied":          None,
            "keyword_emphasis_applied": False,
            "confidence":               round(confidence, 4),
            "reason":                   full_reason,
            "reasoning":                list(reasoning or []),
        }
    }


def _get_dict(edit_plan: Any, attr: str) -> dict:
    """Duck-typed attribute read — works for AIEditPlan or dict. Never raises."""
    try:
        if isinstance(edit_plan, dict):
            val = edit_plan.get(attr)
        else:
            val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(val: Any) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0
