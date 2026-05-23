"""
files.py — File upload endpoint for editor BGM/audio assets.

POST /api/upload-file
  Accepts a multipart form upload (field name: "file").
  Saves the file to a safe temp/editor-uploads directory inside the project.
  Returns {"path": "<absolute_path_to_saved_file>"}.

Security:
  - safe_filename() strips path separators and null bytes.
  - Files are saved under APP_DATA_DIR/editor-uploads only — no traversal possible.
  - Does NOT implement or restore /api/upload/* (old upload domain).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.core.config import APP_DATA_DIR

router = APIRouter(tags=["files"])
logger = logging.getLogger("app.files")

# Upload directory — inside APP_DATA_DIR; created lazily on first use.
_EDITOR_UPLOADS_DIR = APP_DATA_DIR / "editor-uploads"

# Maximum upload size: 200 MB (audio files only; no video expected here)
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe filename stripped of path traversal characters.

    - Removes any path separators (/ and \\) so callers cannot escape the
      upload directory.
    - Removes null bytes.
    - Normalises unicode to NFKC to collapse lookalike characters.
    - Collapses any remaining whitespace runs to a single underscore.
    - Returns a non-empty fallback ("upload") when the result would be blank.
    """
    if not name:
        return "upload"
    # Normalise unicode
    name = unicodedata.normalize("NFKC", name)
    # Strip null bytes
    name = name.replace("\x00", "")
    # Strip path separators — prevents traversal (e.g. "../../etc/passwd")
    name = re.sub(r"[/\\]+", "_", name)
    # Strip leading dots (prevent hidden files like ".bashrc")
    name = name.lstrip(".")
    # Collapse whitespace
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "upload"


@router.post("/api/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """Accept a multipart file upload and return its saved path.

    Frontend contract (editor-audio-runtime.js, editor-view.js):
        Request:  POST /api/upload-file  with FormData field "file"
        Response: {"path": "<saved_absolute_path>"}

    Raises:
        400 — filename is empty after sanitisation (should never happen in practice)
        413 — file exceeds _MAX_UPLOAD_BYTES (200 MB)
        500 — I/O error saving the file
    """
    original_name = file.filename or ""
    safe_name = _safe_filename(original_name)

    # Reject obviously bad names that survive sanitisation as pure gibberish
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    _EDITOR_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    dest = _EDITOR_UPLOADS_DIR / safe_name

    # If file already exists, suffix with a counter to avoid overwrites
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = _EDITOR_UPLOADS_DIR / f"{stem}_{counter}{suffix}"
            counter += 1

    try:
        written = 0
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large (max {_MAX_UPLOAD_BYTES // (1024*1024)} MB)",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("upload_file_error: %s", exc)
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to save uploaded file") from exc

    logger.info(
        "upload_file_saved: name=%s size=%d dest=%s",
        safe_name, written, dest,
    )
    # Return the absolute path — frontend stores this as bgmPath for the render payload
    return {"path": str(dest)}
