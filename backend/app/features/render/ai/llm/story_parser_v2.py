"""
story_parser_v2.py — parse the Super-Prompt response into a StoryPlan v2.

STRICTLY DEFENSIVE (Sacred Contract #3): returns None on any None/empty/unparseable
input; never raises. Extracts the JSON object even when wrapped in prose / code
fences (strip fences → first balanced object). Enforces the domain INVARIANTS via
StoryPlan.validate_refs + cap_visuals, and drops any AI-provided ``render`` block
(INV9 — render state is pipeline-filled only).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.domain.story_plan_v2 import StoryPlan

logger = logging.getLogger("app.render.story_parser_v2")

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _extract_json_object(raw: str) -> Optional[dict]:
    """Best-effort extract of the first JSON object. Strip fences → strict parse →
    brace-balanced substring salvage (string-aware). Returns dict or None."""
    if not raw or not isinstance(raw, str):
        return None
    s = _FENCE_RE.sub("", raw.strip())
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
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


def parse_super_plan_response(raw: "str | None", ceiling: int = 15) -> Optional[StoryPlan]:
    """Parse a Super-Prompt response → StoryPlan v2, or None. Never raises."""
    data = _extract_json_object(raw or "")
    if data is None:
        return None
    try:
        # INV9: the AI must not set render state — drop it if present.
        data.pop("render", None)
        plan = StoryPlan._from_dict(data)
        plan.validate_refs()          # INV1-8
        plan.cap_visuals(ceiling)     # INV6
        if plan.is_empty() or not plan.visuals:
            return None
        return plan
    except Exception as exc:
        logger.info("story_parser_v2: build error %s", exc)
        return None


__all__ = ["parse_super_plan_response"]
