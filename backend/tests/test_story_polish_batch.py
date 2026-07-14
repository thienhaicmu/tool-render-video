"""Story Mode STORY-POLISH batch — KO wiring, voice picker/override, source
truncation flag, and result_json reproducibility fields.

Covers the pure-logic surface (no live AI): Phase 1 (Korean), Phase 3 (version
constant), Phase 4 (list_voices + user-set voice preservation). The endpoint /
e2e paths are exercised by the existing test_story_plan_endpoint / _e2e suites.
"""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef
from app.features.render.ai.llm.story_prompts_v2 import _lang_name, SUPER_PROMPT_VERSION
from app.features.render.ai.llm.story_voice_cast import apply_voice_cast_v2, list_voices


# ── Phase 1: Korean is a first-class narration language ───────────────────────

def test_korean_lang_name_resolved():
    assert _lang_name("ko").startswith("Korean")
    assert _lang_name("ko-KR").startswith("Korean")


def test_korean_routes_elevenlabs_with_voices():
    v = list_voices("ko")
    assert v["engine"] == "elevenlabs"      # KO → ElevenLabs (multilingual_v2 covers Korean)
    assert v["female"] and v["male"]        # non-empty pools → picker has options


def test_korean_voice_cast_fills_plan():
    p = StoryPlan(language="ko", characters=[
        CharacterDef(id="a", name="A", voice_gender="female"),
        CharacterDef(id="b", name="B", voice_gender="male"),
    ])
    apply_voice_cast_v2(p, "ko")
    assert p.render.voices["a"][0] == "elevenlabs" and p.render.voices["a"][1]
    assert p.render.voices["b"][1] != p.render.voices["a"][1]   # distinct genders/voices


# ── Phase 4: voice picker + user-set override preservation ────────────────────

def test_list_voices_engine_split_by_language():
    assert list_voices("en")["engine"] == "elevenlabs"
    assert list_voices("ja")["engine"] == "elevenlabs"
    assert list_voices("vi")["engine"] == "gemini"


def test_list_voices_never_raises_bad_input():
    v = list_voices("zz-unknown")
    assert set(v.keys()) == {"engine", "female", "male"}


def test_user_set_voice_is_preserved():
    # An approved plan override carried a user-chosen voice → render must keep it.
    p = StoryPlan(language="vi", characters=[CharacterDef(id="hp", name="HP", voice_gender="male")])
    p.render.voices["hp"] = ["gemini", "CUSTOM_VOICE"]
    apply_voice_cast_v2(p, "vi")
    assert p.render.voices["hp"] == ["gemini", "CUSTOM_VOICE"]


def test_empty_voice_id_recasts_to_auto():
    # An override entry with a blank voice_id ("auto") must fall through to the cast.
    p = StoryPlan(language="vi", characters=[CharacterDef(id="hp", name="HP", voice_gender="male")])
    p.render.voices["hp"] = ["gemini", ""]
    apply_voice_cast_v2(p, "vi")
    assert p.render.voices["hp"][0] == "gemini" and p.render.voices["hp"][1]


def test_fresh_plan_autocast_unchanged():
    # No pre-existing voices → byte-identical to the legacy auto-cast.
    p = StoryPlan(language="vi", characters=[CharacterDef(id="x", name="X", voice_gender="female")])
    apply_voice_cast_v2(p, "vi")
    assert p.render.voices["x"][0] == "gemini" and p.render.voices["x"][1]
    assert "" in p.render.voices          # narrator always cast


# ── Phase 3: reproducibility constant is present + stable shape ───────────────

def test_prompt_version_constant_present():
    assert isinstance(SUPER_PROMPT_VERSION, str) and SUPER_PROMPT_VERSION
