"""Story-to-Video P1 — story_parser defensive tests (Sacred Contract #3)."""
from __future__ import annotations

import json

from app.features.render.ai.llm.story_parser import (
    parse_story_digest_response,
    parse_story_reduce_response,
)


def test_digest_none_and_garbage_return_none():
    assert parse_story_digest_response(None) is None
    assert parse_story_digest_response("") is None
    assert parse_story_digest_response("not json at all") is None
    assert parse_story_digest_response("[1,2,3]") is None  # not an object


def test_digest_valid_parses_entities():
    raw = json.dumps({
        "summary": "Hàn Phong tỉnh dậy.",
        "beats": ["tỉnh dậy", "nhận ra sức mạnh"],
        "characters": [{"id": "han_phong", "name": "Hàn Phong", "description": "áo trắng"}],
        "environments": [{"id": "phong", "name": "Phòng", "description": "tối"}],
    })
    out = parse_story_digest_response(raw)
    assert out is not None
    assert out["summary"].startswith("Hàn Phong")
    assert out["beats"] == ["tỉnh dậy", "nhận ra sức mạnh"]
    assert out["characters"][0].id == "han_phong"
    assert out["environments"][0].name == "Phòng"


def test_digest_handles_code_fence_wrapping():
    raw = "```json\n" + json.dumps({"summary": "x", "characters": []}) + "\n```"
    out = parse_story_digest_response(raw)
    assert out is not None and out["summary"] == "x"


def test_digest_salvages_trailing_prose():
    raw = 'Sure! Here you go: {"summary":"ok","beats":[],"characters":[],"environments":[]} — done'
    out = parse_story_digest_response(raw)
    assert out is not None and out["summary"] == "ok"


def test_reduce_valid_returns_bible_and_meta():
    raw = json.dumps({
        "topic": "tiên hiệp", "tone": "epic", "audience": "general",
        "video_style": "cinematic", "setting": "Tu tiên giới",
        "hook": "phế vật trỗi dậy", "cta": "đón chương sau",
        "rolling_summary": "Toàn chương...",
        "characters": [{"id": "han_phong", "name": "Hàn Phong", "description": "áo trắng, kiếm bạc"}],
        "environments": [{"id": "van_kiem", "name": "Vạn Kiếm Tông", "description": "trên mây"}],
    })
    parsed = parse_story_reduce_response(raw)
    assert parsed is not None
    bible, meta = parsed
    assert bible.character("han_phong") is not None
    assert bible.environment("van_kiem") is not None
    assert meta["topic"] == "tiên hiệp"
    assert meta["rolling_summary"].startswith("Toàn chương")


def test_reduce_empty_content_returns_none():
    # No bible + no summary + no topic → not usable → None.
    assert parse_story_reduce_response(json.dumps({"characters": [], "environments": []})) is None
    assert parse_story_reduce_response("garbage") is None
