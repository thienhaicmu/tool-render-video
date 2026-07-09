"""Story-to-Video P0 — StoryPlan domain round-trip + defensive-load tests.

Pins the same defensive contract as content_plan / recap_plan:
1. from_json is defensive — None/empty/garbage/unknown-keys never raise.
2. Scene→Shot hierarchy survives a to_json → from_json round-trip.
3. Clamps + enum normalisation apply (reading_speed, quality_tier, shot_type).
4. StoryBible characters + environments load; helpers resolve by id/name.
5. Estimation + narration_audit never raise and behave sanely.
"""
from __future__ import annotations

import json

from app.domain.story_plan import (
    StoryPlan, StoryScene, Shot, StoryBible, StoryCharacter, StoryEnvironment,
    SCHEMA_VERSION,
)


def _sample_plan() -> StoryPlan:
    return StoryPlan(
        series_id="tienhiep-1", chapter_no=186, language="vi", art_style="wuxia",
        aspect_ratio="9:16", reading_pace="normal",
        story_bible=StoryBible(
            setting="Tu tiên giới", hook="Kẻ phế vật trỗi dậy", cta="Đón chương sau",
            characters=[StoryCharacter(id="ha_phong", name="Hàn Phong",
                                       description="thiếu niên áo trắng, kiếm bạc")],
            environments=[StoryEnvironment(id="van_kiem", name="Vạn Kiếm Tông",
                                           description="tông môn trên mây")],
        ),
        scenes=[
            StoryScene(index=0, scene_title="Mở đầu", role="hook", emotion="suspense",
                       characters=["ha_phong"], transition_out="fade", shots=[
                Shot(index=0, sid="s1", shot_type="establishing", narration="Đêm trăng lạnh.",
                     camera="zoom_in", characters=["ha_phong"], asset_type="ai_image",
                     quality_tier="low", visual_prompt="cold moonlit peak", transition_out="cut"),
                Shot(index=1, sid="s2", shot_type="close_up", narration="Hàn Phong mở mắt.",
                     speaker="ha_phong", emotion="excited", camera="still",
                     quality_tier="high", visual_prompt="close up silver-haired youth"),
            ]),
        ],
    )


def test_roundtrip_preserves_scene_shot_hierarchy():
    plan = _sample_plan()
    restored = StoryPlan.from_json(plan.to_json())
    assert restored is not None
    assert restored.scene_count() == 1
    assert restored.shot_count() == 2
    assert restored.series_id == "tienhiep-1"
    assert restored.chapter_no == 186
    assert restored.scenes[0].shots[1].speaker == "ha_phong"
    assert restored.scenes[0].shots[0].shot_type == "establishing"
    # StoryBible survived with characters + environments.
    assert restored.story_bible.character("ha_phong") is not None
    assert restored.story_bible.character("Hàn Phong") is not None  # by name too
    assert restored.story_bible.environment("van_kiem") is not None


def test_from_json_none_and_garbage_return_none():
    assert StoryPlan.from_json(None) is None
    assert StoryPlan.from_json("") is None
    assert StoryPlan.from_json("not json {") is None
    assert StoryPlan.from_json("[1,2,3]") is None  # not a dict


def test_unknown_keys_dropped_and_missing_defaulted():
    blob = json.dumps({
        "series_id": "x", "bogus_key": 123,
        "scenes": [{"index": 0, "weird": True, "shots": [
            {"index": 0, "narration": "hi", "totally_unknown": "drop me"},
        ]}],
    })
    plan = StoryPlan.from_json(blob)
    assert plan is not None
    assert plan.schema_version == SCHEMA_VERSION
    assert plan.language == ""  # missing → default
    assert plan.shot_count() == 1
    assert plan.all_shots()[0].narration == "hi"


def test_clamps_and_enum_normalisation():
    blob = json.dumps({"scenes": [{"index": 0, "shots": [{
        "index": 0, "narration": "x",
        "reading_speed": 9.0,          # → clamp to 2.0
        "pause_before": 999,           # → clamp to 5.0
        "shot_type": "banana",         # → default "medium"
        "quality_tier": "nope",        # invalid → default by shot_type (medium→medium)
        "asset_type": "weird",         # → default "ai_image"
    }]}]})
    plan = StoryPlan.from_json(blob)
    sh = plan.all_shots()[0]
    assert sh.reading_speed == 2.0
    assert sh.pause_before == 5.0
    assert sh.shot_type == "medium"
    assert sh.quality_tier == "medium"
    assert sh.asset_type == "ai_image"


def test_quality_tier_defaults_by_shot_type():
    blob = json.dumps({"scenes": [{"index": 0, "shots": [
        {"index": 0, "narration": "a", "shot_type": "establishing"},  # → low
        {"index": 1, "narration": "b", "shot_type": "close_up"},      # → high
    ]}]})
    shots = StoryPlan.from_json(blob).all_shots()
    assert shots[0].quality_tier == "low"
    assert shots[1].quality_tier == "high"


def test_is_empty_and_estimation_never_raise():
    empty = StoryPlan()
    assert empty.is_empty() is True
    assert empty.estimated_total_sec() == 0.0
    assert empty.narration_audit()["rated"] == 0

    plan = _sample_plan()
    assert plan.is_empty() is False
    assert plan.estimated_total_sec() > 0.0
    audit = plan.narration_audit()
    assert "weak" in audit and isinstance(audit["shots"], list)


def test_reading_pace_affects_estimate():
    plan = _sample_plan()
    plan.reading_pace = "normal"
    base = plan.estimated_total_sec()
    plan.reading_pace = "fast"
    faster = plan.estimated_total_sec()
    assert faster < base  # faster pace → shorter estimate
