"""
P-A — SVG-only Story: the super-prompt no longer asks the AI for dead image-gen
fields (visual.prompt, visual.tier, character.voice_style).

Story renders procedurally (SVG) from setting/archetype/asset + the per-beat labels;
it never reads visual.prompt/tier and the voice cast uses gender not voice_style.
Those fields used to cost output tokens (inflating cost + truncation) for nothing.
s11 removes them from what the AI produces. The DATACLASS fields are retained so
plans stored under an older schema still deserialize (Sacred Contract #2).
"""
from __future__ import annotations

from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_idea_prompt,
)
from app.domain.story_plan_v2 import StoryPlan, Visual, CharacterDef


def test_prompt_no_longer_asks_for_image_gen_fields():
    for build in (
        lambda: build_super_story_prompt("once", "vi")[1],
        lambda: build_super_idea_prompt("an idea", duration_sec=60, language="vi")[1],
    ):
        user = build()
        # The visuals schema no longer advertises an image prompt / tier field …
        assert '"prompt"' not in user
        assert '"tier"' not in user
        assert '"voice_style"' not in user
        assert "FULL English image prompt" not in user
        # … and the rules say so explicitly (render composes procedurally).
        assert "no image prompt" in user.lower() or "there is no image prompt" in user.lower()


def test_dataclass_fields_retained_for_backward_compat():
    # Old stored plans carry these keys; the domain must still accept them.
    v = Visual()
    assert hasattr(v, "prompt") and hasattr(v, "tier")
    assert hasattr(CharacterDef(), "voice_style")
    # A plan JSON that still includes them round-trips without error.
    p = StoryPlan.from_json(
        '{"visuals":[{"id":"v1","prompt":"legacy","tier":"high"}],'
        '"characters":[{"id":"c1","voice_style":"calm"}],'
        '"timeline":[{"id":"b1","narration":"x","visual_id":"v1"}]}'
    )
    assert p is not None and p.visual("v1").tier == "high"
