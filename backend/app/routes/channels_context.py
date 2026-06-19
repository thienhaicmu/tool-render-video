"""
routes/channels_context.py — Per-channel CreatorContext REST endpoints.

GET  /api/channels/{channel_code}/context
     Return the CreatorContext for the given channel (falls back to the
     global singleton when no per-channel row exists). Never 404 —
     always returns an envelope with is_configured=False on first call.

PUT  /api/channels/{channel_code}/context
     Persist a per-channel CreatorContext. Does NOT touch the global
     singleton. Returns the saved envelope.

DELETE /api/channels/{channel_code}/context
     Remove the per-channel row. 404 when no row exists.

All endpoints delegate directly to existing creator_repo helpers —
no new DB logic. The CreatorContextPayload / CreatorContextEnvelope
Pydantic models are imported from settings.py to avoid duplication.

Blast radius: LOW — new file, no existing routes modified.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.creator_repo import (
    delete_creator_context_for_channel,
    get_creator_context_for_channel,
    upsert_creator_context_for_channel,
)
from app.routes.settings import CreatorContextEnvelope, CreatorContextPayload

router = APIRouter(prefix="/api/channels", tags=["channels-context"])


@router.get("/{channel_code}/context", response_model=CreatorContextEnvelope)
def get_channel_context(channel_code: str) -> CreatorContextEnvelope:
    """Return the persisted CreatorContext for a channel (or defaults).

    Falls back to the global singleton when no per-channel row exists.
    Never 404 — the response always carries a valid envelope so the
    frontend can render the settings form unconditionally.
    """
    ctx = get_creator_context_for_channel(channel_code.strip())
    return CreatorContextEnvelope(
        is_configured=ctx is not None and not ctx.is_empty(),
        creator_context=CreatorContextPayload.from_domain(ctx),
    )


@router.put("/{channel_code}/context", response_model=CreatorContextEnvelope)
def put_channel_context(
    channel_code: str, payload: CreatorContextPayload
) -> CreatorContextEnvelope:
    """Persist a per-channel CreatorContext and return what was saved.

    Writes to the per-channel table only — global singleton is untouched.
    Posting an empty body clears all fields (is_configured=False on readback).
    """
    code = channel_code.strip()
    if not code:
        raise HTTPException(status_code=422, detail="channel_code must not be empty")
    upsert_creator_context_for_channel(code, payload.to_domain())
    saved = get_creator_context_for_channel(code)
    return CreatorContextEnvelope(
        is_configured=saved is not None and not saved.is_empty(),
        creator_context=CreatorContextPayload.from_domain(saved),
    )


@router.delete("/{channel_code}/context")
def delete_channel_context(channel_code: str) -> dict:
    """Remove the per-channel CreatorContext row.

    Returns 404 when no per-channel row exists for the given channel_code.
    The global singleton is never affected.
    """
    code = channel_code.strip()
    if not delete_creator_context_for_channel(code):
        raise HTTPException(
            status_code=404,
            detail=f"No per-channel context found for: {code}",
        )
    return {"channel_code": code, "deleted": True}
