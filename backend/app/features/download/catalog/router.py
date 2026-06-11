"""catalog/router.py — REST endpoints for the asset catalog and acquisition queue.

Mounted at /api/downloader/catalog by main.py.
Asset mutations go through LifecycleManager to enforce the state machine.
Queue operations go through AcquisitionScheduler.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


# ── Acquisition Queue endpoints ───────────────────────────────────────────────

class QueueRequest(BaseModel):
    url: str
    platform: str = ""
    quality: str = "best"
    output_dir: str = ""
    priority: int = 5       # 1=highest, 10=lowest
    max_retries: int = 3


@router.post("/queue")
def add_to_queue(req: QueueRequest):
    """Add a URL to the acquisition queue for background download."""
    from app.features.download.catalog.scheduler import _scheduler
    from app.features.download.engine.platform_detect import detect_platform
    platform = req.platform or detect_platform(req.url)
    queue_id = _scheduler.enqueue(
        req.url,
        platform=platform,
        quality=req.quality,
        output_dir=req.output_dir,
        priority=max(1, min(10, req.priority)),
        max_retries=max(0, req.max_retries),
    )
    return {"queue_id": queue_id, "platform": platform}


@router.get("/queue")
def list_queue_items(status: str | None = None, limit: int = 100):
    """List acquisition queue items, optionally filtered by status."""
    from app.db.queue_repo import list_queue
    return list_queue(status=status, limit=min(limit, 500))


@router.delete("/queue/{queue_id}")
def cancel_queue_item(queue_id: str):
    """Cancel a pending queue item (only items with status='queued' can be cancelled)."""
    from app.db.queue_repo import get_queue_item, update_queue_item
    from app.db.connection import _utc_now_iso
    item = get_queue_item(queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    if item.get("status") != "queued":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel item with status '{item.get('status')}' — "
                   "only 'queued' items can be cancelled",
        )
    update_queue_item(queue_id, status="cancelled", completed_at=_utc_now_iso())
    return {"ok": True, "queue_id": queue_id}
