"""
response_parser.py — Parses raw cloud API text into AnalysisSignals.

Handles JSON embedded in markdown fences, stray text, and partial responses.
All parsing is defensive — never raises, returns None on any failure.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.ai.analysis.signals import (
    AnalysisSignals, ClipSignal, EmotionSignal, SubtitleHints, CameraHints,
)

logger = logging.getLogger("app.ai.analysis.cloud.parser")

_VALID_HOOK_TYPES = frozenset({
    "curiosity", "surprise", "warning", "authority",
    "problem", "story", "contrarian", "result_first", "none",
})
_VALID_CLIP_TYPES = frozenset({
    "hook", "payoff", "educational", "emotional", "transition", "unknown",
})
_VALID_CAMERA_BEHAVIORS = frozenset({
    "dramatic_push", "fast_follow", "slow_reveal", "subject_lock", "none",
})
_VALID_SUBTITLE_PRESETS = frozenset({"viral_bold", "clean_pro", "boxed_caption"})
_VALID_DENSITY = frozenset({"compact", "normal", "relaxed"})


def parse_response(raw: str) -> Optional[AnalysisSignals]:
    try:
        data = _extract_json(raw)
        if not isinstance(data, dict):
            return None
        return AnalysisSignals(
            clip_signals=_parse_clips(data.get("clip_signals") or []),
            emotion=_parse_emotion(data.get("emotion") or {}),
            subtitle_hints=_parse_subtitle(data.get("subtitle_hints")),
            camera_hints=_parse_camera(data.get("camera_hints")),
            confidence=0.85,
            source="cloud",
            warnings=[],
        )
    except Exception as exc:
        logger.debug("response_parser_failed: %s", exc)
        return None


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(raw: str) -> Optional[dict]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Markdown code fence
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # First JSON object anywhere in the text
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ── Field parsers ─────────────────────────────────────────────────────────────

def _parse_clips(raw_list: list) -> list[ClipSignal]:
    signals: list[ClipSignal] = []
    for item in raw_list[:5]:  # cap at 5 clips
        try:
            if item.get("drop") is True:
                continue
            hook_type = str(item.get("hook_type", "none"))
            if hook_type not in _VALID_HOOK_TYPES:
                hook_type = "none"
            clip_type = str(item.get("clip_type", "unknown"))
            if clip_type not in _VALID_CLIP_TYPES:
                clip_type = "unknown"
            raw_thumb = item.get("thumbnail_sec")
            thumbnail_sec = float(raw_thumb) if raw_thumb is not None else None
            signals.append(ClipSignal(
                start=float(item["start"]),
                end=float(item["end"]),
                hook_score=max(0.0, min(100.0, float(item.get("hook_score", 50)))),
                hook_type=hook_type,
                relevance_score=max(0.0, min(100.0, float(item.get("relevance_score", 50)))),
                reason=str(item.get("reason", "")),
                source="cloud",
                clip_type=clip_type,
                thumbnail_sec=thumbnail_sec,
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return signals


def _parse_emotion(raw: dict) -> EmotionSignal:
    return EmotionSignal(
        dominant=str(raw.get("dominant", "neutral")),
        score=max(0.0, min(100.0, float(raw.get("score", 0.0)))),
        source="cloud",
    )


def _parse_subtitle(raw: Optional[dict]) -> Optional[SubtitleHints]:
    if not raw:
        return None
    preset = raw.get("style_preset")
    if preset not in _VALID_SUBTITLE_PRESETS:
        preset = None
    density = str(raw.get("density", "normal"))
    if density not in _VALID_DENSITY:
        density = "normal"
    keywords = [str(k) for k in (raw.get("highlight_keywords") or []) if k][:20]
    return SubtitleHints(style_preset=preset, highlight_keywords=keywords, density=density, source="cloud")


def _parse_camera(raw: Optional[dict]) -> Optional[CameraHints]:
    if not raw:
        return None
    behavior = str(raw.get("behavior", "none"))
    if behavior not in _VALID_CAMERA_BEHAVIORS:
        behavior = "none"
    zoom = max(1.0, min(1.18, float(raw.get("zoom_strength", 1.0))))
    follow = max(0.0, min(0.85, float(raw.get("follow_strength", 0.5))))
    return CameraHints(behavior=behavior, zoom_strength=zoom, follow_strength=follow, source="cloud")
