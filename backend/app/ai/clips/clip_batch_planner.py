"""
clip_batch_planner.py — AI multi-clip batch plan builder. Phase 37.

Converts Phase 36 selected clip segments into safe batch render plans.
Planning-only: never executes renders, never enqueues jobs, never mutates FFmpeg.
No external API calls. No GPU. No internet. Never raises.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.clips.clip_batch_schema import AIClipBatchPlan, AIClipBatchPlanSet
from app.ai.clips.clip_batch_safety import (
    is_batch_plan_safe,
    sanitize_batch_plan,
    sanitize_batch_payload_overrides,
)

logger = logging.getLogger("app.ai.clips.clip_batch_planner")

_DEFAULT_BATCH_LIMIT = 5


def build_clip_batch_plans(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AIClipBatchPlanSet:
    """Convert selected clip segments into safe batch render plans.

    Never raises — returns a disabled/empty plan set on any error.
    Never executes renders, never enqueues jobs, never mutates payload in-place.
    """
    ctx = context or {}
    job_id = str(ctx.get("job_id", "unknown"))

    try:
        enabled = bool(getattr(payload, "ai_clip_batch_planning_enabled", False))
        batch_limit = int(getattr(payload, "ai_clip_batch_limit", _DEFAULT_BATCH_LIMIT))
        batch_limit = max(1, min(20, batch_limit))

        if not enabled:
            logger.debug("ai_clip_batch_planning_skipped job_id=%s (disabled)", job_id)
            return AIClipBatchPlanSet(
                available=True,
                enabled=False,
                mode="planning_only",
                plans=[],
                recommended_plan_ids=[],
                warnings=[],
            )

        selected_segments = _get_selected_segments(edit_plan)
        policy_mode = _get_policy_mode(edit_plan)
        creator_style = _get_creator_style(edit_plan)

        if not selected_segments:
            logger.debug(
                "ai_clip_batch_planning_skipped job_id=%s (no_selected_segments)", job_id
            )
            return AIClipBatchPlanSet(
                available=True,
                enabled=True,
                mode="planning_only",
                plans=[],
                recommended_plan_ids=[],
                warnings=["no_selected_segments_available"],
            )

        plans: list[AIClipBatchPlan] = []
        for idx, seg in enumerate(selected_segments[:batch_limit]):
            plan = _build_single_plan(
                seg=seg,
                idx=idx,
                edit_plan=edit_plan,
                policy_mode=policy_mode,
                creator_style=creator_style,
            )
            plans.append(plan)

        recommended_plan_ids = [
            p.batch_plan_id for p in plans if p.safe
        ][:3]

        if plans:
            logger.info(
                "ai_clip_batch_planning_enabled job_id=%s plans=%d recommended=%d",
                job_id, len(plans), len(recommended_plan_ids),
            )
            for p in plans:
                logger.info(
                    "ai_clip_batch_plan_created job_id=%s batch_plan_id=%s "
                    "strategy=%s score=%.2f safe=%s",
                    job_id, p.batch_plan_id, p.render_strategy, p.score, p.safe,
                )
            if recommended_plan_ids:
                logger.info(
                    "ai_clip_batch_plan_recommended job_id=%s ids=%s",
                    job_id, ",".join(recommended_plan_ids),
                )

        return AIClipBatchPlanSet(
            available=True,
            enabled=True,
            mode="planning_only",
            plans=plans,
            recommended_plan_ids=recommended_plan_ids,
            warnings=[],
        )

    except Exception as exc:
        logger.debug("ai_clip_batch_planning_failed job_id=%s: %s", job_id, exc)
        return AIClipBatchPlanSet(
            available=False,
            enabled=False,
            mode="planning_only",
            plans=[],
            recommended_plan_ids=[],
            warnings=[f"batch_planning_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_selected_segments(edit_plan: Any) -> list[dict]:
    """Return selected segment dicts from Phase 36, fallback to raw selected_segments."""
    try:
        css = getattr(edit_plan, "clip_segment_selection", None)
        if isinstance(css, dict):
            segs = css.get("selected_segments")
            if isinstance(segs, list) and segs:
                return [s for s in segs if isinstance(s, dict)]

        raw_segs = getattr(edit_plan, "selected_segments", None)
        if isinstance(raw_segs, list) and raw_segs:
            result = []
            for i, s in enumerate(raw_segs):
                if hasattr(s, "__dict__") or hasattr(s, "start"):
                    result.append({
                        "segment_id": f"fallback_{i + 1:02d}",
                        "candidate_id": "",
                        "label": f"Segment {i + 1}",
                        "start_sec": float(getattr(s, "start", 0.0)),
                        "end_sec": float(getattr(s, "end", 0.0)),
                        "duration_sec": max(0.0, float(getattr(s, "end", 0.0)) - float(getattr(s, "start", 0.0))),
                        "score": float(getattr(s, "score", 50.0)),
                        "source_scores": {},
                        "warnings": [],
                    })
                elif isinstance(s, dict):
                    result.append(s)
            return result
    except Exception:
        pass
    return []


def _get_policy_mode(edit_plan: Any) -> str:
    """Return effective policy mode from Phase 31 metadata."""
    try:
        policy = getattr(edit_plan, "ai_apply_policy", None)
        if isinstance(policy, dict):
            return str(policy.get("effective_policy", "conservative"))
    except Exception:
        pass
    return "conservative"


def _get_creator_style(edit_plan: Any) -> str:
    """Return dominant creator style from Phase 14/23 metadata."""
    try:
        adaptation = getattr(edit_plan, "creator_style_adaptation", None)
        if isinstance(adaptation, dict):
            style = adaptation.get("dominant_style", "")
            if style and style != "unknown":
                return str(style)
        style_data = getattr(edit_plan, "creator_style", None)
        if isinstance(style_data, dict):
            style = style_data.get("dominant_style", "")
            if style and style != "unknown":
                return str(style)
    except Exception:
        pass
    return ""


def _assign_render_strategy(seg: dict, edit_plan: Any) -> str:
    """Deterministically assign a render strategy from segment metadata."""
    try:
        source_scores = seg.get("source_scores") or {}
        warnings = seg.get("warnings") or []

        retention = float(source_scores.get("retention", 50.0))
        hook = float(source_scores.get("hook", 50.0))
        story = float(source_scores.get("story", 50.0))

        if "subtitle_overload" in warnings:
            return "subtitle_clarity"

        adaptation = getattr(edit_plan, "creator_style_adaptation", None)
        if isinstance(adaptation, dict):
            confidence = float(adaptation.get("confidence", 0.0))
            if confidence > 0.75:
                return "creator_style_focused"

        camera_apply = getattr(edit_plan, "camera_motion_apply", None)
        if isinstance(camera_apply, dict):
            cam_enabled = camera_apply.get("enabled", False)
            if cam_enabled:
                cam_strategy = str(camera_apply.get("strategy", ""))
                if "dynamic" in cam_strategy or "motion" in cam_strategy:
                    return "camera_dynamic_safe"

        if retention > 70.0 or hook > 70.0 or story > 70.0:
            return "retention_focused"

    except Exception:
        pass
    return "safe_default"


def _assign_variant_strategy(policy_mode: str, edit_plan: Any) -> str:
    """Assign variant strategy based on policy mode and plan metadata."""
    try:
        if policy_mode in ("balanced", "aggressive"):
            variant_sel = getattr(edit_plan, "variant_selection", None)
            if isinstance(variant_sel, dict) and variant_sel.get("available", False):
                return "selected_variant"

            multivariant = getattr(edit_plan, "multivariant_render_plans", None)
            if isinstance(multivariant, dict) and multivariant.get("available", False):
                return "multivariant_limited"

        if policy_mode == "experimental":
            multivariant = getattr(edit_plan, "multivariant_render_plans", None)
            if isinstance(multivariant, dict) and multivariant.get("available", False):
                return "multivariant_limited"
    except Exception:
        pass
    return "single_safe"


def _assign_subtitle_strategy(seg: dict, edit_plan: Any) -> str:
    """Assign subtitle strategy from segment and subtitle metadata."""
    try:
        warnings = seg.get("warnings") or []
        if "subtitle_overload" in warnings:
            return "reduced_density"

        sub_apply = getattr(edit_plan, "subtitle_text_apply", None)
        if isinstance(sub_apply, dict) and sub_apply.get("enabled", False):
            return "optimized"
    except Exception:
        pass
    return "default"


def _assign_camera_strategy(edit_plan: Any) -> str:
    """Assign camera strategy from camera apply metadata."""
    try:
        cam_apply = getattr(edit_plan, "camera_motion_apply", None)
        if isinstance(cam_apply, dict) and cam_apply.get("enabled", False):
            return "motion_guided"
    except Exception:
        pass
    return "default"


def _assign_timing_strategy(edit_plan: Any) -> str:
    """Assign timing strategy from timing apply metadata."""
    try:
        timing_apply = getattr(edit_plan, "timing_apply", None)
        if isinstance(timing_apply, dict) and timing_apply.get("enabled", False):
            return "retention_optimized"
    except Exception:
        pass
    return "default"


def _build_payload_overrides(
    seg: dict,
    render_strategy: str,
    creator_style: str,
    edit_plan: Any,
) -> dict:
    """Build safe planned payload overrides — forbidden keys never included."""
    overrides: dict = {}
    try:
        if creator_style:
            overrides["creator_style"] = creator_style

        sub_apply = getattr(edit_plan, "subtitle_text_apply", None)
        if isinstance(sub_apply, dict) and sub_apply.get("enabled", False):
            density = sub_apply.get("density")
            if density and isinstance(density, str):
                overrides["subtitle_density"] = density
            emphasis = sub_apply.get("emphasis")
            if emphasis and isinstance(emphasis, str):
                overrides["subtitle_emphasis"] = emphasis

        cam_apply = getattr(edit_plan, "camera_motion_apply", None)
        if isinstance(cam_apply, dict) and cam_apply.get("enabled", False):
            behavior = cam_apply.get("behavior")
            if behavior and isinstance(behavior, str):
                overrides["camera_behavior"] = behavior

        pacing_info = getattr(edit_plan, "pacing", None)
        if pacing_info is not None:
            pacing_style = getattr(pacing_info, "pacing_style", None)
            if pacing_style and isinstance(pacing_style, str):
                overrides["pacing_style"] = pacing_style

    except Exception:
        pass
    return sanitize_batch_payload_overrides(overrides)


def _build_single_plan(
    seg: dict,
    idx: int,
    edit_plan: Any,
    policy_mode: str,
    creator_style: str,
) -> AIClipBatchPlan:
    """Build a single AIClipBatchPlan from a selected segment dict."""
    batch_plan_id = f"batch_{idx + 1:02d}"
    segment_id = str(seg.get("segment_id", f"seg_{idx + 1:02d}"))
    candidate_id = str(seg.get("candidate_id", ""))
    label = str(seg.get("label", f"Clip {idx + 1}"))

    start_sec = max(0.0, float(seg.get("start_sec", 0.0)))
    end_sec = max(0.0, float(seg.get("end_sec", 0.0)))
    duration_sec = max(0.0, end_sec - start_sec)
    score = max(0.0, min(100.0, float(seg.get("score", 50.0))))

    render_strategy = _assign_render_strategy(seg, edit_plan)
    variant_strategy = _assign_variant_strategy(policy_mode, edit_plan)
    subtitle_strategy = _assign_subtitle_strategy(seg, edit_plan)
    camera_strategy = _assign_camera_strategy(edit_plan)
    timing_strategy = _assign_timing_strategy(edit_plan)

    overrides = _build_payload_overrides(seg, render_strategy, creator_style, edit_plan)

    explanation: list[str] = [
        f"render_strategy:{render_strategy}",
        f"variant_strategy:{variant_strategy}",
    ]
    warnings_out: list[str] = list(seg.get("warnings") or [])

    raw_plan_dict = {
        "batch_plan_id": batch_plan_id,
        "segment_id": segment_id,
        "candidate_id": candidate_id,
        "label": label,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": duration_sec,
        "rank": idx + 1,
        "score": score,
        "render_strategy": render_strategy,
        "variant_strategy": variant_strategy,
        "planned_payload_overrides": overrides,
        "warnings": warnings_out,
    }
    safe = is_batch_plan_safe(raw_plan_dict)

    return AIClipBatchPlan(
        batch_plan_id=batch_plan_id,
        segment_id=segment_id,
        candidate_id=candidate_id,
        label=label,
        start_sec=start_sec,
        end_sec=end_sec,
        duration_sec=duration_sec,
        rank=idx + 1,
        score=score,
        render_strategy=render_strategy,
        variant_strategy=variant_strategy,
        subtitle_strategy=subtitle_strategy,
        camera_strategy=camera_strategy,
        timing_strategy=timing_strategy,
        creator_style=creator_style,
        safe=safe,
        planned_payload_overrides=overrides,
        warnings=warnings_out,
        explanation=explanation,
    )
