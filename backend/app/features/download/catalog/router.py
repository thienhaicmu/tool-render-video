"""catalog/router.py — REST endpoints for the asset catalog.

Mounted at /api/downloader/catalog by main.py.
All mutations go through LifecycleManager to enforce the state machine.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.db.catalog_repo import get_asset_by_id, list_assets
from app.features.download.catalog.service import _catalog_service
from app.features.download.lifecycle.manager import LifecycleManager
from app.features.download.storage.asset_store import get_asset_store

logger = logging.getLogger("app.catalog")

router = APIRouter(prefix="/api/downloader/catalog", tags=["catalog"])


def _mgr() -> LifecycleManager:
    return LifecycleManager(store=get_asset_store(), catalog=_catalog_service)


@router.get("/")
def list_catalog(status: str | None = None, limit: int = 100):
    """List catalog assets, optionally filtered by status."""
    return list_assets(status=status, limit=min(limit, 500))


@router.get("/{asset_id}")
def get_asset(asset_id: str):
    """Get a single catalog asset by asset_id."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("/{asset_id}/archive")
def archive_asset(asset_id: str):
    """Move asset file to archive tier and transition status to 'archived'."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    ok = _mgr().archive_asset(asset_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot archive asset in state '{asset.get('status')}'",
        )
    return {"ok": True, "asset_id": asset_id}


@router.delete("/{asset_id}")
def delete_asset(asset_id: str):
    """Delete asset file from disk and transition status to 'deleted'."""
    asset = get_asset_by_id(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    ok = _mgr().delete_asset(asset_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete asset in state '{asset.get('status')}'",
        )
    return {"ok": True, "asset_id": asset_id}
