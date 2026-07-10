"""
story_plan_v2.py — StoryPlan v2 (Super-Prompt + Timeline) domain object.

Pure domain: no FFmpeg, no I/O, no LLM SDK. JSON (de)serialise + deterministic
resolution only. Two layers, kept STRICTLY separate:

  • CONTRACT (AI-produced, immutable): characters / settings / visuals / timeline.
  • RENDER STATE (pipeline-filled, keyed-by-id, persisted for resume): visual_assets,
    voices, refs, beat_audio (timed transcript), cues (the absolute CUE SHEET),
    total_sec.

Everything downstream reads the CUE SHEET (``render.cues``) — a pure, deterministic
function of (contract + real TTS durations + seed). See docs/STORY_MODE_V2_PLAN.md.

Kept in a SEPARATE module from the v1 story_plan.py during the v2 build so the v1
pipeline keeps working (cutover removes v1 at B7). Defensive like content_plan.py:
from_json never raises; unknown keys dropped; malformed values → defaults.
"""
from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 2

# ── Enums (declared; unknown → default) ──────────────────────────────────────
FOCUS = ("wide", "left", "center", "right", "top", "bottom", "close")
MOTION = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "static")
TRANSITION = ("cut", "fade", "slide", "zoom", "flash", "to_black")
TIER = ("low", "medium", "high")
GENDER = ("male", "female", "")
SUBTITLE_MODE = ("hook_only", "full", "off")
# Pool a "random" transition resolves into (deterministic via seed).
_RANDOM_TRANSITIONS = ("fade", "slide", "zoom", "flash")

# ── Constants ────────────────────────────────────────────────────────────────
ASPECT_SIZE = {"16:9": (1536, 1024), "9:16": (1024, 1536), "1:1": (1024, 1024)}
CPS = {"vi": 15.0, "en": 14.0, "ja": 8.0, "ko": 9.0}
_CPS_DEFAULT = 14.0
TRANSITION_SEC = 0.4
MIN_BEAT_SEC = 1.5
# Normalised crop rect (x, y, w, h) ∈ [0..1] on the source image, per FOCUS region.
# w == h fraction on purpose: the source image aspect == the output aspect
# (ASPECT_SIZE), so an equal-fraction crop stays the SAME aspect → no distortion
# when scaled to the canvas. x/y bias the crop toward the focus region.
CROP_RECT = {
    "wide":   (0.00, 0.00, 1.00, 1.00),
    "center": (0.11, 0.11, 0.78, 0.78),
    "left":   (0.00, 0.14, 0.72, 0.72),
    "right":  (0.28, 0.14, 0.72, 0.72),
    "top":    (0.14, 0.00, 0.72, 0.72),
    "bottom": (0.14, 0.28, 0.72, 0.72),
    "close":  (0.25, 0.22, 0.50, 0.50),
}

_READING_SPEED_MIN, _READING_SPEED_MAX, _READING_SPEED_DEFAULT = 0.5, 2.0, 1.0
_PAUSE_MAX = 5.0


def cps_for(language: str) -> float:
    return CPS.get((language or "").strip().lower()[:2], _CPS_DEFAULT)


# ── Contract dataclasses (AI-produced, immutable) ────────────────────────────
@dataclass
class CharacterDef:
    id: str = ""
    name: str = ""
    canonical_desc: str = ""
    age: str = ""
    gender: str = ""          # ∈ GENDER
    voice_gender: str = ""    # ∈ GENDER
    voice_style: str = ""


@dataclass
class SettingDef:
    id: str = ""
    name: str = ""
    canonical_desc: str = ""


@dataclass
class Visual:
    id: str = ""
    setting_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    character_ids: list[str] = field(default_factory=list)
    tier: str = "medium"      # ∈ TIER


@dataclass
class Beat:
    id: str = ""
    narration: str = ""
    speaker_id: str = ""      # → CharacterDef.id ∪ ""
    visual_id: str = ""       # → Visual.id
    focus: str = "center"     # ∈ FOCUS
    motion: str = "zoom_in"   # ∈ MOTION
    emotion: str = "normal"
    reading_speed: float = 1.0
    pause_after: float = 0.0
    hold_sec: float = 0.0
    transition_in: str = "cut"  # ∈ TRANSITION (only used when the visual changes)
    hook: bool = False
    hook_text: str = ""


# ── Render-state dataclasses (pipeline-filled) ───────────────────────────────
@dataclass
class Word:
    text: str = ""
    start: float = 0.0
    end: float = 0.0


@dataclass
class BeatAudio:
    path: str = ""
    dur: float = 0.0
    words: list[Word] = field(default_factory=list)


