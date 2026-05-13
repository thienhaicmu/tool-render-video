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


def get_ai_dependency_status() -> dict:
    """Return availability of all optional AI libraries."""
    return {
        "sentence_transformers": has_sentence_transformers(),
        "faiss": has_faiss(),
        "librosa": has_librosa(),
        "mediapipe": has_mediapipe(),
        "faster_whisper": has_faster_whisper(),
        "whisperx": has_whisperx(),
    }
