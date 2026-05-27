"""
groq_provider.py — Groq cloud analyzer implementation.

Uses llama-3.1-8b-instant by default (free tier: 500K tokens/day).
Falls back to openai-compatible endpoint if the groq SDK is not installed.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.analysis.cloud.base import CloudAnalyzerBase
from app.ai.analysis.cloud.prompt_builder import get_system_prompt

logger = logging.getLogger("app.ai.analysis.cloud.groq")

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

try:
    from groq import Groq as _GroqClient
    _GROQ_SDK_AVAILABLE = True
except ImportError:
    _GROQ_SDK_AVAILABLE = False

try:
    import openai as _openai
    _OPENAI_COMPAT_AVAILABLE = True
except ImportError:
    _OPENAI_COMPAT_AVAILABLE = False


class GroqProvider(CloudAnalyzerBase):
    DEFAULT_MODEL = "llama-3.1-8b-instant"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self._api_key = api_key
        self._model = model or self.DEFAULT_MODEL

    @property
    def provider_name(self) -> str:
        return "groq"

    def _call_api(self, prompt: str) -> Optional[str]:
        # Try native groq SDK first
        if _GROQ_SDK_AVAILABLE:
            try:
                client = _GroqClient(api_key=self._api_key)
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": get_system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                )
                return resp.choices[0].message.content
            except Exception as exc:
                logger.debug("groq_native_failed model=%s: %s", self._model, exc)

        # Fallback: Groq is OpenAI-compatible — use openai SDK with custom base_url
        if _OPENAI_COMPAT_AVAILABLE:
            try:
                client = _openai.OpenAI(api_key=self._api_key, base_url=_GROQ_BASE_URL)
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": get_system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                )
                return resp.choices[0].message.content
            except Exception as exc:
                logger.debug("groq_compat_failed model=%s: %s", self._model, exc)

        logger.debug("groq_no_sdk_available")
        return None