@dataclass
class Cue:
    beat_id: str = ""
    visual_id: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    crop_from: tuple = (0.0, 0.0, 1.0, 1.0)
    crop_to: tuple = (0.0, 0.0, 1.0, 1.0)
    transition: str = "cut"
    transition_sec: float = 0.0
    hook: bool = False
    hook_text: str = ""
    audio_path: str = ""
    subtitle: str = ""


@dataclass
class RenderState:
    visual_assets: dict[str, str] = field(default_factory=dict)          # visual_id → path
    voices: dict[str, list] = field(default_factory=dict)                # char_id → [engine, voice_id]
    refs: dict[str, str] = field(default_factory=dict)                   # char_id → ref image path
    beat_audio: dict[str, BeatAudio] = field(default_factory=dict)       # beat_id → BeatAudio
    cues: list[Cue] = field(default_factory=list)
    total_sec: float = 0.0


# ── StoryPlan ────────────────────────────────────────────────────────────────
@dataclass
class StoryPlan:
    schema_version: int = SCHEMA_VERSION
    seed: int = 0
    series_id: str = ""
    chapter_no: int = 0
    language: str = ""
    art_style: str = ""
    aspect_ratio: str = "16:9"
    reading_pace: str = "normal"
    topic: str = ""
    tone: str = ""
    characters: list[CharacterDef] = field(default_factory=list)
    settings: list[SettingDef] = field(default_factory=list)
    visuals: list[Visual] = field(default_factory=list)
    timeline: list[Beat] = field(default_factory=list)
    render: RenderState = field(default_factory=RenderState)

    # ── Lookups ──────────────────────────────────────────────────────────
    def character(self, cid: str) -> Optional[CharacterDef]:
        k = (cid or "").strip().lower()
        return next((c for c in self.characters if c.id.strip().lower() == k), None) if k else None

    def visual(self, vid: str) -> Optional[Visual]:
        k = (vid or "").strip().lower()
        return next((v for v in self.visuals if v.id.strip().lower() == k), None) if k else None

    def setting(self, sid: str) -> Optional[SettingDef]:
        k = (sid or "").strip().lower()
        return next((s for s in self.settings if s.id.strip().lower() == k), None) if k else None

    def image_count(self) -> int:
        return len(self.visuals)

    def beat_count(self) -> int:
        return len(self.timeline)

    def is_empty(self) -> bool:
        return not any((b.narration or "").strip() or b.hold_sec > 0 for b in self.timeline)

    # ── Timing (rule-based; AI never emits seconds) ──────────────────────
    def beat_est_sec(self, beat: "Beat") -> float:
        try:
            n = (beat.narration or "").strip()
            if not n:
                return max(0.0, float(beat.hold_sec or 0.0))
            spd = (float(beat.reading_speed or 1.0) or 1.0)
            return len(n) / cps_for(self.language) / spd
        except Exception:
            return 0.0

    def estimated_total_sec(self) -> float:
        try:
            return sum(self.beat_est_sec(b) + max(0.0, float(b.pause_after or 0.0)) for b in self.timeline)
        except Exception:
            return 0.0

    def voice_runs(self) -> list[tuple]:
        """Gộp beat liên tiếp cùng speaker_id → [(speaker_id, [beat_id,...]), ...].
        Mỗi run = 1 TTS synth call (nguồn của "~1 TTS")."""
        runs: list[tuple] = []
        cur_sp = None
        cur: list[str] = []
        for b in self.timeline:
            sp = (b.speaker_id or "").strip()
            if sp != cur_sp and cur:
                runs.append((cur_sp, cur)); cur = []
            cur_sp = sp; cur.append(b.id)
        if cur:
            runs.append((cur_sp, cur))
        return runs

    # ── Integrity (INV1-8) ───────────────────────────────────────────────
    def validate_refs(self) -> "StoryPlan":
        """Enforce INV1-8 deterministically (drop/repair, never raise)."""
        try:
            # INV7: unique ids per list.
            _dedupe_ids(self.characters); _dedupe_ids(self.settings); _dedupe_ids(self.visuals)
            char_ids = {c.id for c in self.characters}
            set_ids = {s.id for s in self.settings}
            vis_ids = {v.id for v in self.visuals}
            for v in self.visuals:                                   # INV3/INV4/INV5
                if v.setting_id and v.setting_id not in set_ids:
                    v.setting_id = ""
                v.character_ids = [c for c in v.character_ids if c in char_ids]
                v.tier = _norm(v.tier, TIER, "medium")
            for c in self.characters:                                # INV5
                c.gender = _norm(c.gender, GENDER, "")
                c.voice_gender = _norm(c.voice_gender, GENDER, "")
            kept: list[Beat] = []
            for b in self.timeline:
                if b.visual_id not in vis_ids:                       # INV1: dangling → drop
                    continue
                if b.speaker_id and b.speaker_id not in char_ids:    # INV2
                    b.speaker_id = ""
                b.focus = _norm(b.focus, FOCUS, "center")            # INV5
                b.motion = _norm(b.motion, MOTION, "zoom_in")
                b.transition_in = _norm(b.transition_in, TRANSITION, "cut")
                if not (b.narration or "").strip() and b.hold_sec <= 0:   # INV8
                    continue
                kept.append(b)
            self.timeline = kept
            return self.reindex()
        except Exception:
            return self

    def cap_visuals(self, ceiling: int) -> "StoryPlan":
        """INV6: len(visuals) ≤ ceiling — keep visuals referenced by beats first
        (in first-reference order), then drop beats whose visual was cut."""
        try:
            ceiling = max(1, int(ceiling or 1))
            if len(self.visuals) <= ceiling:
                return self
            order: list[str] = []
            for b in self.timeline:
                if b.visual_id and b.visual_id not in order:
                    order.append(b.visual_id)
            by_id = {v.id: v for v in self.visuals}
            keep_ids = order[:ceiling]
            # Fill remaining slots with any unreferenced visuals (defensive).
            for v in self.visuals:
                if len(keep_ids) >= ceiling:
                    break
                if v.id not in keep_ids:
                    keep_ids.append(v.id)
            keep_set = set(keep_ids)
            self.visuals = [by_id[i] for i in keep_ids if i in by_id]
            self.timeline = [b for b in self.timeline if b.visual_id in keep_set]
            return self.reindex()
        except Exception:
            return self

    def reindex(self) -> "StoryPlan":
        """Dense re-id beats (b1..bN) + seed missing ids. Idempotent, never raises."""
        try:
            for i, b in enumerate(self.timeline, start=1):
                if not (b.id or "").strip():
                    b.id = f"b{i}"
            _dedupe_ids(self.timeline)
            for v in self.visuals:
                if not (v.id or "").strip():
                    v.id = "v" + uuid.uuid4().hex[:6]
        except Exception:
            pass
        return self

    # ── CUE SHEET (INV10-14) — deterministic resolve after images + TTS ──
    def build_cues(self, subtitle_mode: str = "hook_only") -> "StoryPlan":
        """Resolve the absolute cue sheet from (contract + render.beat_audio.dur +
        seed). Pure + deterministic; never raises. Fills render.cues + total_sec."""
        try:
            rng = random.Random(int(self.seed or 0))
            cues: list[Cue] = []
            t = 0.0
            prev_vid = None
            prev_crop = None
            for b in self.timeline:
                ba = self.render.beat_audio.get(b.id)
                dur = float(ba.dur) if (ba and ba.dur > 0) else max(0.0, float(b.hold_sec or 0.0))
                if dur <= 0:
                    dur = self.beat_est_sec(b)  # last-resort estimate
                same = (b.visual_id == prev_vid)
                trans = "cut" if same else _resolve_transition(b.transition_in, rng)
                tsec = 0.0 if trans == "cut" else TRANSITION_SEC
                cf_motion, ct_motion = _motion_pair(CROP_RECT.get(b.focus, CROP_RECT["center"]), b.motion)
                crop_from = prev_crop if (same and prev_crop is not None) else cf_motion   # INV13
                crop_to = ct_motion
                start = t - (0.0 if same else tsec)
                end = start + dur + max(0.0, float(b.pause_after or 0.0))
                cues.append(Cue(
                    beat_id=b.id, visual_id=b.visual_id, start_sec=round(start, 3), end_sec=round(end, 3),
                    crop_from=tuple(round(x, 4) for x in crop_from),
                    crop_to=tuple(round(x, 4) for x in crop_to),
                    transition=trans, transition_sec=tsec, hook=bool(b.hook), hook_text=b.hook_text,
                    audio_path=(ba.path if ba else ""),
                    subtitle=(b.narration if subtitle_mode == "full" else ""),
                ))
                t = end
                prev_vid = b.visual_id
                prev_crop = crop_to
            self.render.cues = cues
            self.render.total_sec = round(t, 3)
            return self
        except Exception:
            return self

    def image_timeline(self) -> list[tuple]:
        """[(visual_id, start_sec, end_sec), ...] — 'hình nào ở giây nào'."""
        return [(c.visual_id, c.start_sec, c.end_sec) for c in self.render.cues]

    # ── Serialisation ────────────────────────────────────────────────────
    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: "str | bytes | None") -> Optional["StoryPlan"]:
        if raw is None:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return cls._from_dict(data) if isinstance(data, dict) else None

    @classmethod
    def _from_dict(cls, d: dict[str, Any]) -> "StoryPlan":
        return cls(
            schema_version=_int(d.get("schema_version"), SCHEMA_VERSION),
            seed=_int(d.get("seed"), 0),
            series_id=_str(d.get("series_id")), chapter_no=_int(d.get("chapter_no"), 0),
            language=_str(d.get("language")), art_style=_str(d.get("art_style")),
            aspect_ratio=(_str(d.get("aspect_ratio")) or "16:9"),
            reading_pace=(_str(d.get("reading_pace")) or "normal"),
            topic=_str(d.get("topic")), tone=_str(d.get("tone")),
            characters=[_character_from(x) for x in _list(d.get("characters"))],
            settings=[_setting_from(x) for x in _list(d.get("settings"))],
            visuals=[_visual_from(x) for x in _list(d.get("visuals"))],
            timeline=[_beat_from(x, i) for i, x in enumerate(_list(d.get("timeline")), start=1)],
            render=_render_from(d.get("render")),
        )


