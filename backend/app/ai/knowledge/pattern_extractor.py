"""
pattern_extractor.py — Creator pattern extraction from knowledge registry. Phase 40.

Extracts structured creator intelligence patterns from ingested AICreatorKnowledge items.
Deterministic, local-only, no internet, no model training, no subprocess. Never raises.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.knowledge.pattern_schema import AICreatorPattern
from app.ai.knowledge.pattern_safety import is_pattern_safe, sanitize_pattern

logger = logging.getLogger("app.ai.knowledge.pattern_extractor")

# ---------------------------------------------------------------------------
# Hook pattern archetypes derived from knowledge
# ---------------------------------------------------------------------------

_HOOK_ARCHETYPES = {
    "question_hook": {
        "keywords": ("did you know", "have you ever", "what if", "why does", "how did", "can you"),
        "confidence": 0.85,
        "tags": ["hook", "question", "curiosity"],
        "description": "Question-based opening hook driving viewer curiosity",
    },
    "curiosity_hook": {
        "keywords": ("wait for it", "watch this", "here's why", "you won't believe", "this is how"),
        "confidence": 0.82,
        "tags": ["hook", "curiosity", "tease"],
        "description": "Curiosity-gap hook that teases upcoming payoff",
    },
    "rapid_hook": {
        "keywords": ("pov:", "day in my life", "rating my", "i tried"),
        "confidence": 0.78,
        "tags": ["hook", "rapid", "direct"],
        "description": "Fast direct hook for high-energy short-form content",
    },
    "delayed_payoff": {
        "keywords": ("the thing is", "what nobody tells you", "i realized", "here's what happened"),
        "confidence": 0.75,
        "tags": ["hook", "payoff", "conversational"],
        "description": "Conversational hook with delayed payoff reveal",
    },
}

# ---------------------------------------------------------------------------
# Subtitle pattern archetypes
# ---------------------------------------------------------------------------

_SUBTITLE_ARCHETYPES = {
    "compact_viral": {
        "density": "compact",
        "max_words_per_line": 5,
        "keyword_emphasis": True,
        "capitalize_keywords": True,
        "confidence": 0.85,
        "tags": ["subtitle", "compact", "viral", "tiktok"],
        "description": "Compact, emphasis-driven subtitle style for viral short-form",
    },
    "podcast_readable": {
        "density": "normal",
        "max_words_per_line": 7,
        "keyword_emphasis": True,
        "capitalize_keywords": False,
        "confidence": 0.80,
        "tags": ["subtitle", "podcast", "readable", "conversational"],
        "description": "Readable subtitle style for podcast-style clip content",
    },
    "educational_clean": {
        "density": "normal",
        "max_words_per_line": 8,
        "keyword_emphasis": False,
        "capitalize_keywords": False,
        "confidence": 0.75,
        "tags": ["subtitle", "educational", "clean"],
        "description": "Clean subtitle style for educational and documentary content",
    },
}

# ---------------------------------------------------------------------------
# Pacing pattern archetypes
# ---------------------------------------------------------------------------

_PACING_ARCHETYPES = {
    "fast_hook": {
        "hook_duration_sec": 3,
        "intro_style": "abrupt",
        "cut_cadence": "rapid",
        "silence_tolerance_sec": 0.5,
        "avoid_dead_air": True,
        "confidence": 0.85,
        "tags": ["pacing", "fast", "hook", "attention"],
        "description": "Aggressive front-loaded pacing for 3-second hook capture",
    },
    "calm_storytelling": {
        "hook_duration_sec": 6,
        "intro_style": "gradual",
        "cut_cadence": "conversational",
        "silence_tolerance_sec": 1.5,
        "avoid_dead_air": False,
        "confidence": 0.72,
        "tags": ["pacing", "calm", "storytelling", "podcast"],
        "description": "Calm narrative pacing for story-driven content",
    },
    "high_energy_shortform": {
        "hook_duration_sec": 2,
        "intro_style": "abrupt",
        "cut_cadence": "rapid",
        "silence_tolerance_sec": 0.3,
        "avoid_dead_air": True,
        "confidence": 0.88,
        "tags": ["pacing", "high_energy", "short_form", "tiktok"],
        "description": "Maximum energy pacing for viral short-form content",
    },
}

# ---------------------------------------------------------------------------
# Camera pattern archetypes
# ---------------------------------------------------------------------------

_CAMERA_ARCHETYPES = {
    "dynamic_safe": {
        "behavior": "dynamic_safe",
        "zoom_emphasis": True,
        "subject_lock": False,
        "motion_smoothing": True,
        "confidence": 0.82,
        "tags": ["camera", "dynamic", "safe", "tiktok"],
        "description": "Dynamic camera motion within safe bounds for viral content",
    },
    "cinematic_smooth": {
        "behavior": "slow_reveal",
        "zoom_emphasis": False,
        "subject_lock": True,
        "motion_smoothing": True,
        "confidence": 0.78,
        "tags": ["camera", "cinematic", "smooth", "storytelling"],
        "description": "Smooth cinematic camera motion for storytelling content",
    },
    "static_podcast": {
        "behavior": "static_safe",
        "zoom_emphasis": False,
        "subject_lock": False,
        "motion_smoothing": False,
        "confidence": 0.80,
        "tags": ["camera", "static", "podcast", "stable"],
        "description": "Stable static framing for podcast-style interview content",
    },
}

# ---------------------------------------------------------------------------
# Retention pattern archetypes
# ---------------------------------------------------------------------------

_RETENTION_ARCHETYPES = {
    "loop_payoff": {
        "hook_style": "loop",
        "payoff_timing": "late",
        "reengagement_cadence": "slow",
        "avoid_silence_gaps": True,
        "confidence": 0.80,
        "tags": ["retention", "loop", "payoff"],
        "description": "Loop-inducing hook that rewards rewatchers",
    },
    "rapid_reengagement": {
        "hook_style": "question",
        "payoff_timing": "early",
        "reengagement_cadence": "rapid",
        "avoid_silence_gaps": True,
        "confidence": 0.85,
        "tags": ["retention", "rapid", "reengagement", "tiktok"],
        "description": "Rapid re-engagement pattern for high-retention short-form",
    },
    "payoff_reinforcement": {
        "hook_style": "delayed_payoff",
        "payoff_timing": "mid",
        "reengagement_cadence": "moderate",
        "avoid_silence_gaps": True,
        "confidence": 0.75,
        "tags": ["retention", "payoff", "reinforcement", "podcast"],
        "description": "Payoff-reinforcement retention structure for podcast clips",
    },
}


# ---------------------------------------------------------------------------
# Public extraction API
# ---------------------------------------------------------------------------

def extract_creator_patterns(
    knowledge_registry: Any,
) -> List[AICreatorPattern]:
    """Extract all creator patterns from an AIKnowledgeRegistry or item list.

    Deterministic, local-only. Never raises. No internet, no model training.
    """
    try:
        knowledge_items = _get_knowledge_items(knowledge_registry)
        patterns: List[AICreatorPattern] = []

        patterns.extend(extract_hook_patterns(knowledge_items))
        patterns.extend(extract_subtitle_patterns(knowledge_items))
        patterns.extend(extract_pacing_patterns(knowledge_items))
        patterns.extend(extract_camera_patterns(knowledge_items))
        patterns.extend(extract_retention_patterns(knowledge_items))

        logger.debug(
            "creator_patterns_extracted total=%d hooks=%d subtitle=%d pacing=%d camera=%d retention=%d",
            len(patterns),
            sum(1 for p in patterns if p.pattern_type == "hook"),
            sum(1 for p in patterns if p.pattern_type == "subtitle"),
            sum(1 for p in patterns if p.pattern_type == "pacing"),
            sum(1 for p in patterns if p.pattern_type == "camera"),
            sum(1 for p in patterns if p.pattern_type == "retention"),
        )
        return patterns

    except Exception as exc:
        logger.debug("pattern_extraction_error: %s", exc)
        return []


def extract_hook_patterns(
    knowledge_items: List[Any] = None,
) -> List[AICreatorPattern]:
    """Extract hook patterns from knowledge items + archetypes. Never raises."""
    patterns: List[AICreatorPattern] = []
    try:
        seen_hooks: set[str] = set()
        items = knowledge_items or []

        for item in items:
            hooks = list(getattr(item, "hook_patterns", None) or [])
            if not hooks:
                continue
            style = str(getattr(item, "creator_style", "") or "")
            kid = str(getattr(item, "knowledge_id", "") or "")
            archetype = _match_hook_archetype(hooks)
            pid = f"hook_{archetype}_{kid}" if kid else f"hook_{archetype}"
            if pid in seen_hooks:
                continue
            seen_hooks.add(pid)
            arch = _HOOK_ARCHETYPES.get(archetype, {})
            raw = {
                "pattern_id": pid,
                "pattern_type": "hook",
                "creator_style": style,
                "title": arch.get("description", f"Hook: {archetype}"),
                "description": arch.get("description", ""),
                "confidence": arch.get("confidence", 0.7),
                "tags": list(arch.get("tags", [])),
                "hook_patterns": hooks[:20],
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        # Add archetype defaults not already covered
        for archetype_id, arch in _HOOK_ARCHETYPES.items():
            pid = f"hook_{archetype_id}_default"
            if pid in seen_hooks:
                continue
            seen_hooks.add(pid)
            raw = {
                "pattern_id": pid,
                "pattern_type": "hook",
                "creator_style": "",
                "title": arch["description"],
                "description": arch["description"],
                "confidence": arch["confidence"],
                "tags": list(arch["tags"]),
                "hook_patterns": list(arch["keywords"]),
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        logger.debug("ai_creator_pattern_extracted type=hook count=%d", len(patterns))
    except Exception as exc:
        logger.debug("extract_hook_patterns_error: %s", exc)
    return patterns


def extract_subtitle_patterns(
    knowledge_items: List[Any] = None,
) -> List[AICreatorPattern]:
    """Extract subtitle patterns from knowledge items + archetypes. Never raises."""
    patterns: List[AICreatorPattern] = []
    try:
        seen: set[str] = set()
        items = knowledge_items or []

        for item in items:
            sub = dict(getattr(item, "subtitle_patterns", None) or {})
            if not sub:
                continue
            style = str(getattr(item, "creator_style", "") or "")
            kid = str(getattr(item, "knowledge_id", "") or "")
            archetype = _match_subtitle_archetype(sub, style)
            pid = f"subtitle_{archetype}_{kid}"
            if pid in seen:
                continue
            seen.add(pid)
            arch = _SUBTITLE_ARCHETYPES.get(archetype, {})
            merged = {**arch, **sub}
            raw = {
                "pattern_id": pid,
                "pattern_type": "subtitle",
                "creator_style": style,
                "title": arch.get("description", f"Subtitle: {archetype}"),
                "description": arch.get("description", ""),
                "confidence": arch.get("confidence", 0.7),
                "tags": list(arch.get("tags", [])),
                "subtitle_patterns": {k: v for k, v in merged.items()
                                      if k not in ("confidence", "tags", "description")},
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        for archetype_id, arch in _SUBTITLE_ARCHETYPES.items():
            pid = f"subtitle_{archetype_id}_default"
            if pid in seen:
                continue
            seen.add(pid)
            sub_data = {k: v for k, v in arch.items()
                        if k not in ("confidence", "tags", "description")}
            raw = {
                "pattern_id": pid,
                "pattern_type": "subtitle",
                "creator_style": "",
                "title": arch["description"],
                "description": arch["description"],
                "confidence": arch["confidence"],
                "tags": list(arch["tags"]),
                "subtitle_patterns": sub_data,
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        logger.debug("ai_creator_pattern_extracted type=subtitle count=%d", len(patterns))
    except Exception as exc:
        logger.debug("extract_subtitle_patterns_error: %s", exc)
    return patterns


def extract_pacing_patterns(
    knowledge_items: List[Any] = None,
) -> List[AICreatorPattern]:
    """Extract pacing patterns from knowledge items + archetypes. Never raises."""
    patterns: List[AICreatorPattern] = []
    try:
        seen: set[str] = set()
        items = knowledge_items or []

        for item in items:
            pac = dict(getattr(item, "pacing_patterns", None) or {})
            if not pac:
                continue
            style = str(getattr(item, "creator_style", "") or "")
            kid = str(getattr(item, "knowledge_id", "") or "")
            archetype = _match_pacing_archetype(pac, style)
            pid = f"pacing_{archetype}_{kid}"
            if pid in seen:
                continue
            seen.add(pid)
            arch = _PACING_ARCHETYPES.get(archetype, {})
            merged = {**arch, **pac}
            raw = {
                "pattern_id": pid,
                "pattern_type": "pacing",
                "creator_style": style,
                "title": arch.get("description", f"Pacing: {archetype}"),
                "description": arch.get("description", ""),
                "confidence": arch.get("confidence", 0.7),
                "tags": list(arch.get("tags", [])),
                "pacing_patterns": {k: v for k, v in merged.items()
                                    if k not in ("confidence", "tags", "description")},
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        for archetype_id, arch in _PACING_ARCHETYPES.items():
            pid = f"pacing_{archetype_id}_default"
            if pid in seen:
                continue
            seen.add(pid)
            pac_data = {k: v for k, v in arch.items()
                        if k not in ("confidence", "tags", "description")}
            raw = {
                "pattern_id": pid,
                "pattern_type": "pacing",
                "creator_style": "",
                "title": arch["description"],
                "description": arch["description"],
                "confidence": arch["confidence"],
                "tags": list(arch["tags"]),
                "pacing_patterns": pac_data,
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        logger.debug("ai_creator_pattern_extracted type=pacing count=%d", len(patterns))
    except Exception as exc:
        logger.debug("extract_pacing_patterns_error: %s", exc)
    return patterns


def extract_camera_patterns(
    knowledge_items: List[Any] = None,
) -> List[AICreatorPattern]:
    """Extract camera patterns from knowledge items + archetypes. Never raises."""
    patterns: List[AICreatorPattern] = []
    try:
        seen: set[str] = set()
        items = knowledge_items or []

        for item in items:
            cam = dict(getattr(item, "camera_patterns", None) or {})
            if not cam:
                continue
            style = str(getattr(item, "creator_style", "") or "")
            kid = str(getattr(item, "knowledge_id", "") or "")
            archetype = _match_camera_archetype(cam, style)
            pid = f"camera_{archetype}_{kid}"
            if pid in seen:
                continue
            seen.add(pid)
            arch = _CAMERA_ARCHETYPES.get(archetype, {})
            merged = {**arch, **cam}
            raw = {
                "pattern_id": pid,
                "pattern_type": "camera",
                "creator_style": style,
                "title": arch.get("description", f"Camera: {archetype}"),
                "description": arch.get("description", ""),
                "confidence": arch.get("confidence", 0.7),
                "tags": list(arch.get("tags", [])),
                "camera_patterns": {k: v for k, v in merged.items()
                                    if k not in ("confidence", "tags", "description")},
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        for archetype_id, arch in _CAMERA_ARCHETYPES.items():
            pid = f"camera_{archetype_id}_default"
            if pid in seen:
                continue
            seen.add(pid)
            cam_data = {k: v for k, v in arch.items()
                        if k not in ("confidence", "tags", "description")}
            raw = {
                "pattern_id": pid,
                "pattern_type": "camera",
                "creator_style": "",
                "title": arch["description"],
                "description": arch["description"],
                "confidence": arch["confidence"],
                "tags": list(arch["tags"]),
                "camera_patterns": cam_data,
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        logger.debug("ai_creator_pattern_extracted type=camera count=%d", len(patterns))
    except Exception as exc:
        logger.debug("extract_camera_patterns_error: %s", exc)
    return patterns


def extract_retention_patterns(
    knowledge_items: List[Any] = None,
) -> List[AICreatorPattern]:
    """Extract retention patterns from knowledge items + archetypes. Never raises."""
    patterns: List[AICreatorPattern] = []
    try:
        seen: set[str] = set()
        items = knowledge_items or []

        for item in items:
            ret = dict(getattr(item, "retention_patterns", None) or {})
            if not ret:
                continue
            style = str(getattr(item, "creator_style", "") or "")
            kid = str(getattr(item, "knowledge_id", "") or "")
            archetype = _match_retention_archetype(ret, style)
            pid = f"retention_{archetype}_{kid}"
            if pid in seen:
                continue
            seen.add(pid)
            arch = _RETENTION_ARCHETYPES.get(archetype, {})
            merged = {**arch, **ret}
            raw = {
                "pattern_id": pid,
                "pattern_type": "retention",
                "creator_style": style,
                "title": arch.get("description", f"Retention: {archetype}"),
                "description": arch.get("description", ""),
                "confidence": arch.get("confidence", 0.7),
                "tags": list(arch.get("tags", [])),
                "retention_patterns": {k: v for k, v in merged.items()
                                       if k not in ("confidence", "tags", "description")},
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        for archetype_id, arch in _RETENTION_ARCHETYPES.items():
            pid = f"retention_{archetype_id}_default"
            if pid in seen:
                continue
            seen.add(pid)
            ret_data = {k: v for k, v in arch.items()
                        if k not in ("confidence", "tags", "description")}
            raw = {
                "pattern_id": pid,
                "pattern_type": "retention",
                "creator_style": "",
                "title": arch["description"],
                "description": arch["description"],
                "confidence": arch["confidence"],
                "tags": list(arch["tags"]),
                "retention_patterns": ret_data,
            }
            sanitized = sanitize_pattern(raw)
            if is_pattern_safe(sanitized):
                sanitized["safe"] = True
                patterns.append(_from_dict(sanitized))

        logger.debug("ai_creator_pattern_extracted type=retention count=%d", len(patterns))
    except Exception as exc:
        logger.debug("extract_retention_patterns_error: %s", exc)
    return patterns


# ---------------------------------------------------------------------------
# Archetype matching helpers
# ---------------------------------------------------------------------------

def _match_hook_archetype(hook_patterns: list) -> str:
    hooks_lower = " ".join(str(h).lower() for h in hook_patterns)
    if any(k in hooks_lower for k in ("did you know", "have you ever", "what if", "why does")):
        return "question_hook"
    if any(k in hooks_lower for k in ("wait for it", "watch this", "here's why")):
        return "curiosity_hook"
    if any(k in hooks_lower for k in ("pov:", "day in my life", "rating")):
        return "rapid_hook"
    return "delayed_payoff"


def _match_subtitle_archetype(sub: dict, style: str) -> str:
    density = str(sub.get("density", "")).lower()
    max_w = sub.get("max_words_per_line", 8)
    if density == "compact" or (isinstance(max_w, int) and max_w <= 5):
        return "compact_viral"
    if "podcast" in style.lower():
        return "podcast_readable"
    return "educational_clean"


def _match_pacing_archetype(pac: dict, style: str) -> str:
    intro = str(pac.get("intro_speed", "") or pac.get("intro_style", "")).lower()
    hook_dur = pac.get("hook_duration_sec", 5)
    if "fast" in intro or "abrupt" in intro or (isinstance(hook_dur, (int, float)) and hook_dur <= 3):
        if "tiktok" in style.lower() or "viral" in style.lower():
            return "high_energy_shortform"
        return "fast_hook"
    if "podcast" in style.lower() or "calm" in intro or "gradual" in intro:
        return "calm_storytelling"
    return "fast_hook"


def _match_camera_archetype(cam: dict, style: str) -> str:
    behavior = str(cam.get("behavior", "")).lower()
    zoom = cam.get("zoom_emphasis", False)
    if "static" in behavior or "podcast" in style.lower():
        return "static_podcast"
    if "dynamic" in behavior or zoom:
        return "dynamic_safe"
    return "cinematic_smooth"


def _match_retention_archetype(ret: dict, style: str) -> str:
    hook_style = str(ret.get("hook_style", "")).lower()
    if "question" in hook_style or "tiktok" in style.lower() or "viral" in style.lower():
        return "rapid_reengagement"
    if "loop" in hook_style:
        return "loop_payoff"
    return "payoff_reinforcement"


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _get_knowledge_items(registry: Any) -> list:
    """Extract item list from an AIKnowledgeRegistry or raw list. Never raises."""
    try:
        if isinstance(registry, list):
            return registry
        items = getattr(registry, "_items", None)
        if isinstance(items, list):
            return items
        return []
    except Exception:
        return []


def _from_dict(d: dict) -> AICreatorPattern:
    return AICreatorPattern(
        pattern_id=str(d.get("pattern_id", "")),
        pattern_type=str(d.get("pattern_type", "")),
        creator_style=str(d.get("creator_style", "")),
        title=str(d.get("title", "")),
        description=str(d.get("description", "")),
        confidence=float(d.get("confidence", 0.0)),
        tags=list(d.get("tags") or []),
        hook_patterns=list(d.get("hook_patterns") or []),
        subtitle_patterns=dict(d.get("subtitle_patterns") or {}),
        pacing_patterns=dict(d.get("pacing_patterns") or {}),
        camera_patterns=dict(d.get("camera_patterns") or {}),
        retention_patterns=dict(d.get("retention_patterns") or {}),
        safe=bool(d.get("safe", False)),
        warnings=list(d.get("warnings") or []),
        explanation=list(d.get("explanation") or []),
    )
