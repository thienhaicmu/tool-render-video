"""Story Mode v2 — B2 super parser (defensive, INV enforce, INV9 render drop)."""
from __future__ import annotations

import json

from app.features.render.ai.llm.story_parser_v2 import parse_super_plan_response


def _good(nvis=2) -> dict:
    return {
        "topic": "tiên hiệp", "tone": "epic", "language": "vi", "art_style": "wuxia",
        "characters": [{"id": "han", "name": "Hàn Phong", "canonical_desc": "áo trắng", "voice_gender": "male"}],
        "settings": [{"id": "hall", "name": "Đại điện", "canonical_desc": "đá lạnh"}],
        "visuals": [{"id": f"v{i}", "setting_id": "hall", "prompt": f"wide scene {i}",
                     "character_ids": ["han"], "tier": "medium"} for i in range(1, nvis + 1)],
        "timeline": [
            {"id": "b1", "narration": "Đêm lạnh.", "visual_id": "v1", "focus": "left", "motion": "pan_left"},
            {"id": "b2", "narration": "Hàn Phong bước.", "speaker_id": "han", "visual_id": "v1", "focus": "center"},
        ],
    }


def test_none_and_garbage():
    assert parse_super_plan_response(None) is None
    assert parse_super_plan_response("") is None
    assert parse_super_plan_response("not json") is None
    assert parse_super_plan_response("[1,2]") is None


def test_valid_builds_plan():
    p = parse_super_plan_response(json.dumps(_good()))
    assert p is not None
    assert p.character("han") is not None
    assert p.image_count() == 2 and p.beat_count() == 2
    assert p.timeline[0].focus == "left"


def test_fence_wrapped():
    p = parse_super_plan_response("```json\n" + json.dumps(_good()) + "\n```")
    assert p is not None and p.beat_count() == 2


def test_salvage_trailing_prose():
    p = parse_super_plan_response("Sure! " + json.dumps(_good()) + " — done")
    assert p is not None and p.image_count() == 2


def test_dangling_beat_dropped():
    d = _good()
    d["timeline"].append({"id": "b3", "narration": "lạc", "visual_id": "MISSING"})  # INV1
    p = parse_super_plan_response(json.dumps(d))
    assert [b.id for b in p.timeline] == ["b1", "b2"]


def test_render_block_dropped_inv9():
    d = _good()
    d["render"] = {"visual_assets": {"v1": "/hacked.png"}, "total_sec": 999}  # AI must not set
    p = parse_super_plan_response(json.dumps(d))
    assert p.render.visual_assets == {} and p.render.total_sec == 0.0


def test_cap_visuals_ceiling():
    p = parse_super_plan_response(json.dumps(_good(nvis=8)), ceiling=3)
    assert p.image_count() <= 3


def test_no_visuals_returns_none():
    d = _good(); d["visuals"] = []
    assert parse_super_plan_response(json.dumps(d)) is None


def test_no_narrated_beat_returns_none():
    d = _good()
    d["timeline"] = [{"id": "b1", "narration": "", "visual_id": "v1"}]  # empty → dropped → is_empty
    assert parse_super_plan_response(json.dumps(d)) is None


def test_s4_beat_fields_parsed():
    d = _good()
    d["timeline"][0].update({
        "bgm_cue": "intro", "bgm_intensity": "high", "source_audio": "keep",
        "char_anchor": "left", "char_scale": "large", "char_motion": "slide",
        "text_anchor": "bottom",
    })
    p = parse_super_plan_response(json.dumps(d))
    b = p.timeline[0]
    assert b.bgm_cue == "intro" and b.bgm_intensity == "high" and b.source_audio == "keep"
    assert b.char_anchor == "left" and b.char_scale == "large" and b.char_motion == "slide"
    assert b.text_anchor == "bottom"


def test_s4_missing_fields_default():
    # A pre-s4 (s3) response with no new fields → conservative defaults.
    p = parse_super_plan_response(json.dumps(_good()))
    b = p.timeline[0]
    assert b.bgm_cue == "under" and b.bgm_intensity == "med" and b.source_audio == "mute"
    assert b.char_anchor == "none" and b.text_anchor == "auto"
