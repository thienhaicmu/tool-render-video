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

SCHEMA_VERSION = 4  # R7.3: nested EditorialBlueprint (story → editorial → binding)

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
    # Structural PHASE of the act. NOTE: this is unrelated to StoryModel.beats
    # (which are plot turns) — see the act_phase alias below. Wire key stays
    # ``beat`` for back-compat.
    beat: str = ""               # setup|rising|climax|resolution|"" = unspecified
    scenes: list[RecapScene] = field(default_factory=list)

    @property
    def act_phase(self) -> str:
        """Clearer read-only alias for ``beat`` — the act's structural PHASE
        (setup|rising|climax|resolution). Distinct from StoryModel.plot_turns.
        The persisted key stays ``beat`` (asdict serialises the field, not this)."""
        return self.beat


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


# StoryModel's OWN schema version (independent of RecapPlan.SCHEMA_VERSION). v1 =
# flat str characters/beats; v2 = Character/StoryBeat entities + theme/genre/
# conflict/resolution/emotional_curve. Bumped here, read defensively everywhere.
STORY_SCHEMA_VERSION = 2


@dataclass
class Character:
    """A principal character entity (v2). Replaces the v1 free-string
    "name — role/want". Serialises as a dict; coerces from a v1 string."""
    name: str = ""
    role: str = ""    # who they are / their narrative function
    want: str = ""    # what they want — the motor of their arc

    def __str__(self) -> str:
        bits = [b for b in (self.name.strip(), self.role.strip()) if b]
        s = " — ".join(bits)
        want = self.want.strip()
        if want:
            s = (f"{s} (wants {want})").strip() if s else f"wants {want}"
        return s


@dataclass
class StoryBeat:
    """A key plot turn (v2). Replaces the v1 free-string beat. ``t`` is an
    OPTIONAL source-second anchor (-1 = unanchored) so beats can later be tied
    to scenes; ``kind`` is a free tag (setup|turn|reveal|climax|resolution|…)."""
    text: str = ""
    t: float = -1.0
    kind: str = ""

    def __str__(self) -> str:
        txt = self.text.strip()
        if self.t is not None and self.t >= 0:
            return f"[{self.t:.0f}s] {txt}".strip()
        return txt


