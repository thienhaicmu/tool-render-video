"""Preview session state and lifecycle helpers.

Extracted from routes/render.py (Phase 4H.2).
Owns the singleton _PREVIEW_SESSIONS dict and all functions that mutate it.

Concurrency (audit FINDING-BR01 closure, 2026-06-06):
    _PREVIEW_SESSIONS_LOCK serializes every read+write of _PREVIEW_SESSIONS
    across the four entry points below. An RLock is used so the eviction
    chain (_save_session → _cleanup_preview_session,
     evict_stale_preview_sessions → _cleanup_preview_session) can re-enter
    the lock without deadlock. Disk I/O (file write / rmtree) happens
    INSIDE the locked region to keep the in-memory and on-disk state
    consistent with respect to each session_id. The disk operations are
    short and rarely contended for a single user; if they ever become a
    hotspot, narrow the lock to dict mutation only and accept the small
    window of dict↔disk inconsistency.
"""

import json
import os
import shutil
import threading
import time
import logging
from pathlib import Path

from app.core.config import TEMP_DIR

logger = logging.getLogger("app.preview.session")

_PREVIEW_SESSIONS: dict[str, dict] = {}  # session_id -> {video_path, duration, title, work_dir, created_at}
_PREVIEW_SESSIONS_LOCK = threading.RLock()
_PREVIEW_DIR = TEMP_DIR / "preview"
# Sessions idle longer than this are evicted from memory and their dirs pruned from disk.
_SESSION_TTL_HOURS: int = int(os.getenv("PREVIEW_SESSION_TTL_HOURS", "6"))
_MAX_PREVIEW_SESSIONS: int = 200


def _save_session(session_id: str, data: dict):
    """Persist session to memory + JSON file (survives server restart)."""
    with _PREVIEW_SESSIONS_LOCK:
        if len(_PREVIEW_SESSIONS) >= _MAX_PREVIEW_SESSIONS:
            oldest = min(_PREVIEW_SESSIONS, key=lambda k: _PREVIEW_SESSIONS[k].get("created_at", 0))
            _cleanup_preview_session(oldest)  # reentrant: RLock allows re-acquire
        if "created_at" not in data:
            data = {**data, "created_at": time.time()}
        _PREVIEW_SESSIONS[session_id] = data
        try:
            meta_path = Path(data["work_dir"]) / "session.json"
            meta_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def _load_session(session_id: str) -> dict | None:
    """Load session from memory or fallback to disk JSON."""
    with _PREVIEW_SESSIONS_LOCK:
        if session_id in _PREVIEW_SESSIONS:
            return _PREVIEW_SESSIONS[session_id]
        meta_path = _PREVIEW_DIR / session_id / "session.json"
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                if Path(data.get("video_path", "")).exists():
                    _PREVIEW_SESSIONS[session_id] = data
                    return data
            except Exception:
                pass
        return None


def _cleanup_preview_session(session_id: str):
    """Remove preview session from memory and disk after render consumes it."""
    with _PREVIEW_SESSIONS_LOCK:
        _PREVIEW_SESSIONS.pop(session_id, None)
        preview_dir = _PREVIEW_DIR / session_id
        if preview_dir.exists():
            try:
                shutil.rmtree(preview_dir, ignore_errors=True)
                logger.info("cleanup: removed preview session dir session_id=%s", session_id)
            except Exception:
                pass


def evict_stale_preview_sessions() -> int:
    """Evict in-memory sessions older than _SESSION_TTL_HOURS. Returns evicted count.

    Called periodically by the background cleanup thread in main.py so that
    abandoned sessions do not accumulate in the _PREVIEW_SESSIONS dict.
    """
    cutoff = time.time() - _SESSION_TTL_HOURS * 3600
    with _PREVIEW_SESSIONS_LOCK:
        stale = [
            sid for sid, s in list(_PREVIEW_SESSIONS.items())
            if s.get("created_at", 0) < cutoff
        ]
        for sid in stale:
            logger.info("cleanup: evicting stale preview session session_id=%s", sid)
            _cleanup_preview_session(sid)  # reentrant
    return len(stale)
