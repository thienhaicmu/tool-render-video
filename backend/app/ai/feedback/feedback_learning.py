"""
feedback_learning.py — Creator feedback loop learning engine. Phase 43.

Public API:
    build_feedback_learning_pack(edit_plan, payload=None, context=None)
        -> AIFeedbackLearningPack

Rules:
- Deterministic only
- Never raises
- Assistive-only (influences metadata, never overrides user settings)
- No payload mutation in-place
- No render execution
- No autonomous override
- No internet, no cloud AI, no model fine-tuning
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from app.ai.feedback.feedback_schema import (
    AICreatorFeedbackSignal,
    AIFeedbackLearningPack,
)
from app.ai.feedback.feedback_memory import (
    load_feedback_memory,
    record_feedback_signal,
)
from app.ai.feedback.feedback_safety import sanitize_feedback

logger = logging.getLogger("app.ai.feedback.learning")

# Influence bounds
_MAX_WEIGHT = 0.30
_MIN_WEIGHT = 0.0

# Minimum signal count before biases are considered reliable
_MIN_RELIABLE_COUNT = 3


def build_feedback_learning_pack(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AIFeedbackLearningPack:
    """Build feedback learning pack from edit plan signals and stored feedback.

    Reads feedback memory, records new signals, builds learned patterns and
    ranking biases. Never raises.

    Args:
        edit_plan:  AIEditPlan with all Phase 1–42 metadata attached.
        payload:    Optional render request (read-only). Never mutated.
        context:    Optional dict with session feedback signals.

    Returns:
        AIFeedbackLearningPack with feedback_signals, learned_feedback_patterns,
        ranking_biases, and warnings.
    """
    try:
        return _build_pack(edit_plan, payload, context)
    except Exception as exc:
        logger.debug("feedback_learning_build_error: %s", exc)
        return AIFeedbackLearningPack(
            available=False,
            enabled=False,
            feedback_mode="assistive_only",
            warnings=[f"feedback_learning_error:{type(exc).__name__}"],
        )


def _build_pack(
    edit_plan: Any,
    payload: Optional[Any],
    context: Optional[dict],
) -> AIFeedbackLearningPack:
    ctx = context or {}
    warnings: list[str] = []

    # Extract feedback signals from context and edit_plan
    signal = _extract_feedback_signal(edit_plan, payload, ctx)

    # Record into local memory (always, so we accumulate history)
    memory = record_feedback_signal(signal)

    # Build learned patterns from accumulated memory
    learned_patterns = _build_learned_patterns(memory)

    # Build ranking biases (bounded, assistive-only)
    ranking_biases = _build_ranking_biases(memory, edit_plan)

    enabled = (
        memory.get("total_signals", 0) > 0
        or bool(signal.exported)
        or bool(signal.selected)
    )

    pack = AIFeedbackLearningPack(
        available=True,
        enabled=enabled,
        feedback_mode="assistive_only",
        feedback_signals=[sanitize_feedback(signal.to_dict())],
        learned_feedback_patterns=learned_patterns,
        ranking_biases=ranking_biases,
        warnings=warnings,
    )

    if enabled:
        logger.info(
            "ai_feedback_learning_applied total_signals=%d exports=%d ignores=%d",
            memory.get("total_signals", 0),
            memory.get("total_exports", 0),
            memory.get("total_ignores", 0),
        )
    else:
        logger.debug("ai_feedback_learning_skipped no_signals_yet")

    return pack


def _extract_feedback_signal(
    edit_plan: Any,
    payload: Optional[Any],
    context: dict,
) -> AICreatorFeedbackSignal:
    """Extract a feedback signal from session context, edit plan, and payload. Never raises."""
    signal = AICreatorFeedbackSignal(
        feedback_id=str(context.get("feedback_id") or uuid.uuid4())[:36],
    )

    try:
        # Explicit session feedback (highest priority)
        signal.exported = bool(context.get("exported", False))
        signal.selected = bool(context.get("selected", False))
        signal.ignored = bool(context.get("ignored", False))

        rank_raw = context.get("selected_output_rank", 0)
        try:
            signal.selected_output_rank = max(0, int(rank_raw))
        except Exception:
            signal.selected_output_rank = 0

        for attr in ("creator_style", "subtitle_style", "pacing_style", "camera_style", "duration_bucket", "selected_variant"):
            val = context.get(attr, "")
            if val:
                setattr(signal, attr, str(val))

        # Infer from edit_plan if not set by context
        if edit_plan is not None:
            _infer_signal_from_plan(signal, edit_plan)

        # Infer from payload (read-only)
        if payload is not None:
            _infer_signal_from_payload(signal, payload)

        signal.confidence = _compute_signal_confidence(signal)

    except Exception as exc:
        signal.warnings.append(f"signal_extraction_error:{type(exc).__name__}")
        logger.debug("feedback_signal_extract_error: %s", exc)

    return signal


def _infer_signal_from_plan(signal: AICreatorFeedbackSignal, edit_plan: Any) -> None:
    """Infer feedback fields from edit plan metadata. Read-only. Never raises."""
    try:
        if not signal.creator_style:
            csa = getattr(edit_plan, "creator_style_adaptation", None) or {}
            if isinstance(csa, dict):
                style = csa.get("adapted_style") or csa.get("creator_style") or ""
                if style:
                    signal.creator_style = str(style)

        if not signal.creator_style:
            cs = getattr(edit_plan, "creator_style", None) or {}
            if isinstance(cs, dict):
                style = cs.get("detected_style") or ""
                if style:
                    signal.creator_style = str(style)

        if not signal.subtitle_style:
            sta = getattr(edit_plan, "subtitle_text_apply", None) or {}
            if isinstance(sta, dict):
                style = sta.get("subtitle_style") or sta.get("applied_style") or ""
                if style:
                    signal.subtitle_style = str(style)

        if not signal.pacing_style:
            pacing = getattr(edit_plan, "pacing", None)
            if pacing is not None:
                style = str(getattr(pacing, "pacing_style", "") or "")
                if style and style != "default":
                    signal.pacing_style = style

        if not signal.camera_style:
            cma = getattr(edit_plan, "camera_motion_apply", None) or {}
            if isinstance(cma, dict):
                behavior = cma.get("camera_behavior") or cma.get("applied_behavior") or ""
                if behavior:
                    signal.camera_style = str(behavior)

        if not signal.duration_bucket:
            segments = getattr(edit_plan, "selected_segments", None) or []
            if segments:
                total = sum(
                    float(getattr(s, "end", 0) or 0) - float(getattr(s, "start", 0) or 0)
                    for s in segments
                )
                if total > 0:
                    signal.duration_bucket = _classify_duration(total)

        if not signal.selected_variant:
            vs = getattr(edit_plan, "variant_selection", None) or {}
            if isinstance(vs, dict):
                vid = vs.get("selected_variant_id") or ""
                if vid:
                    signal.selected_variant = str(vid)

        # Infer output rank from output_ranking if present
        if signal.selected_output_rank == 0:
            orr = getattr(edit_plan, "output_ranking", None) or {}
            if isinstance(orr, dict) and orr.get("available"):
                best_id = orr.get("best_output_id")
                if best_id:
                    # Rank 1 means top output was selected
                    signal.selected_output_rank = 1

    except Exception as exc:
        logger.debug("feedback_infer_plan_error: %s", exc)


def _infer_signal_from_payload(signal: AICreatorFeedbackSignal, payload: Any) -> None:
    """Infer feedback fields from render payload (read-only). Never raises."""
    try:
        if not signal.creator_style:
            mode = str(getattr(payload, "ai_mode", "") or "")
            if mode:
                signal.creator_style = mode
    except Exception as exc:
        logger.debug("feedback_infer_payload_error: %s", exc)


def _compute_signal_confidence(signal: AICreatorFeedbackSignal) -> float:
    """Compute signal confidence from its richness. Never raises."""
    try:
        score = 0.0
        if signal.exported:
            score += 0.40
        if signal.selected:
            score += 0.20
        if signal.creator_style:
            score += 0.10
        if signal.subtitle_style:
            score += 0.08
        if signal.pacing_style:
            score += 0.08
        if signal.camera_style:
            score += 0.08
        if signal.duration_bucket:
            score += 0.06
        return round(min(1.0, score), 4)
    except Exception:
        return 0.0


def _classify_duration(total_sec: float) -> str:
    if total_sec < 30:
        return "short_form"
    if total_sec < 90:
        return "mid_form"
    return "long_form"


def _build_learned_patterns(memory: dict) -> dict:
    """Derive learned feedback patterns from memory. Never raises."""
    try:
        pattern_counts = memory.get("pattern_counts", {}) or {}
        total = max(1, int(memory.get("total_signals", 1)))

        def _top(category: str) -> str:
            cat = pattern_counts.get(category, {})
            if not isinstance(cat, dict) or not cat:
                return ""
            return max(cat, key=lambda k: cat[k])

        def _top_count(category: str) -> int:
            cat = pattern_counts.get(category, {})
            if not isinstance(cat, dict) or not cat:
                return 0
            return max(cat.values())

        exported_ranks = list(pattern_counts.get("exported_ranks", []))
        ignored_ranks = list(pattern_counts.get("ignored_ranks", []))

        avg_export_rank = (
            round(sum(exported_ranks) / len(exported_ranks), 2)
            if exported_ranks else 0.0
        )

        return {
            "dominant_creator_style": _top("creator_style"),
            "dominant_subtitle_style": _top("subtitle_style"),
            "dominant_pacing_style": _top("pacing_style"),
            "dominant_camera_style": _top("camera_style"),
            "dominant_duration_bucket": _top("duration_bucket"),
            "creator_style_count": _top_count("creator_style"),
            "subtitle_style_count": _top_count("subtitle_style"),
            "pacing_style_count": _top_count("pacing_style"),
            "camera_style_count": _top_count("camera_style"),
            "total_signals": int(memory.get("total_signals", 0)),
            "total_exports": int(memory.get("total_exports", 0)),
            "total_ignores": int(memory.get("total_ignores", 0)),
            "avg_export_rank": avg_export_rank,
            "ignored_rank_count": len(ignored_ranks),
        }
    except Exception as exc:
        logger.debug("feedback_learned_patterns_error: %s", exc)
        return {}


def _build_ranking_biases(memory: dict, edit_plan: Any) -> dict:
    """Build bounded ranking bias signals from feedback history. Assistive-only. Never raises.

    All bias values are metadata-only [0.0, 0.30].
    No FFmpeg, no playback_speed, no subtitle timing, no executor override.
    """
    try:
        pattern_counts = memory.get("pattern_counts", {}) or {}
        total_exports = max(0, int(memory.get("total_exports", 0)))
        total_ignores = max(0, int(memory.get("total_ignores", 0)))
        total_signals = max(0, int(memory.get("total_signals", 0)))

        biases: dict = {
            "output_ranking_bias": 0.0,
            "variant_ranking_bias": 0.0,
            "retrieval_weighting_bias": 0.0,
            "subtitle_weighting_bias": 0.0,
            "pacing_weighting_bias": 0.0,
            "camera_weighting_bias": 0.0,
            "assistive_only": True,
        }

        # Output ranking bias: repeated top-rank exports increase confidence
        exported_ranks = list(pattern_counts.get("exported_ranks", []))
        if total_exports >= _MIN_RELIABLE_COUNT and exported_ranks:
            top_rank_exports = sum(1 for r in exported_ranks if r <= 1)
            ratio = top_rank_exports / max(1, len(exported_ranks))
            biases["output_ranking_bias"] = _bound(ratio * 0.20)

        # Lower-rank exports bias ranking engine toward those outputs
        if total_exports >= _MIN_RELIABLE_COUNT and exported_ranks:
            low_rank_exports = sum(1 for r in exported_ranks if r > 1)
            if low_rank_exports > 0:
                biases["variant_ranking_bias"] = _bound(
                    (low_rank_exports / max(1, len(exported_ranks))) * 0.15
                )

        # Ignored outputs reduce future ranking weight
        ignored_ranks = list(pattern_counts.get("ignored_ranks", []))
        if total_ignores >= _MIN_RELIABLE_COUNT and ignored_ranks:
            # Ignored outputs get a small negative signal (we represent as 0 bias)
            biases["output_ranking_bias"] = _bound(
                biases["output_ranking_bias"] - (total_ignores * 0.01)
            )

        # Style-based biases from pattern frequency
        def _style_bias(category: str, scale: float) -> float:
            cat = pattern_counts.get(category, {})
            if not isinstance(cat, dict) or not cat:
                return 0.0
            top_count = max(cat.values()) if cat else 0
            if total_signals < _MIN_RELIABLE_COUNT or top_count < _MIN_RELIABLE_COUNT:
                return 0.0
            return _bound((top_count / max(1, total_signals)) * scale)

        biases["subtitle_weighting_bias"] = _style_bias("subtitle_style", 0.25)
        biases["pacing_weighting_bias"] = _style_bias("pacing_style", 0.25)
        biases["camera_weighting_bias"] = _style_bias("camera_style", 0.25)

        # Retrieval bias from creator style dominance
        biases["retrieval_weighting_bias"] = _style_bias("creator_style", 0.20)

        # Incorporate adaptive intelligence if available (never raises)
        _inject_adaptive_bias(biases, edit_plan)

        return biases

    except Exception as exc:
        logger.debug("feedback_ranking_biases_error: %s", exc)
        return {"assistive_only": True}


def _inject_adaptive_bias(biases: dict, edit_plan: Any) -> None:
    """Amplify biases slightly when adaptive profile agrees with feedback. Never raises."""
    try:
        aci = getattr(edit_plan, "adaptive_creator_intelligence", None)
        if not isinstance(aci, dict) or not aci.get("enabled"):
            return

        adaptive_influences = aci.get("adaptive_influences", {}) or {}
        if not isinstance(adaptive_influences, dict):
            return

        # If adaptive pacing confidence aligns, slightly amplify pacing bias
        pacing_w = float(adaptive_influences.get("pacing_enhancement_weight", 0.0) or 0)
        if pacing_w > 0:
            biases["pacing_weighting_bias"] = _bound(
                biases.get("pacing_weighting_bias", 0.0) + pacing_w * 0.10
            )

        # Same for subtitle
        sub_w = float(adaptive_influences.get("subtitle_enhancement_weight", 0.0) or 0)
        if sub_w > 0:
            biases["subtitle_weighting_bias"] = _bound(
                biases.get("subtitle_weighting_bias", 0.0) + sub_w * 0.10
            )

    except Exception as exc:
        logger.debug("feedback_adaptive_inject_error: %s", exc)


def _bound(value: float) -> float:
    """Clamp bias weight to [0.0, 0.30]. Never raises."""
    try:
        return round(max(_MIN_WEIGHT, min(_MAX_WEIGHT, float(value))), 4)
    except Exception:
        return 0.0
