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

from app.domain.recap_plan import (
    EditorialBlueprint,
    RecapPlan,
    StoryModel,
    editorial_blueprint_from_dict,
    story_model_from_dict,
)

logger = logging.getLogger("app.render.llm_recap_parser")

# Minimum recap scene length — safety net against the AI emitting subtitle-line
# fragments (2–5s) that make a choppy montage. Short scenes are MERGED into a
# neighbour. Override via RECAP_MIN_SCENE_SEC.
import os as _os
_RECAP_MIN_SCENE_SEC: float = max(0.0, float(_os.getenv("RECAP_MIN_SCENE_SEC", "6") or 6))
# R6 — hard cap on episode count (soft-guided in the prompt, enforced here).
_RECAP_MAX_EPISODES: int = max(1, int(_os.getenv("RECAP_MAX_EPISODES", "4") or 4))


def _merge_two_modes(a: str, b: str) -> str:
    """Audio mode of a merged scene: narrate wins (only stays original when BOTH
    are original) so a short 'original' fragment folded into a narrated beat
    doesn't silence the narration."""
    return "original" if (a == "original" and b == "original") else "narrate"


def _merge_short_scenes(scenes: list[dict], min_sec: float) -> list[dict]:
    """Merge consecutive scenes shorter than min_sec into a neighbour so no
    2–5s fragments survive. Combines is_climax + audio_mode + keeps the first
    non-empty narration_intent. Never raises."""
    if not scenes or min_sec <= 0:
        return scenes
    try:
        out: list[dict] = [dict(scenes[0])]
        for s in scenes[1:]:
            prev = out[-1]
            if (prev["end"] - prev["start"]) < min_sec:
                prev["end"] = s["end"]
                prev["is_climax"] = bool(prev.get("is_climax")) or bool(s.get("is_climax"))
                prev["audio_mode"] = _merge_two_modes(
                    str(prev.get("audio_mode") or "narrate"), str(s.get("audio_mode") or "narrate"))
                # Concatenate the AI-authored narration so the merged scene keeps
                # both lines (the engine speaks the combined text).
                if s.get("narration"):
                    prev["narration"] = (str(prev.get("narration", "")).strip() + " " + s["narration"]).strip()
                if not prev.get("narration_intent") and s.get("narration_intent"):
                    prev["narration_intent"] = s["narration_intent"]
                if not prev.get("title") and s.get("title"):
                    prev["title"] = s["title"]
                # A merged scene that ended up narrate must not have empty text.
                if prev["audio_mode"] == "narrate" and not str(prev.get("narration", "")).strip():
                    prev["narration"] = str(s.get("narration", "") or "").strip()
            else:
                out.append(dict(s))
        # If the final scene is still too short, fold it back into its neighbour.
        if len(out) >= 2 and (out[-1]["end"] - out[-1]["start"]) < min_sec:
            last = out.pop()
            out[-1]["end"] = last["end"]
            out[-1]["is_climax"] = bool(out[-1].get("is_climax")) or bool(last.get("is_climax"))
            out[-1]["audio_mode"] = _merge_two_modes(
                str(out[-1].get("audio_mode") or "narrate"), str(last.get("audio_mode") or "narrate"))
        return out
    except Exception:
        return scenes

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
    """Recover a usable dict from a TRUNCATED JSON response (the recap output is
    large and can be cut off by the model's token limit). Tries to balance-close
    the whole thing, then progressively trims back to earlier '}' boundaries
    (dropping the cut-off tail scene). Returns the first dict that has 'acts'."""
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
            if not isinstance(d, dict):
                continue
            # Accept either the R6 episode shape or the legacy top-level acts.
            if isinstance(d.get("episodes"), list) and d["episodes"]:
                return d
            if isinstance(d.get("acts"), list) and d["acts"]:
                return d
        return None
    except Exception:
        return None


