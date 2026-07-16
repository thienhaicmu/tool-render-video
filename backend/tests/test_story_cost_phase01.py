"""
Phase 0 + Phase 1 — Story planner cost controls (2026-07-16 review).

Pins:
  * is_billing_safe_retry — a read-TIMEOUT is never retried (the aborted request
    is still billed server-side); 429/connection failures are safe to retry.
  * call_with_retry(should_retry=...) stops after the first non-retryable raise.
  * usage ledger (ai/llm/usage.py) — record → pop returns once, then clears.
  * story_director_v2._observed_call attaches billed tokens to call_completed
    and never mis-attributes a STALE ledger entry to a cache-hit call.
  * _stream_chat_text salvages the partial text on a mid-generation break
    (no re-buy) and raises only when NOTHING was received.
  * Writer continuation: ONE bounded follow-up when finish_reason=length.
  * estimate_super_plan_cost surfaces the bounded worst case (llm_calls_max).
  * generate_story_plan_v2 PINS its provider by default; the cross-provider
    chain is opt-in via STORY_PROVIDER_FALLBACK=1.
  * story_plan_runs/ artifact dirs are pruned to a cap.

Offline: SDK + cache monkeypatched — no network.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import app.features.render.ai.llm as L
import app.features.render.ai.llm.providers.openai as oai
from app.features.render.ai.llm.retry import call_with_retry, is_billing_safe_retry
from app.features.render.ai.llm.usage import pop_usage, record_usage
from app.features.render.ai.llm.story_director_v2 import (
    _observed_call, estimate_super_plan_cost,
)


# ── billing-safe retry classification ─────────────────────────────────────────

def test_billing_safe_timeout_is_not_retryable():
    assert is_billing_safe_retry(Exception("Request timed out.")) is False
    assert is_billing_safe_retry(Exception("httpx.ReadTimeout: timeout")) is False


def test_billing_safe_rate_limit_and_connection_are_retryable():
    assert is_billing_safe_retry(Exception("429 Too Many Requests")) is True
    assert is_billing_safe_retry(Exception("Connection error.")) is True
    assert is_billing_safe_retry(Exception("503 Service Unavailable")) is True


def test_call_with_retry_stops_on_non_retryable():
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        raise TimeoutError("Request timed out.")

    out = call_with_retry(_fn, label="t", should_retry=is_billing_safe_retry)
    assert out is None
    assert calls["n"] == 1              # timeout → NO second (double-billed) attempt


def test_call_with_retry_still_retries_safe_errors():
    calls = {"n": 0}

    class _RL(Exception):
        retry_after = 0.01              # keep the backoff sleep negligible

    def _fn():
        calls["n"] += 1
        raise _RL("429 rate limit")

    out = call_with_retry(_fn, label="t", should_retry=is_billing_safe_retry)
    assert out is None
    assert calls["n"] == 2              # default max_attempts unchanged


# ── usage ledger + observed-call attribution ──────────────────────────────────

def test_usage_ledger_pop_clears():
    record_usage("openai", "gpt-4o", 11, 22)
    got = pop_usage()
    assert got == {"provider": "openai", "model": "gpt-4o",
                   "input_tokens": 11, "output_tokens": 22}
    assert pop_usage() is None


def test_observed_call_attaches_tokens():
    events = []

    def _call(sys, usr):
        record_usage("openai", "gpt-4o", 100, 200)
        return "raw"

    out = _observed_call(_call, "s", "u", stage="writer",
                         provider_label="openai", observer=events.append)
    assert out == "raw"
    done = [e for e in events if e["event"] == "call_completed"][0]
    assert done["input_tokens"] == 100 and done["output_tokens"] == 200


def test_observed_call_does_not_misattribute_stale_usage():
    record_usage("openai", "gpt-4o", 999, 999)   # stale entry from a prior call
    events = []
    _observed_call(lambda s, u: "cached", "s", "u", stage="structure",
                   provider_label="openai", observer=events.append)
    done = [e for e in events if e["event"] == "call_completed"][0]
    assert done["input_tokens"] == 0 and done["output_tokens"] == 0


# ── streaming salvage ─────────────────────────────────────────────────────────

def _chunk(text=None, finish=None, usage=None):
    delta = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)],
                           usage=usage)


class _FakeStreamClient:
    def __init__(self, chunks, explode_after=None):
        self._chunks = chunks
        self._explode_after = explode_after
        outer = self

        def _create(**kwargs):
            outer.kwargs = kwargs

            def _gen():
                for i, c in enumerate(outer._chunks):
                    if outer._explode_after is not None and i >= outer._explode_after:
                        raise RuntimeError("connection dropped mid-stream")
                    yield c
            return _gen()

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def test_stream_salvages_partial_on_midstream_break():
    client = _FakeStreamClient([_chunk("Hello "), _chunk("world"), _chunk("!!")],
                               explode_after=2)
    text, finish, usage = oai._stream_chat_text(
        client, {"model": "gpt-4o", "messages": []}, label="story-writer")
    assert text == "Hello world"        # salvage, not a raise → no re-buy upstream
    assert finish is None


def test_stream_raises_when_nothing_received():
    client = _FakeStreamClient([_chunk("x")], explode_after=0)
    with pytest.raises(RuntimeError):
        oai._stream_chat_text(client, {"model": "gpt-4o", "messages": []}, label="t")


def test_stream_collects_finish_and_usage():
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
    client = _FakeStreamClient([_chunk("a"), _chunk(None, finish="stop", usage=usage)])
    text, finish, got = oai._stream_chat_text(
        client, {"model": "gpt-4o", "messages": []}, label="t")
    assert text == "a" and finish == "stop" and got is usage


# ── writer continuation on length-truncation ─────────────────────────────────

class _FakeCompletionClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        outer = self

        def _create(**kwargs):
            outer.requests.append(kwargs)
            content, finish = outer._responses.pop(0)
            choice = SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason=finish)
            return SimpleNamespace(choices=[choice], usage=None)

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


def test_writer_continuation_on_length(monkeypatch):
    client = _FakeCompletionClient([("PART1", "length"), ("PART2", "stop")])
    monkeypatch.setattr(oai, "_STORY_STREAM", False)
    monkeypatch.setattr(oai, "_STORY_WRITER_CONTINUE", True)
    monkeypatch.setattr(oai, "_story_client", lambda key, streaming: client)
    out = oai._call_openai_writer_once("k", "gpt-4o", "sys", "usr")
    assert out == "PART1\nPART2"
    assert len(client.requests) == 2    # exactly ONE bounded continuation round
    cont_msgs = client.requests[1]["messages"]
    assert any(m["role"] == "assistant" and m["content"] == "PART1" for m in cont_msgs)


def test_writer_no_continuation_when_disabled(monkeypatch):
    client = _FakeCompletionClient([("PART1", "length")])
    monkeypatch.setattr(oai, "_STORY_STREAM", False)
    monkeypatch.setattr(oai, "_STORY_WRITER_CONTINUE", False)
    monkeypatch.setattr(oai, "_story_client", lambda key, streaming: client)
    assert oai._call_openai_writer_once("k", "gpt-4o", "s", "u") == "PART1"
    assert len(client.requests) == 1


# ── pre-flight estimate surfaces the bounded worst case ──────────────────────

def test_estimate_reports_bounded_max():
    est = estimate_super_plan_cost(source_chars=15000, ceiling=10, source="paste")
    assert est["llm_calls_max"] >= est["llm_calls"]
    assert est["cost_usd_max"] >= est["cost_usd"]


# ── story provider pinned by default ──────────────────────────────────────────

def _pin_env(monkeypatch):
    for var in ("STORY_PROVIDER_FALLBACK", "LLM_DISABLED_PROVIDERS",
                "STORY_STRUCTURE_PROVIDER", "STORY_WRITER_PROVIDER",
                "STORY_UNDERSTANDING_PROVIDER", "STORY_STRUCTURE_MODEL",
                "STORY_WRITER_MODEL", "STORY_UNDERSTANDING_MODEL"):
        monkeypatch.delenv(var, raising=False)


def test_story_provider_pinned_by_default(monkeypatch):
    _pin_env(monkeypatch)
    attempted = []
    monkeypatch.setattr(
        L, "_get_story_call_fn",
        lambda p, k, m: (attempted.append(p) or None))
    out = L.generate_story_plan_v2(
        provider="openai", source="paste", chapter="some chapter text",
        api_key="k", resolve_key=lambda _p: "k")
    assert out is None
    assert attempted == ["openai"]      # no silent Gemini/Claude re-run


def test_story_provider_chain_optin(monkeypatch):
    _pin_env(monkeypatch)
    monkeypatch.setenv("STORY_PROVIDER_FALLBACK", "1")
    monkeypatch.setattr(L, "_LLM_FALLBACK_ENABLED", True)
    attempted = []
    monkeypatch.setattr(
        L, "_get_story_call_fn",
        lambda p, k, m: (attempted.append(p) or None))
    L.generate_story_plan_v2(
        provider="openai", source="paste", chapter="some chapter text",
        api_key="k", resolve_key=lambda _p: "k")
    assert attempted[0] == "openai" and len(attempted) == 3


# ── plan-run artifact prune ───────────────────────────────────────────────────

def test_plan_run_dirs_pruned(tmp_path, monkeypatch):
    import app.features.story.router as story_router
    runs = tmp_path / "story_plan_runs"
    runs.mkdir()
    now = time.time()
    for i in range(5):
        d = runs / f"run{i}"
        d.mkdir()
        (d / "manifest.json").write_text("{}", encoding="utf-8")
        stamp = now - (5 - i) * 60
        import os
        os.utime(d, (stamp, stamp))
    monkeypatch.setattr(story_router, "_PLAN_RUN_DIR", runs)
    monkeypatch.setattr(story_router, "_PLAN_RUNS_MAX", 2)
    monkeypatch.setattr(story_router, "_PLAN_RUNS_TTL_DAYS", 365.0)
    story_router._prune_plan_run_dirs()
    left = sorted(p.name for p in runs.iterdir())
    assert left == ["run3", "run4"]     # newest kept, oldest dropped to the cap
