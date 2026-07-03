"""
content_plan.py — ContentPlan dataclass for the AI Content Mode
(render_format="content": Script → AI narration → Video).

Pure domain object: no FFmpeg, no file I/O, no LLM SDK. JSON (de)serialise
only. Mirrors the defensive contract of recap_plan.py / render_plan.py:

- Every field has a safe default; loading a legacy/partial blob never errors.
- ``from_json`` is strictly defensive — unknown keys dropped, malformed values
  fall back to defaults, NEVER raises (Sacred Contract #3 spirit; the AI /
  pipeline paths must not crash a render job).
- ``to_json`` is deterministic (sorted keys, compact) so the persisted blob is
  stable across rebuilds.

Shape (see docs/CONTENT_MODE_SPEC.md) — v1 MVP director scope:

    ContentPlan
      schema_version: int
      topic, tone, audience, language: str   # AI-detected metadata
      total_target_sec: float                # AI-estimated total length
      subtitle_style: str                    # AI suggestion (capcut|word_by_word|…)
      bgm_mood: str                          # HINT-only v1 (epic|calm|news|…)
      scenes: list[ContentScene]             # AI splits the script by MEANING
    ContentScene
      index: int
      role: str                              # hook|intro|explain|example|conclusion|cta
      narration: str                         # AI-authored voice-over — TTS + subtitle source
      emotion: str                           # normal|excited|calm|suspense|epic|…
      reading_speed: float                   # 0.5–2.0 (clamped)
      pause_before, pause_after: float       # seconds of silence around the scene
      emphasis: list[str]                    # words/phrases to stress
      est_duration_sec: float                # AI estimate; engine refines from real TTS
      # ── HINT-only v1 (stored, NOT yet consumed by the render) ──
      visual_hint, camera_hint,
      transition_hint, animation_hint: str

v1 renders visuals as a user-chosen background (color/image/video loop) with
animated subtitles + TTS over it — the visual_hint/camera_hint/etc. fields are
captured for a later phase (stock/AI-image/slideshow), stored but not consumed.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 3  # CS-A(v2): per-scene scene_title/visual_prompt/negative_prompt/
                    # subtitle_style/asset_suggestion + plan-level video_style.
                    # CU-4(v3): plan-level StoryBible (characters/setting/hook/cta) +
                    # per-scene characters[]/continuity. v1/v2 blobs load unchanged.

# Reading-speed clamp — guards against the LLM emitting an absurd multiplier that
# would make TTS unintelligible or the timeline nonsensical.
_READING_SPEED_MIN = 0.5
_READING_SPEED_MAX = 2.0
_READING_SPEED_DEFAULT = 1.0

# Pause clamp (seconds) — a single inter-scene pause should never dwarf the scene.
_PAUSE_MAX = 5.0

# Allowed scene roles (free-form tolerated, but normalised toward this set).
SCENE_ROLES = ("hook", "intro", "explain", "example", "conclusion", "cta")


@dataclass
class BibleCharacter:
    """A recurring character in the Story Bible (CU-4). ``description`` is the
    CANONICAL visual/role description injected into every scene the character
    appears in — the basis of visual consistency (CU-6)."""
    id: str = ""
    name: str = ""
    description: str = ""


@dataclass
class StoryBible:
    """CU-4 — whole-script understanding committed BEFORE the plan is written, so
    narration + visuals stay consistent across scenes (mirrors recap's StoryModel).
    Plan-level topic/tone/audience/video_style live on ContentPlan; the Bible adds
    the through-line + character canon. Every field defaults empty → a legacy plan
    (no bible) loads fine (Sacred Contract #3 spirit)."""
    setting: str = ""
    hook: str = ""
    cta: str = ""
    characters: list[BibleCharacter] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.setting or self.hook or self.cta or self.characters)

    def character(self, key: str) -> "Optional[BibleCharacter]":
        k = (key or "").strip().lower()
        for c in self.characters:
            if c.id.strip().lower() == k or c.name.strip().lower() == k:
                return c
        return None


@dataclass
class ContentScene:
    """One semantic scene of the content video, in narration order."""
    index: int = 0
    scene_title: str = ""       # short AI label for the scene (Review UI / timeline)
    role: str = ""              # hook|intro|explain|example|conclusion|cta|""
    narration: str = ""         # AI-authored voice-over spoken over this scene
    emotion: str = "normal"     # normal|excited|calm|suspense|epic|sad|happy|…
    reading_speed: float = _READING_SPEED_DEFAULT
    pause_before: float = 0.0
    pause_after: float = 0.0
    emphasis: list[str] = field(default_factory=list)
    est_duration_sec: float = 0.0
    # CU-4: which StoryBible character ids appear in this scene (drives CU-6
    # consistency injection) + a short continuity note (what carries over).
    characters: list[str] = field(default_factory=list)
    continuity: str = ""
    # Per-scene subtitle style override ("" = use the plan/global style).
    subtitle_style: str = ""
    # ── Visual planning (CS-A) — consumed by the Visual Generator provider layer,
    # NOT by the render engine directly. visual_prompt is the full generator
    # prompt (AI image/video / stock search); visual_hint is the short human
    # label kept for back-compat. asset_suggestion is the AI's guess at the best
    # source ("ai_image"|"ai_video"|"stock"|"upload"|"local"|"" = unspecified). ──
    visual_hint: str = ""
    visual_prompt: str = ""
    negative_prompt: str = ""
    asset_suggestion: str = ""
    # ── CS-E Asset Manager (per-scene visual, consumed by the render) ──
    # visual_source: "" = use the job-level background | "color"|"image"|"video".
    # visual_path: color hex or local asset path. ken_burns: slow zoom/pan on an
    # image background (offline, via FFmpeg zoompan).
    visual_source: str = ""
    visual_path: str = ""
    ken_burns: bool = False
    # ── HINT-only — stored, not consumed by the render engine yet ──
    camera_hint: str = ""
    transition_hint: str = ""
    animation_hint: str = ""


@dataclass
class ContentPlan:
    """AI-emitted plan for a script-driven content video (render_format="content")."""
    schema_version: int = SCHEMA_VERSION
    topic: str = ""
    tone: str = ""
    audience: str = ""
    language: str = ""
    total_target_sec: float = 0.0
    subtitle_style: str = ""
    bgm_mood: str = ""
    video_style: str = ""       # AI-detected overall style (documentary|storytelling|…)
    story_bible: StoryBible = field(default_factory=StoryBible)  # CU-4
    scenes: list[ContentScene] = field(default_factory=list)

    # ── Convenience ──────────────────────────────────────────────────────

    def scene_count(self) -> int:
        return len(self.scenes)

    def is_empty(self) -> bool:
        """True when the plan carries no usable scene — the parser uses this to
        decide whether the LLM produced anything worth keeping."""
        return not any((s.narration or "").strip() for s in self.scenes)

    def total_narration_chars(self) -> int:
        return sum(len((s.narration or "")) for s in self.scenes)

    # ── Serialisation ────────────────────────────────────────────────────

    def to_json(self) -> str:
        """Deterministic JSON dump — sorted keys, compact separators."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: "str | bytes | None") -> Optional["ContentPlan"]:
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
    def _from_dict(cls, data: dict[str, Any]) -> "ContentPlan":
        scenes: list[ContentScene] = []
        raw_scenes = data.get("scenes")
        if isinstance(raw_scenes, list):
            for i, entry in enumerate(raw_scenes):
                if isinstance(entry, dict):
                    scenes.append(_scene_from_dict(entry, i))
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), SCHEMA_VERSION),
            topic=str(data.get("topic", "") or "").strip(),
            tone=str(data.get("tone", "") or "").strip(),
            audience=str(data.get("audience", "") or "").strip(),
            language=str(data.get("language", "") or "").strip(),
            total_target_sec=_coerce_float(data.get("total_target_sec"), 0.0),
            subtitle_style=str(data.get("subtitle_style", "") or "").strip(),
            bgm_mood=str(data.get("bgm_mood", "") or "").strip(),
            video_style=str(data.get("video_style", "") or "").strip(),
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


def _bible_character_from_dict(d: Any) -> Optional[BibleCharacter]:
    if isinstance(d, str):
        s = d.strip()
        return BibleCharacter(name=s, id=s) if s else None
    if not isinstance(d, dict):
        return None
    name = str(d.get("name", "") or "").strip()
    cid = str(d.get("id", name) or "").strip()
    desc = str(d.get("description", d.get("desc", "")) or "").strip()
    if not (name or cid or desc):
        return None
    return BibleCharacter(id=(cid or name), name=(name or cid), description=desc)


def _story_bible_from_dict(d: Any) -> StoryBible:
    """Defensive StoryBible loader. Unknown keys dropped, missing default-empty.
    Never raises."""
    if not isinstance(d, dict):
        return StoryBible()
    chars: list[BibleCharacter] = []
    raw = d.get("characters")
    if isinstance(raw, list):
        for entry in raw:
            c = _bible_character_from_dict(entry)
            if c is not None:
                chars.append(c)
            if len(chars) >= 24:
                break
    return StoryBible(
        setting=str(d.get("setting", "") or "").strip(),
        hook=str(d.get("hook", "") or "").strip(),
        cta=str(d.get("cta", "") or "").strip(),
        characters=chars,
    )


def _scene_from_dict(d: dict[str, Any], fallback_index: int) -> ContentScene:
    return ContentScene(
        index=_coerce_int(d.get("index"), fallback_index),
        scene_title=str(d.get("scene_title", d.get("title", "")) or "").strip(),
        role=str(d.get("role", "") or "").strip().lower(),
        narration=str(d.get("narration", "") or "").strip(),
        emotion=(str(d.get("emotion", "") or "").strip().lower() or "normal"),
        reading_speed=_clamp_float(
            d.get("reading_speed"), _READING_SPEED_MIN, _READING_SPEED_MAX, _READING_SPEED_DEFAULT,
        ),
        pause_before=_clamp_float(d.get("pause_before"), 0.0, _PAUSE_MAX, 0.0),
        pause_after=_clamp_float(d.get("pause_after"), 0.0, _PAUSE_MAX, 0.0),
        emphasis=_coerce_str_list(d.get("emphasis")),
        est_duration_sec=max(0.0, _coerce_float(d.get("est_duration_sec"), 0.0)),
        characters=_coerce_str_list(d.get("characters")),
        continuity=str(d.get("continuity", "") or "").strip(),
        subtitle_style=str(d.get("subtitle_style", "") or "").strip(),
        visual_hint=str(d.get("visual_hint", "") or "").strip(),
        visual_prompt=str(d.get("visual_prompt", "") or "").strip(),
        negative_prompt=str(d.get("negative_prompt", "") or "").strip(),
        asset_suggestion=str(d.get("asset_suggestion", "") or "").strip().lower(),
        visual_source=str(d.get("visual_source", "") or "").strip().lower(),
        visual_path=str(d.get("visual_path", "") or "").strip(),
        ken_burns=_coerce_bool(d.get("ken_burns"), False),
        camera_hint=str(d.get("camera_hint", "") or "").strip().lower(),
        transition_hint=str(d.get("transition_hint", "") or "").strip().lower(),
        animation_hint=str(d.get("animation_hint", "") or "").strip().lower(),
    )
