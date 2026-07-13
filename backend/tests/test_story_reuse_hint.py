"""
P-B — the super-prompt teaches the many-beats/few-images REUSE pattern that the
JSON Schema can't enforce: a 1-shot structure-only example + a computed visual-count
target for idea mode. Reinforces the fix for the "over-imaged → capped → cụt ngủn" bug.
"""
from __future__ import annotations

from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_idea_prompt,
)


def test_reuse_example_present_in_both_modes():
    for user in (
        build_super_story_prompt("once", "vi")[1],
        build_super_idea_prompt("an idea", duration_sec=60, language="vi")[1],
    ):
        assert "REUSE EXAMPLE" in user
        assert "5 beats used just 2 images" in user
        assert "never one image per beat" in user.lower()
        # It is clearly an illustration, not content to copy.
        assert "write YOUR OWN story" in user


def test_idea_mode_has_computed_visual_target():
    # 180s → ~30 beats (1/6s) → ~8 visuals (30/4), clamped to the ceiling.
    _, user = build_super_idea_prompt("a lone knight", duration_sec=180, language="vi", ceiling=15)
    assert "aim for about 8 images" in user
    assert "~30 beats" in user


def test_idea_visual_target_clamped_to_ceiling():
    # A long target with a tiny ceiling must not ask for more than the ceiling.
    _, user = build_super_idea_prompt("epic", duration_sec=600, language="vi", ceiling=5)
    assert "aim for about 5 images" in user      # round(100/4)=25 → clamped to 5


def test_no_duration_falls_back_to_qualitative_visuals():
    _, user = build_super_idea_prompt("idea", duration_sec=0, language="vi")
    assert "a SMALL set of WIDE images" in user   # no number when length is unknown
