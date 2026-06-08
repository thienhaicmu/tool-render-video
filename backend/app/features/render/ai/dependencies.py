"""
dependencies.py — Centralized optional AI dependency detector.

Uses importlib.util.find_spec so heavy libraries are never imported
just to check availability. All functions return clean booleans and
never raise.
"""
from __future__ import annotations

import importlib.util


def has_sentence_transformers() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def has_faiss() -> bool:
    return importlib.util.find_spec("faiss") is not None


def has_librosa() -> bool:
    return importlib.util.find_spec("librosa") is not None


def has_mediapipe() -> bool:
    return importlib.util.find_spec("mediapipe") is not None


def has_faster_whisper() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def has_whisperx() -> bool:
    return importlib.util.find_spec("whisperx") is not None


def has_deepfilternet() -> bool:
    return importlib.util.find_spec("deepfilternet") is not None


def has_xtts() -> bool:
    """Check if Coqui TTS (XTTS v2) package is available."""
    return importlib.util.find_spec("TTS") is not None


def motion_crop_quality() -> str:
    """Report the effective motion-crop quality tier.

    Closes audit FINDING-T01 (2026-06-06). The motion-aware crop pipeline
    prefers MediaPipe (face + pose detection) but silently falls back to
    OpenCV Haar cascade when MediaPipe is absent. The Haar fallback is
    materially worse — face-only, no pose anchor — and the user has no
    way to know without inspecting render output.

    Returns:
        "high"     — MediaPipe is installed; subject tracking uses face +
                     pose, eye-anchor crop framing available.
        "low"      — MediaPipe absent; Haar cascade fallback active.
                     Suggests installing AI extras for best results.
        "unknown"  — Probe failed for an unexpected reason (defensive).
    """
    try:
        return "high" if has_mediapipe() else "low"
    except Exception:  # pragma: no cover — defensive
        return "unknown"


def get_ai_dependency_status() -> dict:
    """Return availability of all optional AI libraries."""
    return {
        "sentence_transformers": has_sentence_transformers(),
        "faiss": has_faiss(),
        "librosa": has_librosa(),
        "mediapipe": has_mediapipe(),
        "faster_whisper": has_faster_whisper(),
        "whisperx": has_whisperx(),
        "deepfilternet": has_deepfilternet(),
        "xtts": has_xtts(),
        # Audit FINDING-T01 closure — surfaces the silent-degrade signal.
        "motion_crop_quality": motion_crop_quality(),
    }
