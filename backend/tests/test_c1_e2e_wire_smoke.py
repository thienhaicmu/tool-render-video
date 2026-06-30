"""C.1 end-to-end wire smoke test (2026-06-30).

Validates the full producer→consumer wire built across C.1 Phase 1+2+3:

  Comprehension stage produces StoryModel
        │
        ▼
  render_pipeline captures _clip_story_model
        │
        ▼
  select_render_plan (dispatcher) forwards story_model kwarg
        │
        ▼
  Provider.select_render_plan threads to build_render_plan_prompt
        │
        ▼
  build_render_plan_prompt injects _story_block_clips → prompt contains
                              STORY INTELLIGENCE section

Strategy
  Pure mock-based. NO real LLM calls (no API credit consumed). All three
  providers are mocked at their public select_render_plan entry point so
  the test runs in ~2s and is CI-safe.

What it catches
  - Provider drops story_model kwarg → TypeError from dispatcher
  - Prompt template loses {story_block_section} slot → KeyError on .format
  - _story_block_clips returns garbage that breaks str.format
  - Dispatcher's kwargs dict drops story_model → providers get None even
    when caller passed a model

What it does NOT catch
  - LLM API call failures (would need real keys + budget)
  - Visual quality of clip selection (needs human eyes on rendered output)
  - Cache invalidation correctness across multi-render workflows
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_story_model():
    """A realistic StoryModel that the Comprehension stage might produce
    for a 20-minute documentary. Used as the input to the dispatcher in
    these smoke tests."""
    from app.domain.recap_plan import StoryModel, StoryBeat, Character
    return StoryModel(
        summary="A small coffee shop fights to preserve its identity against a franchise takeover.",
        theme="craft vs commerce",
        genre="documentary",
        conflict="the soul of artisan coffee vs the scale of franchise",
        characters=[
            Character(name="Maya", role="owner", want="preserve heritage"),
            Character(name="Rio", role="franchise scout", want="acquire the lease"),
        ],
        beats=[
            StoryBeat(text="Maya inherits the shop from her father", t=120.0),
            StoryBeat(text="Rio makes the first offer", t=480.0),
            StoryBeat(text="Maya considers signing", t=900.0),
        ],
        emotional_curve=["hope", "doubt", "resolve"],
        climax="Maya tears up the contract in front of regulars",
        ending="The shop survives but Maya carries the cost",
    )


# ---------------------------------------------------------------------------
# Smoke 1 — dispatcher forwards story_model to the active provider
# ---------------------------------------------------------------------------


def test_dispatcher_forwards_story_model_to_gemini(synthetic_story_model):
    from app.features.render.ai.llm import select_render_plan
    captured: dict = {}

    def fake_gemini_select(**kwargs):
        captured.update(kwargs)
        return None  # provider returns None to short-circuit fallback chain

    with patch(
        "app.features.render.ai.llm._get_provider_impl",
        return_value=fake_gemini_select,
    ):
        select_render_plan(
            provider="gemini",
            srt_content="00:00:00,000 --> 00:00:05,000\nhello",
            output_count=1,
            min_sec=30.0,
            max_sec=60.0,
            video_duration=300.0,
            story_model=synthetic_story_model,
        )

    # The provider received the StoryModel via the dispatcher's kwargs dict.
    assert "story_model" in captured, (
        "Dispatcher dropped the story_model kwarg — provider would get None even "
        "when caller passed a real StoryModel."
    )
    assert captured["story_model"] is synthetic_story_model


def test_dispatcher_passes_none_when_story_model_omitted():
    """Legacy callers (every existing render path) don't pass story_model.
    The dispatcher should forward None — Sacred Contract #2 byte-identical
    wire shape."""
    from app.features.render.ai.llm import select_render_plan
    captured: dict = {}

    def fake_gemini_select(**kwargs):
        captured.update(kwargs)
        return None

    with patch(
        "app.features.render.ai.llm._get_provider_impl",
        return_value=fake_gemini_select,
    ):
        select_render_plan(
            provider="gemini",
            srt_content="00:00:00,000 --> 00:00:05,000\nx",
            output_count=1,
            min_sec=30.0,
            max_sec=60.0,
            video_duration=300.0,
        )

    assert captured.get("story_model") is None


# ---------------------------------------------------------------------------
# Smoke 2 — provider threads story_model into build_render_plan_prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_mod_path", [
    "app.features.render.ai.llm.providers.gemini",
    "app.features.render.ai.llm.providers.openai",
    "app.features.render.ai.llm.providers.claude",
])
def test_provider_threads_story_model_to_prompt_builder(
    provider_mod_path, synthetic_story_model,
):
    """Every provider's select_render_plan signature accepts story_model
    and forwards it to build_render_plan_prompt. If any provider drops
    the kwarg, the prompt builder gets None and the STORY INTELLIGENCE
    section never lands."""
    import importlib
    import inspect

    provider = importlib.import_module(provider_mod_path)
    sig = inspect.signature(provider.select_render_plan)
    assert "story_model" in sig.parameters, (
        f"{provider_mod_path}.select_render_plan dropped story_model kwarg"
    )

    # Also verify it survives the internal _run_render_plan call. We
    # introspect the source of the public entry point to confirm the
    # kwarg appears in the forwarded call. Cheap structural test.
    src = inspect.getsource(provider.select_render_plan)
    assert "story_model=story_model" in src, (
        f"{provider_mod_path}.select_render_plan does not forward "
        f"story_model to _run_render_plan — Phase 3 wire incomplete"
    )


# ---------------------------------------------------------------------------
# Smoke 3 — prompt contains STORY INTELLIGENCE section when story_model present
# ---------------------------------------------------------------------------


def test_prompt_e2e_contains_story_intelligence_section(synthetic_story_model):
    """End-to-end: feed a StoryModel into build_render_plan_prompt and
    inspect the rendered user prompt for the editorial cues that ground
    clip selection in whole-film semantic understanding."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    _, user_prompt = build_render_plan_prompt(
        srt_content="00:00:00,000 --> 00:00:30,000\nMaya speaks about the shop",
        output_count=3,
        min_sec=30.0,
        max_sec=60.0,
        story_model=synthetic_story_model,
    )

    # Header.
    assert "STORY INTELLIGENCE" in user_prompt, (
        "STORY INTELLIGENCE header missing — prompt builder dropped the block"
    )
    # Key semantic anchors.
    assert "craft vs commerce" in user_prompt, "theme dropped from prompt"
    assert "the soul of artisan coffee" in user_prompt, "conflict dropped"
    assert "Maya" in user_prompt, "character dropped"
    # Editorial instruction the audit promised would land.
    assert "viral_score" in user_prompt or "hook_score" in user_prompt, (
        "editorial instruction (raise viral/hook score on conflict landing) missing"
    )


