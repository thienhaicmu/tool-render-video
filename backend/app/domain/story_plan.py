"""
story_plan.py — StoryPlan dataclass for AI Story-to-Video Mode
(render_format="story": Chapter → AI Story Director → Storyboard → Shots → Video).

Pure domain object: no FFmpeg, no file I/O, no LLM SDK. JSON (de)serialise only.
Mirrors the DEFENSIVE contract of content_plan.py / recap_plan.py / render_plan.py:

- Every field has a safe default; loading a legacy/partial blob never errors.
- ``from_json`` is strictly defensive — unknown keys dropped, malformed values
  fall back to defaults, NEVER raises (Sacred Contract #3 spirit; the AI /
  pipeline paths must not crash a render job).
- ``to_json`` is deterministic (sorted keys, compact) so the persisted blob is
  stable across rebuilds.

Kept SELF-CONTAINED (its own StoryBible/StoryCharacter/StoryEnvironment) rather
than importing content_plan's StoryBible, so Content Mode's domain file is never
touched (mode isolation — see docs/STORY_TO_VIDEO_PLAN.md §1).

Shape (see docs/STORY_TO_VIDEO_PLAN.md §3.1) — v1 Story Director scope:

    StoryPlan
      schema_version:int
      series_id, chapter_no          # optional cross-chapter link (Character DB)
      language, art_style, aspect_ratio
      reading_pace                   # slow|normal|fast — global reading-speed lever
      story_bible: StoryBible        # characters + environments + hook/cta/setting
      scenes: list[StoryScene]
    StoryScene
      index, scene_title, role, setting_ref, emotion
      characters:list[str], transition_out
      shots: list[Shot]              # the Scene→Shot hierarchy (new vs Content)
    Shot
      index, sid, shot_type, narration, speaker, emotion,
      reading_speed, pause_before/after, est_duration_sec,
      camera, composition, lighting, characters[], environment_ref,
      asset_type, quality_tier, visual_prompt, negative_prompt,
      visual_source, visual_path, transition_out, subtitle_style
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 1

# Reading-speed clamp — guards against the LLM emitting an absurd multiplier.
_READING_SPEED_MIN = 0.5
_READING_SPEED_MAX = 2.0
_READING_SPEED_DEFAULT = 1.0

# Global reading-pace lever (§7 decision 4) → reading_speed multiplier applied on
# top of per-shot speed. "normal" is inert.
READING_PACE = ("slow", "normal", "fast")
_PACE_FACTOR = {"slow": 0.9, "normal": 1.0, "fast": 1.15}

# Pause clamp (seconds) — a single inter-shot pause should never dwarf the shot.
_PAUSE_MAX = 5.0

# Rough narration reading rate at reading_speed=1.0, used only to ESTIMATE a
# shot's spoken seconds when the AI omitted ``est_duration_sec``. Language-agnostic
# + conservative; the engine always refines from real TTS.
_CHARS_PER_SEC_AT_1X = 15.0

# Allowed enums (free-form tolerated, normalised toward these sets).
SHOT_TYPES = ("establishing", "medium", "close_up", "insert", "action")
ASSET_TYPES = ("ai_image", "local", "pin")
QUALITY_TIERS = ("low", "medium", "high")
SCENE_ROLES = ("hook", "intro", "rising", "climax", "falling", "resolution", "cta")
# Default quality tier by shot_type (§7 decision 5).
_TIER_BY_SHOT = {
    "establishing": "low", "insert": "low",
    "medium": "medium", "action": "medium",
    "close_up": "high",
}


@dataclass
class StoryCharacter:
    """A recurring character in the Story Bible. ``description`` is the CANONICAL
    visual/role description injected into every shot the character appears in —
    the basis of visual consistency. ``reference_image_path`` (when set) is the
    pinned Character Reference Sheet used to condition image generation. Voice
    fields drive per-character casting (Gemini VI / ElevenLabs EN-JP)."""
    id: str = ""
    name: str = ""
    description: str = ""
    age: str = ""
    gender: str = ""
    voice_engine: str = ""
    voice_id: str = ""
    reference_image_path: str = ""


@dataclass
class StoryEnvironment:
    """A recurring setting/location with a CANONICAL description so scenes in the
    same place stay visually consistent."""
    id: str = ""
    name: str = ""
    description: str = ""
    reference_image_path: str = ""


@dataclass
class StoryBible:
    """Whole-chapter understanding committed BEFORE the storyboard is written, so
    narration + visuals stay consistent. Every field defaults empty → a legacy
    plan (no bible) loads fine (Sacred Contract #3 spirit)."""
    setting: str = ""
    hook: str = ""
    cta: str = ""
    characters: list[StoryCharacter] = field(default_factory=list)
    environments: list[StoryEnvironment] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.setting or self.hook or self.cta or self.characters or self.environments)

    def character(self, key: str) -> "Optional[StoryCharacter]":
        k = (key or "").strip().lower()
        if not k:
            return None
        for c in self.characters:
            if c.id.strip().lower() == k or c.name.strip().lower() == k:
                return c
        return None

    def environment(self, key: str) -> "Optional[StoryEnvironment]":
        k = (key or "").strip().lower()
        if not k:
            return None
        for e in self.environments:
            if e.id.strip().lower() == k or e.name.strip().lower() == k:
                return e
        return None