# ── Motion / transition helpers ──────────────────────────────────────────────
def _clamp_rect(r: tuple) -> tuple:
    x, y, w, h = r
    w = min(1.0, max(0.05, w)); h = min(1.0, max(0.05, h))
    x = min(1.0 - w, max(0.0, x)); y = min(1.0 - h, max(0.0, y))
    return (x, y, w, h)


def _expand(r: tuple, f: float) -> tuple:
    x, y, w, h = r
    nw, nh = min(1.0, w * f), min(1.0, h * f)
    nx, ny = x - (nw - w) / 2, y - (nh - h) / 2
    return _clamp_rect((nx, ny, nw, nh))


def _shift(r: tuple, dx: float, dy: float) -> tuple:
    x, y, w, h = r
    return _clamp_rect((x + dx, y + dy, w, h))


def _motion_pair(target: tuple, motion: str) -> tuple:
    """(crop_from, crop_to) cho MOTION quanh vùng đích. Ken Burns nội suy from→to."""
    m = (motion or "zoom_in").strip().lower()
    if m == "zoom_in":   return _expand(target, 1.18), target
    if m == "zoom_out":  return target, _expand(target, 1.18)
    if m == "pan_left":  return _shift(target, 0.08, 0), _shift(target, -0.08, 0)
    if m == "pan_right": return _shift(target, -0.08, 0), _shift(target, 0.08, 0)
    if m == "pan_up":    return _shift(target, 0, 0.08), _shift(target, 0, -0.08)
    if m == "pan_down":  return _shift(target, 0, -0.08), _shift(target, 0, 0.08)
    return target, target  # static


