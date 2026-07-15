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
# Offline asset-library scope hints (Phase 0.5). Story-level region + genre map to the
# asset_library/{kind}/{region}/{genre}/ folders so the pipeline can match a stock asset
# instead of calling AI image gen. All optional — "" = no hint (AI decides / no match).
REGION = ("cn", "jp", "ko", "vi", "eu", "us", "")
GENRE_KEY = ("wuxia", "xianxia", "ngontinh", "horror", "fantasy", "codai", "hiendai", "")
# Background-music moods the AI may tag a Visual with. Each maps to a folder under
# BGM_DIR/{mood}/ (see core.config._pick_bgm_file); "" / unknown → "default" folder.
# Kept in sync with story_prompts_v2 (the AI vocab) and scripts/fetch_free_bgm.py.
BGM_MOODS = ("tense", "calm", "epic", "sad", "romantic", "mysterious",
             "action", "hopeful", "dark", "default")
# ── s4 per-beat AI vocab (all LABELS — pipeline resolves seconds/pixels) ──────
# WHERE the music sits inside a beat's window ("under" = the whole beat, the
# pre-s4 continuous behaviour → backward-compat default).
BGM_CUE = ("under", "intro", "outro", "none")
BGM_INTENSITY = ("low", "med", "high")          # → BGM gain (see bgm_cues)
# How to treat a base video's own audio (consumed once existing-video input lands).
SOURCE_AUDIO = ("mute", "duck", "keep")
# Overlay placement of the speaking character (consumed once overlay compositing lands).
CHAR_ANCHOR = ("none", "left", "center", "right")
CHAR_SCALE = ("small", "medium", "large")
CHAR_MOTION = ("static", "fade", "slide", "float")
# N4+ per-beat character POSE (matches svg_char builder poses). "stand" = neutral (default).
POSE = ("stand", "wave", "cheer", "point", "hip")
# N4 per-beat character EMOTION (matches svg_char emotion_expr + the library variants).
# "normal" = neutral (default). The AI sets this per beat (s8); drives the emotion overlay.
EMOTION = ("normal", "happy", "angry", "sad", "surprised")
# Where on-screen text (hook / future subtitle) sits; "auto" → derived from char_anchor.
TEXT_ANCHOR = ("auto", "top", "bottom", "left", "right")
# GĐ1 Story Compiler pacing LABELS (AI emits labels, never seconds — INV kept).
# Mapped onto the numeric levers at parse time (see _beat_from): a label only
# applies when the numeric field is ABSENT from the JSON, so a hand-authored /
# round-tripped plan carrying real numbers is never overridden.
PACE = ("slow", "normal", "fast")
PAUSE = ("none", "beat", "long")
SEQUENCE_ROLE = ("setup", "inciting", "rising", "climax", "resolution")
SCENE_PURPOSE = ("setup", "reveal", "conflict", "reversal", "climax", "payoff", "transition")
SHOT_SIZE = ("extreme_wide", "wide", "medium", "close", "extreme_close")
SHOT_ANGLE = ("eye_level", "high", "low", "over_shoulder", "top_down", "dutch")
LENS = ("wide", "normal", "portrait", "telephoto")
CAMERA_POSITION = ("front", "three_quarter", "profile", "rear", "overhead")
COMPOSITION = ("centered", "rule_of_thirds", "symmetrical", "leading_lines", "negative_space")
MOTION_INTENT = ("static", "push_in", "pull_out", "track_left", "track_right", "reveal")
_PACE_SPEED = {"slow": 0.88, "normal": 1.0, "fast": 1.12}
_PAUSE_SEC = {"none": 0.0, "beat": 0.7, "long": 1.6}
# Pool a "random" transition resolves into (deterministic via seed).
_RANDOM_TRANSITIONS = ("fade", "slide", "zoom", "flash")

# ── Constants ────────────────────────────────────────────────────────────────
ASPECT_SIZE = {"16:9": (1536, 1024), "9:16": (1024, 1536), "1:1": (1024, 1024)}
CPS = {"vi": 15.0, "en": 14.0, "ja": 8.0, "ko": 9.0}
_CPS_DEFAULT = 14.0
TRANSITION_SEC = 0.4
MIN_BEAT_SEC = 1.5
# s4 placed-BGM: how long an intro/outro sting lasts inside a beat, and the dB gain
# per bgm_intensity (fed to mixer.build_placed_bgm_track).
BGM_EDGE_SEC = 1.5
_BGM_GAIN = {"low": -24.0, "med": -18.0, "high": -12.0}
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
    archetype: str = ""       # Phase 0.5: library role token (English, e.g. "swordsman"); "" = none
    asset: str = ""           # Library-pick: AI-chosen library character slug (exact); "" = none


@dataclass
class SettingDef:
    id: str = ""
    name: str = ""
    canonical_desc: str = ""
    scene_kind: str = ""      # Phase 0.5: library scene token (English, e.g. "cafe"); "" = none
    asset: str = ""           # Library-pick: AI-chosen library background slug (exact); "" = none
    # PASTE-JSON only: a hand-authored declarative SCENE SPEC (bg / floor / elements) that
    # svg_scene_spec renders → banks into the library as a background asset. Lets a NEW scene
    # be DESCRIBED by parameters (no hardcoded generator). {} = not used → old asset/scene_kind
    # flow is untouched. The AI never emits this (not in the AI schema).
    scene_spec: dict = field(default_factory=dict)


@dataclass
class Visual:
    id: str = ""
    setting_id: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    character_ids: list[str] = field(default_factory=list)
    tier: str = "medium"      # ∈ TIER


@dataclass
class Line:
    """P1 — one spoken line inside a Beat (a beat = one shot/khung hình that may hold
    several dialogue turns). ``speaker_id`` '' = narrator. Additive: a beat with no
    ``lines`` falls back to its legacy single-line fields (backward-compat)."""
    speaker_id: str = ""      # → CharacterDef.id ∪ "" (narrator)
    text: str = ""
    emotion: str = "normal"   # ∈ EMOTION — this line's expression
    pose: str = "stand"       # ∈ POSE — this line's gesture


@dataclass
class RelationshipDef:
    source_id: str = ""
    target_id: str = ""
    kind: str = ""
    status: str = ""


