"""
routes/assets.py — Asset Library REST endpoints.

Phase C — Asset Library. CRUD surface for registered source video
assets. Assets are created automatically when a download completes;
they can also be queried by the frontend to build a library UI.

Blast radius: LOW — new file, no existing routes modified.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.db.assets_repo import (
    delete_asset,
    get_asset,
    get_asset_by_path,
    list_assets,
    upsert_asset,
)
from app.domain.asset import Asset

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("")
def get_assets(limit: int = 100, offset: int = 0):
    """List all registered assets, newest first."""
    limit = min(max(1, limit), 500)
    offset = max(0, offset)
    assets = list_assets(limit=limit, offset=offset)
    return {"assets": [a.to_dict() for a in assets], "limit": limit, "offset": offset}


@router.get("/{asset_id}")
def get_asset_by_id(asset_id: str):
    """Get a single asset by its asset_id."""
    asset = get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    return asset.to_dict()


@router.delete("/{asset_id}")
def remove_asset(asset_id: str):
    """Remove an asset record (does NOT delete the source file from disk)."""
    asset = get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")
    delete_asset(asset_id)
    return {"deleted": asset_id}
