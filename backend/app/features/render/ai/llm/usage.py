"""
usage.py — thread-local ledger for REAL (billed) LLM token usage.

Phase 0 (Story cost review, 2026-07-16): the Story observer/trace and /metrics
previously saw only character counts and an estimate — actual billed tokens were
invisible, so "P90 cost per job" was unanswerable. Providers now record the
usage object of each completed request here; the orchestration layer that knows
the STAGE (story_director_v2._observed_call) pops it and attaches it to the
planning trace + Prometheus.

Thread-local because provider calls within one plan run are strictly sequential
on one worker thread — "last recorded usage" is exactly the usage of the call
that just returned. Concurrent jobs live on different threads and never mix.

Defensive (Sacred Contract #3 spirit): every helper catches everything; a
usage-accounting failure must never break a live call.
"""
from __future__ import annotations

import threading
from typing import Optional

_LOCAL = threading.local()


def record_usage(provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Record the billed usage of the request that just completed. Never raises."""
    try:
        _LOCAL.last = {
            "provider": str(provider or ""),
            "model": str(model or ""),
            "input_tokens": max(0, int(input_tokens or 0)),
            "output_tokens": max(0, int(output_tokens or 0)),
        }
    except Exception:
        pass


def record_usage_obj(provider: str, model: str, usage: object) -> None:
    """Record from an SDK usage object (OpenAI: prompt_tokens/completion_tokens).
    No-op on None/malformed. Never raises."""
    try:
        if usage is None:
            return
        in_tok = getattr(usage, "prompt_tokens", None)
        out_tok = getattr(usage, "completion_tokens", None)
        if in_tok is None and isinstance(usage, dict):
            in_tok = usage.get("prompt_tokens")
            out_tok = usage.get("completion_tokens")
        record_usage(provider, model, int(in_tok or 0), int(out_tok or 0))
    except Exception:
        pass


def pop_usage() -> Optional[dict]:
    """Return-and-clear the last recorded usage for THIS thread, or None."""
    try:
        last = getattr(_LOCAL, "last", None)
        _LOCAL.last = None
        return last
    except Exception:
        return None


__all__ = ["record_usage", "record_usage_obj", "pop_usage"]
