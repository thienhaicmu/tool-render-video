"""Story Mode v2 — B4 voice cast: fill render.voices by language + gender."""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef
from app.features.render.ai.llm.story_voice_cast import apply_voice_cast_v2


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
