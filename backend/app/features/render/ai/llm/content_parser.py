"""
content_parser.py — Parse the Content Director LLM response into a ContentPlan.

Defensive: never raises, returns None on any failure (Sacred Contract #3).
Drops scenes with empty narration, clamps reading_speed via the ContentPlan
loader, re-indexes scenes in order, and recomputes total_target_sec defensively.

The Content output is small (an article-length plan), but the model can still
truncate at its token limit — so the parser tries a strict JSON parse, then a
substring extract, then a balance-close salvage of the complete prefix.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.domain.content_plan import ContentPlan

logger = logging.getLogger("app.render.llm_content_parser")

_FENCE_RE = re.compile(r"^\s*```(?:[a-z]+)?\s*\n?|\n?\s*```\s*$", re.IGNORECASE)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_wrappers(text: str) -> str:
    text = _FENCE_RE.sub("", text).strip()
    text = _FENCE_RE.sub("", text).strip()
    return text


def _extract_json_object(raw: str) -> Optional[dict]:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    m = _JSON_OBJECT_RE.search(raw)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return None


def _balance_close(s: str) -> str:
    """Close any unterminated string + open brackets so a truncated JSON parses.
    Drops a dangling trailing comma. Pragmatic — recovers the complete prefix."""
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack:
                stack.pop()
    res = s
    if in_str:
        res += '"'
    res = res.rstrip()
    if res.endswith(","):
        res = res[:-1]
    res += "".join(reversed(stack))
    return res


def _salvage_json(raw: str) -> Optional[dict]:
    """Recover a usable dict from a TRUNCATED JSON response. Balance-close the
    whole thing, then progressively trim back to earlier '}' boundaries (dropping
    the cut-off tail scene). Returns the first dict that carries 'scenes'."""
    try:
        i = raw.find("{")
        if i < 0:
            return None
        s = raw[i:]
        candidates = [_balance_close(s)]
        pos = len(s)
        for _ in range(12):
            j = s.rfind("}", 0, pos)
            if j < 0:
                break
            candidates.append(_balance_close(s[: j + 1]))
            pos = j
        for cand in candidates:
            try:
                d = json.loads(cand)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(d, dict) and isinstance(d.get("scenes"), list) and d["scenes"]:
                return d
        return None
    except Exception:
        return None


def _clean(data: dict, target_duration: float) -> Optional[ContentPlan]:
    """Build a ContentPlan from a parsed dict: drop empty-narration scenes,
    re-index in order, recompute total_target_sec. Returns None if nothing usable."""
    raw_scenes = data.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        return None

    scenes_out: list[dict] = []
    for s in raw_scenes:
        if not isinstance(s, dict):
            continue
        narration = str(s.get("narration", "") or "").strip()
        if not narration:
            continue  # a scene with no voice-over has nothing to render/speak
        entry = dict(s)
        entry["narration"] = narration
        entry["index"] = len(scenes_out)  # re-index densely, in emitted order
        scenes_out.append(entry)
    if not scenes_out:
        return None

    # total_target_sec: trust the model when sane, else fall back to the summed
    # per-scene estimates, else the caller's target duration.
    try:
        total = float(data.get("total_target_sec") or 0.0)
    except (TypeError, ValueError):
        total = 0.0
    if total <= 0:
        summed = 0.0
        for s in scenes_out:
            try:
                summed += max(0.0, float(s.get("est_duration_sec") or 0.0))
            except (TypeError, ValueError):
                pass
        total = summed if summed > 0 else max(0.0, float(target_duration or 0.0))

    normalised = dict(data)
    normalised["scenes"] = scenes_out
    normalised["total_target_sec"] = round(total, 3)
    # ContentPlan.from_json applies all per-field defensive coercion + clamps.
    return ContentPlan.from_json(json.dumps(normalised, ensure_ascii=False))


def parse_content_plan_response(raw: str, target_duration: float = 0.0) -> Optional[ContentPlan]:
    """Parse the Content Director LLM response into a ContentPlan. Returns None on
    any failure or when nothing usable was produced (Sacred Contract #3)."""
    try:
        if not raw or not str(raw).strip():
            return None
        text = _strip_wrappers(str(raw).strip())
        data = _extract_json_object(text)
        if not isinstance(data, dict):
            data = _salvage_json(text)
            if isinstance(data, dict):
                _n = len(data.get("scenes") or [])
                logger.warning("content_parser: response was truncated — salvaged %d scene(s)", _n)
        if not isinstance(data, dict):
            logger.warning("content_parser: no JSON object found (even after salvage)")
            return None
        plan = _clean(data, target_duration)
        if plan is None or plan.is_empty():
            logger.warning("content_parser: no usable scenes after cleaning")
            return None
        return plan
    except Exception as exc:
        logger.warning("content_parser: unexpected error %s", exc, exc_info=True)
        return None