@dataclass
class StoryModel:
    """R7 — the recap's whole-film understanding, produced by the pass-1 "Story
    Understanding" LLM call BEFORE any scene selection. Pass-2 editorial planning
    is conditioned on it, and it is persisted for UI / future re-edit. Every field
    defaults empty so a partial/legacy blob never errors (Sacred Contract #3 spirit).

    v2 (2026-06-30 architecture review): characters/beats are now ENTITIES
    (Character/StoryBeat) and the model carries theme/genre/conflict/resolution/
    emotional_curve + its own ``schema_version``. ``story_model_from_dict`` loads
    BOTH v1 (flat strings) and v2 (objects) blobs — back-compat is preserved."""
    schema_version: int = STORY_SCHEMA_VERSION
    summary: str = ""                                        # 3-6 sentence whole-film synopsis
    # Principal characters as ENTITIES. NOTE: constructing directly with raw
    # strings is tolerated downstream (str(c) is used for prompts), but
    # ``story_model_from_dict`` always yields Character instances.
    characters: list[Character] = field(default_factory=list)
    # Key plot TURNS, chronological, as entities. NOTE: unrelated to Act.beat (the
    # structural phase) — see the plot_turns alias below. Wire key stays ``beats``.
    beats: list[StoryBeat] = field(default_factory=list)
    climax: str = ""                                         # the peak/turning point, one line
    ending: str = ""                                         # how the film resolves, one line
    theme: str = ""                                          # central theme, one line
    genre: str = ""                                          # genre / tone, short
    conflict: str = ""                                       # the central conflict, one line
    resolution: str = ""                                     # how the conflict resolves, one line
    # Emotion per phase, ordered (e.g. ["hope","dread","catharsis"]). The pacing
    # spine for editorial planning (consumed by the Phase 3 editorial layer).
    emotional_curve: list[str] = field(default_factory=list)

    @property
    def plot_turns(self) -> list[StoryBeat]:
        """Clearer read-only alias for ``beats`` — the story's key plot turns.
        Distinct from Act.act_phase (the structural phase). The persisted key
        stays ``beats`` (asdict serialises the field, not this property)."""
        return self.beats

    def is_empty(self) -> bool:
        """True when no field carries usable content — used by the parser to
        decide whether pass-1 produced anything worth keeping."""
        return not (
            self.summary or self.characters or self.beats or self.climax
            or self.ending or self.theme or self.genre or self.conflict
            or self.resolution or self.emotional_curve
        )

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-safe nested dict (entities → dicts) for result_json / events / UI.
        Use this instead of touching the dataclass fields directly when emitting."""
        return asdict(self)


# EditorialBlueprint's OWN schema version (independent of RecapPlan/StoryModel).
EDITORIAL_SCHEMA_VERSION = 1


@dataclass
class EditorialBeat:
    """One planned editorial beat (R7.3 pass-2). Maps a story beat to its
    editorial role + the emotional intent to land + whether to NARRATE or HOLD
    (let source audio play). No timestamps — pass-3 binds those."""
    summary: str = ""          # which beat / moment
    story_role: str = ""       # setup|inciting|rising|climax|resolution|…
    emotional_intent: str = "" # the feeling this beat should land
    treatment: str = ""        # "narrate" | "hold"


@dataclass
class EditorialBlueprint:
    """R7.3 — the recap's EDITORIAL plan ("HOW to tell it"), produced by the
    pass-2 editorial LLM call FROM the StoryModel (no transcript → cheap), BEFORE
    scene binding. Pass-3 executes it. Persisted on the RecapPlan for re-edit.
    Every field defaults empty so a partial/legacy blob never errors (Sacred #3)."""
    schema_version: int = EDITORIAL_SCHEMA_VERSION
    episode_count: int = 0     # 0 = unspecified → fall back to the duration heuristic
    episode_rationale: str = ""
    pacing: str = ""           # overall pacing guidance derived from emotional_curve
    beats: list[EditorialBeat] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.episode_count or self.episode_rationale or self.pacing or self.beats)

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-safe nested dict (entities → dicts) for result_json / events / UI."""
        return asdict(self)


@dataclass
class RecapPlan:
    """AI-emitted plan for an act-structured recap, split into 1..N episodes."""
    schema_version: int = SCHEMA_VERSION
    total_target_sec: float = 0.0
    # R7: nested Story Model (pass-1 understanding). Replaces the v1 flat
    # ``story_summary`` field — back-compat preserved via the ``story_summary``
    # property + defensive ``_from_dict`` (a v1 blob's flat string is wrapped).
    story: "StoryModel" = field(default_factory=StoryModel)
    # R7.3: nested Editorial Blueprint (pass-2 plan). Default-empty so legacy
    # blobs (pre-R7.3, no "editorial" key) load fine — back-compat preserved.
    editorial: "EditorialBlueprint" = field(default_factory=EditorialBlueprint)
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
        editorial = editorial_blueprint_from_dict(data.get("editorial"))
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), SCHEMA_VERSION),
            total_target_sec=_coerce_float(data.get("total_target_sec"), 0.0),
            story=story,
            editorial=editorial,
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


def _split_name_role(s: str) -> tuple[str, str]:
    """Parse a v1 "Name — role/want" free string into (name, role). Tries a few
    common separators; falls back to the whole string as the name."""
    for sep in ("—", "–", " - ", ":"):
        if sep in s:
            name, _, rest = s.partition(sep)
            return name.strip(), rest.strip()
    return s.strip(), ""


def _coerce_character(v: Any) -> Optional["Character"]:
    """One Character from a Character / v1 string / v2 dict. None if empty."""
    if isinstance(v, Character):
        return v if (v.name or v.role or v.want) else None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        name, role = _split_name_role(s)
        return Character(name=name, role=role)
    if isinstance(v, dict):
        name = str(v.get("name", "") or "").strip()
        role = str(v.get("role", "") or "").strip()
        want = str(v.get("want", v.get("goal", "")) or "").strip()
        if not (name or role or want):
            return None
        return Character(name=name, role=role, want=want)
    return None


def _coerce_beat(v: Any) -> Optional["StoryBeat"]:
    """One StoryBeat from a StoryBeat / v1 string / v2 dict. None if empty."""
    if isinstance(v, StoryBeat):
        return v if v.text else None
    if isinstance(v, str):
        s = v.strip()
        return StoryBeat(text=s) if s else None
    if isinstance(v, dict):
        text = str(v.get("text", v.get("beat", "")) or "").strip()
        if not text:
            return None
        return StoryBeat(
            text=text,
            t=_coerce_float(v.get("t", v.get("time", -1.0)), -1.0),
            kind=str(v.get("kind", "") or "").strip(),
        )
    return None


def _coerce_list(value: Any, coerce_one, max_items: int = 24) -> list:
    """Generic defensive list coercion: accepts a single item or a list, drops
    Nones, caps the count. ``coerce_one`` maps one raw item → obj|None. Never raises."""
    out: list = []
    if isinstance(value, (str, dict)):
        value = [value]
    if isinstance(value, (list, tuple)):
        for v in value:
            try:
                item = coerce_one(v)
            except Exception:
                item = None
            if item is not None:
                out.append(item)
            if len(out) >= max_items:
                break
    return out


def story_model_from_dict(d: Any) -> "StoryModel":
    """Defensive StoryModel from a dict. Loads BOTH v1 (flat str characters/beats)
    and v2 (Character/StoryBeat objects) blobs. Unknown keys dropped, missing keys
    default-empty. Never raises."""
    if not isinstance(d, dict):
        return StoryModel()
    return StoryModel(
        schema_version=_coerce_int(d.get("schema_version"), STORY_SCHEMA_VERSION),
        summary=str(d.get("summary", "") or "").strip(),
        characters=_coerce_list(d.get("characters"), _coerce_character),
        beats=_coerce_list(d.get("beats"), _coerce_beat),
        climax=str(d.get("climax", "") or "").strip(),
        ending=str(d.get("ending", "") or "").strip(),
        theme=str(d.get("theme", "") or "").strip(),
        genre=str(d.get("genre", "") or "").strip(),
        conflict=str(d.get("conflict", "") or "").strip(),
        resolution=str(d.get("resolution", "") or "").strip(),
        emotional_curve=_coerce_str_list(d.get("emotional_curve")),
    )


def _coerce_treatment(value: Any) -> str:
    """Normalise an editorial beat treatment → 'narrate' | 'hold'. Default
    narrate (conservative — hold is the AI's explicit opt-in for source audio)."""
    s = str(value or "").strip().lower()
    return "hold" if s in ("hold", "original", "source", "raw", "silent", "keep") else "narrate"


def _coerce_editorial_beat(v: Any) -> Optional["EditorialBeat"]:
    """One EditorialBeat from an EditorialBeat / string / dict. None if empty."""
    if isinstance(v, EditorialBeat):
        return v if (v.summary or v.story_role or v.emotional_intent) else None
    if isinstance(v, str):
        s = v.strip()
        return EditorialBeat(summary=s, treatment=_coerce_treatment(None)) if s else None
    if isinstance(v, dict):
        summary = str(v.get("summary", v.get("text", "")) or "").strip()
        story_role = str(v.get("story_role", v.get("role", "")) or "").strip()
        emo = str(v.get("emotional_intent", v.get("emotion", "")) or "").strip()
        if not (summary or story_role or emo):
            return None
        return EditorialBeat(
            summary=summary, story_role=story_role, emotional_intent=emo,
            treatment=_coerce_treatment(v.get("treatment")),
        )
    return None


def editorial_blueprint_from_dict(d: Any) -> "EditorialBlueprint":
    """Defensive EditorialBlueprint from a dict. Unknown keys dropped, missing
    keys default-empty. Never raises."""
    if not isinstance(d, dict):
        return EditorialBlueprint()
    return EditorialBlueprint(
        schema_version=_coerce_int(d.get("schema_version"), EDITORIAL_SCHEMA_VERSION),
        episode_count=max(0, _coerce_int(d.get("episode_count"), 0)),
        episode_rationale=str(d.get("episode_rationale", "") or "").strip(),
        pacing=str(d.get("pacing", "") or "").strip(),
        beats=_coerce_list(d.get("beats"), _coerce_editorial_beat),
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
