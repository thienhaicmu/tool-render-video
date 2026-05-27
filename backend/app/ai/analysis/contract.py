"""
contract.py — Abstract base class all analyzers must implement.

Both LocalAnalyzer and cloud providers satisfy this interface.
The AI Director talks only to this contract — never to concrete implementations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.ai.analysis.signals import AnalysisSignals


class AnalyzerContract(ABC):
    @abstractmethod
    def analyze(
        self,
        chunks: list[dict],
        context: dict,
    ) -> Optional[AnalysisSignals]:
        """Analyze transcript chunks and return signals.

        Returns AnalysisSignals on success, None on failure.
        MUST NOT raise under any circumstances — Contract 3.
        """
        ...
