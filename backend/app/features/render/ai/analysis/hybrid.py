"""
hybrid_analyzer.py — Orchestrates local + cloud analyzers with safe fallback.

Always returns AnalysisSignals — never raises, never returns None.
If both analyzers fail, returns empty signals so callers degrade gracefully.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.features.render.ai.analysis.contract import AnalyzerContract
from app.features.render.ai.analysis.signals import AnalysisSignals, EmotionSignal
from app.features.render.ai.analysis.merger import merge

logger = logging.getLogger("app.ai.analysis.hybrid")


def _empty_signals() -> AnalysisSignals:
    return AnalysisSignals(
        clip_signals=[],
        emotion=EmotionSignal(),
        subtitle_hints=None,
        camera_hints=None,
        confidence=0.0,
        source="local",
        warnings=["analyzer_unavailable"],
    )


class HybridAnalyzer:
    """Runs LocalAnalyzer always; CloudAnalyzer optionally; merges results.

    Usage:
        analyzer = HybridAnalyzer(local=LocalAnalyzer(), cloud=GroqProvider(...))
        signals = analyzer.analyze(chunks, context)

    To use local-only:
        analyzer = HybridAnalyzer(local=LocalAnalyzer())
    """

    def __init__(
        self,
        local: AnalyzerContract,
        cloud: Optional[AnalyzerContract] = None,
    ) -> None:
        self._local = local
        self._cloud = cloud

    def analyze(self, chunks: list[dict], context: dict) -> AnalysisSignals:
        """Always returns AnalysisSignals. Never raises."""
        local_result = self._run_safe(self._local, chunks, context, "local")
        if local_result is None:
            local_result = _empty_signals()

        if self._cloud is None:
            return local_result

        cloud_result = self._run_safe(self._cloud, chunks, context, "cloud")
        merged = merge(local_result, cloud_result)
        logger.debug(
            "hybrid_analyzer_done source=%s confidence=%.2f clips=%d",
            merged.source, merged.confidence, len(merged.clip_signals),
        )
        return merged

    def _run_safe(
        self,
        analyzer: AnalyzerContract,
        chunks: list[dict],
        context: dict,
        label: str,
    ) -> Optional[AnalysisSignals]:
        try:
            return analyzer.analyze(chunks, context)
        except Exception as exc:
            logger.debug("hybrid_%s_failed: %s", label, exc)
            return None

