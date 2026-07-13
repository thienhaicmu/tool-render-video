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