def _norm_audio_mode(v) -> str:
    s = str(v or "").strip().lower()
    return "original" if s in ("original", "source", "raw", "keep", "keep_original", "silent") else "narrate"


def _clean_act(act: dict, dur: float) -> Optional[dict]:
    """Clean one act dict → {title, beat, scenes[]} or None if it has no usable
    scene. Clamps + merges short scenes; carries R6 audio_mode."""
    if not isinstance(act, dict):
        return None
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
        mode = _norm_audio_mode(s.get("audio_mode"))
        narration = str(s.get("narration", "") or "").strip()
        # An "original" scene plays the source audio — never carries narration.
        if mode == "original":
            narration = ""
        scenes_out.append({
            "start": round(st, 3), "end": round(en, 3),
            "title": str(s.get("title", "") or "").strip(),
            "narration": narration,
            "narration_intent": str(s.get("narration_intent", "") or "").strip(),
            "audio_mode": mode,
            "is_climax": bool(s.get("is_climax", False)),
        })
    if not scenes_out:
        return None
    scenes_out.sort(key=lambda x: x["start"])
    scenes_out = _merge_short_scenes(scenes_out, _RECAP_MIN_SCENE_SEC)
    return {
        "title": str(act.get("title", "") or "").strip(),
        "beat": str(act.get("beat", "") or "").strip().lower(),
        "scenes": scenes_out,
    }


def _clean(data: dict, video_duration: float) -> Optional[RecapPlan]:
    """Build + clamp a RecapPlan from a parsed dict. Handles both the R6 episode
    shape and the legacy top-level-acts shape. Returns None if nothing usable."""
    dur = float(video_duration) if video_duration and video_duration > 0 else 0.0

    # Normalise input to a list of raw episode dicts ({title, acts[]}). Legacy
    # blobs (top-level "acts", no "episodes") become a single episode.
    raw_eps = data.get("episodes")
    if isinstance(raw_eps, list) and raw_eps:
        raw_episodes = [e for e in raw_eps if isinstance(e, dict)]
    elif isinstance(data.get("acts"), list) and data["acts"]:
        raw_episodes = [{"title": "", "acts": data["acts"]}]
    else:
        return None

    episodes_out: list[dict] = []
    for ep in raw_episodes:
        acts_out: list[dict] = []
        for act in (ep.get("acts") or []):
            cleaned = _clean_act(act, dur)
            if cleaned:
                acts_out.append(cleaned)
        if acts_out:
            episodes_out.append({"title": str(ep.get("title", "") or "").strip(), "acts": acts_out})
    if not episodes_out:
        return None

    # Enforce the episode cap: fold any overflow episodes' acts into the last
    # kept episode (keeps every scene, just fewer deliverables).
    if len(episodes_out) > _RECAP_MAX_EPISODES:
        head = episodes_out[: _RECAP_MAX_EPISODES]
        for extra in episodes_out[_RECAP_MAX_EPISODES:]:
            head[-1]["acts"].extend(extra["acts"])
        episodes_out = head

    # total_target_sec: trust the model but clamp to (0, film duration]; fall
    # back to the summed scene durations when missing/insane.
    summed = sum(sc["end"] - sc["start"] for e in episodes_out for a in e["acts"] for sc in a["scenes"])
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
        # Carry the AI's whole-film understanding through (was silently dropped).
        # Works for both the episode shape and the legacy top-level-acts shape —
        # `data` is the raw top-level dict in both cases.
        "story_summary": str(data.get("story_summary", "") or "").strip(),
        "episodes": episodes_out,
    }))


def _salvage_story(raw: str) -> Optional[dict]:
    """Recover a Story Model dict from a TRUNCATED pass-1 response. Balance-close
    the prefix, progressively trimming to earlier '}' boundaries. Returns the
    first dict carrying any StoryModel key. Never raises."""
    try:
        i = raw.find("{")
        if i < 0:
            return None
        s = raw[i:]
        candidates = [_balance_close(s)]
        pos = len(s)
        for _ in range(8):
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
            if isinstance(d, dict) and any(
                k in d for k in ("summary", "characters", "beats", "climax", "ending")
            ):
                return d
        return None
    except Exception:
        return None


