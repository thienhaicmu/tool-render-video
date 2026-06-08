"""HTTP media streaming helpers: Range header parsing and byte-range file iteration.

Extracted from routes/render.py (Phase 4H.3).
Route-independent helpers: no APIRouter, no DB, no session state.
"""

import re
from pathlib import Path
from typing import Generator

from fastapi import HTTPException


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse an HTTP Range header. Return (byte1, byte2) inclusive.

    Raises HTTPException(416 Range Not Satisfiable) for malformed or out-of-range values.
    Open-ended ranges ("bytes=N-") are resolved to (N, file_size - 1).
    End clamped to file_size - 1 if it exceeds the file.
    """
    m = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not m:
        raise HTTPException(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"},
            detail="Range Not Satisfiable",
        )
    byte1 = int(m.group(1))
    byte2 = int(m.group(2)) if m.group(2) else file_size - 1
    byte2 = min(byte2, file_size - 1)

    if byte1 > byte2 or byte1 >= file_size:
        raise HTTPException(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"},
            detail="Range Not Satisfiable",
        )
    return byte1, byte2


def _iter_file_bytes(
    path: Path, start: int, end: int, chunk: int = 1 << 16
) -> Generator[bytes, None, None]:
    """Yield file bytes from [start, end] inclusive in chunks of `chunk` bytes."""
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            data = fh.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
