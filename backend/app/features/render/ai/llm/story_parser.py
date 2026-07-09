"""
story_parser.py — parse Story Intelligence LLM responses (P1).

- ``parse_story_digest_response``  → dict {summary, beats, characters, environments}
- ``parse_story_reduce_response``  → (StoryBible, meta) where meta carries
  topic/tone/audience/video_style/rolling_summary.

Both are STRICTLY DEFENSIVE (Sacred Contract #3): return None on any
None/empty/unparseable input, drop unknown keys, never raise. JSON is extracted
even when the model wrapped it in prose / code fences (strip fences → first
balanced object). Reuses the StoryPlan domain loaders so a character/environment
parsed here is identical to one loaded from a persisted plan.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.domain.story_plan import (
    StoryBible, StoryScene, _character_from_dict, _environment_from_dict,
    _coerce_str_list, _scene_from_dict,
)

logger = logging.getLogger("app.render.story_parser")

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _extract_json_object(raw: str) -> Optional[dict]:
    """Best-effort extract of the first JSON object from a model response. Strips
    code fences, then tries a strict parse, then a brace-balanced substring
    salvage. Returns a dict or None. Never raises."""
    if not raw or not isinstance(raw, str):
        return None
    s = _FENCE_RE.sub("", raw.strip())
    # Strict first.
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    # Salvage: first '{' to its matching '}' (balance scan, string-aware).
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def parse_story_digest_response(raw: "str | None") -> Optional[dict]:
    """Parse a pass-1 chunk digest. Returns {summary, beats[], characters[],
    environments[]} (characters/environments as StoryCharacter/StoryEnvironment
    dataclasses) or None. Never raises."""
    data = _extract_json_object(raw or "")
    if data is None:
        return None
    try:
        chars = []
        for entry in (data.get("characters") or []):
            c = _character_from_dict(entry)
            if c is not None:
                chars.append(c)
        envs = []
        for entry in (data.get("environments") or []):
            e = _environment_from_dict(entry)
            if e is not None:
                envs.append(e)
        return {
            "summary": str(data.get("summary", "") or "").strip(),
            "beats": _coerce_str_list(data.get("beats"), max_items=40),
            "characters": chars,
            "environments": envs,
        }
    except Exception as exc:
        logger.info("story_parser: digest parse error %s", exc)
        return None


def parse_story_reduce_response(raw: "str | None") -> "Optional[tuple[StoryBible, dict]]":
    """Parse a pass-2 reduce into (StoryBible, meta). meta = {topic, tone,
    audience, video_style, rolling_summary}. Returns None on unparseable input.
    Never raises."""
    data = _extract_json_object(raw or "")
    if data is None:
        return None
    try:
        chars = []
        for entry in (data.get("characters") or []):
            c = _character_from_dict(entry)
            if c is not None:
                chars.append(c)
        envs = []
        for entry in (data.get("environments") or []):
            e = _environment_from_dict(entry)
            if e is not None:
                envs.append(e)
        bible = StoryBible(
            setting=str(data.get("setting", "") or "").strip(),
            hook=str(data.get("hook", "") or "").strip(),
            cta=str(data.get("cta", "") or "").strip(),
            characters=chars,
            environments=envs,
        )
        meta = {
            "topic": str(data.get("topic", "") or "").strip(),
            "tone": str(data.get("tone", "") or "").strip(),
            "audience": str(data.get("audience", "") or "").strip(),
            "video_style": str(data.get("video_style", "") or "").strip(),
            "rolling_summary": str(data.get("rolling_summary", "") or "").strip(),
        }
        # A reduce that yielded nothing usable → None (caller degrades).
        if bible.is_empty() and not meta["rolling_summary"] and not meta["topic"]:
            return None
        return bible, meta
    except Exception as exc:
        logger.info("story_parser: reduce parse error %s", exc)
        return None


def parse_storyboard_response(raw: "str | None") -> "Optional[list]":
    """Parse a pass-3 storyboard response into a list[StoryScene] (each with its
    shots), reusing the StoryPlan domain loader so a scene/shot here is identical
    to one loaded from a persisted plan. Returns None on unparseable input or when
    no scene carries a narrated shot. Never raises."""
    data = _extract_json_object(raw or "")
    if data is None:
        return None
    try:
        raw_scenes = data.get("scenes")
        if not isinstance(raw_scenes, list):
            return None
        scenes: list[StoryScene] = []
        for i, entry in enumerate(raw_scenes):
            if isinstance(entry, dict):
                scene = _scene_from_dict(entry, i)
                # Drop shots with no narration (they'd produce no TTS).
                scene.shots = [sh for sh in scene.shots if (sh.narration or "").strip()]
                if scene.shots:
                    scenes.append(scene)
        return scenes or None
    except Exception as exc:
        logger.info("story_parser: storyboard parse error %s", exc)
        return None


__all__ = [
    "parse_story_digest_response", "parse_story_reduce_response",
    "parse_storyboard_response",
]
