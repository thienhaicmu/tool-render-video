"""
test_recap_per_episode_narration.py — guard for P1-2 (per-episode narration).

Covers the pure pieces (prompt builder, response parser, dispatcher wiring) and
pins the Sacred-Contract-safe default: the env gate is OFF, so recap is
byte-identical until an operator opts in.
"""
from __future__ import annotations

import app.features.render.ai.llm as llm
from app.features.render.ai.llm.recap_prompts import build_episode_narration_prompt
from app.features.render.ai.llm.recap_parser import parse_episode_narration_response


# ── prompt builder ───────────────────────────────────────────────────────────

def test_prompt_lists_every_scene_index_and_json_shape():
    scenes = [
        {"index": 0, "start": 10, "end": 25, "title": "Opening", "intent": "set up", "audio_mode": "narrate"},
        {"index": 1, "start": 30, "end": 48, "title": "Reveal", "intent": "twist", "audio_mode": "original"},
    ]
    system, user = build_episode_narration_prompt(scenes, story_model=None,
                                                  target_language="vi-VN", episode_title="Tập 1")
    assert "narrator" in system.lower()
    assert "[0]" in user and "[1]" in user
    assert '"narration"' in user and '"index"' in user   # JSON example survived .format()
    assert "Tập 1" in user


def test_prompt_format_safe_with_braces_in_title():
    scenes = [{"index": 0, "start": 0, "end": 10, "title": "use {a: b}", "intent": "", "audio_mode": "narrate"}]
    # Must not raise KeyError/IndexError from str.format.
    _, user = build_episode_narration_prompt(scenes, episode_title="ep {x}")
    assert "[0]" in user


# ── response parser ──────────────────────────────────────────────────────────

def test_parse_valid_narration():
    raw = '{"narration": [{"index": 0, "text": "Câu một."}, {"index": 1, "text": ""}]}'
    out = parse_episode_narration_response(raw)
    assert out == {0: "Câu một.", 1: ""}


def test_parse_tolerant_and_defensive():
    assert parse_episode_narration_response("noise {\"narration\":[{\"index\":2,\"text\":\"x\"}]} tail") == {2: "x"}
    assert parse_episode_narration_response("") == {}
    assert parse_episode_narration_response("not json") == {}
    assert parse_episode_narration_response('{"narration": "wrong type"}') == {}
    assert parse_episode_narration_response('{"other": 1}') == {}


# ── dispatcher ───────────────────────────────────────────────────────────────

def test_impl_lookup_gemini_has_openai_claude_missing():
    assert callable(llm._get_episode_narration_impl("gemini"))
    assert llm._get_episode_narration_impl("openai") is None
    assert llm._get_episode_narration_impl("claude") is None


def test_dispatch_returns_none_when_no_impl(monkeypatch):
    monkeypatch.setattr(llm, "_get_episode_narration_impl", lambda p: None)
    assert llm.select_episode_narration(provider="openai", episode_scenes=[{"index": 0}]) is None


def test_dispatch_forwards_to_impl(monkeypatch):
    captured = {}

    def _fake_impl(**kwargs):
        captured.update(kwargs)
        return {0: "hi"}

    monkeypatch.setattr(llm, "_get_episode_narration_impl", lambda p: _fake_impl)
    out = llm.select_episode_narration(provider="gemini", episode_scenes=[{"index": 0}],
                                       episode_title="Tập 1", api_key="k")
    assert out == {0: "hi"}
    assert captured["episode_title"] == "Tập 1" and captured["api_key"] == "k"


def test_dispatch_never_raises(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("x")
    monkeypatch.setattr(llm, "_get_episode_narration_impl", lambda p: _boom)
    assert llm.select_episode_narration(provider="gemini", episode_scenes=[{"index": 0}]) is None


# ── gate default ─────────────────────────────────────────────────────────────

def test_per_episode_narration_gate_defaults_off():
    import app.features.render.engine.pipeline.recap_pipeline as rp
    assert rp._RECAP_PER_EPISODE_NARRATION is False
