"""Preview session state and lifecycle helpers.

Extracted from routes/render.py (Phase 4H.2).
Owns the singleton _PREVIEW_SESSIONS dict and all functions that mutate it.
"""

import json
import os
import shutil
import time
import logging
from pathlib import Path

from app.core.config import TEMP_DIR

logger = logging.getLogger("app.preview.session")

_PREVIEW_SESSIONS: dict[str, dict] = {}  # session_id -> {video_path, duration, title, work_dir, created_at}
_PREVIEW_DIR = TEMP_DIR / "preview"
# Sessions idle longer than this are evicted from memory and their dirs pruned from disk.
_SESSION_TTL_HOURS: int = int(os.getenv("PREVIEW_SESSION_TTL_HOURS", "6"))
_MAX_PREVIEW_SESSIONS: int = 200


def _save_session(session_id: str, data: dict):
    """Persist session to memory + JSON file (survives server restart)."""
    if len(_PREVIEW_SESSIONS) >= _MAX_PREVIEW_SESSIONS:
        oldest = min(_PREVIEW_SESSIONS, key=lambda k: _PREVIEW_SESSIONS[k].get("created_at", 0))
        _cleanup_preview_session(oldest)
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
    stale = [
        sid for sid, s in list(_PREVIEW_SESSIONS.items())
        if s.get("created_at", 0) < cutoff
    ]
    for sid in stale:
        logger.info("cleanup: evicting stale preview session session_id=%s", sid)
        _cleanup_preview_session(sid)
    return len(stale)
