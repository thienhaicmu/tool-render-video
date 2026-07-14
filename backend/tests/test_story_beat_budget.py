"""
P-C — language-aware per-beat narration budget in the super-prompt.

A beat is one TTS clip; giving the model a per-beat character range (derived from
the language CPS, ~3-8s of speech) keeps beats evenly paced instead of a mix of
one-word stubs and paragraph-long blocks.
"""
from __future__ import annotations

from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_idea_prompt, _beat_char_hint,
)


def test_beat_hint_language_aware():
    assert _beat_char_hint("vi") == " (~45-120 characters, ~1-2 short sentences)"   # cps 15 → 15*3, 15*8
    assert _beat_char_hint("en") == " (~42-112 characters, ~1-2 short sentences)"   # cps 14
    assert _beat_char_hint("ja") == " (~24-64 characters, ~1-2 short sentences)"    # cps 8
    assert _beat_char_hint("zz") == " (~42-112 characters, ~1-2 short sentences)"   # unknown → default 14


def test_budget_present_in_both_modes(monkeypatch):
    # Hermetic: the dev .env may set STORY_MULTILINE_BEATS=1 (config.load_dotenv
    # injects it session-wide), which switches rule 5 to the dialogue variant and
    # drops the per-beat char budget. Pin the code default (off) for this assertion.
    monkeypatch.delenv("STORY_MULTILINE_BEATS", raising=False)
    # P1 (adapt) uses the standard per-beat budget threaded into rule 5.
    vi_story = build_super_story_prompt("once", "vi")[1]
    assert "~45-120 characters" in vi_story and "EVENLY sized" in vi_story
    # P3 (idea) uses a RICHER per-beat hint (full paragraphs) — the length lever.
    vi_idea = build_super_idea_prompt("an idea", duration_sec=60, language="vi")[1]
    assert "FULL 2-4 sentence paragraph" in vi_idea
    # English uses the English range, not the Vietnamese one.
    en = build_super_story_prompt("once", "en")[1]
    assert "~42-112 characters" in en and "~45-120 characters" not in en
