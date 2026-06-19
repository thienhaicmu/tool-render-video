"""
llm_stage.py — LLM stage helpers for the render pipeline.

Provides:
  _build_editorial_hint(payload): translates hook_strength + video_type +
    CreatorContext into a short advisory phrase for the LLM system prompt.
  _resolve_api_key(payload, provider): resolves the API key for the active
    provider from payload fields or env vars.

Both are imported directly by render_pipeline.py.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.render.llm_stage")
logger.info("llm_stage: module loaded (build=2026-06-04.gemini-default)")

# ── Editorial hint tables ─────────────────────────────────────────────────────
# Values map to advisory phrases appended to the LLM system prompt.
# Empty string = no instruction added (keeps baseline behavior).
# Phrases are intentionally short to minimise prompt token overhead and
# avoid confusing JSON-mode models with long prose instructions.

_HOOK_HINTS: dict[str, str] = {
    "aggressive": (
        "Prefer segments where the first 2–3 seconds immediately hook the viewer "
        "with a bold claim, surprising reveal, or strong emotional trigger."
    ),
    "balanced": "",   # default — baseline prompt already covers this
    "soft": (
        "Prefer segments with natural, authentic openings that build trust gradually "
        "rather than aggressive shock-value hooks."
    ),
}

_VIDEO_TYPE_HINTS: dict[str, str] = {
    "auto":           "",  # no bias — let model decide
    "viral":          "Favour highly shareable moments: surprising reveals, relatable humour, or strong emotional peaks that viewers want to share.",
    "storytelling":   "Favour segments with a clear narrative arc — setup, tension, and payoff — that tell a self-contained mini-story.",
    "educational":    "Favour segments that teach something concrete: clear explanations, step-by-step logic, or actionable insights.",
    "emotional":      "Favour emotionally resonant moments: genuine reactions, vulnerability, triumph, or heartfelt exchanges.",
    "high_retention": "Favour segments that maintain consistent engagement from start to finish — avoid slow buildups or trailing-off endings.",
}


def _build_editorial_hint(payload: Any) -> str:
    """Translate hook_strength + video_type payload fields into a prompt hint.

    Returns an empty string when both fields are at their default/neutral
    values so the prompt is byte-for-byte identical to the baseline.
    The hint is ADVISORY only — it never requests new JSON fields and does
    not affect the parser, validation gates, or output dataclass shape.

    Sprint 3.3: also appends the active CreatorContext's prompt hint (if
    any) so the AI Director sees channel persona signals before
    selecting segments. The CreatorContext fetch is wrapped in try/except
    so a transient failure in the AI-context layer cannot crash the LLM
    stage — Sacred Contract #3 (AI modules return None on failure, never
    raise) is preserved end-to-end.
    """
    parts: list[str] = []

    hook = (getattr(payload, "hook_strength", None) or "").strip().lower()
    h = _HOOK_HINTS.get(hook, "")
    if h:
        parts.append(h)

    vtype = (getattr(payload, "video_type", None) or "").strip().lower()
    v = _VIDEO_TYPE_HINTS.get(vtype, "")
    if v:
        parts.append(v)

    # Sprint 3.3 — append CreatorContext hint. Local import keeps this
    # module decoupled from the DB at import time (matches the same
    # pattern used by the builder itself). The builder already returns
    # None on any internal error; we belt-and-braces here so even a
    # raised import failure can't propagate.
    _channel_code = (getattr(payload, "channel_code", "") or "").strip()
    try:
        from app.features.render.ai.context.builder import build_creator_context
        creator_ctx = build_creator_context(channel_code=_channel_code)
        if creator_ctx is not None:
            creator_hint = creator_ctx.to_prompt_hint()
            if creator_hint:
                parts.append(creator_hint)
    except Exception as exc:
        logger.warning("llm_stage: creator context hint append failed: %s", exc)

    # Phase D — append feedback signals so AI personalises clip selection
    # based on what this channel's viewers have liked/disliked before.
    # Skipped silently when channel_code is empty or feedback table is empty.
    # Sacred Contract #3: entire block is wrapped — never raises.
    if _channel_code:
        try:
            from app.db.feedback_repo import get_feedback_signals
            from app.features.render.ai.feedback.signals import build_signals
            _raw = get_feedback_signals(channel_code=_channel_code)
            _signals = build_signals(_raw)
            _fhint = _signals.to_prompt_hint()
            if _fhint:
                parts.append(_fhint)
        except Exception as exc:
            logger.warning("llm_stage: feedback signals append failed: %s", exc)

    return " ".join(parts)


def _resolve_api_key(payload: Any, provider: str) -> tuple[str, str]:
    """Return (api_key, source_label) for the given provider.

    Resolution order per provider:
      1. Per-provider payload field (e.g. payload.gemini_api_key)
      2. Generic payload field (payload.ai_cloud_api_key) — UI sends the active provider's key here
      3. Server env var (GEMINI_API_KEY / GROQ_API_KEY / etc.)
    """
    _per_provider_attr = {
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "claude": "claude_api_key",
    }.get(provider, "")
    _per_provider_env = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "CLAUDE_API_KEY",
    }.get(provider, "")

    if _per_provider_attr:
        _key = (getattr(payload, _per_provider_attr, "") or "").strip()
        if _key:
            return _key, f"payload.{_per_provider_attr}"

    _generic = (getattr(payload, "ai_cloud_api_key", "") or "").strip()
    if _generic:
        return _generic, "payload.ai_cloud_api_key"

    if _per_provider_env:
        import os
        _env = (os.getenv(_per_provider_env) or "").strip()
        if _env:
            return _env, f"env.{_per_provider_env}"

    return "", "none"

