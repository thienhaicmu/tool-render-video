from app.ai.analysis.signals import (
    AnalysisSignals, ClipSignal, EmotionSignal, SubtitleHints, CameraHints,
)
from app.ai.analysis.contract import AnalyzerContract
from app.ai.analysis.hybrid_analyzer import HybridAnalyzer
from app.ai.analysis.local_analyzer import LocalAnalyzer
from app.ai.analysis.merger import merge

# Groq cloud segment selection (Phase A)
try:
    from app.ai.analysis.groq import select_segments, GroqSegment
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

__all__ = [
    # Local analysis
    "AnalysisSignals", "ClipSignal", "EmotionSignal", "SubtitleHints", "CameraHints",
    "AnalyzerContract", "HybridAnalyzer", "LocalAnalyzer", "merge",
    # Groq cloud selection
    "select_segments", "GroqSegment",
]