@dataclass
class Sequence:
    id: str = ""
    role: str = "setup"
    purpose: str = ""
    scene_ids: list[str] = field(default_factory=list)


@dataclass
class Scene:
    id: str = ""
    sequence_id: str = ""
    setting_id: str = ""
    purpose: str = "setup"
    participant_ids: list[str] = field(default_factory=list)
    beat_ids: list[str] = field(default_factory=list)
    shot_ids: list[str] = field(default_factory=list)
    time_of_day: str = ""
    entry_state: str = ""
    exit_state: str = ""
    continuity_key: str = ""


@dataclass
class Shot:
    id: str = ""
    scene_id: str = ""
    beat_ids: list[str] = field(default_factory=list)
    visual_id: str = ""
    shot_size: str = "medium"
    angle: str = "eye_level"
    lens: str = "normal"
    camera_position: str = "front"
    blocking: str = ""
    eyeline: str = ""
    axis: str = ""
    composition: str = "rule_of_thirds"
    motion_intent: str = "static"


@dataclass
class CharacterState:
    character_id: str = ""
    scene_id: str = ""
    objective: str = ""
    emotion: str = "normal"
    position: str = ""
    continuity_notes: str = ""


@dataclass
class Beat:
    id: str = ""
    narration: str = ""
    speaker_id: str = ""      # → CharacterDef.id ∪ ""
    visual_id: str = ""       # → Visual.id
    shot_id: str = ""         # → Shot.id (derived for legacy plans)
    focus: str = "center"     # ∈ FOCUS
    motion: str = "zoom_in"   # ∈ MOTION
    emotion: str = "normal"
    reading_speed: float = 1.0
    pause_after: float = 0.0
    hold_sec: float = 0.0
    transition_in: str = "cut"  # ∈ TRANSITION (only used when the visual changes)
    pose: str = "stand"         # N4+ ∈ POSE — speaker gesture for this beat (overlay mode)
    hook: bool = False
    hook_text: str = ""
    bgm_mood: str = ""          # ∈ BGM_MOODS — AI-chosen music mood for THIS beat
    # ── s4 per-beat AI decisions (labels; defaults reproduce pre-s4 behaviour) ──
    bgm_cue: str = "under"      # ∈ BGM_CUE — WHERE music sits in this beat
    bgm_intensity: str = "med"  # ∈ BGM_INTENSITY — music loudness
    source_audio: str = "mute"  # ∈ SOURCE_AUDIO — base-video audio (consumed later)
    char_anchor: str = "none"   # ∈ CHAR_ANCHOR — speaker overlay position (consumed later)
    char_scale: str = "medium"  # ∈ CHAR_SCALE — speaker overlay size (consumed later)
    char_motion: str = "fade"   # ∈ CHAR_MOTION — speaker overlay entrance (consumed later)
    text_anchor: str = "auto"   # ∈ TEXT_ANCHOR — on-screen text placement
    # P1 — multi-line dialogue: a beat may carry several spoken lines (each its own
    # speaker/emotion). Empty → the legacy single-line fields above ARE the one line.
    lines: list["Line"] = field(default_factory=list)

    def effective_lines(self) -> "list[Line]":
        """The beat's spoken lines, normalised. Uses ``lines`` when present (dropping
        blank ones), else synthesises ONE line from the legacy ``narration`` /
        ``speaker_id`` fields. A silent-hold beat (no text at all) yields []."""
        if self.lines:
            return [ln for ln in self.lines if (ln.text or "").strip()]
        if (self.narration or "").strip():
            return [Line(self.speaker_id, self.narration, self.emotion, self.pose)]
        return []

    def primary_speaker(self) -> str:
        """Beat-level speaker for overlay/anchor: legacy ``speaker_id`` if set, else the
        first non-narrator line's speaker, else '' (narrator)."""
        if (self.speaker_id or "").strip():
            return self.speaker_id
        for ln in self.effective_lines():
            if (ln.speaker_id or "").strip():
                return ln.speaker_id
        return ""


# ── Render-state dataclasses (pipeline-filled) ───────────────────────────────
@dataclass
class Word:
    text: str = ""
    start: float = 0.0
    end: float = 0.0


@dataclass
class LineSpan:
    """P3 — one dialogue line's time window WITHIN a beat's concatenated audio, plus who
    speaks it + how they look. Drives the per-line character overlay (the on-screen
    speaker switches as the line changes). ``anchor`` = that speaker's stable screen slot."""
    start: float = 0.0
    end: float = 0.0
    speaker_id: str = ""
    emotion: str = "normal"
    pose: str = "stand"
    anchor: str = "center"    # ∈ CHAR_ANCHOR — filled by build_cues from the character order


@dataclass
class BeatAudio:
    path: str = ""
    dur: float = 0.0
    words: list[Word] = field(default_factory=list)
    spans: list[LineSpan] = field(default_factory=list)   # P3 — per-line windows (dialogue)


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
    bgm_mood: str = ""          # ∈ BGM_MOODS — carried from the beat for per-beat BGM
    bgm_cue: str = "under"      # ∈ BGM_CUE — carried from the beat (placed-BGM)
    bgm_intensity: str = "med"  # ∈ BGM_INTENSITY — carried from the beat
    text_anchor: str = "auto"   # ∈ TEXT_ANCHOR — carried from the beat (hook placement)
    # A3 character overlay — carried from the beat so the cue render can composite the
    # speaking character's master over a base video (consumed only with a base video).
    speaker_id: str = ""        # → CharacterDef.id ∪ "" (whose master to overlay)
    char_anchor: str = "none"   # ∈ CHAR_ANCHOR — overlay position ("none" = no overlay)
    char_scale: str = "medium"  # ∈ CHAR_SCALE — overlay size
    char_motion: str = "fade"   # ∈ CHAR_MOTION — overlay entrance/motion
    emotion: str = "normal"     # N4 — carried from the beat; picks the speaker's emotion master
    pose: str = "stand"         # N4+ ∈ POSE — carried from the beat; picks the pose master
    source_audio: str = "mute"  # ∈ SOURCE_AUDIO — base-video audio (A4; "mute" = drop it)
    line_overlays: list = field(default_factory=list)   # P3 — [LineSpan] per-line speaker overlays


