"""Story Mode v2 — B4 voice cast: fill render.voices by language + gender."""
from __future__ import annotations

import uuid

from app.db.connection import init_db
from app.db import story_repo
from app.domain.story_plan_v2 import StoryPlan, CharacterDef
from app.features.render.ai.llm.story_voice_cast import apply_voice_cast_v2, _locked_voices


def setup_module(module):  # noqa: D401
    init_db()


def _plan(lang="vi"):
    return StoryPlan(language=lang, characters=[
        CharacterDef(id="han", name="Hàn Phong", gender="male", voice_gender="male"),
        CharacterDef(id="tuyet", name="Tuyết Nhi", gender="female", voice_gender="female"),
        CharacterDef(id="lao", name="Lão Ma", gender="male", voice_gender="male"),
    ])


def test_vietnamese_routes_gemini():
    p = _plan("vi")
    apply_voice_cast_v2(p, "vi")
    assert "" in p.render.voices                       # narrator
    for cid in ("han", "tuyet", "lao"):
        assert p.render.voices[cid][0] == "gemini"     # engine
        assert p.render.voices[cid][1]                 # voice_id set


def test_english_routes_elevenlabs():
    p = _plan("en")
    apply_voice_cast_v2(p, "en")
    assert all(v[0] == "elevenlabs" for v in p.render.voices.values())


def test_distinct_voices_same_gender():
    p = _plan("vi")
    apply_voice_cast_v2(p, "vi")
    # two males (han, lao) rotate to different voices
    assert p.render.voices["han"][1] != p.render.voices["lao"][1]


def test_prefers_voice_gender():
    p = StoryPlan(language="en", characters=[
        CharacterDef(id="x", name="X", gender="female", voice_gender="male"),  # voice_gender wins
    ])
    apply_voice_cast_v2(p, "en")
    mapping_gender = None
    # the male pool should be used → voice_id is one of the male defaults
    from app.features.render.ai.llm.story_voice_cast import _ELEVEN_M
    assert p.render.voices["x"][1] in _ELEVEN_M()


def test_never_raises_empty():
    p = StoryPlan(language="vi")
    assert isinstance(apply_voice_cast_v2(p, "vi"), dict)


# ── G3: cross-chapter voice lock ──────────────────────────────────────────────

def _sid():
    return "vc-" + uuid.uuid4().hex[:10]


def test_locked_voices_helper_gating(monkeypatch):
    sid = _sid()
    cid = sid + "-han"
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(cid, series_id=sid, name="Han",
                                    voice_engine="gemini", voice_id="Charon", gender="male")
        assert _locked_voices(sid, "gemini") == {cid: "Charon"}
        assert _locked_voices(sid, "elevenlabs") == {}      # engine mismatch → not reusable
        assert _locked_voices("", "gemini") == {}           # no series
        monkeypatch.setenv("STORY_SERIES_MEMORY", "0")
        assert _locked_voices(sid, "gemini") == {}          # kill-switch
    finally:
        story_repo.delete_series(sid)


def test_returning_character_keeps_voice():
    sid = _sid()
    cid = sid + "-han"
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(cid, series_id=sid, name="Han",
                                    voice_engine="gemini", voice_id="Charon", gender="male")
        p = StoryPlan(language="vi", series_id=sid,
                      characters=[CharacterDef(id=cid, name="Han", voice_gender="male")])
        apply_voice_cast_v2(p, "vi")
        assert p.render.voices[cid] == ["gemini", "Charon"]   # reused, not re-rotated
    finally:
        story_repo.delete_series(sid)


def test_engine_mismatch_recasts():
    sid = _sid()
    cid = sid + "-han"
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(cid, series_id=sid, name="Han",
                                    voice_engine="elevenlabs", voice_id="EL_ID", gender="male")
        p = StoryPlan(language="vi", series_id=sid,   # vi → gemini, not elevenlabs
                      characters=[CharacterDef(id=cid, name="Han", voice_gender="male")])
        apply_voice_cast_v2(p, "vi")
        assert p.render.voices[cid][0] == "gemini" and p.render.voices[cid][1] != "EL_ID"
    finally:
        story_repo.delete_series(sid)


def test_new_character_avoids_locked_voice():
    sid = _sid()
    a, b = sid + "-a", sid + "-b"
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(a, series_id=sid, name="A",
                                    voice_engine="gemini", voice_id="Kore", gender="female")
        p = StoryPlan(language="vi", series_id=sid, characters=[
            CharacterDef(id=a, name="A", voice_gender="female"),
            CharacterDef(id=b, name="B", voice_gender="female"),   # new
        ])
        apply_voice_cast_v2(p, "vi")
        assert p.render.voices[a][1] == "Kore"           # locked kept
        assert p.render.voices[b][1] != "Kore"           # new char avoids the locked voice
    finally:
        story_repo.delete_series(sid)
