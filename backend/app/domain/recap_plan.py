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

Shape (see docs/RECAP_REVIEW_SPEC.md) — R6 adds the EPISODE layer:

    RecapPlan
      schema_version: int
      total_target_sec: float          # AI-decided total recap length
      episodes: list[Episode]          # R6: AI splits a long film into 1..N
                                       #     episodes (each = its own output)
    Episode
      title: str                       # "Tập 1: ..." — episode card / file label
      acts: list[Act]
    Act
      title: str                       # chapter card title
      beat: str                        # setup|rising|climax|resolution
      scenes: list[RecapScene]
    RecapScene
      start, end: float                # seconds in the SOURCE film
      title: str                       # optional scene label
      narration: str                   # AI-authored recap voice-over (narrate)
      narration_intent: str            # fallback hint when `narration` is empty
      audio_mode: str                  # "narrate" | "original" (R6: let the
                                       #   source audio play instead of narrating)
      is_climax: bool

Back-compat: a legacy blob with top-level ``acts`` (pre-R6, no ``episodes``)
deserialises into a SINGLE episode wrapping those acts — old persisted recap
plans replay bit-identically. ``RecapPlan.acts`` stays available as a flattened
property so older consumers keep working.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 3  # R7: nested StoryModel (two-pass story understanding)

# Allowed per-scene audio modes. "narrate" = TTS the AI narration over the clip
# (default, conservative — the recap default behaviour). "original" = drop the
# narration and let the SOURCE audio play at full volume (AI marks the few
# dramatic beats it wants to land raw).
AUDIO_MODE_NARRATE = "narrate"
AUDIO_MODE_ORIGINAL = "original"


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
    # R6: "narrate" (TTS the narration) or "original" (let source audio play).
    audio_mode: str = AUDIO_MODE_NARRATE
    is_climax: bool = False


@dataclass
class Act:
    """A chapter of the recap — a group of consecutive scenes."""
    title: str = ""
    beat: str = ""               # setup|rising|climax|resolution|"" = unspecified
    scenes: list[RecapScene] = field(default_factory=list)


@dataclass
class Episode:
    """R6: one deliverable episode (Tập) — its own output video. AI splits a
    long film into 1..N of these at natural story breakpoints."""
    title: str = ""
    acts: list[Act] = field(default_factory=list)

    def scenes(self) -> list[RecapScene]:
        out: list[RecapScene] = []
        for act in self.acts:
            out.extend(act.scenes)
        return out

    def scene_count(self) -> int:
        return sum(len(a.scenes) for a in self.acts)


@dataclass
class StoryModel:
    """R7 — the recap's whole-film understanding, produced by the pass-1 "Story
    Understanding" LLM call BEFORE any scene selection. Pass-2 editorial planning
    is conditioned on it, and it is persisted for UI / future re-edit. Every field
    defaults empty so a partial/legacy blob never errors (Sacred Contract #3 spirit)."""
    summary: str = ""                                      # 3-6 sentence whole-film synopsis
    characters: list[str] = field(default_factory=list)   # principal characters (name — role/want)
    beats: list[str] = field(default_factory=list)         # key plot turns, chronological
    climax: str = ""                                       # the peak/turning point, one line
    ending: str = ""                                       # how the film resolves, one line


