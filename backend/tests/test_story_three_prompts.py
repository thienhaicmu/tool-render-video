"""
s14 — THREE specialised super-prompts by use-case, selected by (source, base video):
  P1 build_super_story_prompt — adapt an existing story → SVG (faithful).
  P2 build_super_video_prompt — narrate + overlay characters over a BASE VIDEO.
  P3 build_super_idea_prompt  — write a story OF A TARGET LENGTH from an idea.
Full StoryPlan schema is kept in all three; only the ROLE + INPUT + emphasis differ.
"""
from __future__ import annotations

from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_video_prompt, build_super_idea_prompt,
)
from app.features.render.ai.llm.story_director_v2 import run_super_plan

_OK = '{"visuals":[{"id":"v1"}],"timeline":[{"id":"b1","narration":"x","visual_id":"v1"}]}'


# ── Each prompt has a DISTINCT role + emphasis ────────────────────────────────

def test_p1_adapt_svg_role():
    sysm, user = build_super_story_prompt("chương 1...", "vi")
    assert "adapting an EXISTING written story" in sysm
    assert "procedurally-illustrated (SVG)" in sysm
    # SVG rule 4 (draws from setting/characters, no image prompt).
    assert "draws each picture procedurally" in user
    assert "SUPPLIED VIDEO" not in user            # not the video role
    # Full schema still present.
    assert '"timeline"' in user and '"characters"' in user


def test_p2_over_video_role():
    sysm, user = build_super_video_prompt("chương 1...", "vi", base_video_dur=120)
    assert "BACKGROUND VIDEO" in sysm and "NEVER design scenes" in sysm
    # Video rule 4: the video is the background; visuals are just anchors.
    assert "SUPPLIED VIDEO" in user
    assert "draws each picture procedurally" not in user
    # Overlay + source_audio focus + video-length pacing.
    assert "source_audio" in user and "char_anchor" in user
    assert "120 seconds" in user
    assert '"timeline"' in user                    # same full schema


def test_p3_idea_screenwriter_brief():
    sysm, user = build_super_idea_prompt("một ý tưởng", duration_sec=180, language="vi")
    assert "SCREENWRITER" in sysm
    assert "BRIEF (this defines the whole task)" in user
    assert "SHORT is a FAILURE" in user
    assert "CHARACTERS of spoken text" in user     # length-as-char-budget brief
    assert "HOOK / SETUP" in user and "RESOLUTION" in user   # five-act beat quota


# ── run_super_plan routes to the correct prompt ───────────────────────────────

def _capture():
    box = {}
    def fn(sysm, usr):
        box["sys"] = sysm
        return _OK
    return box, fn


def test_router_paste_no_video_uses_p1():
    box, fn = _capture()
    run_super_plan(call_fn=fn, source="paste", chapter="truyện " * 40, language="vi",
                   has_base_video=False)
    assert "adapting an EXISTING written story" in box["sys"]


def test_router_paste_with_video_uses_p2():
    box, fn = _capture()
    run_super_plan(call_fn=fn, source="paste", chapter="truyện " * 40, language="vi",
                   has_base_video=True, base_video_dur=90)
    assert "BACKGROUND VIDEO" in box["sys"]


def test_router_idea_uses_p3():
    box, fn = _capture()
    run_super_plan(call_fn=fn, source="idea", idea="một ý tưởng", duration_sec=120, language="vi")
    assert "SCREENWRITER" in box["sys"]
