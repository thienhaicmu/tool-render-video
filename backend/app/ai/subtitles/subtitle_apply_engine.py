"""
subtitle_apply_engine.py — Subtitle text optimization apply engine. Phase 33.

Reads advisory subtitle metadata from Phase 17 (subtitle_execution),
Phase 23 (creator_style_adaptation), Phase 25 (execution_recommendations),
and Phase 27 (safe_render_mutations).

Only applies text/style metadata optimizations when policy permits.
Deterministic. Never raises. Never rewrites subtitle timestamps.
No FFmpeg changes. No playback_speed mutation. No in-place payload mutation.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.subtitles.subtitle_apply_schema import (
    AISubtitleTextApply,
    AISubtitleTextApplyPack,
    _ALLOWED_OPTIMIZATION_TYPES,
    _FORBIDDEN_OPTIMIZATION_TYPES,
    _MIN_CONFIDENCE,
)
from app.ai.subtitles.subtitle_apply_safety import (
    sanitize_subtitle_text_changes,
    is_subtitle_text_apply_safe,
)

logger = logging.getLogger("app.ai.subtitles.subtitle_apply_engine")

# Hard cap on optimizations applied per pack
_MAX_APPLIED: int = 6

# Policies that allow subtitle text optimization apply
_ALLOWED_POLICIES: frozenset[str] = frozenset({"balanced", "aggressive", "experimental"})


def build_subtitle_text_apply_pack(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AISubtitleTextApplyPack:
    """Build a subtitle text optimization apply pack from edit plan metadata.

    Only applies optimizations when:
    - policy is balanced, aggressive, or experimental
    - optimization_type is in _ALLOWED_OPTIMIZATION_TYPES
    - all safety gates pass

    Returns a disabled pack if policy blocks. Never raises.
    Never rewrites subtitle timestamps. Never mutates payload in-place.
    """
    try:
        return _build_pack(edit_plan, payload, context or {})
    except Exception as exc:
        logger.debug("subtitle_apply_engine_failed: %s", exc)
        return _disabled_pack(reason=f"engine_error:{type(exc).__name__}")


def _build_pack(edit_plan: Any, payload: Any, context: dict) -> AISubtitleTextApplyPack:
    job_id = str(context.get("job_id", "unknown"))

    # Policy gate
    effective_policy = _resolve_effective_policy(edit_plan, payload, context)
    if effective_policy not in _ALLOWED_POLICIES:
        logger.info(
            "ai_subtitle_text_apply_skipped job_id=%s policy=%s",
            job_id, effective_policy,
        )
        return _disabled_pack(reason=f"policy_blocked:{effective_policy}")

    # Collect candidates from Phase 17/23/25/27 metadata
    raw_candidates = _collect_candidates(edit_plan)

    if not raw_candidates:
        logger.info(
            "ai_subtitle_text_apply_skipped job_id=%s: no candidates", job_id
        )
        return AISubtitleTextApplyPack(
            available=True,
            enabled=True,
            mode="active",
            applied=[],
            blocked=[],
            warnings=["no_subtitle_candidates_available"],
        )

    applied_list: list[AISubtitleTextApply] = []
    blocked_list: list[AISubtitleTextApply] = []

    for raw in raw_candidates:
        apply_id = str(raw.get("apply_id") or f"sta_{len(applied_list) + len(blocked_list)}")
        opt_type = str(raw.get("optimization_type") or "")
        confidence = float(raw.get("confidence") or 0.0)
        source_id = str(raw.get("source_candidate_id") or "")
        changes = raw.get("changes") or {}

        # Applied count cap
        if len(applied_list) >= _MAX_APPLIED:
            blocked_list.append(AISubtitleTextApply(
                apply_id=apply_id,
                optimization_type=opt_type,
                source_candidate_id=source_id,
                confidence=confidence,
                applied=False,
                safe=False,
                changes=dict(changes),
                warnings=["max_applied_optimizations_reached"],
            ))
            continue

        if is_subtitle_text_apply_safe(raw):
            safe_changes = sanitize_subtitle_text_changes(changes)
            applied_list.append(AISubtitleTextApply(
                apply_id=apply_id,
                optimization_type=opt_type,
                source_candidate_id=source_id,
                confidence=confidence,
                applied=True,
                safe=True,
                target_scope="metadata",
                changes=safe_changes,
                explanation=[f"Safe {opt_type} applied"],
            ))
            logger.info(
                "ai_subtitle_text_optimization_applied job_id=%s apply_id=%s type=%s",
                job_id, apply_id, opt_type,
            )
        else:
            warn_reasons: list[str] = []
            if opt_type in _FORBIDDEN_OPTIMIZATION_TYPES:
                warn_reasons.append("forbidden_optimization_type")
            elif opt_type not in _ALLOWED_OPTIMIZATION_TYPES:
                warn_reasons.append("unknown_optimization_type")
            elif confidence < _MIN_CONFIDENCE:
                warn_reasons.append("confidence_too_low")
            else:
                raw_ch = raw.get("changes") or {}
                if isinstance(raw_ch, dict):
                    forbidden_found = [k for k in raw_ch if k in _FORBIDDEN_CHANGE_KEYS]
                    if forbidden_found:
                        warn_reasons.append(f"forbidden_change_key:{forbidden_found[0]}")
                if not warn_reasons:
                    warn_reasons.append("safety_gate_failed")

            blocked_list.append(AISubtitleTextApply(
                apply_id=apply_id,
                optimization_type=opt_type,
                source_candidate_id=source_id,
                confidence=confidence,
                applied=False,
                safe=False,
                changes=dict(changes),
                warnings=warn_reasons,
            ))
            logger.info(
                "ai_subtitle_text_optimization_blocked job_id=%s apply_id=%s reason=%s",
                job_id, apply_id, warn_reasons[0] if warn_reasons else "unknown",
            )

    logger.info(
        "ai_subtitle_text_apply_enabled job_id=%s applied=%d blocked=%d",
        job_id, len(applied_list), len(blocked_list),
    )
    return AISubtitleTextApplyPack(
        available=True,
        enabled=True,
        mode="active",
        applied=applied_list,
        blocked=blocked_list,
        warnings=[],
    )


def _resolve_effective_policy(edit_plan: Any, payload: Any, context: dict) -> str:
    """Resolution priority: context > payload attribute > edit_plan dict > conservative."""
    try:
        ctx_policy = context.get("ai_apply_policy")
        if ctx_policy and isinstance(ctx_policy, str):
            return ctx_policy.strip().lower()
    except Exception:
        pass
    try:
        pol_attr = getattr(payload, "ai_apply_policy", None)
        if pol_attr and isinstance(pol_attr, str):
            return pol_attr.strip().lower()
    except Exception:
        pass
    try:
        plan_pol = getattr(edit_plan, "ai_apply_policy", {})
        if isinstance(plan_pol, dict):
            sp = plan_pol.get("selected_policy")
            if sp and isinstance(sp, str):
                return sp.strip().lower()
    except Exception:
        pass
    return "conservative"


def _collect_candidates(edit_plan: Any) -> list:
    """Collect subtitle optimization candidates from Phase metadata. Never raises."""
    candidates: list = []

    # Phase 17: subtitle_execution — global_hint density/emphasis
    try:
        se = getattr(edit_plan, "subtitle_execution", {})
        if isinstance(se, dict) and se.get("available"):
            hint = se.get("global_hint") or {}
            if isinstance(hint, dict):
                density_mode = str(hint.get("density_mode") or "normal")
                emphasis = float(hint.get("emphasis_strength") or 0.0)
                confidence = 0.80  # Phase 17 data is pre-validated

                if density_mode == "compact":
                    candidates.append({
                        "apply_id": "p17_density_compact",
                        "optimization_type": "compact_overload",
                        "source_candidate_id": "subtitle_execution",
                        "confidence": confidence,
                        "target_scope": "metadata",
                        "changes": {"subtitle_density": "compact"},
                    })

                if emphasis > 0.3:
                    candidates.append({
                        "apply_id": "p17_emphasis",
                        "optimization_type": "keyword_emphasis",
                        "source_candidate_id": "subtitle_execution",
                        "confidence": min(1.0, confidence + emphasis * 0.1),
                        "target_scope": "metadata",
                        "changes": {
                            "subtitle_emphasis": round(min(1.0, float(emphasis)), 3),
                            "keyword_emphasis": True,
                        },
                    })
    except Exception:
        pass

    # Phase 23: creator_style_adaptation — tone hints
    try:
        csa = getattr(edit_plan, "creator_style_adaptation", {})
        if isinstance(csa, dict) and csa.get("available"):
            adapted = csa.get("adapted_style") or {}
            if isinstance(adapted, dict):
                tone = str(adapted.get("subtitle_tone") or adapted.get("tone") or "")
                conf = float(csa.get("confidence") or 0.0)
                if tone and conf >= _MIN_CONFIDENCE:
                    candidates.append({
                        "apply_id": "p23_creator_tone",
                        "optimization_type": "creator_style_tone",
                        "source_candidate_id": "creator_style_adaptation",
                        "confidence": conf,
                        "target_scope": "metadata",
                        "changes": {"creator_style_tone": tone},
                    })
    except Exception:
        pass

    # Phase 16: retention — subtitle overload detection
    try:
        ret = getattr(edit_plan, "retention", {})
        if isinstance(ret, dict) and ret.get("available"):
            overload = ret.get("subtitle_overload_detected") or ret.get("overload_detected")
            if overload:
                candidates.append({
                    "apply_id": "p16_density_reduce",
                    "optimization_type": "density_reduce",
                    "source_candidate_id": "retention",
                    "confidence": 0.75,
                    "target_scope": "metadata",
                    "changes": {"subtitle_density": "compact", "max_chars_per_line": 32},
                })
    except Exception:
        pass

    # Phase 19 timing plan — hook region detected → hook_emphasis
    try:
        tm = getattr(edit_plan, "timing_mutation", {})
        if isinstance(tm, dict) and tm.get("available"):
            for c in (tm.get("candidates") or []):
                if not isinstance(c, dict):
                    continue
                if c.get("action") == "hold_hook" and float(c.get("confidence") or 0.0) >= _MIN_CONFIDENCE:
                    candidates.append({
                        "apply_id": "p19_hook_emphasis",
                        "optimization_type": "hook_emphasis",
                        "source_candidate_id": "timing_mutation",
                        "confidence": float(c.get("confidence") or 0.70),
                        "target_scope": "metadata",
                        "changes": {
                            "hook_emphasis": True,
                            "subtitle_emphasis": 0.8,
                        },
                    })
                    break  # one hook emphasis is enough
    except Exception:
        pass

    return candidates


def _disabled_pack(reason: str = "disabled") -> AISubtitleTextApplyPack:
    return AISubtitleTextApplyPack(
        available=True,
        enabled=False,
        mode="disabled",
        applied=[],
        blocked=[],
        warnings=[reason],
    )
