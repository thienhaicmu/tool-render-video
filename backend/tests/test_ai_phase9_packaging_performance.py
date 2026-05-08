"""
test_ai_phase9_packaging_performance.py

Phase 9 — Packaging + Performance Stabilization.

Verifies:
- diagnostics module is safe to import
- get_ai_runtime_diagnostics() never raises and returns expected shape
- dependency status has all expected keys
- embeddings module does not load model at import time
- embed_text/embed_texts return None safely when dependency missing
- vector store health() works in fallback mode
- SQLite health() works on temp DB
- prune() removes oldest rows and keeps embeddings consistent
- memory health/compact never raise
- no API key required
- no GPU required

No sentence-transformers required.
No faiss required.
No real rendering required.
No Electron required.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 1. Importing diagnostics module does not raise / does not load heavy libs
# ─────────────────────────────────────────────────────────────────────────────

def test_import_diagnostics_does_not_raise():
    from app.ai import diagnostics  # noqa: F401


def test_diagnostics_import_does_not_load_sentence_transformers():
    """After importing diagnostics, sentence_transformers must not appear in
    sys.modules unless it was already present before this test ran."""
    heavy_libs = ["sentence_transformers", "faiss", "mediapipe", "faster_whisper"]
    pre_loaded = {lib: lib in sys.modules for lib in heavy_libs}

    import importlib
    import app.ai.diagnostics
    importlib.reload(app.ai.diagnostics)

    for lib in heavy_libs:
        if not pre_loaded[lib]:
            assert lib not in sys.modules, (
                f"diagnostics import caused {lib} to load at module level"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_ai_runtime_diagnostics() never raises and has expected shape
# ─────────────────────────────────────────────────────────────────────────────

def test_diagnostics_never_raises():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    assert isinstance(result, dict)


def test_diagnostics_has_required_top_level_keys():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    for key in ("dependencies", "startup_safe", "embedding_available",
                "vector_store", "memory", "warnings"):
        assert key in result, f"Missing top-level key: {key}"


def test_diagnostics_startup_safe_is_true():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    assert result["startup_safe"] is True


def test_diagnostics_embedding_available_is_bool():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    assert isinstance(result["embedding_available"], bool)


def test_diagnostics_vector_store_shape():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    vs = result["vector_store"]
    assert isinstance(vs, dict)
    assert "faiss_available" in vs
    assert "fallback_mode" in vs
    assert isinstance(vs["faiss_available"], bool)
    assert isinstance(vs["fallback_mode"], bool)


def test_diagnostics_memory_shape():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    mem = result["memory"]
    assert isinstance(mem, dict)
    assert "sqlite_available" in mem
    assert "warnings" in mem
    assert isinstance(mem["warnings"], list)


def test_diagnostics_warnings_is_list():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    assert isinstance(result["warnings"], list)


def test_diagnostics_dependencies_shape():
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    result = get_ai_runtime_diagnostics()
    deps = result["dependencies"]
    assert isinstance(deps, dict)
    for key in ("sentence_transformers", "faiss", "librosa", "mediapipe", "faster_whisper"):
        assert key in deps, f"Missing dependency key in diagnostics: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Dependency status has expected keys and all return bool
# ─────────────────────────────────────────────────────────────────────────────

def test_dependency_status_has_expected_keys():
    from app.ai.dependencies import get_ai_dependency_status
    status = get_ai_dependency_status()
    for key in ("sentence_transformers", "faiss", "librosa", "mediapipe", "faster_whisper"):
        assert key in status, f"Missing dependency key: {key}"
        assert isinstance(status[key], bool), f"{key} must be bool"


def test_dependency_detectors_never_raise():
    from app.ai.dependencies import (
        has_sentence_transformers, has_faiss, has_librosa,
        has_mediapipe, has_faster_whisper,
    )
    for fn in (has_sentence_transformers, has_faiss, has_librosa,
               has_mediapipe, has_faster_whisper):
        result = fn()
        assert isinstance(result, bool), f"{fn.__name__} must return bool, got {type(result)}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Embeddings module does not load model at import time
# ─────────────────────────────────────────────────────────────────────────────

def test_embeddings_model_is_none_at_import():
    """After a fresh module reload, _model must be None — lazy load guarantee.

    We reload (not just re-import) so prior test runs that already triggered
    _load_model() don't pollute this assertion.
    """
    import importlib
    import app.ai.rag.embeddings as emb
    importlib.reload(emb)
    assert emb._model is None, (
        "_model must be None after reload (lazy-load guarantee: model only loads on embed call)"
    )


def test_embeddings_reload_does_not_trigger_model_load():
    """A second reload must also leave _model as None — reload itself must not call _load_model()."""
    import importlib
    import app.ai.rag.embeddings as emb
    importlib.reload(emb)
    assert emb._model is None, "_model must be None after reload (no auto-load)"


# ─────────────────────────────────────────────────────────────────────────────
# 5. embed_text / embed_texts return None safely when dependency missing
# ─────────────────────────────────────────────────────────────────────────────

def test_embed_text_returns_none_or_list():
    from app.ai.rag.embeddings import embed_text, is_embedding_available
    result = embed_text("hello world")
    if is_embedding_available():
        assert isinstance(result, list), "Expected list[float] when embeddings available"
        assert all(isinstance(v, float) for v in result)
    else:
        assert result is None, "Expected None when sentence-transformers not installed"


def test_embed_texts_returns_none_or_list():
    from app.ai.rag.embeddings import embed_texts, is_embedding_available
    result = embed_texts(["hello", "world"])
    if is_embedding_available():
        assert isinstance(result, list)
        assert len(result) == 2
    else:
        assert result is None


def test_embed_text_empty_string_safe():
    from app.ai.rag.embeddings import embed_text
    result = embed_text("")
    assert result is None or isinstance(result, list)


def test_embed_text_none_input_safe():
    from app.ai.rag.embeddings import embed_text
    # embed_text expects str — passing None should not raise (internally cast)
    try:
        result = embed_text(None)  # type: ignore
        assert result is None or isinstance(result, list)
    except Exception as exc:
        raise AssertionError(f"embed_text(None) raised: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# 6. Vector store health() works in fallback mode (no FAISS required)
# ─────────────────────────────────────────────────────────────────────────────

def test_vector_store_health_empty():
    from app.ai.rag.vector_store import LocalVectorStore
    store = LocalVectorStore()
    h = store.health()
    assert isinstance(h, dict)
    for key in ("count", "faiss_available", "fallback_mode", "warnings"):
        assert key in h, f"Missing health key: {key}"
    assert h["count"] == 0
    assert isinstance(h["faiss_available"], bool)
    assert isinstance(h["fallback_mode"], bool)
    assert isinstance(h["warnings"], list)


def test_vector_store_health_with_entries():
    from app.ai.rag.vector_store import LocalVectorStore
    store = LocalVectorStore()
    store.add("a", "text a", [1.0, 0.0])
    store.add("b", "text b", [0.0, 1.0])
    h = store.health()
    assert h["count"] == 2


def test_vector_store_health_never_raises_on_corruption():
    from app.ai.rag.vector_store import LocalVectorStore
    store = LocalVectorStore()
    # Forcibly corrupt internal state
    store._entries = None  # type: ignore
    h = store.health()
    assert isinstance(h, dict)
    assert "warnings" in h
    # Must not raise even on corrupted state


# ─────────────────────────────────────────────────────────────────────────────
# 7. SQLite health() works on temp DB
# ─────────────────────────────────────────────────────────────────────────────

def test_sqlite_health_on_initialized_db():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_ai.db"
        store = SQLiteMemoryStore(db_path=db_path)
        store.initialize()
        h = store.health()
        assert isinstance(h, dict)
        assert h.get("sqlite_available") is True
        assert h.get("count") == 0
        assert isinstance(h.get("warnings"), list)


def test_sqlite_health_before_init_does_not_raise():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "nonexistent.db"
        store = SQLiteMemoryStore(db_path=db_path)
        # Not initialized — must not raise
        h = store.health()
        assert isinstance(h, dict)
        assert "sqlite_available" in h
        assert "warnings" in h


def test_sqlite_vacuum_on_initialized_db():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_vac.db"
        store = SQLiteMemoryStore(db_path=db_path)
        store.initialize()
        result = store.vacuum()
        assert isinstance(result, bool)
        assert result is True


def test_sqlite_vacuum_before_init_returns_false():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteMemoryStore(db_path=Path(tmp) / "x.db")
        result = store.vacuum()
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# 8. prune() removes oldest rows and keeps embeddings consistent
# ─────────────────────────────────────────────────────────────────────────────

def _make_memory(idx: int):
    from app.ai.rag.memory_schema import RenderMemory
    return RenderMemory(
        id=f"mem-{idx:04d}",
        text=f"render memory number {idx}",
        market="US",
        mode="viral_short",
        status="completed",
    )


def test_prune_removes_oldest_rows():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_prune.db"
        store = SQLiteMemoryStore(db_path=db_path)
        store.initialize()

        for i in range(20):
            store.add_memory(_make_memory(i))

        assert store.count() == 20

        deleted = store.prune(max_rows=10)
        assert deleted == 10
        assert store.count() == 10


def test_prune_noop_when_under_limit():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_noop.db"
        store = SQLiteMemoryStore(db_path=db_path)
        store.initialize()

        for i in range(5):
            store.add_memory(_make_memory(i))

        deleted = store.prune(max_rows=100)
        assert deleted == 0
        assert store.count() == 5


def test_prune_safe_on_empty_db():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_empty.db"
        store = SQLiteMemoryStore(db_path=db_path)
        store.initialize()
        deleted = store.prune(max_rows=5000)
        assert deleted == 0


def test_prune_before_init_returns_zero():
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        store = SQLiteMemoryStore(db_path=Path(tmp) / "noinit.db")
        result = store.prune(max_rows=100)
        assert result == 0


def test_prune_removes_matching_embeddings():
    """Pruned memories must also have their embeddings deleted."""
    import json
    from app.ai.rag.sqlite_store import SQLiteMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_embed_prune.db"
        store = SQLiteMemoryStore(db_path=db_path)
        store.initialize()

        # Add memories with fake embeddings
        for i in range(10):
            mem = _make_memory(i)
            vec = [float(i), 0.0, 0.0]
            store.add_memory(mem, vector=vec)

        # Verify embeddings were stored
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        count_before = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()
        assert count_before == 10

        # Prune to 5
        store.prune(max_rows=5)
        assert store.count() == 5

        # Embeddings for pruned memories must be gone
        conn = sqlite3.connect(str(db_path))
        count_after = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()
        assert count_after == 5, f"Expected 5 embeddings remaining, got {count_after}"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Memory health / compact never raise
# ─────────────────────────────────────────────────────────────────────────────

def test_memory_health_no_sqlite():
    from app.ai.rag.memory_store import LocalMemoryStore
    store = LocalMemoryStore()
    h = store.get_memory_health()
    assert isinstance(h, dict)
    for key in ("vector_count", "faiss_available", "fallback_mode",
                "sqlite_available", "hydrated", "warnings"):
        assert key in h, f"Missing memory health key: {key}"
    assert isinstance(h["warnings"], list)


def test_memory_health_with_sqlite():
    from app.ai.rag.memory_store import LocalMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "mem_health.db"
        store = LocalMemoryStore()
        store.initialize_with_sqlite(db_path=db_path)
        h = store.get_memory_health()
        assert isinstance(h, dict)
        assert "sqlite_count" in h
        assert "hydrated" in h


def test_memory_health_never_raises():
    from app.ai.rag.memory_store import LocalMemoryStore
    store = LocalMemoryStore()
    # Force _store to a broken state
    store._store = None  # type: ignore
    h = store.get_memory_health()
    assert isinstance(h, dict)
    assert "warnings" in h


def test_compact_memory_no_sqlite():
    from app.ai.rag.memory_store import LocalMemoryStore
    store = LocalMemoryStore()
    result = store.compact_memory()
    assert isinstance(result, dict)
    assert "pruned" in result
    assert result["pruned"] == 0


def test_compact_memory_with_sqlite():
    from app.ai.rag.memory_store import LocalMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "compact.db"
        store = LocalMemoryStore()
        store.initialize_with_sqlite(db_path=db_path)
        result = store.compact_memory(max_rows=5000)
        assert isinstance(result, dict)
        assert result["pruned"] == 0
        assert "vacuumed" in result
        assert "message" in result


def test_compact_memory_prunes_then_vacuums():
    from app.ai.rag.memory_store import LocalMemoryStore
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "compact2.db"
        store = LocalMemoryStore()
        store.initialize_with_sqlite(db_path=db_path)

        # Add memories via sqlite directly
        from app.ai.rag.sqlite_store import SQLiteMemoryStore
        sq = SQLiteMemoryStore(db_path=db_path)
        sq.initialize()
        for i in range(15):
            sq.add_memory(_make_memory(i))

        # Use same store's sqlite for compact
        store._sqlite = sq
        result = store.compact_memory(max_rows=10)
        assert result["pruned"] == 5
        assert isinstance(result["vacuumed"], bool)


# ─────────────────────────────────────────────────────────────────────────────
# 10. No API key required — no cloud calls in any diagnostic path
# ─────────────────────────────────────────────────────────────────────────────

def test_no_api_key_required():
    """Diagnostics must work without any AI API keys in environment."""
    import os
    keys = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "HUGGINGFACE_TOKEN")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        from app.ai.diagnostics import get_ai_runtime_diagnostics
        result = get_ai_runtime_diagnostics()
        assert isinstance(result, dict)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_no_gpu_required():
    """All diagnostics and dependency checks must complete without GPU/CUDA."""
    from app.ai.diagnostics import get_ai_runtime_diagnostics
    from app.ai.dependencies import get_ai_dependency_status
    result = get_ai_runtime_diagnostics()
    deps = get_ai_dependency_status()
    assert isinstance(result, dict)
    assert isinstance(deps, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 11. Diagnostics do not load model — verified via _model sentinel
# ─────────────────────────────────────────────────────────────────────────────

def test_diagnostics_does_not_trigger_model_load():
    """Calling get_ai_runtime_diagnostics() must not load the embedding model."""
    import app.ai.rag.embeddings as emb

    # Reset the sentinel if a previous test already triggered a load
    original_model = emb._model
    emb._model = None

    try:
        from app.ai.diagnostics import get_ai_runtime_diagnostics
        get_ai_runtime_diagnostics()
        assert emb._model is None, (
            "get_ai_runtime_diagnostics() triggered embedding model load"
        )
    finally:
        emb._model = original_model  # restore for other tests
