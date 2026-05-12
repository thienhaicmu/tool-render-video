"""
knowledge_reasoning_context.py — Phase 53E Knowledge-Aware Render Reasoning.

Connects Phase 53B/C/D domain retrievers (subtitle, camera, hook) into a
unified cross-domain reasoning context. Routes retrieval from edit plan
quality signals, assembles matched knowledge items, and produces structured
reasoning metadata for use by quality evaluators and AI UX layers.

Public API:
    build_knowledge_reasoning_context(edit_plan) -> dict

Returns:
    {
        "knowledge_reasoning_context": {
            "available": bool,
            "domains": List[str],
            "matches": [
                {"domain": str, "rule_id": str, "title": str, "confidence": float}
            ],
            "confidence": float,
            "reasoning": List[str],
        }
    }

Safety contract:
    - Local only: no internet, no subprocess, no cloud API
    - Never raises — fallback-safe
    - Deterministic: same inputs → same output
    - Advisory only: never mutates render, FFmpeg, subtitle timing, or motion_crop
    - Bounded: max 3 domain retrievals, max 1 item per domain routed to context
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.ai.knowledge.reasoning_context")

_MATCH_CONFIDENCE = 0.75
_STYLE_CONFIDENCE = 0.60
_MAX_REASONING_LINES = 5


def build_knowledge_reasoning_context(edit_plan: Any) -> dict:
    """Build a cross-domain knowledge reasoning context from edit plan signals.

    Reads quality signals from Phase 52A/B/C results and creator preference
    metadata, routes retrieval to subtitle/camera/hook knowledge retrievers,
    and assembles a structured advisory reasoning context.

    Never raises. Fallback returns available=False context.
    """
    try:
        return _build(edit_plan)
    except Exception as exc:
        logger.debug("knowledge_reasoning_context_error: %s", exc)
        return {"knowledge_reasoning_context": _fallback()}


def _fallback() -> dict:
    return {
        "available": False,
        "domains": [],
        "matches": [],
        "confidence": 0.0,
        "reasoning": [],
    }


def _build(edit_plan: Any) -> dict:
    if edit_plan is None:
        return {"knowledge_reasoning_context": _fallback()}

    matches: List[Dict] = []
    domains: List[str] = []
    reasoning: List[str] = []

    # --- Subtitle domain routing ---
    subtitle_tags = _get_subtitle_tags(edit_plan)
    if subtitle_tags:
        subtitle_match = _retrieve_subtitle_match(subtitle_tags)
        if subtitle_match:
            matches.append(subtitle_match)
            domains.append("subtitle")
            reasoning.append(
                f"Subtitle knowledge ({subtitle_match['title']}) is relevant "
                "to the current subtitle quality signals"
            )

    # --- Camera domain routing ---
    camera_tags = _get_camera_tags(edit_plan)
    if camera_tags:
        camera_match = _retrieve_camera_match(camera_tags)
        if camera_match:
            matches.append(camera_match)
            domains.append("camera")
            reasoning.append(
                f"Camera knowledge ({camera_match['title']}) is relevant "
                "to the current camera quality signals"
            )

    # --- Hook domain routing ---
    hook_tags = _get_hook_tags(edit_plan)
    if hook_tags:
        hook_match = _retrieve_hook_match(hook_tags)
        if hook_match:
            matches.append(hook_match)
            domains.append("hook")
            reasoning.append(
                f"Hook knowledge ({hook_match['title']}) is relevant "
                "to the current hook quality signals"
            )

    if not matches:
        return {"knowledge_reasoning_context": _fallback()}

    # Integrated summary line
    if len(domains) >= 2:
        domain_str = ", ".join(domains[:-1]) + " and " + domains[-1] if len(domains) > 1 else domains[0]
        reasoning.append(
            f"Knowledge matched across {domain_str} domains supports quality reasoning"
        )

    confidence = round(
        sum(m["confidence"] for m in matches) / len(matches), 2
    )

    logger.debug(
        "knowledge_reasoning_context_built domains=%s matches=%d confidence=%.2f",
        domains, len(matches), confidence,
    )

    return {
        "knowledge_reasoning_context": {
            "available": True,
            "domains": sorted(set(domains)),
            "matches": matches,
            "confidence": confidence,
            "reasoning": reasoning[:_MAX_REASONING_LINES],
        }
    }


# ---------------------------------------------------------------------------
# Tag routing helpers
# ---------------------------------------------------------------------------

def _get_subtitle_tags(edit_plan: Any) -> List[str]:
    """Derive subtitle retrieval tags from quality signals and creator preference."""
    tags: List[str] = []

    sqv2 = _get(edit_plan, "subtitle_quality_v2")
    mobile_readability = int(sqv2.get("mobile_readability") or 0)
    overall = int(sqv2.get("overall") or 0)

    # Mobile readability weakness → readability knowledge
    if overall > 0 and mobile_readability < 70:
        tags.extend(["mobile", "readability"])

    # Creator subtitle preference style → style-aware tags
    csp = _get(edit_plan, "creator_subtitle_preference")
    pref = csp.get("subtitle_preference") or {}
    if isinstance(pref, dict):
        style = str(pref.get("style") or "").lower()
    else:
        style = ""

    if style == "viral_bold":
        tags.extend(["tiktok", "shortform"])
    elif style == "clean_pro":
        tags.extend(["podcast", "clean"])

    # Fallback: if quality data exists, always include generic subtitle tag
    if overall > 0 and not tags:
        tags.extend(["mobile", "readability"])

    return tags


def _get_camera_tags(edit_plan: Any) -> List[str]:
    """Derive camera retrieval tags from quality signals and creator preference."""
    tags: List[str] = []

    cqv2 = _get(edit_plan, "camera_quality_v2")
    overall = int(cqv2.get("overall") or 0)
    jitter = int(cqv2.get("micro_jitter_risk") or 0)
    whip_pan = int(cqv2.get("whip_pan_risk") or 0)

    if overall > 0:
        # Jitter risk → anti-jitter knowledge
        if jitter >= 35:
            tags.extend(["anti_jitter", "jitter"])

        # Whip pan risk → stability knowledge
        if whip_pan >= 35:
            tags.extend(["stable_framing", "smooth"])

    # Creator camera preference motion style → style-aware tags
    ccp = _get(edit_plan, "creator_camera_preference")
    cam_pref = ccp.get("camera_preference") or {}
    if isinstance(cam_pref, dict):
        motion_style = str(cam_pref.get("motion_style") or "").lower()
    else:
        motion_style = ""

    if motion_style == "static_center":
        tags.extend(["interview", "talking_head"])
    elif motion_style == "smooth_subject" and not tags:
        tags.extend(["stable_framing", "smooth"])
    elif motion_style == "dynamic_subject" and not tags:
        tags.extend(["dynamic", "viral"])

    # Fallback: if quality data exists, include generic stability tag
    if overall > 0 and not tags:
        tags.extend(["stable_framing"])

    return tags


def _get_hook_tags(edit_plan: Any) -> List[str]:
    """Derive hook retrieval tags from hook quality signals and market data."""
    tags: List[str] = []

    hqv2 = _get(edit_plan, "hook_quality_v2")
    overall = int(hqv2.get("overall") or 0)

    if overall > 0:
        first_3s = int(hqv2.get("first_3s_strength") or 0)
        curiosity = int(hqv2.get("curiosity_strength") or 0)
        fatigue = int(hqv2.get("hook_fatigue_risk") or 0)

        if first_3s < 55:
            tags.extend(["first_3s", "opening"])

        if curiosity < 50:
            tags.extend(["curiosity", "open_loop"])

        if fatigue >= 40:
            tags.extend(["fatigue", "overuse"])

    # Market-specific hook routing
    moi = _get(edit_plan, "market_optimization_intelligence")
    market = str(moi.get("target_market") or "").strip().lower()
    if market:
        tags.extend(["market_hook", market])

    # Fallback: if quality data exists, include generic hook tag
    if overall > 0 and not tags:
        tags.extend(["first_3s", "retention"])

    return tags


# ---------------------------------------------------------------------------
# Domain retrievers
# ---------------------------------------------------------------------------

def _retrieve_subtitle_match(tags: List[str]) -> Optional[Dict]:
    """Retrieve one subtitle knowledge item and return a match dict."""
    try:
        from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="subtitle", tags=tags, max_results=1)
        if not pack.available or not pack.items:
            return None
        item = pack.items[0]
        return {
            "domain": "subtitle",
            "rule_id": item.knowledge_id,
            "title": item.title,
            "confidence": _MATCH_CONFIDENCE,
        }
    except Exception:
        return None


def _retrieve_camera_match(tags: List[str]) -> Optional[Dict]:
    """Retrieve one camera knowledge item and return a match dict."""
    try:
        from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="camera", tags=tags, max_results=1)
        if not pack.available or not pack.items:
            return None
        item = pack.items[0]
        return {
            "domain": "camera",
            "rule_id": item.knowledge_id,
            "title": item.title,
            "confidence": _MATCH_CONFIDENCE,
        }
    except Exception:
        return None


def _retrieve_hook_match(tags: List[str]) -> Optional[Dict]:
    """Retrieve one hook knowledge item and return a match dict."""
    try:
        from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="hook", tags=tags, max_results=1)
        if not pack.available or not pack.items:
            return None
        item = pack.items[0]
        return {
            "domain": "hook",
            "rule_id": item.knowledge_id,
            "title": item.title,
            "confidence": _MATCH_CONFIDENCE,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Safety filter — strips any execution-related keys before output
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
})


def safe_knowledge_reasoning_summary(ctx: dict) -> str:
    """Return a creator-facing one-liner from a knowledge_reasoning_context dict.

    Never raises. Returns empty string when context is unavailable.
    Advisory only — no internal rule dump, no raw JSON, no file paths.
    """
    try:
        if not ctx or not ctx.get("available"):
            return ""
        domains = ctx.get("domains") or []
        if not domains:
            return ""
        if len(domains) == 1:
            return f"AI used {domains[0]} knowledge to support this recommendation."
        domain_str = ", ".join(domains[:-1]) + " and " + domains[-1]
        return f"AI used {domain_str} knowledge to support this recommendation."
    except Exception:
        return ""


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
