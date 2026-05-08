"""
vision_analyzer.py — Optional computer vision scaffolding via mediapipe.

This phase is dependency-ready only — no frame processing is implemented.
No hard import at module level.

Public API:
    is_vision_analysis_available() -> bool
    get_vision_dependency_status() -> dict
"""
from __future__ import annotations

from app.ai.dependencies import has_mediapipe


def is_vision_analysis_available() -> bool:
    return has_mediapipe()


def get_vision_dependency_status() -> dict:
    available = has_mediapipe()
    return {
        "available": available,
        "backend": "mediapipe" if available else None,
        "features": ["pose", "face", "hands"] if available else [],
        "warnings": [] if available else ["mediapipe_not_installed"],
    }