@dataclass
class RecapPlan:
    """AI-emitted plan for an act-structured recap, split into 1..N episodes."""
    schema_version: int = SCHEMA_VERSION
    total_target_sec: float = 0.0
    # R7: nested Story Model (pass-1 understanding). Replaces the v1 flat
    # ``story_summary`` field — back-compat preserved via the ``story_summary``
    # property + defensive ``_from_dict`` (a v1 blob's flat string is wrapped).
    story: "StoryModel" = field(default_factory=StoryModel)
    episodes: list[Episode] = field(default_factory=list)

    # ── Convenience ──────────────────────────────────────────────────────

    @property
    def story_summary(self) -> str:
        """Back-compat alias for the v1 flat field. Read-only — ``asdict``/
        ``to_json`` serialise the nested ``story`` object, not this property."""
        return self.story.summary

    @property
    def acts(self) -> list[Act]:
        """Flattened acts across all episodes — back-compat for consumers that
        predate the episode layer."""
        out: list[Act] = []
        for ep in self.episodes:
            out.extend(ep.acts)
        return out

    def scenes(self) -> list[RecapScene]:
        """Flatten all episodes→acts → a chronological list of scenes."""
        out: list[RecapScene] = []
        for ep in self.episodes:
            out.extend(ep.scenes())
        return out

    def scene_count(self) -> int:
        return sum(ep.scene_count() for ep in self.episodes)

    def episode_count(self) -> int:
        return len(self.episodes)

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
        episodes: list[Episode] = []
        raw_eps = data.get("episodes")
        if isinstance(raw_eps, list) and raw_eps:
            for entry in raw_eps:
                if isinstance(entry, dict):
                    episodes.append(_episode_from_dict(entry))
        else:
            # Legacy (pre-R6): acts live at the top level → wrap as one episode.
            raw_acts = data.get("acts")
            if isinstance(raw_acts, list) and raw_acts:
                acts = [_act_from_dict(a) for a in raw_acts if isinstance(a, dict)]
                if acts:
                    episodes.append(Episode(title="", acts=acts))
        # Story Model: prefer the R7 nested "story" object; fall back to the v1
        # flat "story_summary" string (wrap into a summary-only StoryModel).
        raw_story = data.get("story")
        if isinstance(raw_story, dict):
            story = story_model_from_dict(raw_story)
        else:
            story = StoryModel(summary=str(data.get("story_summary", "") or "").strip())
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), SCHEMA_VERSION),
            total_target_sec=_coerce_float(data.get("total_target_sec"), 0.0),
            story=story,
            episodes=episodes,
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


def _coerce_str_list(value: Any, max_items: int = 24) -> list[str]:
    """Coerce an arbitrary value into a clean list[str] — drops blanks, caps the
    count, accepts a single string. Never raises."""
    out: list[str] = []
    if isinstance(value, str):
        value = [value]
    if isinstance(value, (list, tuple)):
        for v in value:
            try:
                s = str(v or "").strip()
            except Exception:
                continue
            if s:
                out.append(s)
            if len(out) >= max_items:
                break
    return out


def story_model_from_dict(d: Any) -> "StoryModel":
    """Defensive StoryModel from a dict. Unknown keys dropped, missing keys
    default-empty. Never raises."""
    if not isinstance(d, dict):
        return StoryModel()
    return StoryModel(
        summary=str(d.get("summary", "") or "").strip(),
        characters=_coerce_str_list(d.get("characters")),
        beats=_coerce_str_list(d.get("beats")),
        climax=str(d.get("climax", "") or "").strip(),
        ending=str(d.get("ending", "") or "").strip(),
    )


def _coerce_audio_mode(value: Any) -> str:
    """Normalise to one of the two allowed modes. Default narrate (conservative —
    narration is the recap default; original is the AI's explicit opt-in)."""
    s = str(value or "").strip().lower()
    if s in ("original", "source", "raw", "keep", "keep_original", "silent"):
        return AUDIO_MODE_ORIGINAL
    return AUDIO_MODE_NARRATE


def _scene_from_dict(d: dict[str, Any]) -> RecapScene:
    return RecapScene(
        start=_coerce_float(d.get("start"), 0.0),
        end=_coerce_float(d.get("end"), 0.0),
        title=str(d.get("title", "") or ""),
        narration=str(d.get("narration", "") or ""),
        narration_intent=str(d.get("narration_intent", "") or ""),
        audio_mode=_coerce_audio_mode(d.get("audio_mode")),
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


def _episode_from_dict(d: dict[str, Any]) -> Episode:
    acts: list[Act] = []
    raw_acts = d.get("acts")
    if isinstance(raw_acts, list):
        for a in raw_acts:
            if isinstance(a, dict):
                acts.append(_act_from_dict(a))
    return Episode(
        title=str(d.get("title", "") or ""),
        acts=acts,
    )
