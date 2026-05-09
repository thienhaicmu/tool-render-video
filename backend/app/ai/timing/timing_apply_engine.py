"""
timing_apply_engine.py — Safe timing mutation apply engine. Phase 32.

Reads advisory timing candidates from Phase 19/20 metadata.
Only applies safe, bounded timing mutations when policy permits.
Deterministic. Never raises. Never mutates payload in-place.
No FFmpeg changes. No subtitle timing rewrite. No segment reorder.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.timing.timing_apply_schema import (
    AITimingMutationApply,
    AITimingApplyPack,
    _ALLOWED_MUTATION_TYPES,
    _FORBIDDEN_MUTATION_TYPES,
    _MAX_SINGLE_DELTA_SEC,
    _MAX_TOTAL_DELTA_SEC,
    _MIN_CONFIDENCE,
)
from app.ai.timing.timing_apply_safety import (
    sanitize_timing_candidate,
    is_timing_mutation_safe,
)

logger = logging.getLogger("app.ai.timing.timing_apply_engine")

# Hard cap on mutations applied per pack
_MAX_APPLIED_MUTATIONS: int = 5

# Phase 19 action → Phase 32 mutation type mapping
_ACTION_TO_MUTATION_TYPE: dict[str, str] = {
    "tighten_setup": "tighten_setup",
    "trim_silence": "trim_silence_gap",
    "shorten_outro": "shorten_outro",
}


def build_timing_apply_pack(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AITimingApplyPack:
    """Build a safe timing apply pack from edit plan metadata.

    Only applies mutations when:
    - policy is aggressive or experimental
    - mutation type is in _ALLOWED_MUTATION_TYPES
    - all safety gates pass
    - total delta stays within _MAX_TOTAL_DELTA_SEC

    Returns a disabled pack if policy blocks or no candidates exist. Never raises.
    """
    try:
        return _build_pack(edit_plan, payload, context or {})
    except Exception as exc:
        logger.debug("timing_apply_engine_failed: %s", exc)
        return _disabled_pack(reason=f"engine_error:{type(exc).__name__}")


def _build_pack(edit_plan: Any, payload: Any, context: dict) -> AITimingApplyPack:
    job_id = str(context.get("job_id", "unknown"))

    # Policy gate — only aggressive/experimental may apply timing mutations
    effective_policy = _resolve_effective_policy(edit_plan, payload, context)
    if not _policy_allows_timing_apply(effective_policy):
        logger.info(
            "ai_timing_apply_skipped job_id=%s policy=%s",
            job_id, effective_policy,
        )
        return _disabled_pack(reason=f"policy_blocked:{effective_policy}")

    # Collect candidates from Phase 19 + Phase 20 metadata
    raw_candidates = _collect_candidates(edit_plan)

    if not raw_candidates:
        logger.info("ai_timing_apply_skipped job_id=%s: no candidates available", job_id)
        return AITimingApplyPack(
            available=True,
            enabled=True,
            mode="active",
            applied_mutations=[],
            blocked_mutations=[],
            total_delta_sec=0.0,
            warnings=["no_timing_candidates_available"],
        )

    safety_ctx = _build_safety_context(edit_plan, context)
    applied: list[AITimingMutationApply] = []
    blocked: list[AITimingMutationApply] = []
    total_delta = 0.0

    for raw in raw_candidates:
        sanitized = sanitize_timing_candidate(raw)
        if not sanitized:
            continue

        mut_id = sanitized.get("mutation_id") or f"tap_{len(applied) + len(blocked)}"
        mut_type = sanitized.get("mutation_type") or ""
        delta = float(sanitized.get("delta_sec") or 0.0)
        confidence = float(sanitized.get("confidence") or 0.0)
        start_sec = sanitized.get("start_sec")
        end_sec = sanitized.get("end_sec")
        reason = sanitized.get("reason") or ""

        # Total delta budget gate
        if total_delta + delta > _MAX_TOTAL_DELTA_SEC:
            blocked.append(AITimingMutationApply(
                mutation_id=mut_id,
                mutation_type=mut_type,
                source_candidate_id=sanitized.get("source_candidate_id") or "",
                confidence=confidence,
                applied=False,
                safe=False,
                start_sec=start_sec,
                end_sec=end_sec,
                delta_sec=delta,
                reason=reason,
                warnings=["total_delta_budget_exceeded"],
            ))
            continue

        # Applied count cap
        if len(applied) >= _MAX_APPLIED_MUTATIONS:
            blocked.append(AITimingMutationApply(
                mutation_id=mut_id,
                mutation_type=mut_type,
                source_candidate_id=sanitized.get("source_candidate_id") or "",
                confidence=confidence,
                applied=False,
                safe=False,
                start_sec=start_sec,
                end_sec=end_sec,
                delta_sec=delta,
                reason=reason,
                warnings=["max_applied_mutations_reached"],
            ))
            continue

        if is_timing_mutation_safe(sanitized, context=safety_ctx):
            total_delta += delta
            applied.append(AITimingMutationApply(
                mutation_id=mut_id,
                mutation_type=mut_type,
                source_candidate_id=sanitized.get("source_candidate_id") or "",
                confidence=confidence,
                applied=True,
                safe=True,
                start_sec=start_sec,
                end_sec=end_sec,
                delta_sec=delta,
                reason=reason,
                explanation=[f"Safe {mut_type} applied: delta={delta:.2f}s"],
            ))
            logger.info(
                "ai_timing_mutation_applied job_id=%s mutation_id=%s type=%s delta=%.2f",
                job_id, mut_id, mut_type, delta,
            )
        else:
            warn_reasons = list(sanitized.get("warnings") or [])
            if mut_type in _FORBIDDEN_MUTATION_TYPES:
                warn_reasons.append("forbidden_mutation_type")
            elif mut_type not in _ALLOWED_MUTATION_TYPES:
                warn_reasons.append("unknown_mutation_type")
            elif confidence < _MIN_CONFIDENCE:
                warn_reasons.append("confidence_too_low")
            elif delta > _MAX_SINGLE_DELTA_SEC:
                warn_reasons.append("single_delta_exceeds_limit")
            else:
                warn_reasons.append("safety_gate_failed")

            blocked.append(AITimingMutationApply(
                mutation_id=mut_id,
                mutation_type=mut_type,
                source_candidate_id=sanitized.get("source_candidate_id") or "",
                confidence=confidence,
                applied=False,
                safe=False,
                start_sec=start_sec,
                end_sec=end_sec,
                delta_sec=delta,
                reason=reason,
                warnings=warn_reasons,
            ))
            logger.info(
                "ai_timing_mutation_blocked job_id=%s mutation_id=%s type=%s reason=%s",
                job_id, mut_id, mut_type,
                warn_reasons[0] if warn_reasons else "unknown",
            )

    logger.info(
        "ai_timing_apply_enabled job_id=%s applied=%d blocked=%d total_delta=%.2f",
        job_id, len(applied), len(blocked), total_delta,
    )
    return AITimingApplyPack(
        available=True,
        enabled=True,
        mode="active",
        applied_mutations=applied,
        blocked_mutations=blocked,
        total_delta_sec=round(total_delta, 3),
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


def _policy_allows_timing_apply(policy: str) -> bool:
    """Only aggressive and experimental policies allow timing apply."""
    return policy in ("aggressive", "experimental")


def _collect_candidates(edit_plan: Any) -> list:
    """Collect timing candidates from Phase 19 and Phase 20 metadata. Never raises."""
    candidates: list = []

    try:
        tm = getattr(edit_plan, "timing_mutation", {})
        if isinstance(tm, dict) and tm.get("available"):
            for c in (tm.get("candidates") or []):
                if not isinstance(c, dict):
                    continue
                if not c.get("safe_to_apply"):
                    continue
                action = str(c.get("action") or "")
                mut_type = _ACTION_TO_MUTATION_TYPE.get(action)
                if mut_type is None:
                    continue  # unknown/forbidden Phase 19 action — skip
                candidates.append({
                    "mutation_id": f"p19_{action}_{len(candidates)}",
                    "mutation_type": mut_type,
                    "source_candidate_id": action,
                    "confidence": float(c.get("confidence") or 0.0),
                    "start_sec": float(c.get("start") or 0.0),
                    "end_sec": float(c.get("end") or 0.0),
                    "delta_sec": float(c.get("max_trim_seconds") or 0.0),
                    "reason": str(c.get("reason") or ""),
                    "warnings": list(c.get("warnings") or []),
                })
    except Exception:
        pass

    try:
        so = getattr(edit_plan, "story_optimization", {})
        if isinstance(so, dict) and so.get("available"):
            for h in (so.get("timing_hints") or []):
                if not isinstance(h, dict):
                    continue
                mut_type = str(h.get("mutation_type") or "")
                if mut_type not in _ALLOWED_MUTATION_TYPES:
                    continue
                candidates.append({
                    "mutation_id": f"p20_{mut_type}_{len(candidates)}",
                    "mutation_type": mut_type,
                    "source_candidate_id": "story_optimization",
                    "confidence": float(h.get("confidence") or 0.0),
                    "start_sec": h.get("start_sec"),
                    "end_sec": h.get("end_sec"),
                    "delta_sec": float(h.get("delta_sec") or 0.0),
                    "reason": str(h.get("reason") or ""),
                    "warnings": [],
                })
    except Exception:
        pass

    return candidates


def _build_safety_context(edit_plan: Any, context: dict) -> dict:
    """Merge edit plan metadata into safety context for overlap guards. Never raises."""
    safety_ctx: dict = dict(context)
    try:
        ret = getattr(edit_plan, "retention", {})
        if isinstance(ret, dict) and ret.get("available"):
            protected = ret.get("protected_windows") or ret.get("hook_window") or []
            if isinstance(protected, list):
                safety_ctx["protected_windows"] = protected
            elif isinstance(protected, dict):
                safety_ctx["protected_windows"] = [protected]
    except Exception:
        pass
    try:
        se = getattr(edit_plan, "subtitle_execution", {})
        if isinstance(se, dict) and se.get("available"):
            dense = se.get("dense_regions") or []
            if isinstance(dense, list):
                safety_ctx["subtitle_dense_regions"] = dense
    except Exception:
        pass
    return safety_ctx


def _disabled_pack(reason: str = "disabled") -> AITimingApplyPack:
    return AITimingApplyPack(
        available=True,
        enabled=False,
        mode="disabled",
        applied_mutations=[],
        blocked_mutations=[],
        total_delta_sec=0.0,
        warnings=[reason],
    )
