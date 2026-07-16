"""
P2 — Story audit observability / cost / cache-versioning / key-security.

  * F-08 estimate_super_plan_cost — a non-zero source yields a non-zero $ estimate
    (the pre-flight no longer reports a misleading $0 total for the paid LLM).
  * F-10 _story_cache_namespace — embeds the super-prompt + schema version so a
    prompt/schema change invalidates the story cache by construction.
  * F-11 _resolve_api_key(allow_generic=False) — the generic ai_cloud_api_key is
    NOT handed to a cross-provider fallback.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.features.render.ai.llm.story_director_v2 import estimate_super_plan_cost
from app.features.render.ai.llm.providers.openai import _story_cache_namespace
from app.features.render.engine.pipeline.llm_stage import _resolve_api_key


def test_cost_estimate_nonzero(monkeypatch):
    monkeypatch.delenv("OPENAI_STORY_PRICE_IN_PER_M", raising=False)
    monkeypatch.delenv("OPENAI_STORY_PRICE_OUT_PER_M", raising=False)
    monkeypatch.delenv("OPENAI_STORY_MINI_PRICE_IN_PER_M", raising=False)
    monkeypatch.delenv("OPENAI_STORY_MINI_PRICE_OUT_PER_M", raising=False)
    est = estimate_super_plan_cost(source_chars=20000, ceiling=15)
    assert est["input_tokens"] > 0 and est["output_tokens"] > 0
    assert est["cost_usd"] > 0.0
    # Rates are env-tunable — Phase 3 added a mini tier (Understanding +
    # Structure), so zeroing the estimate means zeroing BOTH tiers' rates.
    monkeypatch.setenv("OPENAI_STORY_PRICE_IN_PER_M", "0")
    monkeypatch.setenv("OPENAI_STORY_PRICE_OUT_PER_M", "0")
    monkeypatch.setenv("OPENAI_STORY_MINI_PRICE_IN_PER_M", "0")
    monkeypatch.setenv("OPENAI_STORY_MINI_PRICE_OUT_PER_M", "0")
    assert estimate_super_plan_cost(source_chars=20000, ceiling=15)["cost_usd"] == 0.0


def test_cost_estimate_defensive():
    # Never raises on junk input.
    assert estimate_super_plan_cost(source_chars=-5, ceiling=0)["cost_usd"] >= 0.0


def test_cache_namespace_is_versioned():
    ns = _story_cache_namespace()
    from app.features.render.ai.llm.story_prompts_v2 import SUPER_PROMPT_VERSION
    from app.domain.story_plan_v2 import SCHEMA_VERSION
    assert ns.startswith("openai-story-plan|")
    assert SUPER_PROMPT_VERSION in ns
    assert f"v{SCHEMA_VERSION}" in ns


def test_generic_key_withheld_from_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)   # no env fallback for gemini
    payload = SimpleNamespace(ai_cloud_api_key="active-openai-key")
    # Primary (active provider) still gets the generic key.
    key, src = _resolve_api_key(payload, "openai", allow_generic=True)
    assert key == "active-openai-key" and src == "payload.ai_cloud_api_key"
    # Cross-provider fallback must NOT receive the active provider's generic key.
    key2, src2 = _resolve_api_key(payload, "gemini", allow_generic=False)
    assert key2 == "" and src2 == "none"


def test_per_provider_key_still_wins_over_generic_gate(monkeypatch):
    # allow_generic=False must not block a provider's OWN explicit key.
    payload = SimpleNamespace(ai_cloud_api_key="generic", gemini_api_key="gem-own")
    key, src = _resolve_api_key(payload, "gemini", allow_generic=False)
    assert key == "gem-own" and src == "payload.gemini_api_key"