@dataclass
class Shot:
    """One camera shot of the storyboard, in narration order. The visual/timing
    atom the render composes (image + motion effect + subtitle + narration)."""
    index: int = 0
    sid: str = ""               # stable short id (React key / temp file naming)
    shot_type: str = "medium"   # establishing|medium|close_up|insert|action
    narration: str = ""         # voice-over / dialogue spoken over this shot
    speaker: str = ""           # StoryBible character id ("" = narrator)
    emotion: str = "normal"
    reading_speed: float = _READING_SPEED_DEFAULT
    pause_before: float = 0.0
    pause_after: float = 0.0
    est_duration_sec: float = 0.0
    # Camera / composition — drives the render-time motion EFFECT (Ken Burns / pan
    # / zoom); no video is generated. Consumed by content_scene_render's camera.
    camera: str = ""            # zoom_in|zoom_out|pan_left|pan_right|still|""
    composition: str = ""
    lighting: str = ""
    characters: list[str] = field(default_factory=list)   # StoryBible char ids present
    environment_ref: str = ""   # StoryBible environment id
    # Asset planning.
    asset_type: str = "ai_image"   # ai_image|local|pin
    quality_tier: str = "medium"   # low|medium|high (gpt-image-1)
    visual_prompt: str = ""
    negative_prompt: str = ""
    # Per-shot local/pin override (mirrors Content CS-E). "" = generate per asset_type.
    visual_source: str = ""     # ""|color|image|video
    visual_path: str = ""
    # Shot-boundary transition (default cut — 2-tier: cut within a scene).
    transition_out: str = "cut"
    subtitle_style: str = ""


@dataclass
class StoryScene:
    """One narrative scene (a coherent beat/place), holding an ordered list of
    Shots. Scene = narrative unit; Shot = visual/timing unit."""
    index: int = 0
    scene_title: str = ""
    role: str = ""              # hook|intro|rising|climax|falling|resolution|cta
    setting_ref: str = ""       # StoryBible environment id
    emotion: str = "normal"
    characters: list[str] = field(default_factory=list)
    # Scene-boundary transition (default fade — 2-tier: fade between scenes).
    transition_out: str = "fade"
    shots: list[Shot] = field(default_factory=list)

    def shot_count(self) -> int:
        return len(self.shots)


