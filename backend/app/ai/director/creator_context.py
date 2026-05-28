"""
creator_context.py — Creator context attachment helpers extracted from ai_director.py.

All functions are module-level, stateless, and follow the AI module safety contract:
never raise, return None on failure, use lazy imports for optional dependencies.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.director")


# ---------------------------------------------------------------------------
# Phase 14 — Creator Style Classification
# ---------------------------------------------------------------------------

def _attach_creator_style(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    job_id: str,
) -> None:
    """Classify creator style and attach result + recommendation to plan. Never raises."""
    try:
        from app.ai.styles.style_classifier import classify_creator_style
        from app.ai.styles.style_recommender import recommend_style_adjustments

        # Build transcript context from chunks
        transcript_ctx = {
            "text": " ".join(c.get("text", "") for c in chunks[:15] if isinstance(c, dict)),
            "chunk_count": len(chunks),
        }

        # Story context from plan.story (may be empty dict if story analysis not run)
        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}

        classification = classify_creator_style(
            transcript_context=transcript_ctx,
            pacing_context=pacing_ctx,
            story_context=story_ctx,
        )

        recommendation = recommend_style_adjustments(
            classification,
            current_context={"mode": plan.mode},
        )

        plan.creator_style = {
            **classification.to_dict(),
            "recommendation": recommendation.to_dict(),
        }

        logger.info(
            "ai_creator_style_classified job_id=%s style=%s confidence=%.1f",
            job_id,
            classification.dominant_style,
            classification.confidence,
        )

        _append_style_explainability(plan, classification)

    except Exception as exc:
        plan.creator_style = {
            "available": False,
            "warnings": [f"creator_style_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_style_failed job_id=%s: %s", job_id, exc)


def _append_style_explainability(plan: "AIEditPlan", classification: Any) -> None:
    """Append compact creator style insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        style = getattr(classification, "dominant_style", "unknown")
        if style == "unknown" or not getattr(classification, "available", False):
            return

        _STYLE_LINES: dict[str, str] = {
            "podcast_viral": "Podcast-style pacing identified",
            "high_energy_reaction": "High-energy reaction editing archetype detected",
            "storytelling_cinematic": "Cinematic storytelling structure recognized",
            "documentary_clean": "Documentary clean style identified",
            "educational_focus": "Educational focus editing style detected",
            "anime_edit": "High-energy anime edit style identified",
            "gameplay_highlight": "Gameplay highlight editing style detected",
            "motivation_short": "Motivation short-form style identified",
            "interview_clip": "Interview clip editing style recognized",
            "calm_minimal": "Calm minimal editing style identified",
        }

        line = _STYLE_LINES.get(style)
        if line and not any(line in str(l) for l in lines):
            lines.append(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 23 — Creator Style Adaptation
# ---------------------------------------------------------------------------

def _attach_creator_style_adaptation(plan: "AIEditPlan", job_id: str) -> None:
    """Detect Phase 23 creator style and build advisory adaptation hints.

    Runs after Phase 14 (creator_style) and Phase 16/20 (retention/story)
    so all prior metadata is available. Result stored in plan.creator_style_adaptation.
    Never raises. Never mutates render payload. Advisory metadata only.
    """
    try:
        from app.ai.styles.style_classifier import detect_creator_styles
        from app.ai.styles.style_adapter import build_style_adaptation

        style_set = detect_creator_styles(edit_plan=plan, context={"job_id": job_id})

        # Build adaptation for primary style
        primary_profile = style_set.styles[0] if style_set.styles else None
        adaptation_result: dict = {}
        if primary_profile is not None:
            adaptation_result = build_style_adaptation(
                primary_profile, edit_plan=plan, context={"job_id": job_id}
            )

        plan.creator_style_adaptation = {
            "detected": style_set.detected,
            "primary_style": style_set.primary_style,
            "confidence": round(float(primary_profile.confidence if primary_profile else 0.0), 4),
            "adaptation": adaptation_result.get("adaptation", {}),
            "fallback_used": style_set.fallback_used,
            "warnings": list(style_set.warnings),
        }

        logger.info(
            "ai_creator_style_detected job_id=%s primary=%s confidence=%.4f fallback=%s styles=%d",
            job_id,
            style_set.primary_style,
            plan.creator_style_adaptation["confidence"],
            style_set.fallback_used,
            len(style_set.styles),
        )

        if style_set.fallback_used:
            logger.info("ai_creator_style_fallback job_id=%s reason=low_confidence_or_unknown", job_id)

        _append_creator_style_adaptation_explainability(plan, style_set, adaptation_result)

    except Exception as exc:
        plan.creator_style_adaptation = {
            "detected": False,
            "primary_style": "safe_generic",
            "confidence": 0.0,
            "adaptation": {},
            "fallback_used": True,
            "warnings": [f"creator_style_adaptation_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_style_adaptation_failed job_id=%s: %s", job_id, exc)


def _append_creator_style_adaptation_explainability(
    plan: "AIEditPlan",
    style_set: Any,
    adaptation_result: dict,
) -> None:
    """Append compact creator-style adaptation lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        primary = style_set.primary_style
        fallback = style_set.fallback_used
        adaptation = adaptation_result.get("adaptation", {})

        if fallback:
            line = "Creator style: safe generic fallback used"
        else:
            _STYLE_LABELS: dict[str, str] = {
                "viral_tiktok": "viral TikTok",
                "cinematic": "cinematic",
                "educational": "educational",
                "podcast": "podcast",
                "product_demo": "product demo",
                "storytelling": "storytelling",
                "commentary": "commentary",
                "interview": "interview",
            }
            label = _STYLE_LABELS.get(primary, primary)
            line = f"Creator style classified as {label}"

        if not any("Creator style" in str(l) for l in lines):
            lines.append(line)

        # Pacing hint line
        pacing_hint = adaptation.get("pacing_hint", "")
        if pacing_hint and pacing_hint not in ("default", ""):
            hint_line = f"{pacing_hint.replace('_', ' ').title()} pacing adaptation suggested"
            if not any("pacing adaptation" in str(l) for l in lines):
                lines.append(hint_line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 39 — Creator Knowledge Registry
# ---------------------------------------------------------------------------

def _attach_creator_knowledge(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Load local creator knowledge registry and attach compact summary.

    Local-first: reads only from the knowledge/ directory on the local filesystem.
    No internet, no scraping, no subprocess, no cloud dependency.
    Never mutates FFmpeg, never overrides executor. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry

        registry = load_knowledge_registry()
        registry_dict = registry.to_dict()
        plan.creator_knowledge = registry_dict

        loaded = registry_dict.get("loaded_count", 0)
        categories = registry_dict.get("categories") or []
        styles = registry_dict.get("creator_styles") or []

        if loaded > 0:
            logger.info(
                "ai_creator_knowledge_loaded job_id=%s count=%d categories=%s",
                job_id, loaded, categories,
            )
            logger.info(
                "ai_creator_knowledge_registry_ready job_id=%s styles=%s",
                job_id, styles,
            )
        else:
            logger.debug(
                "ai_creator_knowledge_skipped job_id=%s (no_knowledge_files_found)", job_id
            )

        _append_creator_knowledge_explainability(plan, registry_dict)

    except Exception as exc:
        plan.creator_knowledge = {
            "available": False,
            "loaded_count": 0,
            "categories": [],
            "creator_styles": [],
            "warnings": [f"creator_knowledge_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_knowledge_failed job_id=%s: %s", job_id, exc)


def _append_creator_knowledge_explainability(
    plan: "AIEditPlan",
    registry_dict: dict,
) -> None:
    """Append compact creator knowledge lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        loaded = registry_dict.get("loaded_count", 0)
        if loaded > 0:
            line = "External creator knowledge registry loaded"
            if not any(line in str(l) for l in lines):
                lines.append(line)
            line = "Local creator intelligence available"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        line = "Knowledge ingestion remains local-first"
        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 40 — Creator Pattern Extraction
# ---------------------------------------------------------------------------

def _attach_creator_patterns(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Extract creator intelligence patterns from knowledge registry.

    Local-only: reads from knowledge/patterns/. No internet, no model training.
    Never mutates FFmpeg, never overrides executor. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.knowledge.pattern_registry import load_pattern_registry

        registry = load_pattern_registry()
        registry_dict = registry.to_dict()
        plan.creator_patterns = registry_dict

        loaded = registry_dict.get("loaded_patterns", 0)
        pattern_types = registry_dict.get("pattern_types") or []
        styles = registry_dict.get("creator_styles") or []

        if loaded > 0:
            logger.info(
                "ai_creator_pattern_loaded job_id=%s count=%d types=%s",
                job_id, loaded, pattern_types,
            )
            logger.info(
                "ai_creator_pattern_registry_ready job_id=%s styles=%s",
                job_id, styles,
            )
        else:
            logger.debug(
                "ai_creator_pattern_skipped job_id=%s (no_patterns_found)", job_id
            )

        _append_creator_patterns_explainability(plan, registry_dict)

    except Exception as exc:
        plan.creator_patterns = {
            "available": False,
            "loaded_patterns": 0,
            "pattern_types": [],
            "creator_styles": [],
            "warnings": [f"creator_patterns_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_patterns_failed job_id=%s: %s", job_id, exc)


def _append_creator_patterns_explainability(
    plan: "AIEditPlan",
    registry_dict: dict,
) -> None:
    """Append compact creator pattern lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        pattern_types = registry_dict.get("pattern_types") or []
        loaded = registry_dict.get("loaded_patterns", 0)

        if loaded > 0:
            if "hook" in pattern_types:
                line = "Creator hook patterns extracted"
                if not any(line in str(l) for l in lines):
                    lines.append(line)
            if "subtitle" in pattern_types:
                line = "Subtitle style patterns available"
                if not any(line in str(l) for l in lines):
                    lines.append(line)
            if "pacing" in pattern_types:
                line = "Creator pacing patterns loaded"
                if not any(line in str(l) for l in lines):
                    lines.append(line)

    except Exception:
        pass


# Phase 41 — Retrieval-Based Creator Intelligence


def _attach_creator_retrieval(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Retrieve creator intelligence patterns from Phase 40 registry.

    Retrieval-only: assistive metadata, no internet, no model training.
    Never mutates FFmpeg, never overrides executor. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence

        logger.debug("ai_creator_retrieval_started job_id=%s", job_id)

        pack = retrieve_creator_intelligence(plan)
        plan.creator_retrieval = pack.to_dict()

        matches = pack.matches or []
        enabled = pack.enabled
        style = pack.recommended_creator_style or ""

        if enabled and matches:
            logger.info(
                "ai_creator_retrieval_completed job_id=%s matches=%d recommended_style=%s",
                job_id, len(matches), style,
            )
            for m in matches[:3]:
                logger.debug(
                    "ai_creator_retrieval_match job_id=%s id=%s type=%s score=%.2f",
                    job_id, m.match_id, m.pattern_type, m.retrieval_score,
                )
        else:
            logger.debug(
                "ai_creator_retrieval_skipped job_id=%s (no_matches)", job_id
            )

        _append_creator_retrieval_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.creator_retrieval = {
            "available": False,
            "enabled": False,
            "retrieval_mode": "assistive_only",
            "matches": [],
            "recommended_creator_style": "",
            "warnings": [f"creator_retrieval_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_retrieval_failed job_id=%s: %s", job_id, exc)


def _append_creator_retrieval_explainability(
    plan: "AIEditPlan",
    retrieval_dict: dict,
) -> None:
    """Append compact creator retrieval lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        enabled = retrieval_dict.get("enabled", False)
        matches = retrieval_dict.get("matches", [])
        style = retrieval_dict.get("recommended_creator_style", "")

        if enabled and matches:
            pacing_matches = [m for m in matches if isinstance(m, dict) and m.get("pattern_type") == "pacing"]
            subtitle_matches = [m for m in matches if isinstance(m, dict) and m.get("pattern_type") == "subtitle"]

            if pacing_matches:
                line = "Creator pacing patterns retrieved"
                if not any(line in str(l) for l in lines):
                    lines.append(line)
            if subtitle_matches:
                line = "Compact subtitle creator patterns applied"
                if not any(line in str(l) for l in lines):
                    lines.append(line)

            line = "Retrieval-based creator intelligence remains assistive-only"
            if not any("assistive-only" in str(l) for l in lines):
                lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 42 — Adaptive creator intelligence
# ---------------------------------------------------------------------------

def _attach_adaptive_creator_intelligence(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build adaptive learning pack from edit plan signals and creator profile.

    Assistive-only: influences metadata ranking only.
    Never mutates FFmpeg, never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack

        logger.debug("ai_adaptive_creator_intelligence_started job_id=%s", job_id)

        context: dict = {}
        raw_profile_id = getattr(request, "ai_adaptive_profile_id", None)
        if raw_profile_id:
            context["profile_id"] = str(raw_profile_id)

        pack = build_adaptive_learning_pack(plan, payload=request, context=context)
        plan.adaptive_creator_intelligence = pack.to_dict()

        if pack.enabled:
            profile_dict = pack.creator_profile or {}
            style = profile_dict.get("creator_style_preference", "")
            subtitle = profile_dict.get("preferred_subtitle_style", "")
            pacing = profile_dict.get("preferred_pacing_style", "")
            camera = profile_dict.get("preferred_camera_style", "")

            logger.info(
                "ai_adaptive_learning_applied job_id=%s style=%s subtitle=%s pacing=%s camera=%s",
                job_id, style, subtitle, pacing, camera,
            )
        else:
            logger.debug("ai_adaptive_learning_skipped job_id=%s (no_signals)", job_id)

        _append_adaptive_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.adaptive_creator_intelligence = {
            "available": False,
            "enabled": False,
            "learning_mode": "assistive_only",
            "creator_profile": {},
            "learned_preferences": {},
            "adaptive_influences": {},
            "warnings": [f"adaptive_creator_intelligence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_adaptive_creator_intelligence_failed job_id=%s: %s", job_id, exc)


def _append_adaptive_explainability(
    plan: "AIEditPlan",
    adaptive_dict: dict,
) -> None:
    """Append compact adaptive intelligence lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        enabled = adaptive_dict.get("enabled", False)
        if not enabled:
            return

        learned = adaptive_dict.get("learned_preferences", {}) or {}
        subtitle_style = learned.get("subtitle_style", "")
        pacing_style = learned.get("pacing_style", "")
        camera_style = learned.get("camera_style", "")

        if subtitle_style:
            line = "Creator subtitle preferences learned"
            if not any("subtitle preferences" in str(l) for l in lines):
                lines.append(line)

        if pacing_style:
            line = "Adaptive creator preferences updated"
            if not any("Adaptive creator preferences" in str(l) for l in lines):
                lines.append(line)

        if camera_style:
            line = "Creator camera preferences learned"
            if not any("camera preferences" in str(l) for l in lines):
                lines.append(line)

        line = "Adaptive creator intelligence remains assistive-only"
        if not any("Adaptive creator intelligence" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 43 — Creator feedback loop intelligence
# ---------------------------------------------------------------------------

def _attach_creator_feedback_intelligence(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build feedback learning pack from creator behavior signals.

    Assistive-only: influences ranking biases only.
    Never mutates FFmpeg, never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack

        logger.debug("ai_creator_feedback_intelligence_started job_id=%s", job_id)

        context: dict = {}
        raw_fb_id = getattr(request, "ai_feedback_id", None)
        if raw_fb_id:
            context["feedback_id"] = str(raw_fb_id)

        for attr in (
            "ai_feedback_exported",
            "ai_feedback_selected",
            "ai_feedback_ignored",
            "ai_feedback_output_rank",
            "ai_feedback_creator_style",
            "ai_feedback_subtitle_style",
            "ai_feedback_pacing_style",
            "ai_feedback_camera_style",
            "ai_feedback_duration_bucket",
        ):
            val = getattr(request, attr, None)
            if val is not None:
                # Strip the "ai_feedback_" prefix to match context keys
                ctx_key = attr[len("ai_feedback_"):]
                if ctx_key == "output_rank":
                    ctx_key = "selected_output_rank"
                if ctx_key == "exported":
                    ctx_key = "exported"
                context[ctx_key] = val

        pack = build_feedback_learning_pack(plan, payload=request, context=context)
        plan.creator_feedback_intelligence = pack.to_dict()

        if pack.enabled:
            patterns = pack.learned_feedback_patterns or {}
            logger.info(
                "ai_feedback_learning_applied job_id=%s total_signals=%d exports=%d ignores=%d",
                job_id,
                patterns.get("total_signals", 0),
                patterns.get("total_exports", 0),
                patterns.get("total_ignores", 0),
            )
        else:
            logger.debug("ai_feedback_learning_skipped job_id=%s", job_id)

        _append_feedback_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.creator_feedback_intelligence = {
            "available": False,
            "enabled": False,
            "feedback_mode": "assistive_only",
            "feedback_signals": [],
            "learned_feedback_patterns": {},
            "ranking_biases": {},
            "warnings": [f"creator_feedback_intelligence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_feedback_intelligence_failed job_id=%s: %s", job_id, exc)


def _append_feedback_explainability(
    plan: "AIEditPlan",
    feedback_dict: dict,
) -> None:
    """Append compact feedback intelligence lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        enabled = feedback_dict.get("enabled", False)
        if not enabled:
            return

        patterns = feedback_dict.get("learned_feedback_patterns", {}) or {}
        biases = feedback_dict.get("ranking_biases", {}) or {}

        total_exports = patterns.get("total_exports", 0)
        if total_exports > 0:
            line = "Ranking biases adapted from export behavior"
            if not any("Ranking biases" in str(l) for l in lines):
                lines.append(line)

        if biases.get("subtitle_weighting_bias", 0) > 0 or biases.get("pacing_weighting_bias", 0) > 0:
            line = "Creator feedback signals applied"
            if not any("Creator feedback signals" in str(l) for l in lines):
                lines.append(line)

        line = "Creator feedback intelligence remains assistive-only"
        if not any("Creator feedback intelligence" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 46 — Creator Preset Evolution
# ---------------------------------------------------------------------------

def _attach_creator_preset_evolution(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build creator preset evolution pack and attach to plan.

    Assistive-only: evolves preset metadata, never mutates render output,
    never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack

        logger.debug("ai_preset_evolution_started job_id=%s", job_id)

        context: dict = {}
        target = getattr(request, "ai_target_market", None) or getattr(request, "ai_mode", None)
        if target:
            context["target_market"] = str(target)

        pack = build_preset_evolution_pack(plan, payload=request, context=context)
        plan.creator_preset_evolution = pack.to_dict()

        if pack.enabled:
            logger.info(
                "ai_preset_evolution_applied job_id=%s best_preset=%s recommended=%d evolved=%d",
                job_id,
                pack.best_preset_id,
                len(pack.recommended_presets),
                len(pack.evolved_presets),
            )
        else:
            logger.debug("ai_preset_evolution_skipped job_id=%s", job_id)

        _append_preset_evolution_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.creator_preset_evolution = {
            "available": False,
            "enabled": False,
            "evolution_mode": "assistive_only",
            "recommended_presets": [],
            "evolved_presets": [],
            "best_preset_id": "",
            "warnings": [f"creator_preset_evolution_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_preset_evolution_failed job_id=%s: %s", job_id, exc)


def _append_preset_evolution_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact preset evolution lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        enabled = pack_dict.get("enabled", False)
        if not enabled:
            return

        line = "Creator preset evolution prepared"
        if not any("Creator preset evolution" in str(l) for l in lines):
            lines.append(line)

        # Best evolved preset
        evolved = pack_dict.get("evolved_presets") or []
        if evolved:
            best_name = evolved[0].get("preset_name", "")
            if best_name:
                line = f"{best_name} recommended"
                if not any(best_name in str(l) for l in lines):
                    lines.append(line)

        line = "Preset evolution remains assistive-only"
        if not any("Preset evolution remains" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 50A — Creator Subtitle Preference Intelligence
# ---------------------------------------------------------------------------

def _attach_creator_subtitle_preference(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Infer deep subtitle preferences from all available AI metadata. Phase 50A.

    Reads Phase 17, 33, 42–48 signal fields from the edit plan and produces
    a rich subtitle preference profile. Inference-only: no render mutation,
    no subtitle engine rewrite, no timing rewrite, no executor override.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_subtitle.subtitle_preference_inference import (
            infer_subtitle_preference,
        )

        logger.debug("ai_subtitle_preference_started job_id=%s", job_id)
        result = infer_subtitle_preference(plan)
        plan.creator_subtitle_preference = result

        conf = (result.get("subtitle_preference") or {}).get("confidence", 0.0)
        style = (result.get("subtitle_preference") or {}).get("style", "unknown")
        logger.info(
            "ai_subtitle_preference_done job_id=%s style=%s confidence=%.2f",
            job_id, style, float(conf),
        )

    except Exception as exc:
        plan.creator_subtitle_preference = {
            "available": False,
            "inference_mode": "metadata_only",
            "subtitle_preference": {
                "style": "unknown", "density": "unknown", "line_count": 2,
                "uppercase": "unknown", "keyword_emphasis": "unknown",
                "motion_style": "unknown", "caption_box": "unknown",
                "readability_priority": "unknown", "mobile_safe": True,
                "confidence": 0.0, "signals": [],
            },
            "warnings": [f"creator_subtitle_preference_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_subtitle_preference_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50B — Creator Camera Preference Intelligence
# ---------------------------------------------------------------------------

def _attach_creator_camera_preference(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Infer creator camera preferences from all available AI metadata. Phase 50B.

    Reads Phase 34, 42–48 signal fields from the edit plan and produces a rich
    camera preference profile plus bounded MotionCropConfig tuning deltas.
    Inference-only metadata: no motion_crop rewrite, no tracking rewrite,
    no FFmpeg mutation, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_camera.camera_preference_inference import infer_camera_preference
        from app.ai.creator_camera.camera_tuning_engine import compute_camera_tuning
        from app.ai.creator_camera.camera_preference_schema import AICameraPreferencePack

        logger.debug("ai_camera_preference_started job_id=%s", job_id)
        camera_pref = infer_camera_preference(plan)
        tuning_pack = compute_camera_tuning(camera_pref)
        pack = AICameraPreferencePack(
            available=True,
            inference_mode="metadata_only",
            camera_preference=camera_pref,
            tuning_pack=tuning_pack,
        )
        plan.creator_camera_preference = pack.to_dict()

        conf = camera_pref.confidence
        style = camera_pref.motion_style
        tier = tuning_pack.confidence_tier
        logger.info(
            "ai_camera_preference_done job_id=%s style=%s confidence=%.2f tier=%s applied=%s",
            job_id, style, float(conf), tier, tuning_pack.applied,
        )

    except Exception as exc:
        plan.creator_camera_preference = {
            "available": False,
            "inference_mode": "metadata_only",
            "camera_preference": {
                "motion_style": "unknown", "crop_aggressiveness": "unknown",
                "stability_priority": "unknown", "deadzone_preference": "unknown",
                "subject_hold": "unknown", "scene_sensitivity": "unknown",
                "center_bias": "unknown", "reframing_risk_tolerance": "unknown",
                "smoothness_priority": "unknown", "confidence": 0.0, "signals": [],
            },
            "tuning_pack": {
                "applied": False, "confidence_tier": "low",
                "deadzone_delta": 0.0, "ema_alpha_delta": 0.0,
                "hold_frames_delta": 0, "scene_threshold_delta": 0.0,
                "smooth_window_delta": 0, "reasoning": [], "warnings": [],
            },
            "warnings": [f"creator_camera_preference_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_camera_preference_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50C — Subtitle Preference Safe Influence
# ---------------------------------------------------------------------------

def _attach_creator_subtitle_influence(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Compute bounded subtitle influence recommendations from Phase 50A preferences. Phase 50C.

    Reads plan.creator_subtitle_preference (produced by Phase 50A) and
    generates six bounded subtitle tuning signals.  No subtitle engine
    rewrite, no ASS generation rewrite, no timing rewrite, no FFmpeg mutation.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_subtitle.subtitle_influence_engine import compute_subtitle_influence

        logger.debug("ai_subtitle_influence_started job_id=%s", job_id)
        pref_pack = getattr(plan, "creator_subtitle_influence", None)
        # Input is the Phase 50A preference pack, not the influence pack field
        subtitle_pref = getattr(plan, "creator_subtitle_preference", None) or {}
        influence = compute_subtitle_influence(subtitle_pref)
        plan.creator_subtitle_influence = influence.to_dict()

        tier  = influence.confidence_tier
        bias  = influence.preset_bias
        avail = influence.available
        logger.info(
            "ai_subtitle_influence_done job_id=%s tier=%s preset_bias=%s available=%s",
            job_id, tier, bias, avail,
        )
        del pref_pack  # unused variable guard

    except Exception as exc:
        plan.creator_subtitle_influence = {
            "available":                False,
            "confidence_tier":          "low",
            "preset_bias":              "unknown",
            "preset_bias_strength":     0.0,
            "density_nudge":            "none",
            "emphasis_delta":           0.0,
            "line_count_bias":          0,
            "motion_style_bias":        "unknown",
            "mobile_readability_nudge": 0.0,
            "reasoning":                [],
            "warnings": [f"creator_subtitle_influence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_subtitle_influence_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50D — Creator Preference Fusion
# ---------------------------------------------------------------------------

def _attach_creator_preference_profile(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Fuse all creator intelligence signals into a unified preference profile. Phase 50D.

    Reads Phase 50A subtitle preference, Phase 50B camera preference, Phase 50C
    influence pack, and Phase 42–47 metadata.  Advisory metadata only — no render
    mutation, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_fusion.fusion_engine import fuse_creator_preferences

        logger.debug("ai_creator_preference_fusion_started job_id=%s", job_id)
        profile = fuse_creator_preferences(plan)
        plan.creator_preference_profile = profile.to_dict()

        sub_style   = profile.subtitle.style
        cam_motion  = profile.camera.motion_style
        conf        = profile.confidence
        n_conflicts = len(profile.conflicts_resolved)
        logger.info(
            "ai_creator_preference_fusion_done job_id=%s"
            " subtitle_style=%s camera_motion=%s confidence=%.2f conflicts=%d",
            job_id, sub_style, cam_motion, float(conf), n_conflicts,
        )

    except Exception as exc:
        plan.creator_preference_profile = {
            "available": False,
            "subtitle":  {"style": "unknown", "density": "unknown",
                          "keyword_emphasis": "unknown", "readability_priority": "unknown"},
            "camera":    {"motion_style": "unknown", "crop_aggressiveness": "unknown",
                          "stability_priority": "unknown", "smoothness_priority": "unknown"},
            "clip":      {"content_style": "unknown", "ranking_preference": "unknown"},
            "market_alignment":  {"target_market": "unknown", "market_fit": "unknown"},
            "quality_alignment": {"readability_priority": "unknown", "smoothness_priority": "unknown"},
            "confidence":         0.0,
            "reasoning":          [],
            "conflicts_resolved": [],
            "warnings": [f"creator_preference_profile_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_preference_profile_failed job_id=%s: %s", job_id, exc)
