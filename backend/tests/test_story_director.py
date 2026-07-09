"""Story-to-Video P1 — story_director map-reduce tests (fake call_fn, no network)."""
from __future__ import annotations

import json

from app.features.render.ai.llm.story_director import run_story_intelligence

_LONG = "\n\n".join(f"Đoạn {i}. " + ("Hàn Phong bước đi. " * 20) for i in range(8))


def _digest_json(i: int = 1) -> str:
    return json.dumps({
        "summary": f"phần {i}",
        "beats": [f"beat {i}"],
        "characters": [{"id": "han_phong", "name": "Hàn Phong", "description": "áo trắng"}],
        "environments": [{"id": "rung", "name": "Rừng", "description": "âm u"}],
    })


def _reduce_json() -> str:
    return json.dumps({
        "topic": "tiên hiệp", "setting": "Tu tiên giới", "hook": "trỗi dậy",
        "rolling_summary": "toàn chương",
        "characters": [{"id": "han_phong", "name": "Hàn Phong", "description": "áo trắng, kiếm bạc"}],
        "environments": [{"id": "rung", "name": "Rừng", "description": "âm u"}],
    })


def test_map_reduce_builds_bible():
    def fake(system, user):
        return _reduce_json() if "PER-PART DIGESTS" in user else _digest_json()
    out = run_story_intelligence(call_fn=fake, chapter_text=_LONG, language="vi", provider_label="test")
    assert out is not None
    bible = out["bible"]
    assert bible.character("han_phong") is not None
    assert bible.environment("rung") is not None
    assert out["meta"]["topic"] == "tiên hiệp"


def test_reduce_failure_degrades_to_deterministic_merge():
    # Digests succeed, reduce returns None → director merges digest entities.
    def fake(system, user):
        return None if "PER-PART DIGESTS" in user else _digest_json()
    out = run_story_intelligence(call_fn=fake, chapter_text=_LONG, language="vi")
    assert out is not None
    bible = out["bible"]
    # Merged from digests (deduped by id).
    assert bible.character("han_phong") is not None
    assert bible.environment("rung") is not None
    assert out["meta"]["rolling_summary"]  # from merged summaries / rolling


def test_all_calls_none_returns_none():
    out = run_story_intelligence(call_fn=lambda s, u: None, chapter_text=_LONG)
    assert out is None


def test_empty_chapter_returns_none():
    assert run_story_intelligence(call_fn=lambda s, u: _digest_json(), chapter_text="  ") is None


def test_call_fn_raising_is_swallowed():
    def boom(system, user):
        raise RuntimeError("provider exploded")
    # Never raises (Sacred Contract #3) → None since no digest survives.
    assert run_story_intelligence(call_fn=boom, chapter_text=_LONG) is None
