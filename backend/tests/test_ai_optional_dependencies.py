"""
test_ai_optional_dependencies.py

Verifies that all AI sub-package modules load safely and degrade
gracefully when optional libraries (sentence-transformers, faiss,
librosa, mediapipe, faster-whisper, whisperx, deepfilternet) are not installed.

No GPU required. No API keys required.
"""
from __future__ import annotations

import math


# ─────────────────────────────────────────────────────────────────────────────
# 1. Importing dependencies module does not raise
# ─────────────────────────────────────────────────────────────────────────────

def test_import_dependencies_does_not_raise():
    from app.ai import dependencies  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_ai_dependency_status returns all expected keys
# ─────────────────────────────────────────────────────────────────────────────

def test_get_ai_dependency_status_keys():
    from app.ai.dependencies import get_ai_dependency_status

    status = get_ai_dependency_status()
    expected_keys = {
        "sentence_transformers",
        "faiss",
        "librosa",
        "mediapipe",
        "faster_whisper",
        "whisperx",
        "deepfilternet",
    }
    assert expected_keys == set(status.keys()), f"Missing keys: {expected_keys - set(status.keys())}"
    for key, val in status.items():
        assert isinstance(val, bool), f"{key} should be bool, got {type(val)}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hook analyzer works without sentence-transformers
# ─────────────────────────────────────────────────────────────────────────────

def test_hook_analyzer_works_without_sentence_transformers():
    from app.ai.analyzers.hook_analyzer import score_hook_text

    score = score_hook_text("hello world")
    assert isinstance(score, float), "score_hook_text must return float"
    assert 0.0 <= score <= 100.0, f"Score out of range: {score}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Viral hook phrase scores higher than generic phrase
# ─────────────────────────────────────────────────────────────────────────────

def test_hook_phrase_scores_higher_than_generic():
    from app.ai.analyzers.hook_analyzer import score_hook_text

    viral_score = score_hook_text("nobody tells you this")
    generic_score = score_hook_text("hello world")
    assert viral_score > generic_score, (
        f"Expected viral score {viral_score} > generic score {generic_score}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. embed_text returns None or list[float]
# ─────────────────────────────────────────────────────────────────────────────

def test_embed_text_returns_none_or_list():
    from app.ai.rag.embeddings import embed_text, is_embedding_available

    result = embed_text("test sentence")
    if is_embedding_available():
        assert isinstance(result, list), "Expected list[float] when embedding available"
        assert all(isinstance(v, float) for v in result)
    else:
        assert result is None, "Expected None when sentence-transformers not installed"


# ─────────────────────────────────────────────────────────────────────────────
# 6. LocalVectorStore works without FAISS (cosine fallback)
# ─────────────────────────────────────────────────────────────────────────────

def test_local_vector_store_fallback():
    from app.ai.rag.vector_store import LocalVectorStore

    store = LocalVectorStore()
    assert store.count() == 0

    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    v3 = [0.9, 0.1, 0.0]

    store.add("doc-1", "first document", v1, {"tag": "a"})
    store.add("doc-2", "second document", v2, {"tag": "b"})
    store.add("doc-3", "third document", v3, {"tag": "c"})

    assert store.count() == 3

    results = store.search(v1, top_k=2)
    assert len(results) == 2

    first = results[0]
    assert first["id"] in {"doc-1", "doc-3"}, "Top result should be closest to v1"
    assert 0.0 <= first["score"] <= 1.0, f"Score out of range: {first['score']}"
    assert "text" in first
    assert "metadata" in first


def test_local_vector_store_empty_search():
    from app.ai.rag.vector_store import LocalVectorStore

    store = LocalVectorStore()
    results = store.search([1.0, 0.0], top_k=5)
    assert results == []


def test_local_vector_store_result_format():
    from app.ai.rag.vector_store import LocalVectorStore

    store = LocalVectorStore()
    store.add("x", "some text", [0.5, 0.5], {"key": "val"})
    results = store.search([0.5, 0.5], top_k=1)

    assert len(results) == 1
    r = results[0]
    assert r["id"] == "x"
    assert r["text"] == "some text"
    assert r["metadata"] == {"key": "val"}
    assert isinstance(r["score"], float)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Beat analyzer returns safe unavailable result when librosa missing
# ─────────────────────────────────────────────────────────────────────────────

def test_beat_analyzer_safe_when_librosa_missing():
    from app.ai.analyzers.beat_analyzer import analyze_beats, is_beat_analysis_available

    result = analyze_beats("nonexistent_file.wav")

    assert "available" in result
    assert "bpm" in result
    assert "beats" in result
    assert "warnings" in result
    assert isinstance(result["beats"], list)
    assert isinstance(result["warnings"], list)

    if not is_beat_analysis_available():
        assert result["available"] is False
        assert "librosa_not_installed" in result["warnings"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. Vision analyzer returns safe status when mediapipe missing
# ─────────────────────────────────────────────────────────────────────────────

def test_vision_analyzer_safe_when_mediapipe_missing():
    from app.ai.analyzers.vision_analyzer import (
        get_vision_dependency_status,
        is_vision_analysis_available,
    )

    status = get_vision_dependency_status()

    assert "available" in status
    assert "warnings" in status
    assert isinstance(status["warnings"], list)

    if not is_vision_analysis_available():
        assert status["available"] is False
        assert "mediapipe_not_installed" in status["warnings"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. is_semantic_hook_available and score_hook_text_semantic are safe
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_hook_safe_without_library():
    from app.ai.analyzers.hook_analyzer import (
        is_semantic_hook_available,
        score_hook_text_semantic,
    )

    available = is_semantic_hook_available()
    assert isinstance(available, bool)

    result = score_hook_text_semantic("nobody tells you this")
    if available:
        assert result is not None
        assert 0.0 <= result <= 100.0
    else:
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 10. All dependency checks return bool and never raise
# ─────────────────────────────────────────────────────────────────────────────

def test_all_dependency_checks_return_bool():
    from app.ai.dependencies import (
        has_faiss,
        has_faster_whisper,
        has_deepfilternet,
        has_librosa,
        has_mediapipe,
        has_sentence_transformers,
        has_whisperx,
    )

    for fn in (
        has_sentence_transformers,
        has_faiss,
        has_librosa,
        has_mediapipe,
        has_faster_whisper,
        has_whisperx,
        has_deepfilternet,
    ):
        result = fn()
        assert isinstance(result, bool), f"{fn.__name__} must return bool"


def test_has_whisperx_does_not_import_whisperx(monkeypatch):
    import sys
    from app.ai import dependencies

    sys.modules.pop("whisperx", None)

    def fake_find_spec(name):
        assert name == "whisperx"
        return None

    monkeypatch.setattr(dependencies.importlib.util, "find_spec", fake_find_spec)

    assert dependencies.has_whisperx() is False
    assert "whisperx" not in sys.modules


def test_has_deepfilternet_does_not_import_ml_packages(monkeypatch):
    import sys
    from app.ai import dependencies

    for name in ("deepfilternet", "torch", "torchaudio"):
        sys.modules.pop(name, None)

    def fake_find_spec(name):
        assert name == "deepfilternet"
        return None

    monkeypatch.setattr(dependencies.importlib.util, "find_spec", fake_find_spec)

    assert dependencies.has_deepfilternet() is False
    assert "deepfilternet" not in sys.modules
    assert "torch" not in sys.modules
    assert "torchaudio" not in sys.modules