def parse_story_model_response(raw: str) -> Optional[StoryModel]:
    """Parse the pass-1 Story Model LLM response into a StoryModel. Returns None on
    any failure or when nothing usable was produced (Sacred Contract #3)."""
    try:
        if not raw or not str(raw).strip():
            return None
        text = _strip_wrappers(str(raw).strip())
        data = _extract_json_object(text)
        if not isinstance(data, dict):
            data = _salvage_story(text)
            if isinstance(data, dict):
                logger.warning("recap_parser: story model response was truncated — salvaged")
        if not isinstance(data, dict):
            logger.warning("recap_parser: no story model JSON found")
            return None
        sm = story_model_from_dict(data)
        if sm.is_empty():
            logger.warning("recap_parser: story model empty after cleaning")
            return None
        return sm
    except Exception as exc:
        logger.warning("recap_parser: story model parse error %s", exc, exc_info=True)
        return None


def _salvage_editorial(raw: str) -> Optional[dict]:
    """Recover an Editorial Blueprint dict from a TRUNCATED pass-2 response.
    Balance-close the prefix, progressively trimming to earlier '}' boundaries.
    Returns the first dict carrying any EditorialBlueprint key. Never raises."""
    try:
        i = raw.find("{")
        if i < 0:
            return None
        s = raw[i:]
        candidates = [_balance_close(s)]
        pos = len(s)
        for _ in range(8):
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
            if isinstance(d, dict) and any(
                k in d for k in ("episode_count", "episode_rationale", "pacing", "beats")
            ):
                return d
        return None
    except Exception:
        return None


def parse_editorial_response(raw: str) -> Optional[EditorialBlueprint]:
    """Parse the pass-2 Editorial Blueprint LLM response into an EditorialBlueprint.
    Returns None on any failure or when nothing usable was produced (Sacred #3)."""
    try:
        if not raw or not str(raw).strip():
            return None
        text = _strip_wrappers(str(raw).strip())
        data = _extract_json_object(text)
        if not isinstance(data, dict):
            data = _salvage_editorial(text)
            if isinstance(data, dict):
                logger.warning("recap_parser: editorial response was truncated — salvaged")
        if not isinstance(data, dict):
            logger.warning("recap_parser: no editorial JSON found")
            return None
        eb = editorial_blueprint_from_dict(data)
        if eb.is_empty():
            logger.warning("recap_parser: editorial blueprint empty after cleaning")
            return None
        return eb
    except Exception as exc:
        logger.warning("recap_parser: editorial parse error %s", exc, exc_info=True)
        return None


def parse_recap_response(raw: str, video_duration: float) -> Optional[RecapPlan]:
    """Parse the recap LLM response into a RecapPlan. None on any failure."""
    try:
        if not raw or not str(raw).strip():
            return None
        text = _strip_wrappers(str(raw).strip())
        data = _extract_json_object(text)
        if not isinstance(data, dict):
            # The recap output is large and can be truncated by the token limit
            # → salvage the complete prefix (drops only the cut-off tail scene).
            data = _salvage_json(text)
            if isinstance(data, dict):
                _n = len(data.get("episodes") or data.get("acts") or [])
                logger.warning("recap_parser: response was truncated — salvaged %d episode/act group(s)", _n)
        if not isinstance(data, dict):
            logger.warning("recap_parser: no JSON object found (even after salvage)")
            return None
        plan = _clean(data, video_duration)
        if plan is None or not plan.acts:
            logger.warning("recap_parser: no usable acts after cleaning")
            return None
        return plan
    except Exception as exc:
        logger.warning("recap_parser: unexpected error %s", exc, exc_info=True)
        return None