@dataclass
class StoryPlan:
    """AI-emitted storyboard for a chapter-driven video (render_format="story")."""
    schema_version: int = SCHEMA_VERSION
    series_id: str = ""         # "" = one-off chapter (no cross-chapter Character DB)
    chapter_no: int = 0
    language: str = ""          # vi|en|ja
    art_style: str = ""         # anime|wuxia|romance|realistic|inkwash|...
    aspect_ratio: str = "9:16"
    reading_pace: str = "normal"   # slow|normal|fast (global reading-speed lever)
    topic: str = ""
    tone: str = ""
    story_bible: StoryBible = field(default_factory=StoryBible)
    scenes: list[StoryScene] = field(default_factory=list)

    # ── Convenience ──────────────────────────────────────────────────────

    def scene_count(self) -> int:
        return len(self.scenes)

    def shot_count(self) -> int:
        return sum(len(s.shots) for s in self.scenes)

    def all_shots(self) -> list[Shot]:
        """Flatten scenes → shots in narration order."""
        out: list[Shot] = []
        for s in self.scenes:
            out.extend(s.shots)
        return out

    def reindex(self) -> "StoryPlan":
        """Densely re-number scene/shot indices in order and seed a stable ``sid``
        for any shot missing one. Idempotent; mutates + returns self. Never raises.
        Called after assembling scenes from multiple chunks so indices are coherent."""
        try:
            for si, scene in enumerate(self.scenes):
                scene.index = si
                for shi, shot in enumerate(scene.shots):
                    shot.index = shi
                    if not (shot.sid or "").strip():
                        shot.sid = uuid.uuid4().hex[:8]
        except Exception:
            pass
        return self

    def is_empty(self) -> bool:
        """True when no shot carries usable narration — the parser uses this to
        decide whether the LLM produced anything worth keeping."""
        return not any((sh.narration or "").strip() for sh in self.all_shots())

    def total_narration_chars(self) -> int:
        return sum(len((sh.narration or "")) for sh in self.all_shots())

    def _pace_factor(self) -> float:
        return _PACE_FACTOR.get((self.reading_pace or "normal").strip().lower(), 1.0)

    def _shot_spoken_sec(self, shot: "Shot") -> float:
        """Best estimate of a shot's SPOKEN (non-pause) seconds. Trusts the AI's
        ``est_duration_sec`` when present; else estimates from narration length at
        the shot's reading speed × the global pace factor. Never raises."""
        try:
            est = float(getattr(shot, "est_duration_sec", 0.0) or 0.0)
            if est > 0:
                return est / self._pace_factor()
            chars = len((getattr(shot, "narration", "") or ""))
            spd = (float(getattr(shot, "reading_speed", 1.0) or 1.0) or 1.0) * self._pace_factor()
            if chars <= 0:
                return 0.0
            return (chars / _CHARS_PER_SEC_AT_1X) / spd
        except Exception:
            return 0.0

    def estimated_total_sec(self) -> float:
        """Estimated final length: spoken time (all shots) + inter-shot pauses.
        Pure estimate; the engine refines spoken time from real TTS. Never raises."""
        try:
            shots = self.all_shots()
            spoken = sum(self._shot_spoken_sec(sh) for sh in shots)
            pauses = sum(
                max(0.0, float(getattr(sh, "pause_before", 0.0) or 0.0))
                + max(0.0, float(getattr(sh, "pause_after", 0.0) or 0.0))
                for sh in shots
            )
            return spoken + pauses
        except Exception:
            return 0.0

    def narration_audit(
        self,
        cps: float = _CHARS_PER_SEC_AT_1X,
        overload_ratio: float = 1.3,
        sparse_ratio: float = 0.6,
    ) -> dict:
        """Deterministic per-shot narration/timing sanity check (no LLM, never
        raises). Mirrors ContentPlan.narration_audit but over the flattened shot
        list. For each shot with an AI ``est_duration_sec``, compare narration
        length to the char CAPACITY of that window (cps × reading_speed × est):
          load > overload_ratio → "overloaded"; < sparse_ratio → "sparse"; else "ok".
        ``weak`` is True when ANY shot is overloaded, or >40% of rated shots are
        sparse. Diagnostic only."""
        out: dict = {"weak": False, "rated": 0, "overloaded": 0, "sparse": 0, "shots": []}
        try:
            n_over = n_sparse = n_rated = 0
            for i, sh in enumerate(self.all_shots(), start=1):
                chars = len((getattr(sh, "narration", "") or "").strip())
                est = float(getattr(sh, "est_duration_sec", 0.0) or 0.0)
                spd = float(getattr(sh, "reading_speed", 1.0) or 1.0) or 1.0
                if est <= 0 or chars <= 0:
                    out["shots"].append({"n": i, "chars": chars, "load": None, "flag": "no_estimate"})
                    continue
                capacity = cps * spd * est
                load = (chars / capacity) if capacity > 0 else None
                if load is None:
                    flag = "no_estimate"
                elif load > overload_ratio:
                    flag = "overloaded"; n_over += 1; n_rated += 1
                elif load < sparse_ratio:
                    flag = "sparse"; n_sparse += 1; n_rated += 1
                else:
                    flag = "ok"; n_rated += 1
                out["shots"].append({
                    "n": i, "chars": chars,
                    "capacity_chars": round(capacity) if capacity else 0,
                    "load": round(load, 2) if load is not None else None,
                    "flag": flag,
                })
            out["rated"] = n_rated
            out["overloaded"] = n_over
            out["sparse"] = n_sparse
            out["weak"] = bool(n_over > 0 or (n_rated > 0 and n_sparse / n_rated > 0.4))
            return out
        except Exception:
            return out

    # ── Serialisation ────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Deterministic JSON dump — sorted keys, compact separators."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: "str | bytes | None") -> Optional["StoryPlan"]:
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
    def _from_dict(cls, data: dict[str, Any]) -> "StoryPlan":
        scenes: list[StoryScene] = []
        raw_scenes = data.get("scenes")
        if isinstance(raw_scenes, list):
            for i, entry in enumerate(raw_scenes):
                if isinstance(entry, dict):
                    scenes.append(_scene_from_dict(entry, i))
        pace = str(data.get("reading_pace", "normal") or "normal").strip().lower()
        if pace not in READING_PACE:
            pace = "normal"
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), SCHEMA_VERSION),
            series_id=str(data.get("series_id", "") or "").strip(),
            chapter_no=_coerce_int(data.get("chapter_no"), 0),
            language=str(data.get("language", "") or "").strip(),
            art_style=str(data.get("art_style", "") or "").strip(),
            aspect_ratio=str(data.get("aspect_ratio", "9:16") or "9:16").strip(),
            reading_pace=pace,
            topic=str(data.get("topic", "") or "").strip(),
            tone=str(data.get("tone", "") or "").strip(),
            story_bible=_story_bible_from_dict(data.get("story_bible")),
            scenes=scenes,
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


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    v = _coerce_float(value, default)
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


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


