"""
multivariant_execution.py — Safe multi-variant render execution engine.

Phase 29: FIRST phase where AI-prepared variant plans may become actual render jobs.

Execution is opt-in only (ai_multivariant_execution_enabled=True required).
Maximum 3 execution jobs (clamped from ai_multivariant_execution_limit).
safe_baseline is always preserved.

Rules:
- Never raises
- Never mutates original payload
- No FFmpeg mutation
- No playback_speed mutation
- No subtitle timing rewrite
- No segment reorder
- No executor override
- No validation bypass
- Deterministic: same inputs → same execution set
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from .multivariant_execution_schema import (
    AIMultiVariantExecution,
    AIMultiVariantExecutionSet,
)
from .multivariant_execution_safety import (
    sanitize_execution_overrides,
    is_execution_override_safe,
    collect_execution_blocked_fields,
)

logger = logging.getLogger(__name__)

_MAX_EXECUTION_JOBS = 3
_MIN_EXECUTION_JOBS = 1


def build_multivariant_execution_set(
    edit_plan: Any,
    payload: Any,
    context: Optional[dict] = None,
) -> AIMultiVariantExecutionSet:
    """Build a bounded multi-variant render execution set. Never raises."""
    context = context or {}
    try:
        execution_enabled = bool(context.get("ai_multivariant_execution_enabled", False))
        raw_limit = int(context.get("ai_multivariant_execution_limit", 2))
        limit = max(_MIN_EXECUTION_JOBS, min(_MAX_EXECUTION_JOBS, raw_limit))

        plans = _extract_plans(edit_plan)

        if not execution_enabled:
            return _disabled_set(plans)

        executions, executed_ids, blocked_ids = _process_plans(plans, payload, limit)

        warnings: list[str] = []
        if not executed_ids:
            warnings.append("no_plans_executed")

        result = AIMultiVariantExecutionSet(
            available=True,
            execution_enabled=True,
            executions=executions,
            executed_plan_ids=executed_ids,
            blocked_plan_ids=blocked_ids,
            warnings=warnings,
        )

        logger.info(
            "ai_multivariant_execution_created executed=%d blocked=%d limit=%d",
            len(executed_ids), len(blocked_ids), limit,
        )
        return result

    except Exception as exc:
        logger.warning("multivariant_execution_error: %s", exc)
        return _fallback_set(str(exc))


def _extract_plans(edit_plan: Any) -> list[dict]:
    """Extract variant plans from the edit_plan's multivariant_render_plans. Never raises."""
    try:
        mvp = getattr(edit_plan, "multivariant_render_plans", None)
        if not isinstance(mvp, dict):
            return []
        plans = mvp.get("plans") or []
        return [p for p in plans if isinstance(p, dict)]
    except Exception:
        return []


