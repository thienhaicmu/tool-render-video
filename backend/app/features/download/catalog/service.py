"""catalog/service.py — CatalogService: deduplication and state machine for asset_catalog.

dedup_key is SHA256(url) — ensures one catalog record per unique URL regardless
of which download job fetched it. The state machine is enforced by transition():
callers must go through this method rather than calling catalog_repo.update_asset()
directly to mutate status.
"""
from __future__ import annotations

import hashlib
import logging
import uuid

logger = logging.getLogger("app.catalog")

_VALID_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("pending",     "downloading"),
    ("pending",     "failed"),
    ("downloading", "ready"),
    ("downloading", "failed"),
    ("ready",       "processing"),
    ("ready",       "archived"),
    ("processing",  "ready"),
    ("processing",  "archived"),
    ("archived",    "deleted"),
    ("failed",      "pending"),
})


class CatalogService:
    """Owns deduplication and state-machine transitions for asset_catalog."""

    def dedup_key(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def register_or_get(
        self,
        url: str,
        platform: str = "",
        quality: str = "best",
        output_dir: str = "",
    ) -> dict:
        """Return existing catalog record for this URL, or create a new pending one."""
        from app.db.catalog_repo import create_asset, get_asset_by_dedup_key
        key = self.dedup_key(url)
        existing = get_asset_by_dedup_key(key)
        if existing:
            logger.debug("catalog.register_or_get: existing asset_id=%s url=%s", existing["asset_id"], url[:80])
            return existing
        asset_id = str(uuid.uuid4())
        create_asset(asset_id, key, url, platform=platform, quality=quality)
        logger.info("catalog.register: new asset_id=%s platform=%s url=%s", asset_id, platform, url[:80])
        record = get_asset_by_dedup_key(key)
        return record or {"asset_id": asset_id, "dedup_key": key, "url": url, "status": "pending"}

    def transition(self, asset_id: str, new_status: str) -> bool:
        """Apply a state-machine transition. Returns True if applied, False if invalid."""
        from app.db.catalog_repo import get_asset_by_id, update_asset
        asset = get_asset_by_id(asset_id)
        if not asset:
            logger.warning("catalog.transition: asset_id=%s not found", asset_id)
            return False
        current = asset.get("status", "")
        if (current, new_status) not in _VALID_TRANSITIONS:
            logger.warning(
                "catalog.transition: invalid %s→%s for asset_id=%s",
                current, new_status, asset_id,
            )
            return False
        update_asset(asset_id, status=new_status)
        logger.debug("catalog.transition: %s→%s asset_id=%s", current, new_status, asset_id)
        return True

    def link_download_job(self, asset_id: str, job_id: str) -> None:
        from app.db.catalog_repo import update_asset
        update_asset(asset_id, download_job_id=job_id)

    def mark_ready(
        self,
        asset_id: str,
        storage_path: str,
        filename: str,
        filesize: int,
        storage_tier: str = "raw",
        **meta,
    ) -> bool:
        """Transition to 'ready' and persist storage metadata in one call."""
        from app.db.catalog_repo import update_asset
        ok = self.transition(asset_id, "ready")
        if ok:
            allowed_meta = {
                k: v for k, v in meta.items()
                if k in {"title", "duration", "height", "fps", "thumbnail_url"}
            }
            update_asset(
                asset_id,
                storage_path=storage_path,
                filename=filename,
                filesize=filesize,
                storage_tier=storage_tier,
                **allowed_meta,
            )
        return ok


_catalog_service = CatalogService()
