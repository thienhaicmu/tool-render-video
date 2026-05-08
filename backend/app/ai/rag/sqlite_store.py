"""
sqlite_store.py — Local SQLite persistence for AI render memory.

Stores render memories and optional embedding vectors.
Falls back safely on any DB error — rendering is never blocked.

DB path: APP_DATA_DIR / "ai_memory.db" (same packaging-safe dir as app.db)

Public API:
    SQLiteMemoryStore
        .initialize() -> bool
        .add_memory(memory, vector=None) -> bool
        .search_memories(limit=100) -> list[RenderMemory]
        .count() -> int
        .load_vectors() -> list[dict]  # {"id", "text", "vector", "metadata"}
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from app.ai.rag.memory_schema import RenderMemory

logger = logging.getLogger("app.ai.rag.sqlite_store")

_DDL_MEMORIES = """
CREATE TABLE IF NOT EXISTS render_memories (
    id              TEXT PRIMARY KEY,
    text            TEXT NOT NULL,
    market          TEXT,
    mode            TEXT,
    duration        REAL,
    score           REAL,
    subtitle_tone   TEXT,
    camera_behavior TEXT,
    status          TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    metadata_json   TEXT
)
"""

_DDL_EMBEDDINGS = """
CREATE TABLE IF NOT EXISTS embeddings (
    memory_id   TEXT PRIMARY KEY,
    vector_json TEXT NOT NULL
)
"""


def _default_db_path() -> Path:
    try:
        from app.core.config import APP_DATA_DIR
        return Path(APP_DATA_DIR) / "ai_memory.db"
    except Exception:
        # Fallback: resolve relative to this file (backend/app/ai/rag/)
        return Path(__file__).resolve().parents[4] / "data" / "ai_memory.db"


class SQLiteMemoryStore:
    """Persistent SQLite store for render memories.

    All methods are fallback-safe — never raises, never blocks rendering.
    Accepts an explicit db_path for testing; uses APP_DATA_DIR otherwise.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else _default_db_path()
        self._ready = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Create DB file and tables if missing. Returns False on any failure."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect()
            if conn is None:
                return False
            with conn:
                conn.execute(_DDL_MEMORIES)
                conn.execute(_DDL_EMBEDDINGS)
            conn.close()
            self._ready = True
            logger.debug("sqlite_store_ready path=%s", self._db_path)
            return True
        except Exception as exc:
            logger.warning("sqlite_store_init_failed: %s", exc)
            self._ready = False
            return False

    def _connect(self) -> Optional[sqlite3.Connection]:
        try:
            return sqlite3.connect(str(self._db_path), timeout=5)
        except Exception as exc:
            logger.debug("sqlite_store_connect_failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_memory(
        self,
        memory: RenderMemory,
        vector: Optional[list[float]] = None,
    ) -> bool:
        """Persist a render memory and optionally its embedding vector.

        Returns False (never raises) on any DB failure.
        """
        if not self._ready:
            return False
        conn = self._connect()
        if conn is None:
            return False
        try:
            meta_json = _safe_json(memory.metadata)
            with conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO render_memories
                    (id, text, market, mode, duration, score,
                     subtitle_tone, camera_behavior, status, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory.id,
                        memory.text,
                        memory.market,
                        memory.mode,
                        memory.duration,
                        memory.score,
                        memory.subtitle_tone,
                        memory.camera_behavior,
                        memory.status,
                        meta_json,
                    ),
                )
                if vector is not None:
                    conn.execute(
                        "INSERT OR REPLACE INTO embeddings (memory_id, vector_json) VALUES (?, ?)",
                        (memory.id, json.dumps(vector)),
                    )
            return True
        except Exception as exc:
            logger.warning("sqlite_store_add_failed: %s", exc)
            return False
        finally:
            _close(conn)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search_memories(self, limit: int = 100) -> list[RenderMemory]:
        """Return recent memories ordered newest-first. Returns [] on failure."""
        if not self._ready:
            return []
        conn = self._connect()
        if conn is None:
            return []
        try:
            cur = conn.execute(
                """
                SELECT id, text, market, mode, duration, score,
                       subtitle_tone, camera_behavior, status, metadata_json
                FROM render_memories
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [_row_to_memory(r) for r in rows]
        except Exception as exc:
            logger.warning("sqlite_store_search_failed: %s", exc)
            return []
        finally:
            _close(conn)

    def count(self) -> int:
        """Return total number of stored memories. Returns 0 on failure."""
        if not self._ready:
            return 0
        conn = self._connect()
        if conn is None:
            return 0
        try:
            cur = conn.execute("SELECT COUNT(*) FROM render_memories")
            return int(cur.fetchone()[0])
        except Exception:
            return 0
        finally:
            _close(conn)

    def load_vectors(self) -> list[dict]:
        """Load memories with stored vectors for in-memory vector store hydration.

        Returns list of {"id", "text", "vector", "metadata"}.
        Memories without stored embeddings are excluded (vector-only hydration).
        """
        if not self._ready:
            return []
        conn = self._connect()
        if conn is None:
            return []
        try:
            cur = conn.execute(
                """
                SELECT m.id, m.text, e.vector_json, m.metadata_json
                FROM render_memories m
                JOIN embeddings e ON e.memory_id = m.id
                ORDER BY m.created_at DESC
                LIMIT 500
                """
            )
            rows = cur.fetchall()
            results: list[dict] = []
            for row in rows:
                try:
                    vec = json.loads(row[2])
                    meta = _safe_json_loads(row[3])
                    results.append(
                        {"id": row[0], "text": row[1], "vector": vec, "metadata": meta}
                    )
                except Exception:
                    continue
            return results
        except Exception as exc:
            logger.warning("sqlite_store_load_vectors_failed: %s", exc)
            return []
        finally:
            _close(conn)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj)
    except Exception:
        return "{}"


def _safe_json_loads(s: Any) -> dict:
    try:
        return dict(json.loads(s) if s else {})
    except Exception:
        return {}


def _close(conn: Any) -> None:
    try:
        if conn is not None:
            conn.close()
    except Exception:
        pass


def _row_to_memory(row: tuple) -> RenderMemory:
    return RenderMemory(
        id=str(row[0]),
        text=str(row[1]),
        market=row[2] or None,
        mode=row[3] or None,
        duration=float(row[4]) if row[4] is not None else None,
        score=float(row[5]) if row[5] is not None else None,
        subtitle_tone=row[6] or None,
        camera_behavior=row[7] or None,
        status=row[8] or None,
        metadata=_safe_json_loads(row[9]),
    )