def _process_plans(
    plans: list[dict],
    payload: Any,
    limit: int,
) -> tuple[list[AIMultiVariantExecution], list[str], list[str]]:
    """Process plans into executions, respecting the limit. Never raises."""
    executions: list[AIMultiVariantExecution] = []
    executed_ids: list[str] = []
    blocked_ids: list[str] = []
    executed_count = 0

    for plan in plans:
        plan_id = str(plan.get("plan_id") or "")
        variant_id = str(plan.get("variant_id") or "")
        overrides_raw = plan.get("planned_payload_overrides") or {}
        safe_to_enqueue = bool(plan.get("safe_to_enqueue", False))

        blocked_fields = collect_execution_blocked_fields(overrides_raw)
        sanitized = sanitize_execution_overrides(overrides_raw)
        is_safe = is_execution_override_safe(overrides_raw) and len(blocked_fields) == 0

        exec_id = f"mvexec_{plan_id}"

        if not is_safe or not safe_to_enqueue:
            exec_obj = AIMultiVariantExecution(
                execution_id=exec_id,
                plan_id=plan_id,
                variant_id=variant_id,
                enabled=False,
                safe=False,
                advisory_origin=True,
                payload_overrides=sanitized,
                blocked_fields=blocked_fields,
                render_job_created=False,
                warnings=["unsafe_overrides" if not is_safe else "not_safe_to_enqueue"],
                explanation=["Blocked: unsafe or not safe_to_enqueue"],
            )
            executions.append(exec_obj)
            blocked_ids.append(plan_id)
            logger.info("ai_multivariant_execution_blocked plan_id=%s", plan_id)
            continue

        if executed_count >= limit:
            exec_obj = AIMultiVariantExecution(
                execution_id=exec_id,
                plan_id=plan_id,
                variant_id=variant_id,
                enabled=False,
                safe=True,
                advisory_origin=True,
                payload_overrides=sanitized,
                blocked_fields=[],
                render_job_created=False,
                warnings=["limit_reached"],
                explanation=[f"Skipped: execution limit {limit} reached"],
            )
            executions.append(exec_obj)
            blocked_ids.append(plan_id)
            logger.info("ai_multivariant_execution_skipped plan_id=%s limit=%d", plan_id, limit)
            continue

        # Safe plan within limit — create bounded render job descriptor
        payload_copy = _make_payload_copy(payload, sanitized)
        render_job_created = payload_copy is not None

        exec_obj = AIMultiVariantExecution(
            execution_id=exec_id,
            plan_id=plan_id,
            variant_id=variant_id,
            enabled=True,
            safe=True,
            advisory_origin=True,
            payload_overrides=sanitized,
            blocked_fields=[],
            render_job_created=render_job_created,
            warnings=[],
            explanation=[
                f"Executed: safe plan {plan_id}",
                f"Overrides applied: {list(sanitized.keys())}",
            ],
        )
        executions.append(exec_obj)
        executed_ids.append(plan_id)
        executed_count += 1

        logger.info(
            "ai_multivariant_execution_created plan_id=%s variant_id=%s "
            "render_job_created=%s overrides=%s",
            plan_id, variant_id, render_job_created, list(sanitized.keys()),
        )

    return executions, executed_ids, blocked_ids


def _make_payload_copy(payload: Any, safe_overrides: dict) -> Optional[dict]:
    """Create a shallow copy of the payload dict with safe overrides applied. Never raises."""
    try:
        if payload is None:
            # No payload — return just the overrides as the job descriptor
            return dict(safe_overrides)

        if isinstance(payload, dict):
            result = dict(payload)
        elif hasattr(payload, "__dict__"):
            result = dict(vars(payload))
        else:
            result = {}

        # Apply only sanitized safe overrides — never forbidden fields
        for k, v in safe_overrides.items():
            result[k] = v

        return result
    except Exception:
        return None


def _disabled_set(plans: list[dict]) -> AIMultiVariantExecutionSet:
    """Return a disabled execution set with all plans listed as blocked (not executed)."""
    blocked_ids = [str(p.get("plan_id") or "") for p in plans if isinstance(p, dict)]
    executions = [
        AIMultiVariantExecution(
            execution_id=f"mvexec_{p.get('plan_id', '')}",
            plan_id=str(p.get("plan_id") or ""),
            variant_id=str(p.get("variant_id") or ""),
            enabled=False,
            safe=bool(p.get("safe_to_enqueue", False)),
            advisory_origin=True,
            payload_overrides=sanitize_execution_overrides(
                p.get("planned_payload_overrides") or {}
            ),
            blocked_fields=[],
            render_job_created=False,
            warnings=["execution_disabled"],
            explanation=["Execution disabled: ai_multivariant_execution_enabled=False"],
        )
        for p in plans
        if isinstance(p, dict)
    ]
    logger.info("ai_multivariant_execution_skipped execution_disabled=True plans=%d", len(plans))
    return AIMultiVariantExecutionSet(
        available=True,
        execution_enabled=False,
        executions=executions[:_MAX_EXECUTION_JOBS],
        executed_plan_ids=[],
        blocked_plan_ids=blocked_ids,
        warnings=["execution_disabled"],
    )


def _fallback_set(reason: str) -> AIMultiVariantExecutionSet:
    return AIMultiVariantExecutionSet(
        available=False,
        execution_enabled=False,
        executions=[],
        executed_plan_ids=[],
        blocked_plan_ids=[],
        warnings=[f"multivariant_execution_error:{reason}"],
    )
