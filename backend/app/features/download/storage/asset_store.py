"""storage/asset_store.py — 4-tier file store for downloaded assets.

Tiers (in promotion order):
  tmp       — in-flight downloads and temp files
  raw       — completed downloads, original quality
  processed — rendered/processed variants
  archive   — archived files (low-priority, eligible for deletion)

All files live under APP_DATA_DIR/assets/<tier>/. AssetStore never touches
paths outside its base_dir, and never interacts with download_jobs output.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("app.asset_store")

TIERS: tuple[str, ...] = ("tmp", "raw", "processed", "archive")

_TIER_ORDER = {t: i for i, t in enumerate(TIERS)}


class AssetStore:
    """Manages physical file movement across the 4 storage tiers."""

    def __init__(self, base_dir: Path) -> None:
        self._base = Path(base_dir)
        for tier in TIERS:
            (self._base / tier).mkdir(parents=True, exist_ok=True)

    def tier_path(self, tier: str) -> Path:
        if tier not in _TIER_ORDER:
            raise ValueError(f"Unknown storage tier {tier!r}. Valid: {TIERS}")
        return self._base / tier

    def promote(self, src: Path, to_tier: str) -> Path:
        """Move src into to_tier directory. Returns the new path."""
        dest_dir = self.tier_path(to_tier)
        dest = dest_dir / src.name
        if dest.exists() and dest.resolve() != src.resolve():
            stem = src.stem
            suffix = src.suffix
            for i in range(1, 1000):
                candidate = dest_dir / f"{stem}_{i}{suffix}"
                if not candidate.exists():
                    dest = candidate
                    break
        src.rename(dest)
        logger.debug("asset_store.promote: %s → %s", src, dest)
        return dest

    def delete_file(self, path: Path) -> bool:
        """Delete file from disk. Returns True if the file existed."""
        try:
            if path.is_file():
                path.unlink()
                logger.debug("asset_store.delete: %s", path)
                return True
        except Exception as exc:
            logger.warning("asset_store.delete failed: %s — %s", path, exc)
        return False

    def exists(self, path: Path) -> bool:
        return Path(path).is_file()


_store: AssetStore | None = None


def get_asset_store() -> AssetStore:
    """Return the module-level singleton, initialised from APP_DATA_DIR."""
    global _store
    if _store is None:
        from app.core.config import APP_DATA_DIR
        _store = AssetStore(Path(APP_DATA_DIR) / "assets")
    return _store