def _norm_enum(value: Any, allowed: tuple, default: str) -> str:
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def _character_from_dict(d: Any) -> Optional[StoryCharacter]:
    if isinstance(d, str):
        s = d.strip()
        return StoryCharacter(name=s, id=s) if s else None
    if not isinstance(d, dict):
        return None
    name = str(d.get("name", "") or "").strip()
    cid = str(d.get("id", name) or "").strip()
    desc = str(d.get("description", d.get("desc", "")) or "").strip()
    if not (name or cid or desc):
        return None
    return StoryCharacter(
        id=(cid or name), name=(name or cid), description=desc,
        age=str(d.get("age", "") or "").strip(),
        gender=str(d.get("gender", "") or "").strip().lower(),
        voice_engine=str(d.get("voice_engine", "") or "").strip().lower(),
        voice_id=str(d.get("voice_id", "") or "").strip(),
        reference_image_path=str(d.get("reference_image_path", "") or "").strip(),
    )


def _environment_from_dict(d: Any) -> Optional[StoryEnvironment]:
    if isinstance(d, str):
        s = d.strip()
        return StoryEnvironment(name=s, id=s) if s else None
    if not isinstance(d, dict):
        return None
    name = str(d.get("name", "") or "").strip()
    eid = str(d.get("id", name) or "").strip()
    desc = str(d.get("description", d.get("desc", "")) or "").strip()
    if not (name or eid or desc):
        return None
    return StoryEnvironment(
        id=(eid or name), name=(name or eid), description=desc,
        reference_image_path=str(d.get("reference_image_path", "") or "").strip(),
    )


