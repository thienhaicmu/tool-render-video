from __future__ import annotations

from app.domain.story_plan_v2 import Beat, StoryPlan, Visual
from app.features.render.ai import llm
from app.features.render.ai.llm import story_director_v2


def _plan() -> StoryPlan:
    return StoryPlan(visuals=[Visual(id="v1")],
                     timeline=[Beat(id="b1", narration="hello", visual_id="v1")])


def test_story_role_routing_binds_each_role_and_traces_models(monkeypatch):
    monkeypatch.setenv("LLM_DISABLED_PROVIDERS", "")
    monkeypatch.setenv("STORY_ROLE_ROUTING", "1")
    monkeypatch.setenv("STORY_UNDERSTANDING_PROVIDER", "gemini")
    monkeypatch.setenv("STORY_UNDERSTANDING_MODEL", "gemini-understand")
    monkeypatch.setenv("STORY_WRITER_PROVIDER", "claude")
    monkeypatch.setenv("STORY_WRITER_MODEL", "claude-writer")
    monkeypatch.setenv("STORY_STRUCTURE_PROVIDER", "openai")
    monkeypatch.setenv("STORY_STRUCTURE_MODEL", "openai-structure")
    bound = []

    def bind(kind):
        def inner(provider, key, model):
            bound.append((kind, provider, key, model))
            return lambda system, user: "ok"
        return inner

    monkeypatch.setattr(llm, "_get_story_call_fn", bind("structure"))
    monkeypatch.setattr(llm, "_get_writer_call_fn", bind("writer"))
    monkeypatch.setattr(llm, "_get_json_call_fn", bind("understanding"))
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _plan()

    monkeypatch.setattr(story_director_v2, "run_super_plan", fake_run)
    events = []
    result = llm.generate_story_plan_v2(
        provider="openai", source="idea", idea="idea", api_key="primary",
        resolve_key=lambda provider: f"key-{provider}", observer=events.append,
    )
    assert result is not None
    assert ("understanding", "gemini", "key-gemini", "gemini-understand") in bound
    assert ("writer", "claude", "key-claude", "claude-writer") in bound
    assert ("structure", "openai", "key-openai", "openai-structure") in bound
    assert captured["json_provider_label"] == "gemini"
    assert captured["writer_provider_label"] == "claude"
    assert captured["provider_label"] == "openai"
    selected = next(event for event in events if event["event"] == "provider_selected")
    assert selected["role_routes"]["writer"]["model"] == "claude-writer"


def test_role_route_without_key_falls_back_to_structure(monkeypatch):
    monkeypatch.setenv("LLM_DISABLED_PROVIDERS", "")
    monkeypatch.setenv("STORY_ROLE_ROUTING", "1")
    monkeypatch.setenv("STORY_WRITER_PROVIDER", "claude")
    monkeypatch.delenv("STORY_STRUCTURE_PROVIDER", raising=False)
    monkeypatch.delenv("STORY_UNDERSTANDING_PROVIDER", raising=False)
    monkeypatch.setattr(llm, "_get_story_call_fn", lambda *args: (lambda s, u: "ok"))
    monkeypatch.setattr(llm, "_get_writer_call_fn", lambda provider, *args:
                        (lambda s, u: "ok") if provider == "openai" else None)
    monkeypatch.setattr(llm, "_get_json_call_fn", lambda *args: (lambda s, u: "ok"))
    captured = {}
    monkeypatch.setattr(story_director_v2, "run_super_plan",
                        lambda **kwargs: captured.update(kwargs) or _plan())
    events = []
    result = llm.generate_story_plan_v2(
        provider="openai", source="idea", idea="idea", api_key="primary",
        resolve_key=lambda provider: "" if provider == "claude" else "key",
        observer=events.append,
    )
    assert result is not None
    assert captured["writer_provider_label"] == "openai"
    assert any(event["event"] == "role_route_fallback" and event["role"] == "writer"
               for event in events)
