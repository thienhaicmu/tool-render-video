"""lifecycle/manager.py — LifecycleManager: archive, delete, and prune assets.

Coordinates between AssetStore (disk) and CatalogService (DB state machine).
All operations are soft-first: archive moves the file to the archive tier and
marks the DB record 'archived'; delete removes the file and marks it 'deleted'.
prune_expired_assets() processes assets whose expires_at timestamp has passed.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.lifecycle")


class LifecycleManager:
    """Orchestrates asset lifecycle: archive → delete → prune."""

    def __init__(self, store, catalog) -> None:
        self._store = store
        self._catalog = catalog

    def archive_asset(self, asset_id: str) -> bool:
        """Promote asset file to archive tier and transition status to 'archived'.

        Returns True if the operation succeeded (or file was already archived).
        """
        from app.db.catalog_repo import get_asset_by_id, update_asset
        from pathlib import Path

        asset = get_asset_by_id(asset_id)
        if not asset:
            logger.warning("lifecycle.archive: asset_id=%s not found", asset_id)
            return False

        current_status = asset.get("status", "")
        if current_status == "archived":
            return True
        if current_status == "deleted":
            logger.warning("lifecycle.archive: asset_id=%s already deleted", asset_id)
            return False

        storage_path = asset.get("storage_path", "")
        if storage_path:
            src = Path(storage_path)
            if src.is_file() and asset.get("storage_tier") != "archive":
                try:
                    new_path = self._store.promote(src, "archive")
                    update_asset(asset_id, storage_path=str(new_path), storage_tier="archive")
                except Exception as exc:
                    logger.error("lifecycle.archive: file move failed asset_id=%s — %s", asset_id, exc)
                    return False

        ok = self._catalog.transition(asset_id, "archived")
        if ok:
            from app.db.connection import _utc_now_iso
            update_asset(asset_id, archived_at=_utc_now_iso())
        return ok

    def delete_asset(self, asset_id: str) -> bool:
        """Delete asset file from disk and transition status to 'deleted'.

        Returns True if the operation succeeded.
        """
        from app.db.catalog_repo import get_asset_by_id, update_asset
        from pathlib import Path

        asset = get_asset_by_id(asset_id)
        if not asset:
            logger.warning("lifecycle.delete: asset_id=%s not found", asset_id)
            return False

        if asset.get("status") == "deleted":
            return True

        # Must be in 'archived' state to delete; archive first if needed
        if asset.get("status") not in ("archived", "failed"):
            archived = self.archive_asset(asset_id)
            if not archived:
                return False

        storage_path = asset.get("storage_path", "")
        if storage_path:
            self._store.delete_file(__import__("pathlib").Path(storage_path))

        ok = self._catalog.transition(asset_id, "deleted")
        if ok:
            from app.db.connection import _utc_now_iso
            update_asset(asset_id, deleted_at=_utc_now_iso())
            logger.info("lifecycle.delete: asset_id=%s deleted", asset_id)
        return ok

    def prune_expired_assets(self, max_age_days: int = 30) -> dict:
        """Archive or delete assets whose expires_at timestamp has passed.

        Returns {"archived": N, "deleted": N, "errors": N}.
        """
        from app.db.catalog_repo import get_expired_assets

        if max_age_days <= 0:
            return {"archived": 0, "deleted": 0, "errors": 0}

        expired = get_expired_assets(max_age_days)
        archived = deleted = errors = 0

        for asset in expired:
            asset_id = asset["asset_id"]
            status = asset.get("status", "")
            try:
                if status == "archived":
                    ok = self.delete_asset(asset_id)
                    if ok:
                        deleted += 1
                    else:
                        errors += 1
                else:
                    ok = self.archive_asset(asset_id)
                    if ok:
                        archived += 1
                    else:
                        errors += 1
            except Exception as exc:
                logger.error("lifecycle.prune: error on asset_id=%s — %s", asset_id, exc)
                errors += 1

        logger.info(
            "lifecycle.prune: max_age_days=%d archived=%d deleted=%d errors=%d",
            max_age_days, archived, deleted, errors,
        )
        return {"archived": archived, "deleted": deleted, "errors": errors}