def _story_bible_from_dict(d: Any) -> StoryBible:
    """Defensive StoryBible loader. Unknown keys dropped, missing default-empty.
    Never raises."""
    if not isinstance(d, dict):
        return StoryBible()
    chars: list[StoryCharacter] = []
    for entry in (d.get("characters") or []) if isinstance(d.get("characters"), list) else []:
        c = _character_from_dict(entry)
        if c is not None:
            chars.append(c)
        if len(chars) >= 48:
            break
    envs: list[StoryEnvironment] = []
    for entry in (d.get("environments") or []) if isinstance(d.get("environments"), list) else []:
        e = _environment_from_dict(entry)
        if e is not None:
            envs.append(e)
        if len(envs) >= 48:
            break
    return StoryBible(
        setting=str(d.get("setting", "") or "").strip(),
        hook=str(d.get("hook", "") or "").strip(),
        cta=str(d.get("cta", "") or "").strip(),
        characters=chars,
        environments=envs,
    )


def _shot_from_dict(d: dict[str, Any], fallback_index: int) -> Shot:
    return Shot(
        index=_coerce_int(d.get("index"), fallback_index),
        sid=str(d.get("sid", "") or "").strip(),
        shot_type=_norm_enum(d.get("shot_type"), SHOT_TYPES, "medium"),
        narration=str(d.get("narration", "") or "").strip(),
        speaker=str(d.get("speaker", "") or "").strip(),
        emotion=(str(d.get("emotion", "") or "").strip().lower() or "normal"),
        reading_speed=_clamp_float(
            d.get("reading_speed"), _READING_SPEED_MIN, _READING_SPEED_MAX, _READING_SPEED_DEFAULT,
        ),
        pause_before=_clamp_float(d.get("pause_before"), 0.0, _PAUSE_MAX, 0.0),
        pause_after=_clamp_float(d.get("pause_after"), 0.0, _PAUSE_MAX, 0.0),
        est_duration_sec=max(0.0, _coerce_float(d.get("est_duration_sec"), 0.0)),
        camera=str(d.get("camera", d.get("camera_hint", "")) or "").strip().lower(),
        composition=str(d.get("composition", "") or "").strip(),
        lighting=str(d.get("lighting", "") or "").strip(),
        characters=_coerce_str_list(d.get("characters")),
        environment_ref=str(d.get("environment_ref", "") or "").strip(),
        asset_type=_norm_enum(d.get("asset_type"), ASSET_TYPES, "ai_image"),
        quality_tier=_norm_enum(
            d.get("quality_tier"), QUALITY_TIERS,
            _TIER_BY_SHOT.get(_norm_enum(d.get("shot_type"), SHOT_TYPES, "medium"), "medium"),
        ),
        visual_prompt=str(d.get("visual_prompt", "") or "").strip(),
        negative_prompt=str(d.get("negative_prompt", "") or "").strip(),
        visual_source=str(d.get("visual_source", "") or "").strip().lower(),
        visual_path=str(d.get("visual_path", "") or "").strip(),
        transition_out=(str(d.get("transition_out", "") or "").strip().lower() or "cut"),
        subtitle_style=str(d.get("subtitle_style", "") or "").strip(),
    )


def _scene_from_dict(d: dict[str, Any], fallback_index: int) -> StoryScene:
    shots: list[Shot] = []
    raw_shots = d.get("shots")
    if isinstance(raw_shots, list):
        for i, entry in enumerate(raw_shots):
            if isinstance(entry, dict):
                shots.append(_shot_from_dict(entry, i))
    return StoryScene(
        index=_coerce_int(d.get("index"), fallback_index),
        scene_title=str(d.get("scene_title", d.get("title", "")) or "").strip(),
        role=str(d.get("role", "") or "").strip().lower(),
        setting_ref=str(d.get("setting_ref", "") or "").strip(),
        emotion=(str(d.get("emotion", "") or "").strip().lower() or "normal"),
        characters=_coerce_str_list(d.get("characters")),
        transition_out=(str(d.get("transition_out", "") or "").strip().lower() or "fade"),
        shots=shots,
    )
