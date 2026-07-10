"""
story_voice_cast.py — Voice Casting for Story Mode (P4).

Assigns each Story Bible character a TTS engine + voice so dialogue uses a
DISTINCT, consistent voice per character (and the narrator its own), routed by
language (Gemini for Vietnamese, ElevenLabs for English/Japanese — see
resolve_story_tts_engine). Deterministic + rule-based (no LLM, no network): pick
from a per-engine/gender voice pool, rotating so different characters of the same
gender get different voices. Reproducible across chapters so a character keeps its
voice for the whole series.

Under ``features/render/ai/**`` → Sacred Contract #3: never raises; returns a safe
mapping (falls back to gender defaults) on any error. Pools are env-overridable.
"""
from __future__ import annotations

import logging
import os

from app.features.render.engine.audio.tts import resolve_story_tts_engine

logger = logging.getLogger("app.render.story_voice_cast")


def _pool(env_name: str, default: "list[str]") -> "list[str]":
    raw = (os.getenv(env_name, "") or "").strip()
    if raw:
        vals = [v.strip() for v in raw.split(",") if v.strip()]
        if vals:
            return vals
    return default


# Prebuilt Gemini TTS voices (native VI). Env: STORY_GEMINI_VOICES_FEMALE/_MALE.
_GEMINI_F = lambda: _pool("STORY_GEMINI_VOICES_FEMALE", ["Kore", "Aoede", "Leda", "Callirrhoe"])
_GEMINI_M = lambda: _pool("STORY_GEMINI_VOICES_MALE", ["Puck", "Charon", "Fenrir", "Orus"])
# ElevenLabs voices (EN/JP) — the ElevenLabs API needs a VOICE ID (not a name).
# Defaults are the library's well-known public default voices (Rachel/Bella/Elli,
# Josh/Antoni/Arnold). Override with your own voice IDs via
# STORY_ELEVEN_VOICES_FEMALE / _MALE in .env.
_ELEVEN_F = lambda: _pool("STORY_ELEVEN_VOICES_FEMALE",
                          ["21m00Tcm4TlvDq8ikWAM", "EXAVITQu4vr4xnSDxMaL", "MF3mGyEYCl7XYWbV9V6O"])
_ELEVEN_M = lambda: _pool("STORY_ELEVEN_VOICES_MALE",
                          ["TxGEqnHWrfWFTfGW9XjX", "ErXwobaYiN019PkySvjV", "VR6AewLTigWG4xSOukaG"])


def _pools_for(engine: str) -> "tuple[list[str], list[str]]":
    if engine == "elevenlabs":
        return _ELEVEN_F(), _ELEVEN_M()
    return _GEMINI_F(), _GEMINI_M()


def _norm_gender(g: str) -> str:
    g = (g or "").strip().lower()
    return "male" if g in ("male", "m", "nam") else "female"


def cast_voices(characters, language: str, narrator_gender: str = "female") -> dict:
    """Return ``{char_id: {"engine", "voice_id", "gender"}}`` plus a ``""`` entry for
    the narrator. Deterministic; never raises. ``characters`` is an iterable of
    objects with ``.id``/``.name``/``.gender`` (StoryCharacter) or dicts."""
    out: dict = {}
    try:
        engine = resolve_story_tts_engine(language)
        pool_f, pool_m = _pools_for(engine)
        idx = {"female": 0, "male": 0}

        def _assign(gender: str) -> str:
            g = _norm_gender(gender)
            pool = pool_m if g == "male" else pool_f
            i = idx[g]
            idx[g] += 1
            return pool[i % len(pool)] if pool else ""

        # Narrator first (own voice).
        out[""] = {"engine": engine, "voice_id": _assign(narrator_gender),
                   "gender": _norm_gender(narrator_gender)}
        for c in (characters or []):
            if isinstance(c, dict):
                cid = (c.get("id") or c.get("name") or "").strip()
                gender = c.get("gender", "")
            else:
                cid = (getattr(c, "id", "") or getattr(c, "name", "") or "").strip()
                gender = getattr(c, "gender", "")
            if not cid or cid in out:
                continue
            out[cid] = {"engine": engine, "voice_id": _assign(gender),
                        "gender": _norm_gender(gender)}
        return out
    except Exception as exc:
        logger.info("story_voice_cast: cast error %s — narrator-only default", exc)
        return out or {"": {"engine": "edge", "voice_id": "", "gender": "female"}}


def apply_voice_cast(bible, language: str, narrator_gender: str = "female") -> dict:
    """Cast voices for a StoryBible AND stamp each character's ``voice_engine`` /
    ``voice_id`` in place (so persistence + the render use them). Returns the cast
    mapping (incl. the narrator ""). Never raises."""
    try:
        chars = getattr(bible, "characters", None) or []
        mapping = cast_voices(chars, language, narrator_gender)
        for c in chars:
            cid = (getattr(c, "id", "") or getattr(c, "name", "") or "").strip()
            entry = mapping.get(cid)
            if entry:
                c.voice_engine = entry["engine"]
                c.voice_id = entry["voice_id"]
        return mapping
    except Exception as exc:
        logger.info("story_voice_cast: apply error %s", exc)
        return {}


def apply_voice_cast_v2(plan, language: str, narrator_gender: str = "female") -> dict:
    """Story v2 — cast voices for a StoryPlan and fill ``plan.render.voices`` (keyed
    by character id; "" = narrator) with ``[engine, voice_id]``. Prefers each
    CharacterDef.voice_gender over gender. Reuses ``cast_voices`` (engine by language
    + gender pool rotation). Returns the mapping. Never raises."""
    from types import SimpleNamespace
    try:
        chars = getattr(plan, "characters", None) or []
        adapters = [SimpleNamespace(id=c.id, name=c.name,
                                    gender=((getattr(c, "voice_gender", "") or getattr(c, "gender", "") or "")))
                    for c in chars]
        mapping = cast_voices(adapters, language, narrator_gender)
        for cid, entry in mapping.items():
            plan.render.voices[cid] = [entry["engine"], entry["voice_id"]]
        return mapping
    except Exception as exc:
        logger.info("story_voice_cast: apply_v2 error %s", exc)
        return {}


__all__ = ["cast_voices", "apply_voice_cast", "apply_voice_cast_v2"]
