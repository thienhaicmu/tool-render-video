"""Tests for the Content per-scene narration refine (2026-07-04 upgrade).

An opt-in (CONTENT_REFINE_NARRATION=1) second LLM pass re-authors the whole scene
set's narration so it flows scene→scene and fits each scene's planned length.
Reuses the recap {"narration":[{index,text}]} response shape. Never raises; None
leaves the original narration untouched (Sacred Contract #3).
"""
from __future__ import annotations

import app.features.render.ai.llm.providers.gemini as gem
from app.features.render.ai.llm import select_content_narration
from app.features.render.ai.llm.content_prompts import build_content_narration_refine_prompt


def test_prompt_is_format_safe_and_lists_every_scene():
    scenes = [
        {"index": 0, "role": "hook", "seconds": 8, "narration": "Xin chào {x} }{ lạ"},
        {"index": 1, "role": "explain", "seconds": 20, "narration": "Nội dung"},
    ]
    system, user = build_content_narration_refine_prompt(scenes, topic="T", tone="epic")
    assert "[0]" in user and "[1]" in user
    assert "lạ" in user                     # braces in narration survived
    assert "narration" in system.lower()


def test_dispatch_returns_none_without_key():
    assert select_content_narration(scenes=[{"index": 0, "narration": "x"}], api_key="") is None


def test_dispatch_returns_none_on_empty_scenes():
    assert select_content_narration(scenes=[], api_key="k") is None


def test_gemini_impl_parses_refined_narration(monkeypatch):
    # Exercise prompt-build + parse without a real SDK call.
    monkeypatch.setattr(gem, "_GENAI_SDK", True, raising=False)
    monkeypatch.setattr(
        gem, "_call_gemini_content_narration",
        lambda api_key, model, sys_p, usr_p: (
            '{"narration":[{"index":0,"text":"Hook mới"},{"index":1,"text":"Giải thích mới"}]}'
        ),
    )
    out = gem.select_content_narration(
        scenes=[{"index": 0, "role": "hook", "seconds": 8, "narration": "cũ"},
                {"index": 1, "role": "explain", "seconds": 20, "narration": "cũ"}],
        topic="T", tone="epic", target_language="vi-VN", api_key="k",
    )
    assert out == {0: "Hook mới", 1: "Giải thích mới"}


def test_gemini_impl_never_raises_on_bad_response(monkeypatch):
    monkeypatch.setattr(gem, "_GENAI_SDK", True, raising=False)
    monkeypatch.setattr(gem, "_call_gemini_content_narration",
                        lambda *a, **k: "not json at all")
    out = gem.select_content_narration(
        scenes=[{"index": 0, "narration": "x"}], api_key="k",
    )
    assert out is None  # unparseable → None → caller keeps original narration
