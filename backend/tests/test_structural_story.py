"""
P3-3 — judge-free structural scorers for StoryPlan v2 (ai_eval.structural_story).

Pure, network-free: hand-authored good vs weak plans, asserting the instrument
rewards the super-prompt's spec (visual reuse, hook discipline, character
grounding, narration coverage, referential integrity) and penalises the failure
modes (one-image-per-beat, orphan refs, looping narration).
"""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat
from ai_eval.structural_story import (
    image_reuse, hook_discipline, character_grounding, narration_quality,
    ref_integrity, duration_fit, story_structural_report, summarize_story_structural,
    scene_shot_quality,
)


def _good() -> StoryPlan:
    return StoryPlan(
        language="vi",
        characters=[CharacterDef(id="hero", name="Hero", canonical_desc="a young swordsman in blue")],
        settings=[SettingDef(id="s1", name="Forest", canonical_desc="misty pine forest")],
        visuals=[
            Visual(id="v1", setting_id="s1", prompt="wide forest at dawn", character_ids=["hero"]),
            Visual(id="v2", setting_id="s1", prompt="forest clearing", character_ids=["hero"]),
        ],
        timeline=[
            Beat(id="b1", narration="Chàng bước vào rừng sâu.", speaker_id="hero", visual_id="v1"),
            Beat(id="b2", narration="Gió lạnh thổi qua tán cây.", speaker_id="hero", visual_id="v1"),
            Beat(id="b3", narration="Một bóng người xuất hiện.", speaker_id="hero", visual_id="v1",
                 hook=True, hook_text="Ai đó?"),
            Beat(id="b4", narration="Trận chiến bắt đầu.", speaker_id="hero", visual_id="v2"),
            Beat(id="b5", narration="Chàng chiến thắng.", speaker_id="hero", visual_id="v2"),
        ],
    )


def _weak() -> StoryPlan:
    # One image per beat (no reuse), no canonical_desc, looping narration, a dangling ref.
    return StoryPlan(
        language="vi",
        characters=[CharacterDef(id="hero", name="Hero", canonical_desc="")],
        visuals=[Visual(id="v1", setting_id="", prompt="a"),
                 Visual(id="v2", setting_id="", prompt="b")],
        timeline=[
            Beat(id="b1", narration="Lặp.", speaker_id="hero", visual_id="v1"),
            Beat(id="b2", narration="Lặp.", speaker_id="hero", visual_id="v2"),
            Beat(id="b3", narration="Lặp.", speaker_id="ghost", visual_id="v1"),  # dangling speaker
        ],
    )


def test_image_reuse_rewards_reuse_penalises_over_imaging():
    assert image_reuse(_good())["reuse_score"] == 100.0     # 5 beats / 2 visuals = 2.5 ≥ target
    weak = image_reuse(_weak())
    assert weak["beats_per_visual"] < 2.0
    assert weak["reuse_score"] < 100.0


def test_hook_discipline_band():
    assert hook_discipline(_good())["in_band"] is True       # exactly 1 hook
    # zero hooks → score 0 but raw count preserved.
    p = _good()
    for b in p.timeline:
        b.hook = False
    hz = hook_discipline(p)
    assert hz["hooks_total"] == 0 and hz["hook_score"] == 0.0
    # too many hooks → decays.
    for b in p.timeline:
        b.hook = True
    assert hook_discipline(p)["hook_score"] < 100.0


def test_character_grounding():
    assert character_grounding(_good())["grounding_score"] == 100.0
    assert character_grounding(_weak())["grounding_score"] == 0.0
    assert character_grounding(StoryPlan())["grounding_score"] is None   # no cast


def test_narration_quality_penalises_repeats():
    assert narration_quality(_good())["repeat_rate"] == 0.0
    assert narration_quality(_weak())["repeat_rate"] > 0.0
    assert narration_quality(_good())["narration_score"] > narration_quality(_weak())["narration_score"]


def test_ref_integrity_catches_dangling():
    assert ref_integrity(_good())["dangling"] == 0
    assert ref_integrity(_good())["integrity_score"] == 100.0
    assert ref_integrity(_weak())["dangling"] >= 1
    assert ref_integrity(_weak())["integrity_score"] < 100.0


def test_duration_fit_idea_mode():
    p = _good()
    # requested 0 → None (paste mode).
    assert duration_fit(p, 0)["duration_score"] is None
    # a plausible target scores; a wildly-off target scores lower.
    good_ratio = duration_fit(p, p.estimated_total_sec())["duration_score"]
    off_ratio = duration_fit(p, p.estimated_total_sec() * 10)["duration_score"]
    assert good_ratio == 100.0 and off_ratio < good_ratio


def test_overall_separates_good_from_weak():
    good = story_structural_report(_good())
    weak = story_structural_report(_weak())
    assert good["overall_score"] > weak["overall_score"]
    assert 0.0 <= weak["overall_score"] <= good["overall_score"] <= 100.0
    assert isinstance(summarize_story_structural(good), str)


def test_report_never_raises_on_none():
    r = story_structural_report(None)
    assert r["empty"] is True and r["overall_score"] == 0.0


def test_scene_shot_quality_rewards_derived_grammar():
    plan = _good().derive_scene_shot_grammar()
    report = scene_shot_quality(plan)
    assert report["beat_coverage"] == 1.0
    assert report["establishing_rate"] == 1.0
    assert report["shot_score"] >= 75.0
