"""
routes/assets.py — Asset Library REST endpoints.

Asset Library. CRUD surface for registered source video
assets. Assets are created automatically when a download completes;
they can also be queried by the frontend to build a library UI.

Asset Search & Filter. GET /api/assets now accepts optional
query params: content_type, language, min_duration, max_duration, q.

Blast radius: LOW — new file, no existing routes modified.
"""
from __future__ import annotations


from fastapi import APIRouter, HTTPException, Query

from app.db.assets_repo import (
    delete_asset,
    get_asset,
    list_assets,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("")
def get_assets(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    content_type: str = Query("", description="Filter by content type (e.g. 'vlog', 'interview')"),
    language: str = Query("", description="Filter by language ISO code (e.g. 'vi', 'en')"),
    min_duration: float = Query(0.0, ge=0, description="Minimum duration in seconds"),
    max_duration: float = Query(0.0, ge=0, description="Maximum duration in seconds (0 = no limit)"),
    q: str = Query("", description="Title keyword search (case-insensitive LIKE)"),
):
    """List registered assets with optional filter params. Newest first."""
    assets = list_assets(
        limit=limit,
        offset=offset,
        content_type=content_type,
        language=language,
        min_duration=min_duration,
        max_duration=max_duration,
        q=q,
    )
    return {
        "assets": [a.to_dict() for a in assets],
        "limit": limit,
        "offset": offset,
        "filters": {
            "content_type": content_type,
            "language": language,
            "min_duration": min_duration,
            "max_duration": max_duration,
            "q": q,
        },
    }


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
