"""
asset.py — Asset domain dataclass.

Pure data object: no I/O, no FFmpeg, no DB access. Represents a single
source video file registered in the asset library.

Phase C — Asset Library. Every field has a safe default so partial
enrichment (e.g. ffprobe succeeded but Whisper timed out) can be
persisted without losing the rows that did succeed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Asset:
    asset_id: str = ""
    file_path: str = ""
    original_url: str = ""
    title: str = ""
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    file_size_bytes: int = 0
    language: str = ""
    content_type: str = ""            # interview|vlog|tutorial|commentary|montage|gaming|""
    transcription_cache_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    created_at: str = ""
    enriched_at: Optional[str] = None
    # Phase U2 — explicit lifecycle state: pending|enriching|ready|failed
    status: str = "pending"

    # ── Serialisation ────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> "Asset":
        """Build from a sqlite3.Row dict. Unknown keys are ignored; missing
        keys fall back to dataclass defaults. Never raises."""
        if not isinstance(row, dict):
            return cls()
        return cls(
            asset_id=str(row.get("asset_id") or ""),
            file_path=str(row.get("file_path") or ""),
            original_url=str(row.get("original_url") or ""),
            title=str(row.get("title") or ""),
            duration_sec=_coerce_float(row.get("duration_sec"), 0.0),
            width=_coerce_int(row.get("width"), 0),
            height=_coerce_int(row.get("height"), 0),
            fps=_coerce_float(row.get("fps"), 0.0),
            file_size_bytes=_coerce_int(row.get("file_size_bytes"), 0),
            language=str(row.get("language") or ""),
            content_type=str(row.get("content_type") or ""),
            transcription_cache_path=row.get("transcription_cache_path") or None,
            thumbnail_path=row.get("thumbnail_path") or None,
            created_at=str(row.get("created_at") or ""),
            enriched_at=row.get("enriched_at") or None,
            status=str(row.get("status") or "pending"),
        )


# ── Internal helpers ─────────────────────────────────────────────────────

def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
