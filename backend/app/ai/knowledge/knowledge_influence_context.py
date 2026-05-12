"""
knowledge_influence_context.py — Phase 54 Knowledge-Aware Influence Upgrade.

Reads Phase 53E knowledge_reasoning_context and builds per-domain influence
support metadata with bounded confidence deltas and creator-facing reasoning.

This module produces advisory metadata that downstream influence engines can
use to enrich their reasoning. It NEVER:
  - modifies the Phase 48 safety gate evaluation
  - lowers safety thresholds
  - unblocks blocked influence
  - touches FFmpeg, subtitle timing, motion_crop, or clip boundaries

Confidence delta bounds (strictly enforced):
  - max per domain:   0.05
  - max total boost:  0.10
  - final confidence: clamped [0.0, 1.0]

Public API:
    build_knowledge_influence_context(edit_plan) -> dict
    enrich_subtitle_influence_reasoning(influence_dict, influence_support) -> dict
    enrich_camera_influence_reasoning(influence_dict, influence_support) -> dict
    enrich_ranking_influence_reasoning(influence_dict, influence_support) -> dict

Safety contract:
  - Local only: no internet, no subprocess, no cloud API
  - Never raises — fallback-safe
  - Deterministic: same inputs → same output
  - Advisory only: confidence_delta is metadata, NEVER fed into safety gate
  - Safety gates are NEVER bypassed or lowered by knowledge
  - Bounded: max_delta capped per domain and in total
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.ai.knowledge.influence_context")

# Confidence delta limits — strictly enforced
_MAX_DELTA_PER_DOMAIN = 0.05
_MAX_TOTAL_DELTA = 0.10

# Per-domain fixed deltas (all within bounds)
_SUBTITLE_DELTA = 0.04
_CAMERA_DELTA   = 0.03
_RANKING_DELTA  = 0.04

_MAX_INFLUENCE_REASONS = 3
_MAX_REASONING_LINES   = 5


def build_knowledge_influence_context(edit_plan: Any) -> dict:
    """Build per-domain knowledge influence support context from Phase 53E output.

    Reads knowledge_reasoning_context from the edit plan, derives per-domain
    influence support with bounded confidence deltas, and produces creator-facing
    reasoning strings.

    Never raises. Fallback returns available=False context.
    Advisory only — confidence_delta is informational metadata, never fed to
    safety gate or influence execution logic.
    """
    try:
        return _build(edit_plan)
    except Exception as exc:
        logger.debug("knowledge_influence_context_error: %s", exc)
        return {"knowledge_influence_context": _fallback()}


def enrich_subtitle_influence_reasoning(
    influence_dict: dict,
    influence_support: dict,
) -> dict:
    """Append knowledge-aware reasons to a subtitle influence dict. Never raises.

    Additive only — appends to existing 'reasoning' list, preserves all other
    fields. Caps total reasoning at 6 items. Does NOT change any bias values.
    """
    try:
        if not influence_dict or not influence_support.get("supported"):
            return influence_dict or {}
        reasons = influence_support.get("reasons") or []
        if not reasons:
            return influence_dict
        existing = list(influence_dict.get("reasoning") or [])
        merged = (existing + reasons)[:6]
        return {**influence_dict, "reasoning": merged}
    except Exception:
        return influence_dict or {}


def enrich_camera_influence_reasoning(
    influence_dict: dict,
    influence_support: dict,
) -> dict:
    """Append knowledge-aware reasons to a camera tuning dict. Never raises.

    Additive only — appends to existing 'reasoning' list, preserves all other
    fields. Caps total reasoning at 6 items. Does NOT change any tuning deltas.
    """
    try:
        if not influence_dict or not influence_support.get("supported"):
            return influence_dict or {}
        reasons = influence_support.get("reasons") or []
        if not reasons:
            return influence_dict
        existing = list(influence_dict.get("reasoning") or [])
        merged = (existing + reasons)[:6]
        return {**influence_dict, "reasoning": merged}
    except Exception:
        return influence_dict or {}


def enrich_ranking_influence_reasoning(
    influence_dict: dict,
    influence_support: dict,
) -> dict:
    """Append knowledge-aware reasons to a ranking influence dict. Never raises.

    Additive only — appends to existing ranking 'reasoning' or 'explainability'
    list, preserves all other fields. Does NOT change ranking priorities.
    """
    try:
        if not influence_dict or not influence_support.get("supported"):
            return influence_dict
        reasons = influence_support.get("reasons") or []
        if not reasons:
            return influence_dict
        # ranking bias may use "reasoning" or "explainability"
        for key in ("reasoning", "explainability"):
            if key in influence_dict:
                existing = list(influence_dict[key] or [])
                return {**influence_dict, key: (existing + reasons)[:6]}
        return influence_dict
    except Exception:
        return influence_dict


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _fallback() -> dict:
    return {
        "available": False,
        "domains": [],
        "influence_support": {},
        "confidence": 0.0,
        "knowledge_influence_reasoning": [],
    }


def _build(edit_plan: Any) -> dict:
    if edit_plan is None:
        return {"knowledge_influence_context": _fallback()}

    # Read Phase 53E knowledge_reasoning_context
    krc = _get(edit_plan, "knowledge_reasoning_context")
    if not krc.get("available"):
        return {"knowledge_influence_context": _fallback()}

    matches: List[Dict] = krc.get("matches") or []
    krc_domains = krc.get("domains") or []
    krc_confidence = float(krc.get("confidence") or 0.0)

    if not matches or not krc_domains:
        return {"knowledge_influence_context": _fallback()}

    influence_support: Dict[str, dict] = {}
    reasoning: List[str] = []
    total_delta = 0.0

    # --- Subtitle domain ---
    subtitle_matches = [m for m in matches if m.get("domain") == "subtitle"]
    if subtitle_matches:
        delta = min(_SUBTITLE_DELTA, _MAX_DELTA_PER_DOMAIN)
        remaining = max(0.0, _MAX_TOTAL_DELTA - total_delta)
        delta = min(delta, remaining)
        title = subtitle_matches[0].get("title") or "Subtitle Knowledge"
        reasons = _build_subtitle_reasons(subtitle_matches[0], title)
        influence_support["subtitle"] = {
            "supported": True,
            "confidence_delta": round(delta, 3),
            "reasons": reasons,
        }
        if reasoning_line := _subtitle_reasoning_line(title):
            reasoning.append(reasoning_line)
        total_delta += delta

    # --- Camera domain ---
    camera_matches = [m for m in matches if m.get("domain") == "camera"]
    if camera_matches and total_delta < _MAX_TOTAL_DELTA:
        delta = min(_CAMERA_DELTA, _MAX_DELTA_PER_DOMAIN)
        remaining = max(0.0, _MAX_TOTAL_DELTA - total_delta)
        delta = min(delta, remaining)
        title = camera_matches[0].get("title") or "Camera Knowledge"
        reasons = _build_camera_reasons(camera_matches[0], title)
        influence_support["camera"] = {
            "supported": True,
            "confidence_delta": round(delta, 3),
            "reasons": reasons,
        }
        if reasoning_line := _camera_reasoning_line(title):
            reasoning.append(reasoning_line)
        total_delta += delta

    # --- Ranking domain (from hook knowledge) ---
    hook_matches = [m for m in matches if m.get("domain") == "hook"]
    if hook_matches and total_delta < _MAX_TOTAL_DELTA:
        delta = min(_RANKING_DELTA, _MAX_DELTA_PER_DOMAIN)
        remaining = max(0.0, _MAX_TOTAL_DELTA - total_delta)
        delta = min(delta, remaining)
        title = hook_matches[0].get("title") or "Hook Knowledge"
        reasons = _build_ranking_reasons(hook_matches[0], title)
        influence_support["ranking"] = {
            "supported": True,
            "confidence_delta": round(delta, 3),
            "reasons": reasons,
        }
        if reasoning_line := _ranking_reasoning_line(title):
            reasoning.append(reasoning_line)
        total_delta += delta

    if not influence_support:
        return {"knowledge_influence_context": _fallback()}

    # Overall confidence: krc_confidence as the basis (clamped)
    confidence = round(max(0.0, min(1.0, krc_confidence)), 2)

    active_domains = sorted(influence_support.keys())

    logger.debug(
        "knowledge_influence_context_built domains=%s total_delta=%.3f confidence=%.2f",
        active_domains, total_delta, confidence,
    )

    return {
        "knowledge_influence_context": {
            "available": True,
            "domains": active_domains,
            "influence_support": influence_support,
            "confidence": confidence,
            "knowledge_influence_reasoning": reasoning[:_MAX_REASONING_LINES],
        }
    }


# ---------------------------------------------------------------------------
# Per-domain reason builders
# ---------------------------------------------------------------------------

def _build_subtitle_reasons(match: dict, title: str) -> List[str]:
    rule_id = str(match.get("rule_id") or "").lower()
    if "mobile" in rule_id or "readability" in rule_id:
        return [f"Mobile readability knowledge supports compact subtitle density"]
    if "tiktok" in rule_id or "shortform" in rule_id:
        return [f"Short-form subtitle knowledge supports compact visual style"]
    if "podcast" in rule_id or "clean" in rule_id:
        return [f"Podcast subtitle knowledge supports clean readable caption style"]
    return [f"Subtitle knowledge ({title}) supports current subtitle influence"]


def _build_camera_reasons(match: dict, title: str) -> List[str]:
    rule_id = str(match.get("rule_id") or "").lower()
    if "anti_jitter" in rule_id or "jitter" in rule_id:
        return [f"Anti-jitter knowledge supports stable framing and smoother camera tuning"]
    if "stable_framing" in rule_id:
        return [f"Stable framing knowledge supports smoother camera motion guidance"]
    if "interview" in rule_id or "talking_head" in rule_id:
        return [f"Interview framing knowledge supports centered stable camera preference"]
    if "vertical" in rule_id:
        return [f"Vertical framing knowledge supports subtitle-safe camera placement"]
    return [f"Camera knowledge ({title}) supports current camera influence"]


def _build_ranking_reasons(match: dict, title: str) -> List[str]:
    rule_id = str(match.get("rule_id") or "").lower()
    if "first_3s" in rule_id or "opening" in rule_id:
        return [f"Opening hook knowledge supports hook-strength priority in ranking"]
    if "first_5s" in rule_id or "retention" in rule_id:
        return [f"Retention knowledge supports hook-aware ranking bias"]
    if "curiosity" in rule_id or "open_loop" in rule_id:
        return [f"Curiosity/open-loop knowledge supports retention priority in ranking"]
    if "market_hook" in rule_id:
        return [f"Market hook knowledge supports market-fit weighting in ranking"]
    if "fatigue" in rule_id or "overuse" in rule_id:
        return [f"Hook fatigue knowledge supports varied hook-style ranking preference"]
    return [f"Hook knowledge ({title}) supports hook-aware retention ranking"]


# ---------------------------------------------------------------------------
# Per-domain one-line summary builders
# ---------------------------------------------------------------------------

def _subtitle_reasoning_line(title: str) -> str:
    return f"Subtitle readability knowledge supported compact caption density"


def _camera_reasoning_line(title: str) -> str:
    return f"Stable framing guidance supported smoother camera motion"


def _ranking_reasoning_line(title: str) -> str:
    return f"Retention knowledge supported hook-aware ranking bias"


# ---------------------------------------------------------------------------
# Safety filter: ensure no execution-related keys are surfaced
# ---------------------------------------------------------------------------

_FORBIDDEN_INFLUENCE_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "scene_detection_mutation",
})


def _is_safe_influence_output(d: dict) -> bool:
    """Return True if the influence dict contains no forbidden execution keys."""
    s = str(d)
    return not any(k in s for k in _FORBIDDEN_INFLUENCE_KEYS)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _get(edit_plan: Any, attr: str) -> dict:
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        if isinstance(val, dict):
            return val
        return {}
    except Exception:
        return {}
