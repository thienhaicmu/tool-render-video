"""
execution_simulator.py — Advisory execution simulation builder. Phase 26.

Estimates the expected impact of AI execution recommendations WITHOUT actually
mutating render execution. All output is heuristic metadata only.

Design rules:
- Deterministic only.
- Heuristic-only — no ML, no cloud API, no GPU.
- Never raises.
- Advisory metadata only — no payload mutation, no FFmpeg, no render trigger.
- Reads from: execution_recommendations, retention, story_optimization,
  subtitle_execution, creator_style_adaptation, beat_visual_execution,
  timing_mutation.
- sim_safe_baseline always present.
- advisory_only always True.

Public API:
    simulate_execution_recommendations(edit_plan, context=None) -> AISimulationPack
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.simulation.simulation_schema import (
    AIExecutionSimulation,
    AISimulationPack,
    VALID_SAFETY_LEVELS,
)
from app.ai.simulation.simulation_scoring import score_simulation

logger = logging.getLogger("app.ai.simulation")

_SAFE_BASELINE_ID = "sim_safe_baseline"


def simulate_execution_recommendations(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> AISimulationPack:
    """Build advisory execution simulation pack from edit plan metadata.

    Estimates the likely impact of AI execution recommendations by reading
    all prior-phase AI metadata and applying heuristic gain models.

    Args:
        edit_plan:  AIEditPlan or None. Read-only.
        context:    Optional metadata dict.

    Returns:
        Serialisable AISimulationPack. Never raises.
    """
    try:
        return _build(edit_plan, context or {})
    except Exception as exc:
        logger.debug("simulate_execution_recommendations_failed: %s", exc)
        return _fallback_pack(str(exc))


# ── Internal builder ──────────────────────────────────────────────────────────

def _build(edit_plan: Any, context: dict) -> AISimulationPack:
    if edit_plan is None:
        logger.info("ai_execution_simulation_skipped: no_edit_plan")
        return AISimulationPack(
            available=False,
            mode="simulation_only",
            warnings=["no_edit_plan"],
        )

    simulations: list[AIExecutionSimulation] = []

    # ── Simulate from execution recommendation pack (Phase 25 output) ─────────
    er = _safe_dict(getattr(edit_plan, "execution_recommendations", {}))
    recs = er.get("recommendations") or []
    simulated_ids: set[str] = set()

    for rec in recs:
        if not isinstance(rec, dict):
            continue
        sim = _simulate_recommendation(rec, edit_plan)
        if sim is not None:
            simulations.append(sim)
            simulated_ids.add(sim.simulation_id)

    # ── Supplement with direct-metadata simulations for missing categories ─────
    if "sim_retention" not in simulated_ids:
        retention = _safe_dict(getattr(edit_plan, "retention", {}))
        if retention:
            sim = _simulate_retention(retention)
            if sim is not None:
                simulations.append(sim)
                simulated_ids.add(sim.simulation_id)

    if "sim_subtitle" not in simulated_ids:
        se = _safe_dict(getattr(edit_plan, "subtitle_execution", {}))
        if se.get("available"):
            sim = _simulate_subtitle(se)
            if sim is not None:
                simulations.append(sim)
                simulated_ids.add(sim.simulation_id)

    if "sim_visual_rhythm" not in simulated_ids:
        bve = _safe_dict(getattr(edit_plan, "beat_visual_execution", {}))
        if bve.get("available"):
            sim = _simulate_visual_rhythm(bve)
            if sim is not None:
                simulations.append(sim)
                simulated_ids.add(sim.simulation_id)

    if "sim_story_pacing" not in simulated_ids:
        so = _safe_dict(getattr(edit_plan, "story_optimization", {}))
        if so.get("available"):
            sim = _simulate_story_pacing(so)
            if sim is not None:
                simulations.append(sim)
                simulated_ids.add(sim.simulation_id)

    if "sim_creator_style" not in simulated_ids:
        csa = _safe_dict(getattr(edit_plan, "creator_style_adaptation", {}))
        if csa.get("detected"):
            sim = _simulate_creator_style(csa)
            if sim is not None:
                simulations.append(sim)
                simulated_ids.add(sim.simulation_id)

    # ── Safe baseline always present ──────────────────────────────────────────
    if _SAFE_BASELINE_ID not in simulated_ids:
        simulations.append(_build_safe_baseline_simulation())

    # ── Select recommended simulation ─────────────────────────────────────────
    recommended_id = _select_recommended(simulations, edit_plan)

    logger.info(
        "ai_execution_simulation_created count=%d recommended=%s",
        len(simulations),
        recommended_id or "none",
    )

    return AISimulationPack(
        available=True,
        mode="simulation_only",
        simulations=simulations,
        recommended_simulation_id=recommended_id,
    )


# ── Recommendation-backed simulators ─────────────────────────────────────────

def _simulate_recommendation(rec: dict, edit_plan: Any) -> Optional[AIExecutionSimulation]:
    """Build a simulation from a Phase 25 recommendation dict."""
    try:
        category = str(rec.get("category") or "")
        rec_id = str(rec.get("recommendation_id") or "")
        confidence = float(rec.get("confidence") or 0.0)
        safe_to_apply = bool(rec.get("safe_to_apply", False))
        settings = rec.get("recommended_settings") or {}

        sim_id = f"sim_{rec_id}"
        safety_level = "safe" if safe_to_apply else "caution"

        if category == "retention":
            return _simulate_retention_from_rec(rec_id, sim_id, confidence, settings, edit_plan, safety_level)
        elif category == "creator_style":
            return _simulate_creator_style_from_rec(rec_id, sim_id, confidence, settings, safety_level)
        elif category == "subtitle":
            return _simulate_subtitle_from_rec(rec_id, sim_id, confidence, settings, safety_level)
        elif category == "visual_rhythm":
            return _simulate_visual_rhythm_from_rec(rec_id, sim_id, confidence, settings, safety_level)
        elif category == "pacing":
            return _simulate_pacing_from_rec(rec_id, sim_id, confidence, settings, edit_plan, safety_level)
        elif category == "safe_baseline":
            return _build_safe_baseline_simulation()
        else:
            return None
    except Exception as exc:
        logger.debug("_simulate_recommendation_failed rec=%s: %s", rec.get("recommendation_id"), exc)
        return None


def _simulate_retention_from_rec(
    rec_id: str, sim_id: str, confidence: float,
    settings: dict, edit_plan: Any, safety_level: str,
) -> AIExecutionSimulation:
    pacing_style = str(settings.get("pacing_style") or "standard")
    retention = _safe_dict(getattr(edit_plan, "retention", {}))
    score = float(retention.get("overall_retention_score") or 50)

    if pacing_style == "fast_cuts":
        retention_gain = 18.0 if score < 40 else 10.0
        pacing_gain = 8.0
    elif pacing_style == "retention_optimized":
        retention_gain = 10.0 if score < 70 else 5.0
        pacing_gain = 5.0
    else:
        retention_gain = 4.0
        pacing_gain = 2.0

    return AIExecutionSimulation(
        simulation_id=sim_id,
        recommendation_id=rec_id,
        label="Retention-Oriented Pacing Simulation",
        estimated_retention_gain=retention_gain,
        estimated_pacing_gain=pacing_gain,
        confidence=confidence,
        safety_level=safety_level,
        advisory_only=True,
        explanation=[
            f"Current retention score: {score:.0f}/100",
            f"Pacing style: {pacing_style}",
            f"Estimated retention improvement: +{retention_gain:.1f}",
        ],
    )


def _simulate_creator_style_from_rec(
    rec_id: str, sim_id: str, confidence: float,
    settings: dict, safety_level: str,
) -> AIExecutionSimulation:
    creator_style = str(settings.get("creator_style") or "safe_generic")
    pacing_hint = str(settings.get("pacing_style") or "default")

    retention_gain = round(confidence * 8.0, 2)
    pacing_gain = round(confidence * 10.0, 2)

    style_label = creator_style.replace("_", " ").title()
    return AIExecutionSimulation(
        simulation_id=sim_id,
        recommendation_id=rec_id,
        label=f"{style_label} Style Simulation",
        estimated_retention_gain=retention_gain,
        estimated_pacing_gain=pacing_gain,
        confidence=confidence,
        safety_level=safety_level,
        advisory_only=True,
        explanation=[
            f"Creator style: {creator_style}",
            f"Pacing hint: {pacing_hint}",
            f"Estimated retention improvement: +{retention_gain:.1f}",
        ],
    )


def _simulate_subtitle_from_rec(
    rec_id: str, sim_id: str, confidence: float,
    settings: dict, safety_level: str,
) -> AIExecutionSimulation:
    density = str(settings.get("subtitle_density") or "normal")
    emphasis = str(settings.get("subtitle_emphasis") or "none")

    if density == "compact":
        subtitle_gain = 12.0
    elif density == "normal":
        subtitle_gain = 6.0
    else:
        subtitle_gain = 3.0

    if emphasis not in ("none", ""):
        subtitle_gain = min(15.0, subtitle_gain + 3.0)

    return AIExecutionSimulation(
        simulation_id=sim_id,
        recommendation_id=rec_id,
        label="Compact Subtitle Clarity Simulation",
        estimated_subtitle_clarity_gain=subtitle_gain,
        confidence=confidence,
        safety_level=safety_level,
        advisory_only=True,
        explanation=[
            f"Subtitle density: {density}",
            f"Emphasis: {emphasis}",
            f"Estimated clarity improvement: +{subtitle_gain:.1f}",
        ],
    )


def _simulate_visual_rhythm_from_rec(
    rec_id: str, sim_id: str, confidence: float,
    settings: dict, safety_level: str,
) -> AIExecutionSimulation:
    mode = str(settings.get("visual_rhythm_mode") or "moderate")

    if mode == "energetic":
        pacing_gain = 10.0
        retention_gain = 6.0
    elif mode == "moderate":
        pacing_gain = 7.0
        retention_gain = 4.0
    else:
        pacing_gain = 5.0
        retention_gain = 2.0

    return AIExecutionSimulation(
        simulation_id=sim_id,
        recommendation_id=rec_id,
        label="Visual Rhythm Simulation",
        estimated_pacing_gain=pacing_gain,
        estimated_retention_gain=retention_gain,
        confidence=confidence,
        safety_level=safety_level,
        advisory_only=True,
        explanation=[
            f"Visual rhythm mode: {mode}",
            f"Estimated pacing improvement: +{pacing_gain:.1f}",
        ],
    )


def _simulate_pacing_from_rec(
    rec_id: str, sim_id: str, confidence: float,
    settings: dict, edit_plan: Any, safety_level: str,
) -> AIExecutionSimulation:
    pacing_style = str(settings.get("pacing_style") or "standard")
    so = _safe_dict(getattr(edit_plan, "story_optimization", {}))
    narrative_score = float(so.get("narrative_score") or 50)

    if pacing_style == "story_driven":
        story_gain = round((100.0 - narrative_score) * 0.15, 2)
        pacing_gain = 8.0
    elif pacing_style == "fast_cuts":
        story_gain = 5.0
        pacing_gain = 10.0
    else:
        story_gain = 3.0
        pacing_gain = 4.0

    return AIExecutionSimulation(
        simulation_id=sim_id,
        recommendation_id=rec_id,
        label="Story-Driven Pacing Simulation",
        estimated_story_gain=story_gain,
        estimated_pacing_gain=pacing_gain,
        confidence=confidence,
        safety_level=safety_level,
        advisory_only=True,
        explanation=[
            f"Pacing style: {pacing_style}",
            f"Narrative score: {narrative_score:.0f}/100",
            f"Estimated story gain: +{story_gain:.1f}",
        ],
    )


# ── Direct-metadata simulators (fallback when no Phase 25 recs) ───────────────

def _simulate_retention(retention: dict) -> Optional[AIExecutionSimulation]:
    try:
        score = float(retention.get("overall_retention_score") or 50)
        if score < 40:
            gain = 18.0
            conf = 0.75
        elif score < 70:
            gain = 10.0
            conf = 0.65
        else:
            gain = 4.0
            conf = 0.55
        return AIExecutionSimulation(
            simulation_id="sim_retention",
            label="Retention Improvement Simulation",
            estimated_retention_gain=gain,
            confidence=conf,
            safety_level="safe",
            advisory_only=True,
            explanation=[
                f"Current retention score: {score:.0f}/100",
                f"Estimated improvement: +{gain:.1f}",
            ],
        )
    except Exception as exc:
        logger.debug("_simulate_retention_failed: %s", exc)
        return None


def _simulate_subtitle(se: dict) -> Optional[AIExecutionSimulation]:
    try:
        density = str(se.get("density") or "normal")
        emphasis = str(se.get("emphasis_style") or "none")
        conf = float(se.get("confidence") or 0.5)

        gain = {"compact": 12.0, "normal": 6.0}.get(density, 3.0)
        if emphasis not in ("none", ""):
            gain = min(15.0, gain + 3.0)

        return AIExecutionSimulation(
            simulation_id="sim_subtitle",
            label="Subtitle Clarity Simulation",
            estimated_subtitle_clarity_gain=gain,
            confidence=conf,
            safety_level="safe",
            advisory_only=True,
            explanation=[
                f"Density: {density}",
                f"Emphasis: {emphasis}",
                f"Estimated clarity: +{gain:.1f}",
            ],
        )
    except Exception as exc:
        logger.debug("_simulate_subtitle_failed: %s", exc)
        return None


def _simulate_visual_rhythm(bve: dict) -> Optional[AIExecutionSimulation]:
    try:
        bpm_raw = bve.get("bpm")
        bpm = float(bpm_raw) if bpm_raw is not None else 0.0

        if bpm > 120:
            pacing_gain = 10.0
        elif bpm > 80:
            pacing_gain = 7.0
        else:
            pacing_gain = 5.0

        return AIExecutionSimulation(
            simulation_id="sim_visual_rhythm",
            label="Visual Rhythm Simulation",
            estimated_pacing_gain=pacing_gain,
            confidence=0.60,
            safety_level="safe",
            advisory_only=True,
            explanation=[
                f"BPM: {bpm:.0f}" if bpm > 0 else "BPM unavailable",
                f"Estimated pacing improvement: +{pacing_gain:.1f}",
            ],
        )
    except Exception as exc:
        logger.debug("_simulate_visual_rhythm_failed: %s", exc)
        return None


def _simulate_story_pacing(so: dict) -> Optional[AIExecutionSimulation]:
    try:
        flow_type = str(so.get("flow_type") or "standard")
        narrative_score = float(so.get("narrative_score") or 50)
        conf = round(min(1.0, narrative_score / 100.0), 4)

        if flow_type in ("three_act", "hero_journey"):
            story_gain = round((100.0 - narrative_score) * 0.15, 2)
            pacing_gain = 8.0
        elif flow_type in ("montage", "highlight"):
            story_gain = 5.0
            pacing_gain = 10.0
        else:
            story_gain = 3.0
            pacing_gain = 4.0

        return AIExecutionSimulation(
            simulation_id="sim_story_pacing",
            label="Story Pacing Simulation",
            estimated_story_gain=story_gain,
            estimated_pacing_gain=pacing_gain,
            confidence=conf,
            safety_level="safe",
            advisory_only=True,
            explanation=[
                f"Flow type: {flow_type}",
                f"Narrative score: {narrative_score:.0f}/100",
                f"Estimated story gain: +{story_gain:.1f}",
            ],
        )
    except Exception as exc:
        logger.debug("_simulate_story_pacing_failed: %s", exc)
        return None


def _simulate_creator_style(csa: dict) -> Optional[AIExecutionSimulation]:
    try:
        primary_style = str(csa.get("primary_style") or "safe_generic")
        confidence = float(csa.get("confidence") or 0.0)
        retention_gain = round(confidence * 8.0, 2)
        pacing_gain = round(confidence * 10.0, 2)
        safety = "safe" if confidence >= 0.50 else "caution"

        style_label = primary_style.replace("_", " ").title()
        return AIExecutionSimulation(
            simulation_id="sim_creator_style",
            label=f"{style_label} Style Simulation",
            estimated_retention_gain=retention_gain,
            estimated_pacing_gain=pacing_gain,
            confidence=confidence,
            safety_level=safety,
            advisory_only=True,
            explanation=[
                f"Creator style: {primary_style}",
                f"Estimated retention improvement: +{retention_gain:.1f}",
            ],
        )
    except Exception as exc:
        logger.debug("_simulate_creator_style_failed: %s", exc)
        return None


def _build_safe_baseline_simulation() -> AIExecutionSimulation:
    return AIExecutionSimulation(
        simulation_id=_SAFE_BASELINE_ID,
        recommendation_id="safe_baseline",
        label="Safe Baseline Simulation",
        estimated_retention_gain=0.0,
        estimated_story_gain=0.0,
        estimated_subtitle_clarity_gain=0.0,
        estimated_pacing_gain=0.0,
        confidence=1.0,
        safety_level="safe",
        advisory_only=True,
        explanation=["Safe baseline — no AI changes applied", "All gains are zero (no-op reference)"],
    )


# ── Selection ─────────────────────────────────────────────────────────────────

def _select_recommended(
    simulations: list[AIExecutionSimulation],
    edit_plan: Any,
) -> Optional[str]:
    """Select the recommended simulation by highest overall score."""
    if not simulations:
        return None
    try:
        scored = [(s, score_simulation(s, edit_plan).get("overall_score", 50.0)) for s in simulations]
        # Prefer non-baseline when there is a clear winner
        non_baseline = [(s, sc) for s, sc in scored if s.simulation_id != _SAFE_BASELINE_ID]
        if non_baseline:
            best_sim, best_score = max(non_baseline, key=lambda x: x[1])
            # Only prefer non-baseline if it actually beats baseline + threshold
            baseline_score = next(
                (sc for s, sc in scored if s.simulation_id == _SAFE_BASELINE_ID), 50.0
            )
            if best_score > baseline_score + 2.0:
                return best_sim.simulation_id
        # Fall back to baseline
        return _SAFE_BASELINE_ID
    except Exception:
        return simulations[0].simulation_id if simulations else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_dict(val: Any) -> dict:
    return val if isinstance(val, dict) else {}


def _fallback_pack(reason: str) -> AISimulationPack:
    logger.info("ai_execution_simulation_fallback reason=%s", reason)
    return AISimulationPack(
        available=False,
        mode="simulation_only",
        simulations=[_build_safe_baseline_simulation()],
        recommended_simulation_id=_SAFE_BASELINE_ID,
        warnings=[f"simulation_error:{reason}"],
    )
