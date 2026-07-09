"""Story-to-Video P4 — Voice Casting tests (deterministic, offline, Sacred #3)."""
from __future__ import annotations

from app.domain.story_plan import StoryCharacter, StoryBible
from app.features.render.ai.llm.story_voice_cast import cast_voices, apply_voice_cast


def _chars():
    return [
        StoryCharacter(id="han_phong", name="Hàn Phong", gender="male"),
        StoryCharacter(id="tuyet_nhi", name="Tuyết Nhi", gender="female"),
        StoryCharacter(id="lao_ma", name="Lão Ma", gender="male"),
    ]


def test_vietnamese_routes_to_gemini():
    cast = cast_voices(_chars(), "vi")
    assert all(v["engine"] == "gemini" for v in cast.values())
    assert "" in cast  # narrator entry present


def test_english_routes_to_elevenlabs():
    cast = cast_voices(_chars(), "en")
    assert all(v["engine"] == "elevenlabs" for v in cast.values())


def test_japanese_routes_to_elevenlabs():
    assert cast_voices(_chars(), "ja")["han_phong"]["engine"] == "elevenlabs"


def test_distinct_voices_per_same_gender():
    cast = cast_voices(_chars(), "vi")
    # Two males (han_phong, lao_ma) get different rotated voices.
    assert cast["han_phong"]["voice_id"] != cast["lao_ma"]["voice_id"]
    assert cast["han_phong"]["gender"] == "male"
    assert cast["tuyet_nhi"]["gender"] == "female"


def test_apply_voice_cast_stamps_characters():
    bible = StoryBible(characters=_chars())
    mapping = apply_voice_cast(bible, "en")
    assert mapping  # non-empty
    for c in bible.characters:
        assert c.voice_engine == "elevenlabs"
        assert c.voice_id  # stamped


def test_never_raises_on_bad_input():
    assert isinstance(cast_voices(None, "vi"), dict)
    assert isinstance(cast_voices([{"no_id": 1}], "en"), dict)
    assert isinstance(apply_voice_cast(None, "vi"), dict)
