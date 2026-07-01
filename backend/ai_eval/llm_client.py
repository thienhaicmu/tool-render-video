"""
llm_client.py — a generic, provider-agnostic text completion for the judge.

Deliberately standalone (mirrors the render providers' call pattern but does
NOT import them) so the eval harness stays decoupled from the render path.
Reuses only ``call_with_retry`` (a generic util) and ``app.core.config`` for
server-side API keys.

All SDKs are lazy-imported so importing this module never fails when an
optional AI extra is missing. ``complete`` returns None on any failure
(Sacred Contract #3 spirit) so a judge batch degrades gracefully rather than
crashing.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("ai_eval.llm_client")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")

# Judge defaults mirror the render providers' cheap/fast tiers. Override via env.
_DEFAULT_MODELS = {
    "gemini": os.getenv("EVAL_GEMINI_MODEL", "gemini-2.5-flash"),
    "openai": os.getenv("EVAL_OPENAI_MODEL", "gpt-4o-mini"),
    "claude": os.getenv("EVAL_CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
}

# Judge should be deterministic — temperature 0.
_TEMPERATURE = float(os.getenv("EVAL_JUDGE_TEMPERATURE", "0") or 0)
_MAX_TOKENS = int(os.getenv("EVAL_JUDGE_MAX_TOKENS", "1500"))
_TIMEOUT_SEC = int(os.getenv("EVAL_JUDGE_TIMEOUT", "60"))


def resolve_api_key(provider: str) -> str:
    """Resolve the server-side API key for a provider from app config / env.
    Never raises — returns '' when unset (caller treats as skip). For gemini this
    returns a non-cooled key from the rotation pool so measurement runs fan out
    across all configured keys."""
    p = (provider or "").strip().lower()
    if p == "gemini":
        try:
            from app.features.render.ai.llm.key_pool import active_key
            _k = active_key()
            if _k:
                return _k
        except Exception:
            pass
    try:
        from app.core import config as _cfg
        return {
            "gemini": getattr(_cfg, "GEMINI_API_KEY", ""),
            "openai": getattr(_cfg, "OPENAI_API_KEY", ""),
            "claude": getattr(_cfg, "CLAUDE_API_KEY", ""),
        }.get(p, "")
    except Exception:
        return {
            "gemini": os.getenv("GEMINI_API_KEY", ""),
            "openai": os.getenv("OPENAI_API_KEY", ""),
            "claude": os.getenv("CLAUDE_API_KEY", ""),
        }.get(p, "")


def default_model(provider: str) -> str:
    return _DEFAULT_MODELS.get((provider or "").strip().lower(), "")


def _call_with_retry(fn, *, label: str):
    """Reuse the render path's retry util when available; fall back to a
    single attempt if the import fails (keeps eval usable in isolation)."""
    try:
        from app.features.render.ai.llm.retry import call_with_retry
        return call_with_retry(fn, label=label)
    except Exception:
        try:
            return fn()
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("ai_eval %s: call failed — %s", label, exc)
            return None


def _complete_gemini(system: str, user: str, api_key: str, model: str) -> Optional[str]:
    from google import genai as _genai  # lazy

    def _once(key: str):
        client = _genai.Client(api_key=key, http_options={"timeout": _TIMEOUT_SEC * 1000})
        resp = client.models.generate_content(
            model=model, contents=user,
            config={
                "system_instruction": system,
                "response_mime_type": "application/json",
                "temperature": _TEMPERATURE,
                "max_output_tokens": _MAX_TOKENS,
                # Gemini 2.5 Flash thinks by default and can consume the entire
                # output budget on a large judging prompt → empty .text → no
                # parseable JSON. The judge does not need thinking; disable it so
                # the full budget goes to the verdict.
                "thinking_config": {"thinking_budget": 0},
            },
        )
        return resp.text

    # Rotate across the Gemini key pool on 429 so judging survives per-key quota.
    try:
        from app.features.render.ai.llm.key_pool import call_gemini_with_rotation
        return call_gemini_with_rotation(_once, label="gemini_judge", seed_key=api_key)
    except Exception:
        return _call_with_retry(lambda: _once(api_key), label="gemini_judge")


def _complete_openai(system: str, user: str, api_key: str, model: str) -> Optional[str]:
    from openai import OpenAI  # lazy
    def _once():
        client = OpenAI(api_key=api_key, timeout=_TIMEOUT_SEC)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content
    return _call_with_retry(_once, label="openai_judge")


def _complete_claude(system: str, user: str, api_key: str, model: str) -> Optional[str]:
    import anthropic  # lazy
    def _once():
        client = anthropic.Anthropic(api_key=api_key, timeout=_TIMEOUT_SEC)
        resp = client.messages.create(
            model=model, system=system, max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate text blocks.
        return "".join(getattr(b, "text", "") for b in (resp.content or []))
    return _call_with_retry(_once, label="claude_judge")


def complete(provider: str, system: str, user: str, *,
             api_key: str = "", model: str | None = None) -> Optional[str]:
    """Return the raw completion string from ``provider``, or None on failure.

    ``api_key`` defaults to the server-config key for the provider. ``model``
    defaults to the provider's judge model. Never raises.
    """
    p = (provider or "").strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        logger.warning("ai_eval: unknown judge provider %r", provider)
        return None
    key = api_key or resolve_api_key(p)
    if not key:
        logger.warning("ai_eval: no API key for judge provider %s — skipping", p)
        return None
    mdl = model or default_model(p)
    try:
        if p == "gemini":
            return _complete_gemini(system, user, key, mdl)
        if p == "openai":
            return _complete_openai(system, user, key, mdl)
        return _complete_claude(system, user, key, mdl)
    except Exception as exc:  # lazy-import failure or SDK-construction error
        logger.warning("ai_eval: judge provider %s unavailable — %s", p, exc)
        return None
