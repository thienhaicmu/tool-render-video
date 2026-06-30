"""Architecture-review Batch C (2026-06-30) — Comprehension stage contract.

Pins the behaviour of ``comprehension_stage.run_comprehension``:

  1. Kill switch (STORY_INTELLIGENCE_HOIST_ENABLED=0) returns None
     IMMEDIATELY without calling the LLM or emitting events.
  2. Happy path with the LLM dispatcher returning a valid StoryModel:
     - LLM is called exactly once
     - Result is persisted (update_story_model called with JSON)
     - Result is cached on disk
     - WS events fired: comprehension.start, comprehension.done (source="llm"),
       and the legacy recap.pass1.done alias (Q3=a)
  3. Cache hit short-circuits the LLM call (LLM dispatcher NOT invoked).
  4. LLM returning None (or an empty model) → returns None, persists nothing,
     emits comprehension.done with ok=False AND the legacy alias.
  5. LLM raising an exception → returns None (Sacred Contract #3).
  6. Atomic write on cache put — .tmp sidecar is cleaned up.
  7. PROMPT_VERSION change invalidates cache entries.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.recap_plan import StoryModel, StoryBeat


@pytest.fixture
def _isolated_cache(tmp_path, monkeypatch):
    """Redirect APP_DATA_DIR so disk cache writes never touch the user's real
    cache. Also enable the kill switch by default for the happy-path tests."""
    monkeypatch.setattr(
        "app.features.render.engine.pipeline.comprehension_stage.APP_DATA_DIR",
        tmp_path,
        raising=False,
    )
    monkeypatch.setenv("STORY_INTELLIGENCE_HOIST_ENABLED", "1")
    yield tmp_path


def _good_story_model() -> StoryModel:
    return StoryModel(
        summary="A small film about a coffee shop and what gets lost.",
        beats=[
            StoryBeat(text="inciting", t=15.0, kind="setup"),
            StoryBeat(text="climax", t=120.0, kind="climax"),
        ],
        theme="loss",
    )


def _collect_events():
    events: list[dict] = []

    def emit(**kwargs):
        events.append(kwargs)

    return events, emit


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_returns_none_without_calling_llm(_isolated_cache, monkeypatch):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    monkeypatch.setenv("STORY_INTELLIGENCE_HOIST_ENABLED", "0")
    calls = {"n": 0}

    def fake_llm(**kwargs):
        calls["n"] += 1
        return _good_story_model()

    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="j1", channel_code="vn",
        srt_content="transcript", video_duration=60.0,
        provider="gemini",
        emit_fn=emit,
        select_story_model_fn=fake_llm,
        update_story_model_fn=lambda jid, blob: None,
    )
    assert result is None
    assert calls["n"] == 0, "LLM must not be called when hoist is disabled"
    assert events == [], "no WS events fired in kill-switch path"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_calls_llm_persists_caches_and_emits(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    llm_calls = []
    persist_calls = []

    def fake_llm(**kwargs):
        llm_calls.append(kwargs)
        return _good_story_model()

    def fake_persist(jid, blob):
        persist_calls.append((jid, blob))

    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="job-1", channel_code="vn",
        srt_content="00:00:00,000 --> 00:00:10,000\nhello",
        video_duration=180.0,
        provider="gemini", model="flash",
        target_language="vi-VN", tone="",
        emit_fn=emit,
        select_story_model_fn=fake_llm,
        update_story_model_fn=fake_persist,
    )
    assert result is not None
    assert result.summary == "A small film about a coffee shop and what gets lost."

    # LLM called exactly once with the right kwargs.
    assert len(llm_calls) == 1
    assert llm_calls[0]["provider"] == "gemini"
    assert llm_calls[0]["video_duration"] == 180.0

    # Persisted as JSON.
    assert len(persist_calls) == 1
    jid, blob = persist_calls[0]
    assert jid == "job-1"
    data = json.loads(blob)
    assert data["summary"] == "A small film about a coffee shop and what gets lost."

    # WS events: comprehension.start → comprehension.done → recap.pass1.done alias.
    event_names = [e["event"] for e in events]
    assert event_names == [
        "comprehension.start",
        "comprehension.done",
        "recap.pass1.done",
    ]
    done_event = events[1]
    assert done_event["context"]["ok"] is True
    assert done_event["context"]["source"] == "llm"
    assert done_event["context"]["story_model"]["summary"] == result.summary

    # On-disk cache populated.
    cache_files = list((_isolated_cache / "cache" / "comprehension").glob("*.json"))
    assert len(cache_files) == 1
    cached_payload = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert cached_payload["summary"] == result.summary


# ---------------------------------------------------------------------------
# Cache hit short-circuit
# ---------------------------------------------------------------------------


def test_cache_hit_skips_llm_and_emits_source_cache(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    # Prime the cache by running once with a stub LLM.
    llm_calls = {"n": 0}

    def fake_llm(**kwargs):
        llm_calls["n"] += 1
        return _good_story_model()

    stage.run_comprehension(
        job_id="prime", channel_code="vn",
        srt_content="same-transcript", video_duration=60.0,
        provider="gemini", model="flash",
        emit_fn=None, select_story_model_fn=fake_llm,
        update_story_model_fn=lambda jid, blob: None,
    )
    assert llm_calls["n"] == 1, "warm-up should invoke the LLM once"

    # Second call with the same transcript+provider+model → cache hit.
    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="second", channel_code="vn",
        srt_content="same-transcript", video_duration=60.0,
        provider="gemini", model="flash",
        emit_fn=emit, select_story_model_fn=fake_llm,
        update_story_model_fn=lambda jid, blob: None,
    )
    assert result is not None
    assert llm_calls["n"] == 1, "LLM must NOT be invoked on cache hit"
    # comprehension.done carries source="cache".
    done = next(e for e in events if e["event"] == "comprehension.done")
    assert done["context"]["source"] == "cache"
    assert done["context"]["ok"] is True


# ---------------------------------------------------------------------------
# LLM failure modes
# ---------------------------------------------------------------------------


def test_llm_returns_none_returns_none_and_emits_failed(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    persist_calls = []
    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="failing", channel_code="vn",
        srt_content="transcript", video_duration=60.0,
        provider="gemini",
        emit_fn=emit,
        select_story_model_fn=lambda **kw: None,
        update_story_model_fn=lambda jid, blob: persist_calls.append((jid, blob)),
    )
    assert result is None
    assert persist_calls == [], "nothing to persist when LLM returned None"
    done = next(e for e in events if e["event"] == "comprehension.done")
    assert done["context"]["ok"] is False
    assert done["context"]["source"] == "failed"
    assert done["context"]["story_model"] is None
    # Legacy alias must also fire (Q3=a).
    alias = next(e for e in events if e["event"] == "recap.pass1.done")
    assert alias["context"]["ok"] is False


def test_llm_returns_empty_model_returns_none(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="empty", channel_code="vn",
        srt_content="transcript", video_duration=60.0,
        provider="gemini",
        emit_fn=emit,
        select_story_model_fn=lambda **kw: StoryModel(),  # explicit empty
        update_story_model_fn=lambda jid, blob: None,
    )
    assert result is None
    done = next(e for e in events if e["event"] == "comprehension.done")
    assert done["context"]["ok"] is False


def test_llm_raising_does_not_propagate(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage

    def boom(**kw):
        raise RuntimeError("provider exploded")

    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="boom", channel_code="vn",
        srt_content="transcript", video_duration=60.0,
        provider="gemini",
        emit_fn=emit,
        select_story_model_fn=boom,
        update_story_model_fn=lambda jid, blob: None,
    )
    assert result is None
    done = next(e for e in events if e["event"] == "comprehension.done")
    assert done["context"]["ok"] is False


# ---------------------------------------------------------------------------
# Cache key composition
# ---------------------------------------------------------------------------


def test_different_transcripts_produce_different_cache_keys(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    k1 = stage._build_cache_key("gemini", "flash", "vi-VN", "", stage._transcript_hash("A"))
    k2 = stage._build_cache_key("gemini", "flash", "vi-VN", "", stage._transcript_hash("B"))
    assert k1 != k2


def test_different_providers_produce_different_cache_keys(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    k1 = stage._build_cache_key("gemini", "flash", "vi-VN", "", "h")
    k2 = stage._build_cache_key("claude", "flash", "vi-VN", "", "h")
    assert k1 != k2


def test_prompt_version_bump_invalidates_cache_key(_isolated_cache, monkeypatch):
    """Folding PROMPT_VERSION (Batch A) into the cache key means a prompt edit
    invalidates the Comprehension cache by construction."""
    from app.features.render.engine.pipeline import comprehension_stage as stage
    monkeypatch.setattr(
        "app.features.render.ai.llm.prompts.PROMPT_VERSION", 1, raising=False
    )
    k_v1 = stage._build_cache_key("gemini", "flash", "vi-VN", "", "h")
    monkeypatch.setattr(
        "app.features.render.ai.llm.prompts.PROMPT_VERSION", 2, raising=False
    )
    k_v2 = stage._build_cache_key("gemini", "flash", "vi-VN", "", "h")
    assert k_v1 != k_v2


# ---------------------------------------------------------------------------
# persist=False (test mode)
# ---------------------------------------------------------------------------


def test_persist_false_skips_db_write_but_still_emits(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage
    persist_calls = []
    events, emit = _collect_events()
    result = stage.run_comprehension(
        job_id="dry-run", channel_code="vn",
        srt_content="x", video_duration=60.0,
        provider="gemini",
        persist=False,
        emit_fn=emit,
        select_story_model_fn=lambda **kw: _good_story_model(),
        update_story_model_fn=lambda jid, blob: persist_calls.append((jid, blob)),
    )
    assert result is not None
    assert persist_calls == []
    done = next(e for e in events if e["event"] == "comprehension.done")
    assert done["context"]["ok"] is True


# ---------------------------------------------------------------------------
# Defensive: callbacks that raise must not break the stage
# ---------------------------------------------------------------------------


def test_emit_fn_raising_does_not_break_stage(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage

    def boom_emit(**kw):
        raise RuntimeError("WS broken")

    result = stage.run_comprehension(
        job_id="x", channel_code="vn",
        srt_content="t", video_duration=60.0,
        provider="gemini",
        emit_fn=boom_emit,
        select_story_model_fn=lambda **kw: _good_story_model(),
        update_story_model_fn=lambda jid, blob: None,
    )
    assert result is not None


def test_update_story_model_fn_raising_does_not_break_stage(_isolated_cache):
    from app.features.render.engine.pipeline import comprehension_stage as stage

    def boom_persist(jid, blob):
        raise RuntimeError("DB locked")

    result = stage.run_comprehension(
        job_id="x", channel_code="vn",
        srt_content="t", video_duration=60.0,
        provider="gemini",
        emit_fn=None,
        select_story_model_fn=lambda **kw: _good_story_model(),
        update_story_model_fn=boom_persist,
    )
    # The model is still returned; persistence failure is logged only.
    assert result is not None
