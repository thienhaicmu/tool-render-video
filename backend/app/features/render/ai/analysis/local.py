"""
local_analyzer.py â€” Wraps existing local analyzers into the AnalyzerContract.

Does NOT modify hook_analyzer.py or emotion_analyzer.py.
Bridges their outputs into AnalysisSignals schema.
Always succeeds (catches all exceptions â†’ returns None for HybridAnalyzer fallback).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.features.render.ai.analysis.contract import AnalyzerContract
from app.features.render.ai.analysis.signals import AnalysisSignals, ClipSignal, EmotionSignal

try:
    from app.features.render.ai.analyzers.emotion_analyzer import analyze_pacing_emotion as _analyze_emotion
    _EMOTION_AVAILABLE = True
except ImportError:
    _EMOTION_AVAILABLE = False
    def _analyze_emotion(*a, **kw) -> dict:  # type: ignore[misc]
        return {"dominant": "neutral", "score": 0.0, "signals": {}, "warnings": []}

try:
    from app.features.render.ai.analyzers.hook_analyzer import (
        score_hook_text as _hook_score,
        score_hook_intelligence as _hook_intel,
        get_opening_window_text as _opening_text,
        detect_hook_type as _hook_type,
    )
    _HOOK_AVAILABLE = True
except ImportError:
    _HOOK_AVAILABLE = False
    def _hook_score(text: str) -> float: return 50.0           # type: ignore[misc]
    def _hook_intel(text: str, goal: str = "") -> float: return 0.0  # type: ignore[misc]
    def _opening_text(chunks, start, *a, **kw) -> str: return ""  # type: ignore[misc]
    def _hook_type(text: str) -> str: return "none"            # type: ignore[misc]

logger = logging.getLogger("app.ai.analysis.local")

# Sample up to this many windows when scoring clips locally.
# Mirrors clip_selector.py's step = max(1, len(chunks) // 12).
_SAMPLE_DIVISOR = 12


class LocalAnalyzer(AnalyzerContract):
    """Runs existing local analyzers and packages results as AnalysisSignals."""

    def analyze(self, chunks: list[dict], context: dict) -> Optional[AnalysisSignals]:
        try:
            emotion = self._build_emotion(chunks)
            clip_signals = self._score_clips(chunks, context)
            return AnalysisSignals(
                clip_signals=clip_signals,
                emotion=emotion,
                subtitle_hints=None,
                camera_hints=None,
                confidence=0.60,
                source="local",
                warnings=[],
            )
        except Exception as exc:
            logger.debug("local_analyzer_failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_emotion(self, chunks: list[dict]) -> EmotionSignal:
        try:
            raw = _analyze_emotion(chunks)
            return EmotionSignal(
                dominant=str(raw.get("dominant", "neutral")),
                score=float(raw.get("score", 0.0)),
                source="local",
            )
        except Exception:
            return EmotionSignal()

    def _score_clips(self, chunks: list[dict], context: dict) -> list[ClipSignal]:
        if not chunks or not _HOOK_AVAILABLE:
            return []
        goal = str(context.get("goal", ""))
        step = max(1, len(chunks) // _SAMPLE_DIVISOR)
        signals: list[ClipSignal] = []
        for i in range(0, len(chunks), step):
            try:
                win = chunks[i: i + step * 2]
                if not win:
                    continue
                start = float(chunks[i].get("start") or 0.0)
                end = float(win[-1].get("end") or start)
                opening = _opening_text(win, start)
                hook_s = min(100.0, _hook_score(opening) + _hook_intel(opening, goal))
                h_type = _hook_type(opening) if opening else "none"
                signals.append(ClipSignal(
                    start=start,
                    end=end,
                    hook_score=round(hook_s, 2),
                    hook_type=h_type,
                    relevance_score=round(hook_s, 2),
                    reason="",
                    source="local",
                ))
            except Exception:
                continue
        return signals

