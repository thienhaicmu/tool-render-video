"""
policy_engine.py — AI apply policy decision engine.

Phase 31: builds a compact policy decision from request metadata.
Deterministic. Never raises. Never mutates payload.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .policy_schema import AIPolicyDecision
from .policy_safety import sanitize_policy, build_policy, get_blocked_capabilities

logger = logging.getLogger(__name__)

_DEFAULT_POLICY = "conservative"


def build_policy_decision(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AIPolicyDecision:
    """Build a bounded AI apply policy decision. Never raises. Never mutates payload."""
    context = context or {}
    try:
        raw_policy = _resolve_policy_name(edit_plan, payload, context)
        safe_name = sanitize_policy(raw_policy)

        if safe_name != raw_policy and raw_policy:
            logger.info(
                "ai_apply_policy_fallback requested=%r effective=%s",
                raw_policy, safe_name,
            )

        policy = build_policy(safe_name)
        blocked = get_blocked_capabilities(policy)
        policy_dict = policy.to_dict()

        logger.info(
            "ai_apply_policy_selected policy=%s blocked=%d",
            safe_name, len(blocked),
        )

        return AIPolicyDecision(
            available=True,
            selected_policy=safe_name,
            effective_policy=policy_dict,
            blocked_capabilities=blocked,
            warnings=list(policy.warnings),
        )

    except Exception as exc:
        logger.warning("ai_apply_policy_blocked error=%s", exc)
        return _fallback_decision(str(exc))


def _resolve_policy_name(edit_plan: Any, payload: Any, context: dict) -> str:
    """Resolve the policy name from context, payload, or edit_plan. Never raises."""
    try:
        # Context takes highest priority
        if context.get("ai_apply_policy"):
            return str(context["ai_apply_policy"])
        # Payload attribute
        if payload is not None:
            val = getattr(payload, "ai_apply_policy", None)
            if val:
                return str(val)
        # Edit plan metadata
        if edit_plan is not None:
            existing = getattr(edit_plan, "ai_apply_policy", None)
            if isinstance(existing, dict):
                val = existing.get("selected_policy") or ""
                if val:
                    return str(val)
    except Exception:
        pass
    return _DEFAULT_POLICY


def _fallback_decision(reason: str) -> AIPolicyDecision:
    from .policy_safety import _GLOBAL_HARD_BLOCKS
    return AIPolicyDecision(
        available=False,
        selected_policy="conservative",
        effective_policy={},
        blocked_capabilities=list(_GLOBAL_HARD_BLOCKS),
        warnings=[f"policy_engine_error:{reason}"],
    )
