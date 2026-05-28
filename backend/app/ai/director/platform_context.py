"""platform_context.py — Platform-aware AI planning helpers (Phases 55A–57).

Extracted from ai_director.py (lines 5602–5868) as part of C-2 decomposition.
All logic is identical — this is a mechanical lift, not a rewrite.

Per AI Safety Contract: callers in ai_director.py wrap every call in try/except
so exceptions here are already contained at the call site. These helpers never
modify render parameters — advisory metadata only.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.director")


# ---------------------------------------------------------------------------
# Phase 55A — Platform Knowledge Foundation helper
# ---------------------------------------------------------------------------

def _attach_platform_context(plan: "Any", request: Any, job_id: str) -> None:
    """Retrieve platform knowledge and attach advisory platform_context to plan.

    Reads platform and creator_type from the request (informational fields),
    calls the platform knowledge retriever, and attaches the result to
    plan.platform_context.

    Foundation only — no influence mutation, no render execution change.
    Advisory only — platform_context is metadata, never alters render parameters.
    """
    from app.ai.knowledge.platform_knowledge_retriever import build_platform_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_context(platform=platform, creator_type=creator_type)
    plan.platform_context = result.get("platform_context", {})
    ctx = plan.platform_context

    logger.debug(
        "ai_platform_context_done job_id=%s available=%s platform=%s creator_type=%s matches=%d confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        len(ctx.get("matches") or []),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55B — Platform Subtitle Intelligence helper
# ---------------------------------------------------------------------------

def _attach_platform_subtitle_context(plan: "Any", request: Any, job_id: str) -> None:
    """Retrieve subtitle-specific platform knowledge and attach to plan.

    Reads platform and creator_type from request, calls the platform subtitle
    retriever, and attaches advisory platform_subtitle_context to the plan.

    Advisory only — no subtitle timing rewrite, no ASS rewrite, no segmentation
    rewrite, no executor override, no autonomous execution.
    """
    from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_subtitle_context(platform=platform, creator_type=creator_type)
    plan.platform_subtitle_context = result.get("platform_subtitle_context", {})
    ctx = plan.platform_subtitle_context

    logger.debug(
        "ai_platform_subtitle_context_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55C — Platform Camera Intelligence helper
# ---------------------------------------------------------------------------

def _attach_platform_camera_context(plan: "Any", request: Any, job_id: str) -> None:
    """Retrieve camera-specific platform knowledge and attach to plan.

    Reads platform and creator_type from request, calls the platform camera
    retriever, and attaches advisory platform_camera_context to the plan.

    Advisory only — no motion_crop rewrite, no tracking config change,
    no FFmpeg mutation, no executor override, no autonomous execution.
    """
    from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_camera_context(platform=platform, creator_type=creator_type)
    plan.platform_camera_context = result.get("platform_camera_context", {})
    ctx = plan.platform_camera_context

    logger.debug(
        "ai_platform_camera_context_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55D — Platform Hook & Retention Intelligence helper
# ---------------------------------------------------------------------------

def _attach_platform_hook_context(plan: "Any", request: Any, job_id: str) -> None:
    """Retrieve hook/retention-specific platform knowledge and attach to plan.

    Reads platform and creator_type from request, calls the platform hook
    retriever, and attaches advisory platform_hook_context to the plan.

    Advisory only — no transcript rewrite, no hook text rewrite, no clip
    boundary change, no render mutation, no executor override, no autonomous
    execution.
    """
    from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_hook_context(platform=platform, creator_type=creator_type)
    plan.platform_hook_context = result.get("platform_hook_context", {})
    ctx = plan.platform_hook_context

    logger.debug(
        "ai_platform_hook_context_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55E — Platform-Aware Render Strategy helper
# ---------------------------------------------------------------------------

def _attach_platform_render_strategy(plan: "Any", job_id: str) -> None:
    """Fuse platform contexts into unified advisory render strategy and attach to plan.

    Reads platform_subtitle_context (55B), platform_camera_context (55C),
    platform_hook_context (55D), platform_context (55A), creator_preference_profile
    (50D), and render_quality_v2 (52D) from the plan and produces one
    deterministic platform_render_strategy.

    Advisory only — strategy enriches orchestrator reasoning, variant evaluation,
    and AI UX explanation. Never executes rendering, never overrides executor
    authority, never mutates render pipeline parameters.
    """
    from app.ai.knowledge.platform_render_strategy_engine import build_platform_render_strategy

    result = build_platform_render_strategy(plan)
    plan.platform_render_strategy = result.get("platform_render_strategy", {})
    strat = plan.platform_render_strategy

    logger.debug(
        "ai_platform_render_strategy_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        strat.get("available", False),
        strat.get("platform", ""),
        strat.get("creator_type", ""),
        float(strat.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 56 — Platform-Aware Strategy Influence helper
# ---------------------------------------------------------------------------

def _attach_platform_strategy_influence(plan: "Any", job_id: str) -> None:
    """Build platform strategy influence context and enrich influence dicts.

    Reads plan.platform_render_strategy (Phase 55E), builds per-domain influence
    support (subtitle, camera, ranking) with bounded confidence deltas, and
    enriches existing influence reasoning (additive only):
      1. plan.creator_subtitle_influence reasoning
      2. plan.creator_camera_preference tuning reasoning
      3. plan.safe_influence_pack reasoning

    Advisory only — confidence_delta is metadata, NEVER fed to safety gate.
    Safety gates are NEVER lowered or bypassed by platform strategy.
    No render mutation, no executor override, no pipeline changes.
    """
    from app.ai.knowledge.platform_strategy_influence_context import (
        build_platform_strategy_influence,
        enrich_subtitle_influence_reasoning,
        enrich_camera_influence_reasoning,
        enrich_ranking_influence_reasoning,
    )

    result = build_platform_strategy_influence(plan)
    plan.platform_strategy_influence = result.get("platform_strategy_influence", {})
    psi = plan.platform_strategy_influence

    if not psi.get("available"):
        logger.debug("ai_platform_strategy_influence_unavailable job_id=%s", job_id)
        return

    # --- Enrich subtitle influence reasoning (additive only) ---
    subtitle_support = psi.get("subtitle") or {}
    if subtitle_support.get("supported") and plan.creator_subtitle_influence:
        plan.creator_subtitle_influence = enrich_subtitle_influence_reasoning(
            plan.creator_subtitle_influence, subtitle_support,
        )

    # --- Enrich camera preference tuning reasoning (additive only) ---
    camera_support = psi.get("camera") or {}
    if camera_support.get("supported") and plan.creator_camera_preference:
        cam_pref = plan.creator_camera_preference
        tuning = cam_pref.get("camera_preference") or {}
        if tuning and isinstance(tuning, dict):
            enriched_tuning = enrich_camera_influence_reasoning(tuning, camera_support)
            plan.creator_camera_preference = {
                **cam_pref,
                "camera_preference": enriched_tuning,
            }

    # --- Enrich ranking influence reasoning (additive only) ---
    ranking_support = psi.get("ranking") or {}
    if ranking_support.get("supported") and plan.safe_influence_pack:
        plan.safe_influence_pack = enrich_ranking_influence_reasoning(
            plan.safe_influence_pack, ranking_support,
        )

    logger.debug(
        "ai_platform_strategy_influence_done job_id=%s available=%s "
        "platform=%s creator_type=%s confidence=%.3f",
        job_id,
        psi.get("available", False),
        psi.get("platform", ""),
        psi.get("creator_type", ""),
        float(psi.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 57 — Platform-Aware Quality Feedback Loop helper
# ---------------------------------------------------------------------------

def _attach_platform_quality_feedback(plan: "Any", job_id: str) -> None:
    """Evaluate platform quality feedback and attach to plan.

    Reads platform_render_strategy (55E), platform_strategy_influence (56),
    subtitle_quality_v2 (52A), camera_quality_v2 (52B), hook_quality_v2 (52C),
    render_quality_v2 (52D), and platform context metadata (55B–55D) to
    evaluate how well the render output aligns with the target platform strategy.

    Quality feedback only — no render mutation, no rerender, no executor override.
    Advisory only — platform_quality_feedback is metadata, never alters render.
    """
    from app.ai.knowledge.platform_quality_feedback_evaluator import (
        evaluate_platform_quality_feedback,
    )

    result = evaluate_platform_quality_feedback(plan)
    plan.platform_quality_feedback = result.get("platform_quality_feedback", {})
    fb = plan.platform_quality_feedback

    logger.debug(
        "ai_platform_quality_feedback_done job_id=%s available=%s "
        "platform=%s creator_type=%s overall=%d confidence=%.3f",
        job_id,
        fb.get("available", False),
        fb.get("platform", ""),
        fb.get("creator_type", ""),
        int(fb.get("overall") or 0),
        float(fb.get("confidence") or 0.0),
    )
