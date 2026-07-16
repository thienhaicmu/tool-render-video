"""
story_script_structurer.py — Phase 4 (2026-07-16): script → StoryPlan by CODE.

The Writer's script format is mandatory and machine-readable ([SCENE: slug] /
NARR: / "Name (emotion): \"line\""), and the Structure gate requires the plan to
keep the script wording VERBATIM — i.e. the LLM Structure call is ~80% a
mechanical transform. This module performs that transform deterministically:

    settings   ← one per distinct [SCENE:] slug
    visuals    ← one per setting (reused across its beats; capped by ceiling)
    characters ← Understanding's pinned cast + any new dialogue speakers
    timeline   ← NARR paragraph → narrator beat; a run of consecutive dialogue
                 lines → one beat with lines[] (or one beat per line when the
                 multiline contract is off); wording verbatim by construction
    hook       ← the first beat

Camera/shot grammar, pacing labels and character assets remain code-derived
downstream (derive_scene_shot_grammar / derive_beat_styling / V3 resolver), so
nothing creative is lost that the engine actually consumes.

Used as the Economy-mode structurer and as the FALLBACK when the LLM Structure
call (and its bounded retry) fails — replacing the legacy full re-buy.

Pure + defensive (Sacred Contract #3 spirit): returns None on unusable input;
never raises; zero LLM calls, zero I/O.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.domain.story_plan_v2 import StoryPlan
from app.features.render.ai.llm.story_understanding import (
    StoryUnderstanding, _norm as _norm_text, _slug,
)

logger = logging.getLogger("app.render.story_script_structurer")

_SCENE_RE = re.compile(r"^\[SCENE\s*:\s*([^\]]+)\]\s*$", re.IGNORECASE)
_NARR_RE = re.compile(r"^NARR\s*:\s*(.+)$", re.IGNORECASE)
_DIALOG_RE = re.compile(
    r"^(?!NARR\b)([^:\n\[\]]{1,60}?)\s*(?:\(([^)]{0,24})\))?\s*:\s*[\"“](.*?)[\"”]?\s*$")

_EMOTIONS = {"normal", "happy", "angry", "sad", "surprised"}


def _match_speaker(name: str, known: "dict[str, str]") -> Optional[str]:
    """Fuzzy match a script speaker name to a known character id (normalised
    containment either way — same rule as the script validator)."""
    n = _norm_text(name)
    if not n:
        return None
    for norm_name, cid in known.items():
        if n in norm_name or norm_name in n:
            return cid
    return None


def structure_script_by_code(script: str, understanding: "Optional[StoryUnderstanding]" = None,
                             *, language: str = "vi", ceiling: int = 15,
                             genre: str = "", multiline: bool = True) -> Optional[StoryPlan]:
    """Deterministically structure a screenplay-lite SCRIPT into a StoryPlan.
    Returns None when the script yields no usable timeline. Never raises."""
    try:
        text = (script or "").strip()
        if not text:
            return None

        characters: "list[dict]" = []
        known: "dict[str, str]" = {}   # normalised name/id → character id
        if understanding is not None:
            for c in understanding.characters:
                cid = str(c.get("id") or "").strip()
                if not cid:
                    continue
                characters.append({
                    "id": cid, "name": str(c.get("name") or cid),
                    "gender": str(c.get("gender") or ""),
                    "canonical_desc": str(c.get("desc") or ""),
                })
                known[_norm_text(str(c.get("name") or cid))] = cid
                known[_norm_text(cid)] = cid

        settings: "list[dict]" = []
        setting_ids: "dict[str, str]" = {}   # slug → setting id
        visuals: "list[dict]" = []
        visual_by_setting: "dict[str, str]" = {}
        timeline: "list[dict]" = []
        pending_lines: "list[dict]" = []
        current_visual = ""

        def _ensure_scene(raw_name: str) -> None:
            nonlocal current_visual
            slug = _slug(raw_name) or f"scene_{len(settings) + 1}"
            sid = setting_ids.get(slug)
            if sid is None:
                sid = slug
                setting_ids[slug] = sid
                settings.append({"id": sid, "name": raw_name.strip() or sid})
                vid = f"v{len(visuals) + 1}"
                visuals.append({"id": vid, "setting_id": sid})
                visual_by_setting[sid] = vid
            current_visual = visual_by_setting[sid]

        def _flush_dialogue() -> None:
            nonlocal pending_lines
            if not pending_lines:
                return
            if multiline:
                timeline.append({"id": f"b{len(timeline) + 1}", "visual_id": current_visual,
                                 "narration": "", "lines": pending_lines})
            else:
                for ln in pending_lines:
                    timeline.append({"id": f"b{len(timeline) + 1}", "visual_id": current_visual,
                                     "narration": ln["text"], "speaker_id": ln["speaker_id"],
                                     "emotion": ln["emotion"]})
            pending_lines = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            m = _SCENE_RE.match(line)
            if m:
                _flush_dialogue()
                _ensure_scene(m.group(1))
                continue
            if not current_visual:
                _ensure_scene("scene 1")
            m = _NARR_RE.match(line)
            if m:
                _flush_dialogue()
                timeline.append({"id": f"b{len(timeline) + 1}", "visual_id": current_visual,
                                 "narration": m.group(1).strip()})
                continue
            m = _DIALOG_RE.match(line)
            if m:
                name = m.group(1).strip()
                emotion = (m.group(2) or "").strip().lower()
                spoken = (m.group(3) or "").strip()
                if not spoken:
                    continue
                cid = _match_speaker(name, known)
                if cid is None:
                    cid = _slug(name)
                    if cid and cid not in {c["id"] for c in characters}:
                        characters.append({"id": cid, "name": name})
                        known[_norm_text(name)] = cid
                pending_lines.append({
                    "speaker_id": cid or "", "text": spoken,
                    "emotion": emotion if emotion in _EMOTIONS else "normal",
                })
                continue
            # Bare prose line (writer omitted the NARR prefix) → narrator beat.
            _flush_dialogue()
            timeline.append({"id": f"b{len(timeline) + 1}", "visual_id": current_visual,
                             "narration": line})
        _flush_dialogue()

        if not timeline or not visuals:
            return None
        timeline[0]["hook"] = True
        plan = StoryPlan._from_dict({
            "topic": (understanding.topic if understanding is not None else "")[:200],
            "tone": (understanding.tone if understanding is not None else ""),
            "language": language,
            "characters": characters,
            "settings": settings,
            "visuals": visuals,
            "timeline": timeline,
        })
        plan.cap_visuals(max(1, int(ceiling or 15)))
        plan.validate_refs()
        if plan.is_empty() or not plan.visuals:
            return None
        logger.info("story_script_structurer: OK settings=%d visuals=%d beats=%d chars=%d",
                    len(plan.settings), len(plan.visuals), len(plan.timeline),
                    len(plan.characters))
        return plan
    except Exception as exc:
        logger.info("story_script_structurer: failed %s", exc)
        return None


__all__ = ["structure_script_by_code"]
