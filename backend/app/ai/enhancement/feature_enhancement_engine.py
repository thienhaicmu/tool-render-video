"""
feature_enhancement_engine.py — AI-assisted existing feature enhancement engine. Phase 38.

Integrates all Phase 1–37 AI systems as enhancement layers for current tool capabilities.

Assistive-only: AI improves subtitle/camera/timing/clip/style/variant/ranking quality.
Never raises. Never executes renders. Never mutates FFmpeg or payload in-place.
No external API calls. No GPU. No internet.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.enhancement.feature_enhancement_schema import (
    AIFeatureEnhancement,
    AIFeatureEnhancementPack,
)
from app.ai.enhancement.feature_enhancement_safety import (
    is_feature_enhancement_safe,
    sanitize_feature_enhancement,
)

logger = logging.getLogger("app.ai.enhancement.engine")


def build_feature_enhancement_pack(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AIFeatureEnhancementPack:
    """Build a unified AI feature enhancement pack from all available AI metadata.

    Never raises — returns an empty/unavailable pack on any error.
    Never mutates edit_plan or payload in-place.
    Assistive-only: enhances existing features, never replaces render engine authority.
    """
    ctx = context or {}
    job_id = str(ctx.get("job_id", "unknown"))

    try:
        subtitle_enh = _build_subtitle_enhancement(edit_plan)
        camera_enh = _build_camera_enhancement(edit_plan)
        timing_enh = _build_timing_enhancement(edit_plan)
        clip_sel_enh = _build_clip_selection_enhancement(edit_plan)
        creator_style_enh = _build_creator_style_enhancement(edit_plan)
        variant_enh = _build_variant_enhancement(edit_plan)
        output_ranking_enh = _build_output_ranking_enhancement(edit_plan)

        enabled_count = sum(
            1 for enh in (
                subtitle_enh, camera_enh, timing_enh, clip_sel_enh,
                creator_style_enh, variant_enh, output_ranking_enh,
            )
            if enh.get("enabled", False)
        )

        if enabled_count > 0:
            logger.info(
                "ai_feature_enhancement_created job_id=%s enabled_categories=%d",
                job_id, enabled_count,
            )
            logger.info(
                "ai_feature_enhancement_assistive_only job_id=%s mode=assistive_only",
                job_id,
            )
        else:
            logger.debug(
                "ai_feature_enhancement_skipped job_id=%s (no_ai_metadata_available)",
                job_id,
            )

        return AIFeatureEnhancementPack(
            available=True,
            mode="assistive_only",
            subtitle_enhancement=subtitle_enh,
            camera_enhancement=camera_enh,
            timing_enhancement=timing_enh,
            clip_selection_enhancement=clip_sel_enh,
            creator_style_enhancement=creator_style_enh,
            variant_enhancement=variant_enh,
            output_ranking_enhancement=output_ranking_enh,
            warnings=[],
        )

    except Exception as exc:
        logger.debug("ai_feature_enhancement_failed job_id=%s: %s", job_id, exc)
        return AIFeatureEnhancementPack(
            available=False,
            mode="assistive_only",
            warnings=[f"feature_enhancement_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Subtitle enhancement
# ---------------------------------------------------------------------------

def _build_subtitle_enhancement(edit_plan: Any) -> dict:
    """Build subtitle enhancement from subtitle_text_apply and subtitle intelligence."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        sub_apply = getattr(edit_plan, "subtitle_text_apply", None)
        if isinstance(sub_apply, dict) and sub_apply.get("enabled", False):
            enabled = True
            confidence = max(confidence, 0.75)
            density = sub_apply.get("density", "")
            if density:
                improvements.append(f"subtitle_density_optimized:{density}")
            emphasis = sub_apply.get("emphasis", "")
            if emphasis and emphasis != "none":
                improvements.append(f"subtitle_emphasis_applied:{emphasis}")
            explanation.append("AI subtitle text optimization applied")

        sub_exec = getattr(edit_plan, "subtitle_execution", None)
        if isinstance(sub_exec, dict) and sub_exec.get("available", False):
            enabled = True
            confidence = max(confidence, 0.6)
            beat_aware = sub_exec.get("beat_aware", False)
            if beat_aware:
                improvements.append("beat_aware_subtitle_timing")
                explanation.append("Beat-aware subtitle timing active")
            density_mode = sub_exec.get("density_mode", "")
            if density_mode and density_mode != "normal":
                improvements.append(f"dynamic_subtitle_density:{density_mode}")

        creator_style = getattr(edit_plan, "creator_style_adaptation", None)
        if isinstance(creator_style, dict):
            tone = creator_style.get("subtitle_tone", "")
            if tone and tone != "default":
                improvements.append(f"creator_subtitle_tone:{tone}")

        enh = AIFeatureEnhancement(
            feature_name="subtitle",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("subtitle")


# ---------------------------------------------------------------------------
# Camera enhancement
# ---------------------------------------------------------------------------

def _build_camera_enhancement(edit_plan: Any) -> dict:
    """Build camera enhancement from camera_motion_apply and visual rhythm metadata."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        cam_apply = getattr(edit_plan, "camera_motion_apply", None)
        if isinstance(cam_apply, dict) and cam_apply.get("enabled", False):
            enabled = True
            confidence = max(confidence, 0.75)
            behavior = cam_apply.get("behavior", "")
            if behavior and behavior != "none":
                improvements.append(f"camera_behavior_guided:{behavior}")
                explanation.append("AI camera motion guidance applied")
            strategy = cam_apply.get("strategy", "")
            if strategy:
                improvements.append(f"camera_strategy:{strategy}")

        beat_visual = getattr(edit_plan, "beat_visual_execution", None)
        if isinstance(beat_visual, dict) and beat_visual.get("available", False):
            enabled = True
            confidence = max(confidence, 0.55)
            rhythm = beat_visual.get("visual_rhythm_mode", "")
            if rhythm and rhythm != "none":
                improvements.append(f"visual_rhythm_mode:{rhythm}")
                explanation.append("Beat-synced visual rhythm applied")

        cam_plan = getattr(edit_plan, "camera", None)
        if cam_plan is not None:
            subject_lock = getattr(cam_plan, "behavior", "")
            if subject_lock in ("subject_lock", "face_lock"):
                improvements.append("subject_lock_preference_active")
            motion_energy = getattr(cam_plan, "motion_energy", None)
            if motion_energy is not None and motion_energy > 0.6:
                improvements.append("motion_smoothing_guidance_active")

        enh = AIFeatureEnhancement(
            feature_name="camera",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("camera")


# ---------------------------------------------------------------------------
# Timing enhancement
# ---------------------------------------------------------------------------

def _build_timing_enhancement(edit_plan: Any) -> dict:
    """Build timing enhancement from timing_apply and pacing intelligence."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        timing_apply = getattr(edit_plan, "timing_apply", None)
        if isinstance(timing_apply, dict) and timing_apply.get("enabled", False):
            enabled = True
            confidence = max(confidence, 0.75)
            explanation.append("AI timing optimization applied")
            adjustments = timing_apply.get("adjustments") or []
            for adj in adjustments[:3]:
                if isinstance(adj, dict):
                    adj_type = adj.get("type", "")
                    if adj_type:
                        improvements.append(f"timing_adjustment:{adj_type}")

        retention = getattr(edit_plan, "retention", None)
        if isinstance(retention, dict):
            risks = retention.get("risk_regions") or []
            silence_gaps = [r for r in risks if isinstance(r, dict) and r.get("category") == "silence_gap"]
            dead_air = [r for r in risks if isinstance(r, dict) and r.get("category") == "dead_air"]
            if silence_gaps:
                enabled = True
                confidence = max(confidence, 0.6)
                improvements.append(f"silence_gap_reduction_guidance:{len(silence_gaps)}_regions")
            if dead_air:
                enabled = True
                confidence = max(confidence, 0.6)
                improvements.append(f"dead_air_reduction_guidance:{len(dead_air)}_regions")

        pacing = getattr(edit_plan, "pacing", None)
        if pacing is not None:
            pacing_style = getattr(pacing, "pacing_style", "default")
            if pacing_style and pacing_style != "default":
                enabled = True
                confidence = max(confidence, 0.5)
                improvements.append(f"pacing_intelligence_applied:{pacing_style}")

        enh = AIFeatureEnhancement(
            feature_name="timing",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("timing")


# ---------------------------------------------------------------------------
# Clip selection enhancement
# ---------------------------------------------------------------------------

def _build_clip_selection_enhancement(edit_plan: Any) -> dict:
    """Build clip selection enhancement from discovery/selection and story/retention."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        css = getattr(edit_plan, "clip_segment_selection", None)
        if isinstance(css, dict) and css.get("enabled", False):
            enabled = True
            confidence = max(confidence, 0.8)
            selected = css.get("selected_segments") or []
            improvements.append(f"ai_clip_segments_selected:{len(selected)}")
            explanation.append("AI clip segment selection active")

        ccd = getattr(edit_plan, "clip_candidate_discovery", None)
        if isinstance(ccd, dict) and ccd.get("enabled", False):
            enabled = True
            confidence = max(confidence, 0.7)
            candidates = ccd.get("candidates") or []
            improvements.append(f"ai_clip_candidates_discovered:{len(candidates)}")
            recommended = ccd.get("recommended_candidate_id")
            if recommended:
                improvements.append(f"best_candidate_recommended:{recommended}")

        story = getattr(edit_plan, "story", None)
        if isinstance(story, dict) and story.get("available", False):
            enabled = True
            confidence = max(confidence, 0.55)
            score = story.get("overall_story_score", 0)
            if score:
                improvements.append(f"story_intelligence_score:{score}")

        retention = getattr(edit_plan, "retention", None)
        if isinstance(retention, dict) and retention.get("available", False):
            enabled = True
            confidence = max(confidence, 0.6)
            ret_score = retention.get("overall_retention_score", 0)
            if ret_score:
                improvements.append(f"retention_score_guidance:{ret_score}")

        enh = AIFeatureEnhancement(
            feature_name="clip_selection",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("clip_selection")


# ---------------------------------------------------------------------------
# Creator style enhancement
# ---------------------------------------------------------------------------

def _build_creator_style_enhancement(edit_plan: Any) -> dict:
    """Build creator style enhancement from style intelligence and market/exec recommendations."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        adaptation = getattr(edit_plan, "creator_style_adaptation", None)
        if isinstance(adaptation, dict) and adaptation.get("available", False):
            enabled = True
            confidence = max(confidence, float(adaptation.get("confidence", 0.0)))
            style = adaptation.get("dominant_style", "")
            if style and style != "unknown":
                improvements.append(f"creator_style_adapted:{style}")
                explanation.append(f"Creator style adaptation active: {style}")

        creator_style = getattr(edit_plan, "creator_style", None)
        if isinstance(creator_style, dict) and creator_style.get("available", False):
            enabled = True
            confidence = max(confidence, 0.5)
            market = creator_style.get("market", "")
            if market:
                improvements.append(f"market_intelligence_applied:{market}")

        exec_recs = getattr(edit_plan, "execution_recommendations", None)
        if isinstance(exec_recs, dict) and exec_recs.get("available", False):
            enabled = True
            confidence = max(confidence, 0.55)
            recs = exec_recs.get("recommendations") or []
            if recs:
                improvements.append(f"execution_recommendations_integrated:{len(recs)}")

        enh = AIFeatureEnhancement(
            feature_name="creator_style",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("creator_style")


# ---------------------------------------------------------------------------
# Variant enhancement
# ---------------------------------------------------------------------------

def _build_variant_enhancement(edit_plan: Any) -> dict:
    """Build variant enhancement from variant selection and execution simulation."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        variant_sel = getattr(edit_plan, "variant_selection", None)
        if isinstance(variant_sel, dict) and variant_sel.get("available", False):
            enabled = True
            confidence = max(confidence, 0.7)
            best = variant_sel.get("best_variant_id", "")
            if best:
                improvements.append(f"best_variant_selected:{best}")
                explanation.append("AI best variant selection active")

        exec_sim = getattr(edit_plan, "execution_simulation", None)
        if isinstance(exec_sim, dict) and exec_sim.get("available", False):
            enabled = True
            confidence = max(confidence, 0.6)
            sim_count = len(exec_sim.get("simulations") or [])
            if sim_count:
                improvements.append(f"execution_simulation_scenarios:{sim_count}")

        batch_planning = getattr(edit_plan, "clip_batch_planning", None)
        if isinstance(batch_planning, dict) and batch_planning.get("enabled", False):
            enabled = True
            confidence = max(confidence, 0.65)
            plans = batch_planning.get("plans") or []
            improvements.append(f"batch_render_plans_available:{len(plans)}")
            explanation.append("Multi-clip batch plans prepared")

        enh = AIFeatureEnhancement(
            feature_name="variant",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("variant")


# ---------------------------------------------------------------------------
# Output ranking enhancement
# ---------------------------------------------------------------------------

def _build_output_ranking_enhancement(edit_plan: Any) -> dict:
    """Build output ranking enhancement from output ranking and best export metadata."""
    try:
        improvements: list[str] = []
        explanation: list[str] = []
        confidence = 0.0
        enabled = False

        output_ranking = getattr(edit_plan, "output_ranking", None)
        if isinstance(output_ranking, dict) and output_ranking.get("available", False):
            enabled = True
            confidence = max(confidence, 0.7)
            best = output_ranking.get("best_output_id", "")
            if best:
                improvements.append(f"best_export_recommended:{best}")
                explanation.append("AI best export recommendation active")
            outputs = output_ranking.get("outputs") or []
            if outputs:
                improvements.append(f"output_ranking_available:{len(outputs)}_variants")

        retention = getattr(edit_plan, "retention", None)
        if isinstance(retention, dict) and retention.get("available", False):
            score = int(retention.get("overall_retention_score", 0))
            if score:
                enabled = True
                confidence = max(confidence, 0.5)
                improvements.append(f"retention_scoring_applied:{score}")

        story = getattr(edit_plan, "story", None)
        if isinstance(story, dict) and story.get("available", False):
            score = story.get("overall_story_score", 0)
            if score:
                enabled = True
                confidence = max(confidence, 0.45)
                improvements.append(f"story_scoring_applied:{score}")

        enh = AIFeatureEnhancement(
            feature_name="output_ranking",
            enabled=enabled,
            enhancement_level="safe" if confidence < 0.7 else "enhanced",
            confidence=round(min(confidence, 1.0), 4),
            improvements=improvements,
            warnings=[],
            explanation=explanation,
        )
        return sanitize_feature_enhancement(enh.to_dict())
    except Exception:
        return _empty_enhancement("output_ranking")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _empty_enhancement(feature_name: str) -> dict:
    return {
        "feature_name": feature_name,
        "enabled": False,
        "enhancement_level": "safe",
        "confidence": 0.0,
        "improvements": [],
        "warnings": [],
        "explanation": [],
    }
