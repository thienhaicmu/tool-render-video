"""
recap_parser.py — Parse the recap selection LLM response into a RecapPlan.

Defensive: never raises, returns None on any failure (Sacred Contract #3).
Clamps scene times to the film duration, drops invalid scenes/acts, keeps
acts in order, and recomputes total_target_sec defensively.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.domain.recap_plan import RecapPlan

logger = logging.getLogger("app.render.llm_recap_parser")

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


def _clean(data: dict, video_duration: float) -> Optional[RecapPlan]:
    """Build + clamp a RecapPlan from a parsed dict. Returns None if nothing usable."""
    dur = float(video_duration) if video_duration and video_duration > 0 else 0.0
    acts_out: list[dict] = []
    raw_acts = data.get("acts")
    if not isinstance(raw_acts, list):
        return None
    for act in raw_acts:
        if not isinstance(act, dict):
            continue
        scenes_out: list[dict] = []
        for s in (act.get("scenes") or []):
            if not isinstance(s, dict):
                continue
            try:
                st = float(s.get("start"))
                en = float(s.get("end"))
            except (TypeError, ValueError):
                continue
            if st < 0:
                st = 0.0
            if dur and en > dur:
                en = dur
            if en <= st or (en - st) < 0.3:
                continue
            scenes_out.append({
                "start": round(st, 3), "end": round(en, 3),
                "title": str(s.get("title", "") or "").strip(),
                "narration_intent": str(s.get("narration_intent", "") or "").strip(),
                "is_climax": bool(s.get("is_climax", False)),
            })
        if not scenes_out:
            continue
        scenes_out.sort(key=lambda x: x["start"])
        acts_out.append({
            "title": str(act.get("title", "") or "").strip(),
            "beat": str(act.get("beat", "") or "").strip().lower(),
            "scenes": scenes_out,
        })
    if not acts_out:
        return None

    # total_target_sec: trust the model but clamp to (0, film duration]; fall
    # back to the summed scene durations when missing/insane.
    summed = sum(sc["end"] - sc["start"] for a in acts_out for sc in a["scenes"])
    try:
        total = float(data.get("total_target_sec") or 0.0)
    except (TypeError, ValueError):
        total = 0.0
    if total <= 0:
        total = summed
    if dur and total > dur:
        total = dur

    return RecapPlan.from_json(json.dumps({
        "total_target_sec": round(total, 3),
        "acts": acts_out,
    }))


def parse_recap_response(raw: str, video_duration: float) -> Optional[RecapPlan]:
    """Parse the recap LLM response into a RecapPlan. None on any failure."""
    try:
        if not raw or not str(raw).strip():
            return None
        text = _strip_wrappers(str(raw).strip())
        data = _extract_json_object(text)
        if not isinstance(data, dict):
            logger.warning("recap_parser: no JSON object found")
            return None
        plan = _clean(data, video_duration)
        if plan is None or not plan.acts:
            logger.warning("recap_parser: no usable acts after cleaning")
            return None
        return plan
    except Exception as exc:
        logger.warning("recap_parser: unexpected error %s", exc, exc_info=True)
        return None