# ---------------------------------------------------------------------------
# Smoke 4 — full Comprehension → dispatcher → provider mock chain
# ---------------------------------------------------------------------------


def test_full_e2e_comprehension_to_provider_with_story_intelligence(
    synthetic_story_model, tmp_path, monkeypatch,
):
    """End-to-end smoke through the real Comprehension stage with a
    mocked LLM, then through the real dispatcher with a mocked provider.
    Verifies the wire from Whisper transcript → StoryModel → prompt
    that providers will see in production."""
    from app.features.render.engine.pipeline import comprehension_stage as stage
    from app.features.render.ai.llm import select_render_plan

    # Isolate the Comprehension disk cache.
    monkeypatch.setattr(stage, "APP_DATA_DIR", tmp_path, raising=False)
    monkeypatch.setenv("STORY_INTELLIGENCE_HOIST_ENABLED", "1")

    # The Comprehension stage's LLM returns our synthetic StoryModel.
    sm = stage.run_comprehension(
        job_id="smoke-c1",
        channel_code="vn",
        srt_content="00:00:00,000 --> 00:00:30,000\nhello",
        video_duration=300.0,
        provider="gemini",
        emit_fn=None,
        persist=False,
        select_story_model_fn=lambda **kw: synthetic_story_model,
        update_story_model_fn=lambda jid, blob: None,
    )
    assert sm is not None
    assert sm.summary.startswith("A small coffee shop")

    # Now the dispatcher receives that StoryModel and forwards through to
    # a mocked provider. The provider captures the kwarg AND runs the
    # real prompt builder so we can verify the prompt content.
    captured_kwargs: dict = {}
    captured_prompt: dict = {}

    def fake_provider(**kwargs):
        captured_kwargs.update(kwargs)
        # Build the prompt the way the real provider would (uses the
        # real build_render_plan_prompt) so we can inspect what would
        # have hit the LLM.
        from app.features.render.ai.llm.prompts import build_render_plan_prompt
        sys_p, user_p = build_render_plan_prompt(
            srt_content=kwargs["srt_content"],
            output_count=kwargs["output_count"],
            min_sec=kwargs["min_sec"],
            max_sec=kwargs["max_sec"],
            language=kwargs.get("language", "auto"),
            video_duration_sec=kwargs.get("video_duration", 0.0),
            story_model=kwargs.get("story_model"),
        )
        captured_prompt["system"] = sys_p
        captured_prompt["user"] = user_p
        return None  # short-circuit fallback chain

    with patch(
        "app.features.render.ai.llm._get_provider_impl",
        return_value=fake_provider,
    ):
        select_render_plan(
            provider="gemini",
            srt_content="00:00:00,000 --> 00:00:30,000\nhello",
            output_count=1,
            min_sec=30.0,
            max_sec=60.0,
            video_duration=300.0,
            story_model=sm,  # the producer→consumer hand-off
        )

    # Story Model survived end-to-end.
    assert captured_kwargs["story_model"] is sm
    # Prompt has the editorial grounding section.
    assert "STORY INTELLIGENCE" in captured_prompt["user"]
    assert "craft vs commerce" in captured_prompt["user"]


# ---------------------------------------------------------------------------
# Smoke 5 — Sacred Contract #2 wire shape: legacy prompt byte-identical
# ---------------------------------------------------------------------------


def test_sacred_contract_2_legacy_callers_get_byte_identical_prompt():
    """A caller that doesn't pass story_model (every existing payload)
    produces a prompt byte-identical to one that passes story_model=None
    explicitly. The LLM disk cache SHA stays stable for legacy traffic."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    args = dict(
        srt_content="00:00:00,000 --> 00:00:10,000\nlegacy",
        output_count=1,
        min_sec=30.0,
        max_sec=60.0,
        language="vi-VN",
        target_duration=45,
        target_platform="tiktok",
        video_type="viral",
        hook_strength="aggressive",
    )
    _, prompt_legacy = build_render_plan_prompt(**args)
    _, prompt_explicit_none = build_render_plan_prompt(**args, story_model=None)
    assert prompt_legacy == prompt_explicit_none, (
        "Sacred Contract #2 violated — passing story_model=None drifts the prompt "
        "vs not passing it at all. Would invalidate legacy LLM cache entries."
    )
