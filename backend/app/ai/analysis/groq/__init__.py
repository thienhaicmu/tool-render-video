"""
ai.analysis.groq — SRT-based segment selection via Groq LLM.

Distinct from ai.analysis.cloud (which analyzes video content signals).
This module takes a full SRT transcript and returns a ranked list of
GroqSegment objects — time ranges Groq judged as best for short clips.

Public surface:
    from app.ai.analysis.groq import select_segments, GroqSegment
"""
from app.ai.analysis.groq.parser import GroqSegment
from app.ai.analysis.groq.client import select_segments

__all__ = ["select_segments", "GroqSegment"]