@dataclass
class RenderState:
    visual_assets: dict[str, str] = field(default_factory=dict)          # visual_id → path
    voices: dict[str, list] = field(default_factory=dict)                # char_id → [engine, voice_id]
    refs: dict[str, str] = field(default_factory=dict)                   # char_id → ref image path
    masters: dict[str, str] = field(default_factory=dict)                # char_id → transparent master PNG (A3 overlay)
    beat_audio: dict[str, BeatAudio] = field(default_factory=dict)       # beat_id → BeatAudio
    cues: list[Cue] = field(default_factory=list)
    total_sec: float = 0.0
    # GĐ3 — per-character asset resolution state (character_resolver):
    # char_id → matched_exact | matched | needs_approval | missing. Additive; {} on
    # legacy plans. Review/monitor surface it; render never gates on it.
    asset_status: dict[str, str] = field(default_factory=dict)


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
    region: str = ""          # Phase 0.5: ∈ REGION — asset-library market scope ("" = none)
    genre_key: str = ""       # Phase 0.5: ∈ GENRE_KEY — asset-library genre scope ("" = none)
    characters: list[CharacterDef] = field(default_factory=list)
    settings: list[SettingDef] = field(default_factory=list)
    visuals: list[Visual] = field(default_factory=list)
    relationships: list[RelationshipDef] = field(default_factory=list)
    sequences: list[Sequence] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    character_states: list[CharacterState] = field(default_factory=list)
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

    def shot(self, shot_id: str) -> Optional[Shot]:
        k = (shot_id or "").strip().lower()
        return next((s for s in self.shots if s.id.strip().lower() == k), None) if k else None

    def scene(self, scene_id: str) -> Optional[Scene]:
        k = (scene_id or "").strip().lower()
        return next((s for s in self.scenes if s.id.strip().lower() == k), None) if k else None

    def image_count(self) -> int:
        return len(self.visuals)

    def beat_count(self) -> int:
        return len(self.timeline)

    def is_empty(self) -> bool:
        return not any(b.effective_lines() or b.hold_sec > 0 for b in self.timeline)

    # ── Timing (rule-based; AI never emits seconds) ──────────────────────
    def beat_est_sec(self, beat: "Beat") -> float:
        try:
            chars = sum(len((ln.text or "").strip()) for ln in beat.effective_lines())
            if not chars:
                return max(0.0, float(beat.hold_sec or 0.0))
            spd = (float(beat.reading_speed or 1.0) or 1.0)
            return chars / cps_for(self.language) / spd
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
            _dedupe_ids(self.sequences); _dedupe_ids(self.scenes); _dedupe_ids(self.shots)
            char_ids = {c.id for c in self.characters}
            set_ids = {s.id for s in self.settings}
            vis_ids = {v.id for v in self.visuals}
            seq_ids = {s.id for s in self.sequences}
            scene_ids = {s.id for s in self.scenes}
            shot_ids = {s.id for s in self.shots}
            beat_ids = {b.id for b in self.timeline}
            self.relationships = [r for r in self.relationships
                                  if r.source_id in char_ids and r.target_id in char_ids
                                  and r.source_id != r.target_id]
            for seq in self.sequences:
                seq.role = _norm(seq.role, SEQUENCE_ROLE, "setup")
                seq.scene_ids = [sid for sid in seq.scene_ids if sid in scene_ids]
            for scene in self.scenes:
                if scene.sequence_id not in seq_ids:
                    scene.sequence_id = ""
                if scene.setting_id not in set_ids:
                    scene.setting_id = ""
                scene.purpose = _norm(scene.purpose, SCENE_PURPOSE, "setup")
                scene.participant_ids = [cid for cid in scene.participant_ids if cid in char_ids]
                scene.beat_ids = [bid for bid in scene.beat_ids if bid in beat_ids]
                scene.shot_ids = [sid for sid in scene.shot_ids if sid in shot_ids]
            for shot in self.shots:
                if shot.scene_id not in scene_ids:
                    shot.scene_id = ""
                if shot.visual_id not in vis_ids:
                    shot.visual_id = ""
                shot.beat_ids = [bid for bid in shot.beat_ids if bid in beat_ids]
                shot.shot_size = _norm(shot.shot_size, SHOT_SIZE, "medium")
                shot.angle = _norm(shot.angle, SHOT_ANGLE, "eye_level")
                shot.lens = _norm(shot.lens, LENS, "normal")
                shot.camera_position = _norm(shot.camera_position, CAMERA_POSITION, "front")
                shot.composition = _norm(shot.composition, COMPOSITION, "rule_of_thirds")
                shot.motion_intent = _norm(shot.motion_intent, MOTION_INTENT, "static")
            self.character_states = [s for s in self.character_states
                                     if s.character_id in char_ids and s.scene_id in scene_ids]
            for state in self.character_states:
                state.emotion = _norm(state.emotion, EMOTION, "normal")
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
                if b.shot_id and b.shot_id not in shot_ids:
                    b.shot_id = ""
                if b.speaker_id and b.speaker_id not in char_ids:    # INV2
                    b.speaker_id = ""
                for ln in b.lines:                                   # INV2 (per line) + INV5
                    if ln.speaker_id and ln.speaker_id not in char_ids:
                        ln.speaker_id = ""
                    ln.emotion = _norm(ln.emotion, EMOTION, "normal")
                    ln.pose = _norm(ln.pose, POSE, "stand")
                b.focus = _norm(b.focus, FOCUS, "center")            # INV5
                b.motion = _norm(b.motion, MOTION, "zoom_in")
                b.transition_in = _norm(b.transition_in, TRANSITION, "cut")
                if not b.effective_lines() and b.hold_sec <= 0:      # INV8
                    continue
                kept.append(b)
            self.timeline = kept
            return self.reindex()
        except Exception:
            return self

    def cap_visuals(self, ceiling: int) -> "StoryPlan":
        """INV6: len(visuals) ≤ ceiling — keep the visuals referenced by beats first
        (first-reference order). Beats whose visual is cut are REMAPPED to a kept
        visual (same setting when possible, else the last kept one) — NEVER dropped.

        Capping the IMAGE count must never truncate the STORY: the previous
        implementation deleted every beat referencing a cut visual, so an
        over-imaged plan (≈one image per beat) had its whole back half silently
        removed — a 3-minute story collapsed to ~30 seconds. Remapping preserves
        every narrated beat, so the video keeps its full length regardless of how
        many distinct images the AI proposed."""
        try:
            ceiling = max(1, int(ceiling or 1))
            if len(self.visuals) <= ceiling:
                return self
            order: list[str] = []
            for b in self.timeline:
                if b.visual_id and b.visual_id not in order:
                    order.append(b.visual_id)
            by_id = {v.id: v for v in self.visuals}          # full set (pre-trim)
            keep_ids = order[:ceiling]
            # Fill remaining slots with any unreferenced visuals (defensive).
            for v in self.visuals:
                if len(keep_ids) >= ceiling:
                    break
                if v.id not in keep_ids:
                    keep_ids.append(v.id)
            keep_set = set(keep_ids)
            self.visuals = [by_id[i] for i in keep_ids if i in by_id]
            # Remap (do NOT drop) beats whose visual was cut → a kept visual in the
            # SAME setting when one exists, else the last kept visual.
            kept_by_setting: dict[str, str] = {}
            for vid in keep_ids:
                v = by_id.get(vid)
                if v is not None and v.setting_id:
                    kept_by_setting.setdefault(v.setting_id, vid)
            fallback = keep_ids[-1] if keep_ids else ""
            for b in self.timeline:
                if b.visual_id in keep_set:
                    continue
                orig = by_id.get(b.visual_id)
                b.visual_id = (kept_by_setting.get(orig.setting_id) if orig is not None else None) or fallback
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

    def normalize_for_render(self, ceiling: int = 15) -> "StoryPlan":
        """Prepare a HAND-PASTED / imported / EDITED plan for rendering (paste-JSON +
        Review edits): scrub dangling refs, cap the image count, dense-reindex, and clear
        only the DERIVED render state that is regenerated every render (cue sheet + timed
        audio). It deliberately PRESERVES the user's Review picks — ``render.voices``
        (per-character voice override), ``render.masters`` (pinned character image) and
        ``render.visual_assets`` (pinned background) — which live in render state; the
        render layer re-validates each path's existence (``_ready`` / master pick), so a
        stale cross-job path simply regenerates. (Was: reset ALL render → wiped the picks.)
        Pure; never raises."""
        try:
            self.cap_visuals(ceiling)      # cap_visuals also reindexes
            self.derive_scene_shot_grammar()
            self.validate_refs()
            self.apply_shot_grammar()
            self.reindex()
            self.render.cues = []          # rebuilt by build_cues every render
            self.render.beat_audio = {}    # re-synthesized by synthesize_timeline
            self.render.refs = {}          # regenerated character reference images
            self.render.total_sec = 0.0
        except Exception:
            pass
        return self

    def derive_scene_shot_grammar(self) -> "StoryPlan":
        """Fill a first-class editorial/camera graph for legacy AI plans.

        Existing authored entities win. Missing entities are derived from contiguous
        setting runs and one executable shot per beat. The timeline remains the
        backward-compatible source of narration and timing.
        """
        try:
            if not self.timeline:
                return self
            beat_ids = {beat.id for beat in self.timeline}
            shot_ids = {shot.id for shot in self.shots}
            if (self.scenes and self.shots
                    and all((beat.shot_id or "") in shot_ids for beat in self.timeline)
                    and all(any(bid in beat_ids for bid in shot.beat_ids) for shot in self.shots)):
                return self.apply_shot_grammar()

            vis_by_id = {v.id: v for v in self.visuals}
            self.sequences = []
            self.scenes = []
            self.shots = []
            self.character_states = []
            total = len(self.timeline)
            ranges = ((0.00, 0.18, "setup"), (0.18, 0.34, "inciting"),
                      (0.34, 0.72, "rising"), (0.72, 0.90, "climax"),
                      (0.90, 1.01, "resolution"))

            scene_beats: list[list[Beat]] = []
            current: list[Beat] = []
            current_key = None
            for beat in self.timeline:
                visual = vis_by_id.get(beat.visual_id)
                setting_id = visual.setting_id if visual else ""
                key = (setting_id, beat.visual_id)
                if current and key != current_key:
                    scene_beats.append(current)
                    current = []
                current_key = key
                current.append(beat)
            if current:
                scene_beats.append(current)

            seq_by_role: dict[str, Sequence] = {}
            size_cycle = ("wide", "medium", "close", "medium", "wide", "extreme_close")
            angle_cycle = ("eye_level", "three_quarter", "low", "over_shoulder", "high")
            comp_cycle = ("rule_of_thirds", "leading_lines", "centered", "negative_space", "symmetrical")
            motion_cycle = ("push_in", "track_left", "static", "track_right", "pull_out", "reveal")
            beat_index = {b.id: i for i, b in enumerate(self.timeline)}
            char_positions = self._char_positions()

            for scene_no, beats in enumerate(scene_beats, start=1):
                first_idx = beat_index.get(beats[0].id, 0)
                fraction = first_idx / max(1, total - 1)
                role = next(r for lo, hi, r in ranges if lo <= fraction < hi)
                sequence = seq_by_role.get(role)
                if sequence is None:
                    sequence = Sequence(id=f"seq{len(seq_by_role) + 1}", role=role,
                                        purpose=role.replace("_", " "))
                    seq_by_role[role] = sequence
                    self.sequences.append(sequence)

                scene_id = f"sc{scene_no}"
                visual = vis_by_id.get(beats[0].visual_id)
                setting_id = visual.setting_id if visual else ""
                purpose = "climax" if role == "climax" else "payoff" if role == "resolution" else (
                    "reversal" if role == "rising" and fraction > 0.55 else
                    "conflict" if role in ("inciting", "rising") else "setup")
                participants: list[str] = []
                for beat in beats:
                    ids = [beat.primary_speaker(), *[line.speaker_id for line in beat.effective_lines()]]
                    for cid in ids:
                        if cid and cid not in participants:
                            participants.append(cid)
                scene = Scene(id=scene_id, sequence_id=sequence.id, setting_id=setting_id,
                              purpose=purpose, participant_ids=participants,
                              beat_ids=[b.id for b in beats], continuity_key=(setting_id or scene_id))
                sequence.scene_ids.append(scene_id)
                self.scenes.append(scene)

                for local_i, beat in enumerate(beats):
                    global_i = beat_index.get(beat.id, 0)
                    shot_id = f"sh{global_i + 1}"
                    is_first = local_i == 0
                    is_hook = bool(beat.hook or (beat.hook_text or "").strip())
                    is_payoff = role == "resolution" and local_i == len(beats) - 1
                    size = "wide" if is_first else size_cycle[(global_i + int(self.seed or 0)) % len(size_cycle)]
                    if is_hook or is_payoff:
                        size = "close"
                    angle_token = angle_cycle[(global_i + scene_no + int(self.seed or 0)) % len(angle_cycle)]
                    shot = Shot(
                        id=shot_id, scene_id=scene_id, beat_ids=[beat.id], visual_id=beat.visual_id,
                        shot_size=size,
                        angle=("eye_level" if angle_token == "three_quarter" else angle_token),
                        lens=("wide" if size in ("extreme_wide", "wide") else
                              "portrait" if size in ("close", "extreme_close") else "normal"),
                        camera_position=("three_quarter" if angle_token == "three_quarter" else
                                         "profile" if global_i % 4 == 3 else "front"),
                        blocking=("establish participants and geography" if is_first else
                                  "hold the active speaker on the dominant third"),
                        eyeline=("toward the opposing third" if beat.primary_speaker() else "environmental"),
                        axis=f"{scene_id}:primary",
                        composition=comp_cycle[(global_i + int(self.seed or 0)) % len(comp_cycle)],
                        motion_intent=("reveal" if is_first else
                                       motion_cycle[(global_i + int(self.seed or 0)) % len(motion_cycle)]),
                    )
                    beat.shot_id = shot_id
                    scene.shot_ids.append(shot_id)
                    self.shots.append(shot)
                for cid in participants:
                    self.character_states.append(CharacterState(
                        character_id=cid, scene_id=scene_id,
                        objective=("resolve the central conflict" if purpose in ("climax", "payoff")
                                   else "advance the scene objective"),
                        emotion=next((b.emotion for b in beats if b.primary_speaker() == cid), "normal"),
                        position=char_positions.get(cid, "center"),
                        continuity_notes=f"Keep appearance and screen side stable within {scene_id}",
                    ))
            return self.apply_shot_grammar()
        except Exception:
            return self

    def apply_shot_grammar(self) -> "StoryPlan":
        """Project editable Shot decisions onto renderer-supported Beat controls."""
        try:
            focus_map = {"extreme_wide": "wide", "wide": "wide", "medium": "center",
                         "close": "close", "extreme_close": "close"}
            motion_map = {"static": "static", "push_in": "zoom_in", "pull_out": "zoom_out",
                          "track_left": "pan_left", "track_right": "pan_right", "reveal": "pan_up"}
            shots = {shot.id: shot for shot in self.shots}
            for beat in self.timeline:
                shot = shots.get(beat.shot_id)
                if shot is None:
                    continue
                beat.focus = focus_map.get(shot.shot_size, beat.focus)
                beat.motion = motion_map.get(shot.motion_intent, beat.motion)
            return self
        except Exception:
            return self

    def _char_positions(self) -> dict:
        """Stable screen slot per character by first appearance (center → left → right → …).
        Shared by derive_beat_styling (beat.char_anchor) and build_cues (per-line overlays)
        so a character stands in the SAME spot whether it's the beat's sole speaker or one
        turn in a dialogue."""
        _POS = ("center", "left", "right")
        order: list[str] = []
        for c in self.characters:
            if c.id and c.id not in order:
                order.append(c.id)
        return {cid: _POS[i % len(_POS)] for i, cid in enumerate(order)}

    def derive_beat_styling(self) -> "StoryPlan":
        """Phase 3 (lean contract): the AI no longer emits the MECHANICAL per-beat style
        labels — derive them here so the render keeps its variety and the speaking-
        character overlay still appears. FILL-ONLY: a beat that already carries a
        NON-DEFAULT value (a P2 / legacy plan where the AI DID set it) is left untouched,
        so this is backward-safe. Pure, deterministic (seed), idempotent, never raises.

        Must run BEFORE overlay-master gen + build_cues (both read these fields)."""
        try:
            # char_anchor — CORRECTNESS: a speaking beat with anchor 'none' composites NO
            # character overlay. Give each character a STABLE screen position by first
            # appearance (center → left → right → …); narrator beats stay 'none'.
            char_pos = self._char_positions()
            _MOT = ("zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down")
            seed = int(self.seed or 0)
            n = len(self.timeline)
            for i, b in enumerate(self.timeline):
                prev_vid = self.timeline[i - 1].visual_id if i > 0 else None
                next_vid = self.timeline[i + 1].visual_id if i < n - 1 else None
                scene_first = (b.visual_id != prev_vid)
                scene_last = (b.visual_id != next_vid)
                sp = b.primary_speaker()
                if (b.char_anchor or "none") == "none" and sp:
                    b.char_anchor = char_pos.get(sp, "center")
                if (b.motion or "zoom_in") == "zoom_in":            # variety (else all zoom_in)
                    b.motion = _MOT[(i + seed) % len(_MOT)]
                if (b.transition_in or "cut") == "cut":             # fade on a scene change
                    b.transition_in = "fade" if scene_first else "cut"
                if (b.bgm_cue or "under") == "under":               # rule-8 intro/outro placement
                    if scene_first and not scene_last:
                        b.bgm_cue = "intro"
                    elif scene_last and not scene_first:
                        b.bgm_cue = "outro"
                    else:
                        b.bgm_cue = "under"
                if (b.bgm_intensity or "med") == "med":             # from mood/emotion
                    mood = (b.bgm_mood or "").lower()
                    emo = (b.emotion or "normal").lower()
                    if mood in ("action", "epic", "tense") or emo in ("angry", "surprised"):
                        b.bgm_intensity = "high"
                    elif mood in ("sad", "calm") or emo == "sad":
                        b.bgm_intensity = "low"
                    else:
                        b.bgm_intensity = "med"
            return self
        except Exception:
            return self

    # ── CUE SHEET (INV10-14) — deterministic resolve after images + TTS ──
    def build_cues(self, subtitle_mode: str = "hook_only") -> "StoryPlan":
        """Resolve the absolute cue sheet from (contract + render.beat_audio.dur +
        seed). Pure + deterministic; never raises. Fills render.cues + total_sec.

        On-screen text is HOOK-ONLY (climactic beats carry hook_text) — there is no
        full-video subtitle. ``subtitle_mode`` is reserved for hook gating upstream."""
        try:
            rng = random.Random(int(self.seed or 0))
            char_pos = self._char_positions()          # P3 — per-line overlay anchors
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
                # Per-line overlay spans: prefer the TTS-produced per-line windows (a
                # dialogue beat with 2+ speakers). When ABSENT — a single-speaker beat
                # takes the one-voice TTS path which emits no spans — derive ONE
                # whole-beat span from the primary speaking line so that character is
                # still overlaid. Without this, the common single-speaker beat renders
                # BACKGROUND-ONLY (the multi-line-beats regression). primary_speaker()
                # returns "" for a narrator-only beat, so those stay overlay-less.
                _ov_spans = list(getattr(ba, "spans", []) or []) if ba else []
                if not _ov_spans:
                    _psp = b.primary_speaker()
                    if _psp:
                        _pl = next((ln for ln in b.effective_lines()
                                    if (ln.speaker_id or "") == _psp), None)
                        _ov_spans = [LineSpan(
                            start=0.0, end=round(dur, 3), speaker_id=_psp,
                            emotion=((_pl.emotion if _pl else b.emotion) or "normal"),
                            pose=((_pl.pose if _pl else b.pose) or "stand"))]
                cues.append(Cue(
                    beat_id=b.id, visual_id=b.visual_id, start_sec=round(start, 3), end_sec=round(end, 3),
                    crop_from=tuple(round(x, 4) for x in crop_from),
                    crop_to=tuple(round(x, 4) for x in crop_to),
                    transition=trans, transition_sec=tsec, hook=bool(b.hook), hook_text=b.hook_text,
                    audio_path=(ba.path if ba else ""),
                    bgm_mood=(b.bgm_mood or ""),
                    bgm_cue=(b.bgm_cue or "under"), bgm_intensity=(b.bgm_intensity or "med"),
                    text_anchor=(b.text_anchor or "auto"),
                    speaker_id=(b.speaker_id or ""), char_anchor=(b.char_anchor or "none"),
                    char_scale=(b.char_scale or "medium"), char_motion=(b.char_motion or "fade"),
                    emotion=(b.emotion or "normal"), pose=(b.pose or "stand"),
                    source_audio=(b.source_audio or "mute"),
                    line_overlays=[
                        LineSpan(start=s.start, end=s.end, speaker_id=s.speaker_id,
                                 emotion=s.emotion, pose=s.pose,
                                 anchor=(char_pos.get(s.speaker_id, "center") if (s.speaker_id or "") else "none"))
                        for s in _ov_spans
                    ],
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

    def bgm_scenes(self) -> list[tuple]:
        """[(mood, start_sec, end_sec), ...] — gộp cue liên tiếp CÙNG bgm_mood thành một
        'đoạn nhạc' (per-beat mood → mood-run). Dùng để dựng track nhạc nền theo
        timeline. start kẹp ≥0 (cue đầu có thể âm do transition). Pure, never raises."""
        out: list[tuple] = []
        try:
            started = False
            cur_mood = ""
            cur_start = 0.0
            cur_end = 0.0
            for c in self.render.cues:
                mood = (c.bgm_mood or "")
                if not started:
                    started = True
                    cur_mood = mood
                    cur_start = float(c.start_sec)
                elif mood != cur_mood:
                    if cur_end > cur_start:
                        out.append((cur_mood, round(max(0.0, cur_start), 3), round(cur_end, 3)))
                    cur_mood = mood
                    cur_start = float(c.start_sec)
                cur_end = float(c.end_sec)
            if started and cur_end > cur_start:
                out.append((cur_mood, round(max(0.0, cur_start), 3), round(cur_end, 3)))
        except Exception:
            return out
        return out

    def bgm_cues(self) -> list[tuple]:
        """[(mood, start_sec, end_sec, gain_db), ...] — PLACED background music from the
        per-beat ``bgm_cue`` label (s4): ``under`` = whole cue, ``intro`` = first
        BGM_EDGE_SEC, ``outro`` = last BGM_EDGE_SEC, ``none`` = skipped. ``bgm_intensity``
        → gain_db. Consecutive continuous windows with the SAME mood+gain are merged so
        an under-run plays as ONE clip (no per-beat re-fade). start clamped ≥0. Pure,
        never raises. Fed to mixer.build_placed_bgm_track."""
        raw: list[list] = []
        try:
            for c in self.render.cues:
                kind = (getattr(c, "bgm_cue", "under") or "under")
                if kind == "none":
                    continue
                s = max(0.0, float(c.start_sec))
                e = float(c.end_sec)
                if e <= s:
                    continue
                gain = _BGM_GAIN.get((getattr(c, "bgm_intensity", "med") or "med"), -18.0)
                if kind == "intro":
                    e = min(e, s + BGM_EDGE_SEC)
                elif kind == "outro":
                    s = max(s, e - BGM_EDGE_SEC)
                if e <= s:
                    continue
                mood = (c.bgm_mood or "")
                if raw and raw[-1][0] == mood and raw[-1][3] == gain and s - raw[-1][2] <= 0.05:
                    raw[-1][2] = e                      # merge adjacent same-mood run
                else:
                    raw.append([mood, s, e, gain])
        except Exception:
            return [(m, round(s, 3), round(e, 3), g) for m, s, e, g in raw]
        return [(m, round(s, 3), round(e, 3), g) for m, s, e, g in raw]

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
            region=_norm(d.get("region"), REGION, ""),
            genre_key=_norm(d.get("genre_key"), GENRE_KEY, ""),
            characters=[_character_from(x) for x in _list(d.get("characters"))],
            settings=[_setting_from(x) for x in _list(d.get("settings"))],
            visuals=[_visual_from(x) for x in _list(d.get("visuals"))],
            relationships=[_relationship_from(x) for x in _list(d.get("relationships"))],
            sequences=[_sequence_from(x) for x in _list(d.get("sequences"))],
            scenes=[_scene_from(x) for x in _list(d.get("scenes"))],
            shots=[_shot_from(x) for x in _list(d.get("shots"))],
            character_states=[_character_state_from(x) for x in _list(d.get("character_states"))],
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
                        voice_gender=_norm(x.get("voice_gender"), GENDER, ""), voice_style=_str(x.get("voice_style")),
                        archetype=_str(x.get("archetype")), asset=_str(x.get("asset")))
def _setting_from(x) -> SettingDef:
    if not isinstance(x, dict): return SettingDef()
    name = _str(x.get("name")); sid = _str(x.get("id")) or name
    _spec = x.get("scene_spec")
    return SettingDef(id=sid, name=(name or sid), canonical_desc=_str(x.get("canonical_desc") or x.get("description")),
                      scene_kind=_str(x.get("scene_kind")), asset=_str(x.get("asset")),
                      scene_spec=(_spec if isinstance(_spec, dict) else {}))
def _visual_from(x) -> Visual:
    if not isinstance(x, dict): return Visual()
    return Visual(id=_str(x.get("id")), setting_id=_str(x.get("setting_id")),
                  prompt=_str(x.get("prompt")), negative_prompt=_str(x.get("negative_prompt")),
                  character_ids=_str_list(x.get("character_ids")), tier=_norm(x.get("tier"), TIER, "medium"))
def _relationship_from(x) -> RelationshipDef:
    if not isinstance(x, dict): return RelationshipDef()
    return RelationshipDef(source_id=_str(x.get("source_id") or x.get("a")),
                           target_id=_str(x.get("target_id") or x.get("b")),
                           kind=_str(x.get("kind") or x.get("type")), status=_str(x.get("status")))
def _sequence_from(x) -> Sequence:
    if not isinstance(x, dict): return Sequence()
    return Sequence(id=_str(x.get("id")), role=_norm(x.get("role"), SEQUENCE_ROLE, "setup"),
                    purpose=_str(x.get("purpose")), scene_ids=_str_list(x.get("scene_ids")))
def _scene_from(x) -> Scene:
    if not isinstance(x, dict): return Scene()
    return Scene(id=_str(x.get("id")), sequence_id=_str(x.get("sequence_id")),
                 setting_id=_str(x.get("setting_id")), purpose=_norm(x.get("purpose"), SCENE_PURPOSE, "setup"),
                 participant_ids=_str_list(x.get("participant_ids")), beat_ids=_str_list(x.get("beat_ids")),
                 shot_ids=_str_list(x.get("shot_ids")), time_of_day=_str(x.get("time_of_day")),
                 entry_state=_str(x.get("entry_state")), exit_state=_str(x.get("exit_state")),
                 continuity_key=_str(x.get("continuity_key")))
def _shot_from(x) -> Shot:
    if not isinstance(x, dict): return Shot()
    return Shot(id=_str(x.get("id")), scene_id=_str(x.get("scene_id")), beat_ids=_str_list(x.get("beat_ids")),
                visual_id=_str(x.get("visual_id")), shot_size=_norm(x.get("shot_size"), SHOT_SIZE, "medium"),
                angle=_norm(x.get("angle"), SHOT_ANGLE, "eye_level"), lens=_norm(x.get("lens"), LENS, "normal"),
                camera_position=_norm(x.get("camera_position"), CAMERA_POSITION, "front"),
                blocking=_str(x.get("blocking")), eyeline=_str(x.get("eyeline")), axis=_str(x.get("axis")),
                composition=_norm(x.get("composition"), COMPOSITION, "rule_of_thirds"),
                motion_intent=_norm(x.get("motion_intent"), MOTION_INTENT, "static"))
def _character_state_from(x) -> CharacterState:
    if not isinstance(x, dict): return CharacterState()
    return CharacterState(character_id=_str(x.get("character_id")), scene_id=_str(x.get("scene_id")),
                          objective=_str(x.get("objective")), emotion=_norm(x.get("emotion"), EMOTION, "normal"),
                          position=_str(x.get("position")), continuity_notes=_str(x.get("continuity_notes")))
def _line_from(x) -> Line:
    if not isinstance(x, dict):
        return Line()
    return Line(speaker_id=_str(x.get("speaker_id")),
                text=_str(x.get("text") or x.get("narration")),
                emotion=_norm(x.get("emotion"), EMOTION, "normal"),
                pose=_norm(x.get("pose"), POSE, "stand"))
def _linespan_from(x) -> LineSpan:
    if not isinstance(x, dict):
        return LineSpan()
    return LineSpan(start=_float(x.get("start")), end=_float(x.get("end")),
                    speaker_id=_str(x.get("speaker_id")),
                    emotion=_norm(x.get("emotion"), EMOTION, "normal"),
                    pose=_norm(x.get("pose"), POSE, "stand"),
                    anchor=_norm(x.get("anchor"), CHAR_ANCHOR, "center"))
def _beat_from(x, i) -> Beat:
    if not isinstance(x, dict): return Beat(id=f"b{i}")
    # GĐ1 pacing LABELS → numeric levers, ONLY when the numeric field is absent
    # (a hand-authored / round-tripped plan carrying numbers is never overridden).
    _rs = x.get("reading_speed")
    if _rs is None:
        _rs = _PACE_SPEED.get(_norm(x.get("pace"), PACE, "normal"), 1.0)
    _pa = x.get("pause_after")
    if _pa is None:
        _pa = _PAUSE_SEC.get(_norm(x.get("pause"), PAUSE, "none"), 0.0)
    return Beat(id=(_str(x.get("id")) or f"b{i}"), narration=_str(x.get("narration")),
                speaker_id=_str(x.get("speaker_id")), visual_id=_str(x.get("visual_id")),
                shot_id=_str(x.get("shot_id")),
                focus=_norm(x.get("focus"), FOCUS, "center"), motion=_norm(x.get("motion"), MOTION, "zoom_in"),
                emotion=_norm(x.get("emotion"), EMOTION, "normal"),
                reading_speed=_clampf(_rs, _READING_SPEED_MIN, _READING_SPEED_MAX, _READING_SPEED_DEFAULT),
                pause_after=_clampf(_pa, 0.0, _PAUSE_MAX, 0.0),
                hold_sec=max(0.0, _float(x.get("hold_sec"))),
                transition_in=_norm(x.get("transition_in"), TRANSITION, "cut"),
                pose=_norm(x.get("pose"), POSE, "stand"),
                hook=_bool(x.get("hook")), hook_text=_str(x.get("hook_text")),
                bgm_mood=_norm(x.get("bgm_mood"), BGM_MOODS, ""),
                bgm_cue=_norm(x.get("bgm_cue"), BGM_CUE, "under"),
                bgm_intensity=_norm(x.get("bgm_intensity"), BGM_INTENSITY, "med"),
                source_audio=_norm(x.get("source_audio"), SOURCE_AUDIO, "mute"),
                char_anchor=_norm(x.get("char_anchor"), CHAR_ANCHOR, "none"),
                char_scale=_norm(x.get("char_scale"), CHAR_SCALE, "medium"),
                char_motion=_norm(x.get("char_motion"), CHAR_MOTION, "fade"),
                text_anchor=_norm(x.get("text_anchor"), TEXT_ANCHOR, "auto"),
                lines=[_line_from(l) for l in _list(x.get("lines"))])
def _render_from(x) -> RenderState:
    if not isinstance(x, dict): return RenderState()
    rs = RenderState()
    try:
        va = x.get("visual_assets"); rs.visual_assets = {str(k): _str(v) for k, v in va.items()} if isinstance(va, dict) else {}
        vo = x.get("voices"); rs.voices = {str(k): list(v)[:2] for k, v in vo.items()} if isinstance(vo, dict) else {}
        rf = x.get("refs"); rs.refs = {str(k): _str(v) for k, v in rf.items()} if isinstance(rf, dict) else {}
        ms = x.get("masters"); rs.masters = {str(k): _str(v) for k, v in ms.items()} if isinstance(ms, dict) else {}
        ba = x.get("beat_audio")
        if isinstance(ba, dict):
            for k, v in ba.items():
                if isinstance(v, dict):
                    words = [Word(_str(w.get("text")), _float(w.get("start")), _float(w.get("end")))
                             for w in _list(v.get("words")) if isinstance(w, dict)]
                    spans = [_linespan_from(s) for s in _list(v.get("spans")) if isinstance(s, dict)]
                    rs.beat_audio[str(k)] = BeatAudio(_str(v.get("path")), _float(v.get("dur")), words, spans)
        for c in _list(x.get("cues")):
            if isinstance(c, dict):
                rs.cues.append(Cue(
                    beat_id=_str(c.get("beat_id")), visual_id=_str(c.get("visual_id")),
                    start_sec=_float(c.get("start_sec")), end_sec=_float(c.get("end_sec")),
                    crop_from=tuple(_float(z) for z in _list(c.get("crop_from"))[:4]) or (0.0, 0.0, 1.0, 1.0),
                    crop_to=tuple(_float(z) for z in _list(c.get("crop_to"))[:4]) or (0.0, 0.0, 1.0, 1.0),
                    transition=_norm(c.get("transition"), TRANSITION, "cut"), transition_sec=_float(c.get("transition_sec")),
                    hook=_bool(c.get("hook")), hook_text=_str(c.get("hook_text")),
                    audio_path=_str(c.get("audio_path")),
                    bgm_mood=_norm(c.get("bgm_mood"), BGM_MOODS, ""),
                    bgm_cue=_norm(c.get("bgm_cue"), BGM_CUE, "under"),
                    bgm_intensity=_norm(c.get("bgm_intensity"), BGM_INTENSITY, "med"),
                    text_anchor=_norm(c.get("text_anchor"), TEXT_ANCHOR, "auto"),
                    speaker_id=_str(c.get("speaker_id")),
                    char_anchor=_norm(c.get("char_anchor"), CHAR_ANCHOR, "none"),
                    char_scale=_norm(c.get("char_scale"), CHAR_SCALE, "medium"),
                    char_motion=_norm(c.get("char_motion"), CHAR_MOTION, "fade"),
                    emotion=_norm(c.get("emotion"), EMOTION, "normal"),
                    pose=_norm(c.get("pose"), POSE, "stand"),
                    source_audio=_norm(c.get("source_audio"), SOURCE_AUDIO, "mute"),
                    line_overlays=[_linespan_from(s) for s in _list(c.get("line_overlays")) if isinstance(s, dict)]))
        st = x.get("asset_status")
        if isinstance(st, dict):
            rs.asset_status = {str(k): _str(v) for k, v in st.items() if _str(v)}
        rs.total_sec = _float(x.get("total_sec"))
    except Exception:
        pass
    return rs


__all__ = [
    "StoryPlan", "CharacterDef", "SettingDef", "Visual", "Beat", "Line",
    "RelationshipDef", "Sequence", "Scene", "Shot", "CharacterState",
    "Word", "BeatAudio", "LineSpan", "Cue", "RenderState",
    "FOCUS", "MOTION", "TRANSITION", "TIER", "GENDER", "SUBTITLE_MODE", "BGM_MOODS",
    "REGION", "GENRE_KEY", "PACE", "PAUSE", "SEQUENCE_ROLE", "SCENE_PURPOSE",
    "SHOT_SIZE", "SHOT_ANGLE", "LENS", "CAMERA_POSITION", "COMPOSITION", "MOTION_INTENT",
    "BGM_CUE", "BGM_INTENSITY", "SOURCE_AUDIO", "CHAR_ANCHOR", "CHAR_SCALE",
    "CHAR_MOTION", "TEXT_ANCHOR", "POSE", "EMOTION",
    "ASPECT_SIZE", "CPS", "CROP_RECT", "TRANSITION_SEC", "MIN_BEAT_SEC", "cps_for",
]
