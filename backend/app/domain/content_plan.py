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

# Rough narration reading rate at reading_speed=1.0, used only to ESTIMATE a
# scene's spoken seconds when the AI omitted ``est_duration_sec``. Deliberately
# language-agnostic + conservative; the engine always refines from real TTS.
_CHARS_PER_SEC_AT_1X = 15.0

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

    def _scene_spoken_sec(self, scene: "ContentScene") -> float:
        """Best estimate of a scene's SPOKEN (non-pause) seconds.

        Trusts the AI's ``est_duration_sec`` when present; otherwise estimates
        from narration length at the scene's reading speed
        (``_CHARS_PER_SEC_AT_1X`` chars/sec at speed 1.0). Never raises."""
        try:
            est = float(getattr(scene, "est_duration_sec", 0.0) or 0.0)
            if est > 0:
                return est
            chars = len((getattr(scene, "narration", "") or ""))
            spd = float(getattr(scene, "reading_speed", 1.0) or 1.0) or 1.0
            if chars <= 0:
                return 0.0
            return (chars / _CHARS_PER_SEC_AT_1X) / spd
        except Exception:
            return 0.0

    def estimated_total_sec(self) -> float:
        """Estimated final length: spoken time (all scenes) + inter-scene pauses.
        Pure estimate; the engine refines spoken time from real TTS. Never raises."""
        try:
            spoken = sum(self._scene_spoken_sec(s) for s in self.scenes)
            pauses = sum(
                max(0.0, float(getattr(s, "pause_before", 0.0) or 0.0))
                + max(0.0, float(getattr(s, "pause_after", 0.0) or 0.0))
                for s in self.scenes
            )
            return spoken + pauses
        except Exception:
            return 0.0

    def fit_to_target_duration(self, target_sec: float, tolerance: float = 0.15) -> dict:
        """Deterministically nudge the plan toward ``target_sec`` WITHOUT dropping
        any scene (content is narrative — every scene carries meaning, unlike a
        recap's redundant coverage).

        Lever: uniformly scale every scene's ``reading_speed`` (clamped
        ``_READING_SPEED_MIN``–``_READING_SPEED_MAX``) so the summed spoken time
        + fixed pauses land near the target. Faster speed → shorter video, and
        vice-versa. ``est_duration_sec`` is recomputed from the applied speed so
        the persisted plan stays coherent; ``total_target_sec`` is refreshed.

        Mirrors the SPIRIT of ``RecapPlan.trim_to_duration_band``
        (deterministic, no LLM trust, pure mutation, never raises) but is
        SCALE-based not TRIM-based, and non-destructive.

        No-op when the target is unknown, the plan is empty, there is no spoken
        content, or the current estimate is already within ``tolerance`` of the
        target. Returns metrics: ``{changed, before_sec, after_sec, target_sec,
        ratio, applied_scale, in_tolerance, scaled_scenes}``."""
        result = {
            "changed": False, "before_sec": 0.0, "after_sec": 0.0,
            "target_sec": round(max(0.0, float(target_sec or 0.0)), 1),
            "ratio": None, "applied_scale": None, "in_tolerance": None,
            "scaled_scenes": 0,
        }
        try:
            target = float(target_sec or 0.0)
            if target <= 0 or not self.scenes:
                return result
            spoken_total = sum(self._scene_spoken_sec(s) for s in self.scenes)
            pause_total = sum(
                max(0.0, float(getattr(s, "pause_before", 0.0) or 0.0))
                + max(0.0, float(getattr(s, "pause_after", 0.0) or 0.0))
                for s in self.scenes
            )
            before = spoken_total + pause_total
            result["before_sec"] = round(before, 1)
            if spoken_total <= 0:
                return result  # nothing to scale (all pause / empty)
            result["ratio"] = round(before / target, 3) if target > 0 else None
            # Already close enough? (measured on the full estimate incl. pauses)
            if abs(before - target) <= tolerance * target:
                result["after_sec"] = round(before, 1)
                result["in_tolerance"] = True
                return result
            # Desired spoken time = target minus the fixed pauses. Ratio<1 → need
            # to SPEED UP (shorten); ratio>1 → slow down (lengthen).
            desired_spoken = target - pause_total
            if desired_spoken <= 0:
                # Pauses alone exceed the target — compress spoken as much as the
                # clamp allows (max speed) and report out-of-tolerance.
                ratio = _READING_SPEED_MIN / _READING_SPEED_MAX  # smallest achievable
            else:
                ratio = desired_spoken / spoken_total
            result["applied_scale"] = round(ratio, 3)
            scaled = 0
            for s in self.scenes:
                try:
                    old_speed = float(getattr(s, "reading_speed", 1.0) or 1.0) or 1.0
                    # new_speed = old_speed / ratio (shorter when ratio<1 ⇒ faster)
                    new_speed = old_speed / ratio if ratio > 0 else old_speed
                    new_speed = min(_READING_SPEED_MAX, max(_READING_SPEED_MIN, new_speed))
                    if abs(new_speed - old_speed) < 1e-6:
                        continue
                    # Recompute est_duration_sec coherently from the applied speed.
                    old_spoken = self._scene_spoken_sec(s)
                    actual_ratio = old_speed / new_speed if new_speed > 0 else 1.0
                    s.reading_speed = round(new_speed, 3)
                    s.est_duration_sec = round(max(0.0, old_spoken * actual_ratio), 3)
                    scaled += 1
                except Exception:
                    continue
            after = self.estimated_total_sec()
            result["after_sec"] = round(after, 1)
            result["scaled_scenes"] = scaled
            result["in_tolerance"] = abs(after - target) <= tolerance * target
            result["changed"] = scaled > 0
            if result["changed"]:
                self.total_target_sec = round(after, 1)
            return result
        except Exception:
            return result

    def narration_audit(
        self,
        cps: float = _CHARS_PER_SEC_AT_1X,
        overload_ratio: float = 1.3,
        sparse_ratio: float = 0.6,
    ) -> dict:
        """Deterministic per-scene narration/timing sanity check (no LLM, never
        raises). For each scene with an AI-provided ``est_duration_sec``, compare
        the narration length to the character CAPACITY of that window at the
        scene's reading speed (``cps × reading_speed × est_duration_sec``):

          load = narration_chars / capacity_chars
            · load > ``overload_ratio``  → "overloaded" (TTS will rush / overflow
              the scene — the AI under-estimated the time it needs)
            · load < ``sparse_ratio``    → "sparse" (awkward silence — over-estimated)
            · otherwise                  → "ok"

        Scenes without an estimate (or empty narration) are reported "no_estimate"
        and excluded from the ``weak`` verdict. ``weak`` is True when ANY scene is
        overloaded, or more than 40% of rated scenes are sparse. Diagnostic only —
        mirrors recap's coverage check; the caller emits it as an event so the
        operator sees a weak plan without the render being blocked."""
        out: dict = {
            "weak": False, "rated": 0, "overloaded": 0, "sparse": 0, "scenes": [],
        }
        try:
            n_over = n_sparse = n_rated = 0
            for i, s in enumerate(self.scenes, start=1):
                chars = len((getattr(s, "narration", "") or "").strip())
                est = float(getattr(s, "est_duration_sec", 0.0) or 0.0)
                spd = float(getattr(s, "reading_speed", 1.0) or 1.0) or 1.0
                if est <= 0 or chars <= 0:
                    out["scenes"].append({"n": i, "chars": chars, "load": None, "flag": "no_estimate"})
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
                out["scenes"].append({
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
