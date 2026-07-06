"""test_content_p22_p41.py — P2.2 content model override + P4.1 budget cap.

P2.2: content planning honours CONTENT_LLM_MODEL (a content-only override of the
      global default) without an explicit payload model; a payload model wins.
P4.1: RenderRequest.content_ai_budget is an additive field — default 0.0 (Sacred
      Contract #2 inert = unlimited), clamps to >= 0, and is on the public wire.
"""
from __future__ import annotations

import json

import app.features.render.ai.llm.providers.gemini as gem
from app.models.render import RenderRequest


# ── P2.2 ─────────────────────────────────────────────────────────────────────

def _spy_models(monkeypatch):
    seen: list[str] = []

    def _fake(api_key, model, system, user):
        seen.append(model)
        if "STORY EDITOR" in system:
            return json.dumps({"topic": "T", "characters": []})
        return json.dumps({"topic": "T", "scenes": [{"index": 0, "narration": "hi"}]})

    monkeypatch.setattr(gem, "_GENAI_SDK", True)
    monkeypatch.setattr(gem, "_call_gemini_content", _fake)
    return seen


def test_content_llm_model_env_override(monkeypatch):
    seen = _spy_models(monkeypatch)
    monkeypatch.setenv("CONTENT_LLM_MODEL", "gemini-3.1-flash-lite")
    plan = gem.select_content_plan(script="a short content script", api_key="k")
    assert plan is not None and seen, seen
    assert all(m == "gemini-3.1-flash-lite" for m in seen), seen


def test_content_explicit_payload_model_wins_over_env(monkeypatch):
    seen = _spy_models(monkeypatch)
    monkeypatch.setenv("CONTENT_LLM_MODEL", "gemini-3.1-flash-lite")
    gem.select_content_plan(script="x", api_key="k", model="gemini-2.5-pro")
    assert seen and all(m == "gemini-2.5-pro" for m in seen), seen


def test_content_env_unset_uses_global_default(monkeypatch):
    seen = _spy_models(monkeypatch)
    monkeypatch.delenv("CONTENT_LLM_MODEL", raising=False)
    monkeypatch.setattr(gem, "_DEFAULT_MODEL", "gemini-x-default")
    gem.select_content_plan(script="x", api_key="k")
    assert seen and all(m == "gemini-x-default" for m in seen), seen


# ── P4.1 ─────────────────────────────────────────────────────────────────────

def test_content_ai_budget_default_zero_inert():
    assert RenderRequest(output_dir="").content_ai_budget == 0.0


def test_content_ai_budget_clamps_and_coerces():
    assert RenderRequest(output_dir="", content_ai_budget=-5).content_ai_budget == 0.0
    assert RenderRequest(output_dir="", content_ai_budget="2.5").content_ai_budget == 2.5
    assert RenderRequest(output_dir="", content_ai_budget="junk").content_ai_budget == 0.0


def test_content_ai_budget_on_public_surface():
    from app.models.render_public import FE_FACING_FIELDS
    assert "content_ai_budget" in FE_FACING_FIELDS
