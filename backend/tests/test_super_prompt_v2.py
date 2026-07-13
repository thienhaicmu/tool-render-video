"""Story Mode v2 — B2 super prompt builders (format-safe, params)."""
from __future__ import annotations

from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_idea_prompt, build_super_repair_prompt,
    SUPER_PROMPT_VERSION,
)


def test_story_prompt_shape_and_params():
    sysm, user = build_super_story_prompt("Chương 1. Hàn Phong tỉnh dậy.", language="vi",
                                          art_style="wuxia", aspect_ratio="16:9",
                                          subtitle_mode="hook_only", ceiling=12)
    assert "DIRECTOR" in sysm
    assert "OUTPUT SCHEMA" in user and '"timeline"' in user and '"visuals"' in user
    assert "AT MOST 12" in user                       # ceiling
    assert "16:9" in user
    assert "Vietnamese" in user                       # lang name
    assert "adapt THIS" in user.lower() or "adapt this" in user.lower()
    # Phase 0.5 — asset-library hint keys present in the schema
    assert '"region"' in user and '"genre_key"' in user
    assert '"archetype"' in user and '"scene_kind"' in user
    # Library-pick — "asset" slug field present in the schema
    assert '"asset"' in user
    # N4+ per-beat pose + emotion fields (s8)
    assert '"pose"' in user
    assert '"emotion"' in user
    # s8 — code-derived TOKEN VOCAB teaches archetype/scene_kind/emotion/pose tokens
    assert "TOKEN VOCAB" in user
    assert "swordsman" in user and "emperor" in user and "demon" in user   # archetype vocab
    assert "temple" in user and "rooftop" in user                          # scene vocab
    assert "normal, happy, angry, sad, surprised" in user                  # emotion vocab


def test_library_catalog_injection():
    cat = ("CHARACTERS:\n  cn_wuxia_swordsman_male_young | cn/wuxia | swordsman male young\n"
           "BACKGROUNDS:\n  cn_wuxia_bamboo_forest | cn/wuxia | bamboo forest")
    _, no = build_super_story_prompt("story", "vi")
    assert "offline art you MAY reuse" not in no           # empty catalog → no block injected
    assert "cn_wuxia_swordsman_male_young" not in no       # and no slug leaked
    _, yes = build_super_story_prompt("story", "vi", library_catalog=cat)
    assert "offline art you MAY reuse" in yes and "cn_wuxia_swordsman_male_young" in yes
    _, yes2 = build_super_idea_prompt("idea", 60, "", "vi", library_catalog=cat)
    assert "cn_wuxia_bamboo_forest" in yes2


def test_idea_prompt_budget_and_genre():
    sysm, user = build_super_idea_prompt("A fallen disciple awakens a forbidden power.",
                                         duration_sec=300, genre="wuxia", language="vi", ceiling=10)
    assert "GENRE: wuxia" in user
    # 300s × 15 cps (vi) = 4500 chars budget (now a REQUIREMENT, s10).
    assert "~4500 characters" in user
    assert "INVENT a COMPLETE story" in user
    assert "never pad" not in user.lower()        # s10: the length-killer is gone
    assert "create FROM this".lower() in user.lower()


def test_idea_prompt_no_duration_lets_model_decide():
    _, user = build_super_idea_prompt("idea", duration_sec=0, language="en")
    assert "model decides" in user


def test_off_subtitle_forces_no_hook():
    _, user = build_super_story_prompt("x", subtitle_mode="off")
    assert "hook=false" in user and "no on-screen text" in user


def test_format_safe_with_braces():
    # Chapter/idea containing braces must NOT break the builder (concatenated, not formatted).
    weird = "Nội dung {có} ngoặc {nhọn} và %s và {{double}}."
    _, u1 = build_super_story_prompt(weird, language="vi")
    _, u2 = build_super_idea_prompt(weird, duration_sec=60, language="vi")
    assert weird in u1 and weird in u2


def test_repair_prompt():
    sysm, user = build_super_repair_prompt('{"visuals":[…broken')
    assert "JSON repair" in sysm
    assert "broken" in user


def test_version_tag():
    assert SUPER_PROMPT_VERSION == "s10"  # s10: idea-mode length enforcement + quantified reuse; s9: drop negative_prompt (F-12)
