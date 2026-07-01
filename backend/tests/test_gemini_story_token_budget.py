"""
test_gemini_story_token_budget.py — regression guard for the StoryModel
truncation bug (fixed 2026-07).

Root cause: Gemini 2.5 Flash draws thinking tokens and answer tokens from the
same max_output_tokens ceiling. At the old default (max=8192, thinking=8192) the
thinking step consumed the budget and the StoryModel JSON was truncated to
near-empty — 0 characters / 0 beats — silently decapitating the whole recap
Story Intelligence.

The invariant that prevents it: the answer must keep real headroom below the
ceiling regardless of the thinking budget. This test pins that headroom so a
future edit can't reintroduce a config where thinking can starve the output.
"""
from __future__ import annotations

from app.features.render.ai.llm.providers import gemini as g

# The full StoryModel for a feature film measured at ~1850 output tokens.
# Require a comfortable multiple of that between the thinking budget and the
# output ceiling so the JSON answer can never be truncated.
_MIN_ANSWER_HEADROOM_TOKENS = 8192


def test_story_answer_has_headroom_above_thinking_budget():
    headroom = g._STORY_MAX_TOKENS - g._STORY_THINKING_BUDGET
    assert headroom >= _MIN_ANSWER_HEADROOM_TOKENS, (
        f"StoryModel output can be starved by thinking: "
        f"max_output_tokens={g._STORY_MAX_TOKENS} - thinking_budget="
        f"{g._STORY_THINKING_BUDGET} = {headroom} tokens of answer headroom "
        f"(< {_MIN_ANSWER_HEADROOM_TOKENS}). This is the config class that "
        f"truncated the StoryModel to 0 characters / 0 beats."
    )


def test_story_thinking_budget_is_below_output_ceiling():
    # A thinking budget >= the output ceiling is the exact 8192/8192 failure.
    assert g._STORY_THINKING_BUDGET < g._STORY_MAX_TOKENS
