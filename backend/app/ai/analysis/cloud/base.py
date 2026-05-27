"""
base.py — Abstract cloud analyzer base class.

All cloud provider implementations (OpenAI, Groq, ...) extend this.
Handles the analyze() lifecycle: build prompt → call API → parse response.
Subclasses only implement _call_api().
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.analysis.contract import AnalyzerContract
from app.ai.analysis.signals import AnalysisSignals
from app.ai.analysis.cloud.prompt_builder import build_prompt
from app.ai.analysis.cloud.response_parser import parse_response

logger = logging.getLogger("app.ai.analysis.cloud")


class CloudAnalyzerBase(AnalyzerContract):
    """Base for all cloud analyzer providers.

    Subclass and implement:
        _call_api(prompt: str) -> Optional[str]
        provider_name -> str
    """

    def analyze(self, chunks: list[dict], context: dict) -> Optional[AnalysisSignals]:
        try:
            prompt = build_prompt(chunks, context)
            raw = self._call_api(prompt)
            if not raw:
                return None
            result = parse_response(raw)
            if result:
                logger.debug(
                    "cloud_analyzer_ok provider=%s clips=%d confidence=%.2f",
                    self.provider_name, len(result.clip_signals), result.confidence,
                )
            return result
        except Exception as exc:
            logger.debug("cloud_analyzer_failed provider=%s: %s", self.provider_name, exc)
            return None

    def _call_api(self, prompt: str) -> Optional[str]:
        raise NotImplementedError(f"{self.__class__.__name__} must implement _call_api()")

    @property
    def provider_name(self) -> str:
        return "base"
