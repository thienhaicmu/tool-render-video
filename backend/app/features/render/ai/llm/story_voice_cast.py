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


def cast_voices(characters, language: str, narrator_gender: str = "female",
                locked: "dict | None" = None) -> dict:
    """Return ``{char_id: {"engine", "voice_id", "gender"}}`` plus a ``""`` entry for
    the narrator. Deterministic; never raises. ``characters`` is an iterable of
    objects with ``.id``/``.name``/``.gender`` (StoryCharacter) or dicts.

    ``locked`` (G3 — cross-chapter consistency): ``{char_id: voice_id}`` already cast
    for this character in an earlier chapter. A locked character REUSES its voice; new
    characters rotate AROUND the locked voices (used-skip) so they don't collide. The
    narrator keeps a stable first-pick regardless of ``locked`` so it doesn't drift as
    the cast grows. ``locked=None`` (or empty) is byte-identical to the legacy path."""
    out: dict = {}
    locked = locked or {}
    try:
        engine = resolve_story_tts_engine(language)
        pool_f, pool_m = _pools_for(engine)
        idx = {"female": 0, "male": 0}
        used: set = set()

        def _rotate(gender: str) -> str:
            g = _norm_gender(gender)
            pool = pool_m if g == "male" else pool_f
            if not pool:
                return ""
            n = len(pool)
            for _ in range(n):                       # first pool voice not already used
                v = pool[idx[g] % n]
                idx[g] += 1
                if v not in used:
                    used.add(v)
                    return v
            v = pool[idx[g] % n]                      # pool exhausted → allow a repeat
            idx[g] += 1
            return v

        # Narrator first, STABLE (plain first pick — ignores locked so it doesn't drift
        # across chapters as the locked set grows).
        ng = _norm_gender(narrator_gender)
        npool = pool_m if ng == "male" else pool_f
        narrator_voice = npool[0] if npool else ""
        out[""] = {"engine": engine, "voice_id": narrator_voice, "gender": ng}
        if narrator_voice:
            used.add(narrator_voice)

        for c in (characters or []):
            if isinstance(c, dict):
                cid = (c.get("id") or c.get("name") or "").strip()
                gender = c.get("gender", "")
            else:
                cid = (getattr(c, "id", "") or getattr(c, "name", "") or "").strip()
                gender = getattr(c, "gender", "")
            if not cid or cid in out:
                continue
            lv = (locked.get(cid) or "").strip()
            if lv:                                   # reuse the earlier-chapter voice
                out[cid] = {"engine": engine, "voice_id": lv, "gender": _norm_gender(gender)}
                used.add(lv)
            else:
                out[cid] = {"engine": engine, "voice_id": _rotate(gender),
                            "gender": _norm_gender(gender)}
        return out
    except Exception as exc:
        logger.info("story_voice_cast: cast error %s — narrator-only default", exc)
        return out or {"": {"engine": "edge", "voice_id": "", "gender": "female"}}


def _locked_voices(series_id: str, engine: str) -> dict:
    """``{char_id: voice_id}`` for characters of this series with a persisted voice on
    the SAME engine (a voice cast for a different-language engine can't be reused).
    Gated by STORY_SERIES_MEMORY. Empty on disable / no series / error. Never raises."""
    if os.getenv("STORY_SERIES_MEMORY", "1") != "1" or not (series_id or "").strip():
        return {}
    out: dict = {}
    try:
        from app.db import story_repo
        for row in story_repo.list_characters(series_id):
            cid = (row.get("id") or "").strip()
            vid = (row.get("voice_id") or "").strip()
            veng = (row.get("voice_engine") or "").strip()
            if cid and vid and veng == engine:
                out[cid] = vid
    except Exception as exc:
        logger.info("story_voice_cast: locked lookup failed series=%s: %s", series_id, exc)
        return {}
    return out


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
        # G3: lock voices already cast for this series' characters (same engine) so a
        # returning character keeps its voice across chapters. No-op for a one-off.
        series_id = (getattr(plan, "series_id", "") or "").strip()
        locked = _locked_voices(series_id, resolve_story_tts_engine(language)) if series_id else {}
        mapping = cast_voices(adapters, language, narrator_gender, locked=locked)
        # Snapshot any pre-existing voices (from an approved plan override where the
        # user picked a voice, or a resume's persisted cast) BEFORE overwriting.
        existing = dict(getattr(plan.render, "voices", None) or {})
        for cid, entry in mapping.items():
            prev = existing.get(cid)
            # A user-set voice ([engine, voice_id] with a non-empty voice_id) wins over
            # the auto cast so a chosen/locked voice is never clobbered on render.
            if isinstance(prev, (list, tuple)) and len(prev) >= 2 and str(prev[1] or "").strip():
                plan.render.voices[cid] = [str(prev[0] or entry["engine"]), str(prev[1])]
            else:
                plan.render.voices[cid] = [entry["engine"], entry["voice_id"]]
        return mapping
    except Exception as exc:
        logger.info("story_voice_cast: apply_v2 error %s", exc)
        return {}


def list_voices(language: str) -> dict:
    """Available Story voices for a language's TTS engine, split by gender:
    ``{"engine", "female": [...], "male": [...]}``. Powers the FE voice picker so a
    user can override a character's auto-cast voice. Never raises — returns an
    edge/empty default on any error."""
    try:
        engine = resolve_story_tts_engine(language)
        pool_f, pool_m = _pools_for(engine)
        return {"engine": engine, "female": list(pool_f), "male": list(pool_m)}
    except Exception as exc:
        logger.info("story_voice_cast: list_voices error %s", exc)
        return {"engine": "edge", "female": [], "male": []}


__all__ = ["cast_voices", "apply_voice_cast_v2", "list_voices"]
