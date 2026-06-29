"""
recap_plan.py — RecapPlan dataclass for the Recap/Review Film render mode.

Pure domain object: no FFmpeg, no file I/O, no LLM SDK. JSON (de)serialise
only. Mirrors the defensive contract of render_plan.py:

- Every field has a safe default; loading a legacy/partial blob never errors.
- ``from_json`` is strictly defensive — unknown keys dropped, malformed values
  fall back to defaults, NEVER raises (Sacred Contract #3 spirit; the AI /
  pipeline paths must not crash a render job).
- ``to_json`` is deterministic (sorted keys, compact) so the persisted blob is
  stable across rebuilds.

Shape (see docs/RECAP_REVIEW_SPEC.md):

    RecapPlan
      schema_version: int
      total_target_sec: float          # AI-decided recap length (scaled to film)
      acts: list[Act]
    Act
      title: str                       # chapter card title
      beat: str                        # setup|rising|climax|resolution
      scenes: list[RecapScene]
    RecapScene
      start, end: float                # seconds in the SOURCE film
      title: str                       # optional scene label
      narration_intent: str           # what the narrator should convey
      is_climax: bool                  # eligible for reaction freeze
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 1


@dataclass
class RecapScene:
    """One source scene selected for the recap, in chronological order."""
    start: float = 0.0
    end: float = 0.0
    title: str = ""
    # AI-authored recap narration spoken over this scene (the actual text, not
    # just an intent). Written with whole-film understanding so the recap is
    # cohesive end-to-end. The engine TTS's this directly — no per-scene rewrite.
    narration: str = ""
    narration_intent: str = ""   # legacy/fallback hint when `narration` is empty
    is_climax: bool = False


@dataclass
class Act:
    """A chapter of the recap — a group of consecutive scenes."""
    title: str = ""
    beat: str = ""               # setup|rising|climax|resolution|"" = unspecified
    scenes: list[RecapScene] = field(default_factory=list)


@dataclass
class RecapPlan:
    """AI-emitted plan for a single long, act-structured recap video."""
    schema_version: int = SCHEMA_VERSION
    total_target_sec: float = 0.0
    acts: list[Act] = field(default_factory=list)

    # ── Convenience ──────────────────────────────────────────────────────

    def scenes(self) -> list[RecapScene]:
        """Flatten all acts → a chronological list of scenes."""
        out: list[RecapScene] = []
        for act in self.acts:
            out.extend(act.scenes)
        return out

    def scene_count(self) -> int:
        return sum(len(a.scenes) for a in self.acts)

    # ── Serialisation ────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Deterministic JSON dump — sorted keys, compact separators."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: "str | bytes | None") -> Optional["RecapPlan"]:
        """Defensive deserialise. Returns None on None/empty/unparseable input;
        unknown keys dropped; missing keys fall back to defaults. Never raises."""
        if raw is None:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "RecapPlan":
        acts: list[Act] = []
        raw_acts = data.get("acts")
        if isinstance(raw_acts, list):
            for entry in raw_acts:
                if isinstance(entry, dict):
                    acts.append(_act_from_dict(entry))
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), SCHEMA_VERSION),
            total_target_sec=_coerce_float(data.get("total_target_sec"), 0.0),
            acts=acts,
        )


# ── Internal helpers ─────────────────────────────────────────────────────────


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off", ""):
            return False
    return default


def _scene_from_dict(d: dict[str, Any]) -> RecapScene:
    return RecapScene(
        start=_coerce_float(d.get("start"), 0.0),
        end=_coerce_float(d.get("end"), 0.0),
        title=str(d.get("title", "") or ""),
        narration=str(d.get("narration", "") or ""),
        narration_intent=str(d.get("narration_intent", "") or ""),
        is_climax=_coerce_bool(d.get("is_climax"), False),
    )


def _act_from_dict(d: dict[str, Any]) -> Act:
    scenes: list[RecapScene] = []
    raw_scenes = d.get("scenes")
    if isinstance(raw_scenes, list):
        for s in raw_scenes:
            if isinstance(s, dict):
                scenes.append(_scene_from_dict(s))
    return Act(
        title=str(d.get("title", "") or ""),
        beat=str(d.get("beat", "") or ""),
        scenes=scenes,
    )
