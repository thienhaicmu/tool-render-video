"""
openai_provider.py — OpenAI cloud analyzer implementation.

Uses gpt-4o-mini by default (~$0.0003 per 10-minute video transcript).
Lazy-imports the openai SDK so the module loads without it installed.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.features.render.ai.analysis.cloud.base import CloudAnalyzerBase
from app.features.render.ai.analysis.cloud.prompt_builder import get_system_prompt

logger = logging.getLogger("app.ai.analysis.cloud.openai")

try:
    import openai as _openai
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


class OpenAIProvider(CloudAnalyzerBase):
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self._api_key = api_key
        self._model = model or self.DEFAULT_MODEL

    @property
    def provider_name(self) -> str:
        return "openai"

    def _call_api(self, prompt: str) -> Optional[str]:
        if not _OPENAI_AVAILABLE:
            logger.debug("openai_sdk_not_installed")
            return None
        try:
            client = _openai.OpenAI(api_key=self._api_key)
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1024,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content
        except Exception as exc:
            logger.debug("openai_call_failed model=%s: %s", self._model, exc)
            return None
