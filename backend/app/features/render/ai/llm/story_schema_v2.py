"""
story_schema_v2.py — OpenAI structured-output (JSON Schema) for the Story super-plan.

F-05: the Story super-plan previously relied on JSON-mode (``response_format=
json_object``) + a prompt-described schema + a defensive parser + a repair pass.
This module builds a STRICT JSON Schema (OpenAI structured outputs) for the
AI-produced CONTRACT half of a StoryPlan so the model is constrained at decode
time — cutting parse failures and the repair round-trip.

The schema is DERIVED FROM the domain enums (``story_plan_v2``) so it never drifts
as new focus/motion/emotion tokens are added. It mirrors EXACTLY the fields the
parser (`story_plan_v2._*_from`) reads for the AI contract — and deliberately
OMITS the pipeline-derived fields (reading_speed / pause_after / hold_sec / seed /
render state) so the model can never emit seconds/pixels (INV: timing is
rule-based, AI emits labels only).

Only the OpenAI-structured-output-supported keyword subset is used
(type / enum / properties / required / items / additionalProperties) — no
min/max/pattern/format/default. STRICT mode requires every property to be listed
in ``required`` and ``additionalProperties: false`` on every object.
"""
from __future__ import annotations

import os as _os

# Phase 3 — LEAN CONTRACT. When on (default), the strict schema asks the model for only
# the CREATIVE per-beat fields; the mechanical style labels (motion / transition_in /
# bgm_cue / bgm_intensity / source_audio / char_anchor / char_scale / char_motion /
# text_anchor) are DERIVED deterministically by StoryPlan.derive_beat_styling — cutting
# ~half the required per-beat tokens (the OpenAI strict-mode truncation driver) and
# letting the model spend decode budget on narration. STORY_LEAN_CONTRACT=0 restores the
# full 19-field beat (the pre-Phase-3 contract, bit-identical).
_LEAN_BEAT_DROP = (
    "motion", "transition_in", "bgm_cue", "bgm_intensity", "source_audio",
    "char_anchor", "char_scale", "char_motion", "text_anchor",
)


def _lean_contract() -> bool:
    return _os.getenv("STORY_LEAN_CONTRACT", "1") != "0"


def _multiline() -> bool:
    """P1 — when on (default off), a beat carries a ``lines[]`` array (multi-speaker
    dialogue) instead of the single narration/speaker/emotion fields. Off = the
    pre-P1 contract, bit-identical."""
    return _os.getenv("STORY_MULTILINE_BEATS", "0") == "1"


def _enum(values) -> dict:
    return {"type": "string", "enum": [str(v) for v in values]}


def _obj(props: dict) -> dict:
    """A strict object: additionalProperties=false + every key required."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


def build_story_plan_schema() -> dict:
    """Return the strict JSON Schema for the AI-produced StoryPlan contract.
    Pure; imports domain enums lazily so a partial hot-reload never breaks import."""
    from app.domain.story_plan_v2 import (
        FOCUS, MOTION, TRANSITION, GENDER, REGION, GENRE_KEY, BGM_MOODS,
        BGM_CUE, BGM_INTENSITY, SOURCE_AUDIO, CHAR_ANCHOR, CHAR_SCALE, CHAR_MOTION,
        EMOTION, POSE, TEXT_ANCHOR,
    )
    # AI-facing mood vocab drops the "default" fallback folder (not a creative choice) —
    # mirrors story_prompts_v2._MOOD_VOCAB.
    mood_enum = [m for m in BGM_MOODS if m != "default"]

    character = _obj({
        "id": {"type": "string"},
        "name": {"type": "string"},
        "canonical_desc": {"type": "string"},
        "archetype": {"type": "string"},
        "asset": {"type": "string"},
        "age": {"type": "string"},
        "gender": _enum(GENDER),
        "voice_gender": _enum(GENDER),
    })
    setting = _obj({
        "id": {"type": "string"},
        "name": {"type": "string"},
        "canonical_desc": {"type": "string"},
        "scene_kind": {"type": "string"},
        "asset": {"type": "string"},
    })
    visual = _obj({
        "id": {"type": "string"},
        "setting_id": {"type": "string"},
        "character_ids": {"type": "array", "items": {"type": "string"}},
    })
    beat = _obj({
        "id": {"type": "string"},
        "narration": {"type": "string"},
        "speaker_id": {"type": "string"},
        "visual_id": {"type": "string"},
        "focus": _enum(FOCUS),
        "motion": _enum(MOTION),
        "transition_in": _enum(TRANSITION),
        "bgm_mood": _enum(mood_enum),
        "bgm_cue": _enum(BGM_CUE),
        "bgm_intensity": _enum(BGM_INTENSITY),
        "source_audio": _enum(SOURCE_AUDIO),
        "char_anchor": _enum(CHAR_ANCHOR),
        "char_scale": _enum(CHAR_SCALE),
        "char_motion": _enum(CHAR_MOTION),
        "emotion": _enum(EMOTION),
        "pose": _enum(POSE),
        "text_anchor": _enum(TEXT_ANCHOR),
        "hook": {"type": "boolean"},
        "hook_text": {"type": "string"},
    })
    if _multiline():
        # P1 — the beat holds a dialogue array; narration/speaker/emotion/pose move
        # into each line. Khung-hình fields (visual_id/focus/bgm_mood/hook) stay.
        line = _obj({
            "speaker_id": {"type": "string"},
            "text": {"type": "string"},
            "emotion": _enum(EMOTION),
            "pose": _enum(POSE),
        })
        beat = _obj({
            "id": {"type": "string"},
            "visual_id": {"type": "string"},
            "focus": _enum(FOCUS),
            "bgm_mood": _enum(mood_enum),
            "hook": {"type": "boolean"},
            "hook_text": {"type": "string"},
            "lines": {"type": "array", "items": line},
        })
    elif _lean_contract():
        beat = _obj({k: v for k, v in beat["properties"].items() if k not in _LEAN_BEAT_DROP})
    return _obj({
        "topic": {"type": "string"},
        "tone": {"type": "string"},
        "language": {"type": "string"},
        "art_style": {"type": "string"},
        "region": _enum(REGION),
        "genre_key": _enum(GENRE_KEY),
        "characters": {"type": "array", "items": character},
        "settings": {"type": "array", "items": setting},
        "visuals": {"type": "array", "items": visual},
        "timeline": {"type": "array", "items": beat},
    })


__all__ = ["build_story_plan_schema"]