def _resolve_transition(t: str, rng: random.Random) -> str:
    t = (t or "cut").strip().lower()
    if t == "random":
        return rng.choice(_RANDOM_TRANSITIONS)
    return t if t in TRANSITION else "fade"


# ── Coercion helpers ─────────────────────────────────────────────────────────
def _int(v, default):
    try: return int(v)
    except (TypeError, ValueError): return default
def _float(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default
def _str(v):
    try: return str(v or "").strip()
    except Exception: return ""
def _bool(v):
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return bool(v)
    if isinstance(v, str): return v.strip().lower() in ("true", "1", "yes", "on")
    return False
def _list(v): return v if isinstance(v, list) else []
def _clampf(v, lo, hi, default):
    x = _float(v, default); return lo if x < lo else hi if x > hi else x
def _norm(v, allowed, default):
    v = _str(v).lower(); return v if v in allowed else default
def _str_list(v, cap=48):
    if isinstance(v, str): v = [v]
    out = []
    for x in (v if isinstance(v, (list, tuple)) else []):
        s = _str(x)
        if s: out.append(s)
        if len(out) >= cap: break
    return out
def _dedupe_ids(items) -> None:
    seen = set()
    for it in items:
        base = (getattr(it, "id", "") or "").strip()
        if not base:
            continue
        cur = base; n = 2
        while cur.lower() in seen:
            cur = f"{base}_{n}"; n += 1
        it.id = cur; seen.add(cur.lower())


def _character_from(x) -> CharacterDef:
    if not isinstance(x, dict): return CharacterDef()
    name = _str(x.get("name")); cid = _str(x.get("id")) or name
    return CharacterDef(id=cid, name=(name or cid), canonical_desc=_str(x.get("canonical_desc") or x.get("description")),
                        age=_str(x.get("age")), gender=_norm(x.get("gender"), GENDER, ""),
                        voice_gender=_norm(x.get("voice_gender"), GENDER, ""), voice_style=_str(x.get("voice_style")))
def _setting_from(x) -> SettingDef:
    if not isinstance(x, dict): return SettingDef()
    name = _str(x.get("name")); sid = _str(x.get("id")) or name
    return SettingDef(id=sid, name=(name or sid), canonical_desc=_str(x.get("canonical_desc") or x.get("description")))
def _visual_from(x) -> Visual:
    if not isinstance(x, dict): return Visual()
    return Visual(id=_str(x.get("id")), setting_id=_str(x.get("setting_id")),
                  prompt=_str(x.get("prompt")), negative_prompt=_str(x.get("negative_prompt")),
                  character_ids=_str_list(x.get("character_ids")), tier=_norm(x.get("tier"), TIER, "medium"))
def _beat_from(x, i) -> Beat:
    if not isinstance(x, dict): return Beat(id=f"b{i}")
    return Beat(id=(_str(x.get("id")) or f"b{i}"), narration=_str(x.get("narration")),
                speaker_id=_str(x.get("speaker_id")), visual_id=_str(x.get("visual_id")),
                focus=_norm(x.get("focus"), FOCUS, "center"), motion=_norm(x.get("motion"), MOTION, "zoom_in"),
                emotion=(_str(x.get("emotion")).lower() or "normal"),
                reading_speed=_clampf(x.get("reading_speed"), _READING_SPEED_MIN, _READING_SPEED_MAX, _READING_SPEED_DEFAULT),
                pause_after=_clampf(x.get("pause_after"), 0.0, _PAUSE_MAX, 0.0),
                hold_sec=max(0.0, _float(x.get("hold_sec"))),
                transition_in=_norm(x.get("transition_in"), TRANSITION, "cut"),
                hook=_bool(x.get("hook")), hook_text=_str(x.get("hook_text")))
def _render_from(x) -> RenderState:
    if not isinstance(x, dict): return RenderState()
    rs = RenderState()
    try:
        va = x.get("visual_assets"); rs.visual_assets = {str(k): _str(v) for k, v in va.items()} if isinstance(va, dict) else {}
        vo = x.get("voices"); rs.voices = {str(k): list(v)[:2] for k, v in vo.items()} if isinstance(vo, dict) else {}
        rf = x.get("refs"); rs.refs = {str(k): _str(v) for k, v in rf.items()} if isinstance(rf, dict) else {}
        ba = x.get("beat_audio")
        if isinstance(ba, dict):
            for k, v in ba.items():
                if isinstance(v, dict):
                    words = [Word(_str(w.get("text")), _float(w.get("start")), _float(w.get("end")))
                             for w in _list(v.get("words")) if isinstance(w, dict)]
                    rs.beat_audio[str(k)] = BeatAudio(_str(v.get("path")), _float(v.get("dur")), words)
        for c in _list(x.get("cues")):
            if isinstance(c, dict):
                rs.cues.append(Cue(
                    beat_id=_str(c.get("beat_id")), visual_id=_str(c.get("visual_id")),
                    start_sec=_float(c.get("start_sec")), end_sec=_float(c.get("end_sec")),
                    crop_from=tuple(_float(z) for z in _list(c.get("crop_from"))[:4]) or (0.0, 0.0, 1.0, 1.0),
                    crop_to=tuple(_float(z) for z in _list(c.get("crop_to"))[:4]) or (0.0, 0.0, 1.0, 1.0),
                    transition=_norm(c.get("transition"), TRANSITION, "cut"), transition_sec=_float(c.get("transition_sec")),
                    hook=_bool(c.get("hook")), hook_text=_str(c.get("hook_text")),
                    audio_path=_str(c.get("audio_path")), subtitle=_str(c.get("subtitle"))))
        rs.total_sec = _float(x.get("total_sec"))
    except Exception:
        pass
    return rs


__all__ = [
    "StoryPlan", "CharacterDef", "SettingDef", "Visual", "Beat",
    "Word", "BeatAudio", "Cue", "RenderState",
    "FOCUS", "MOTION", "TRANSITION", "TIER", "GENDER", "SUBTITLE_MODE",
    "ASPECT_SIZE", "CPS", "CROP_RECT", "TRANSITION_SEC", "MIN_BEAT_SEC", "cps_for",
]
