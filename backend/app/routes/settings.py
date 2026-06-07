"""
routes/settings.py — User-facing settings endpoints.

Sprint 3-FE: ships GET/PUT /api/settings/creator-context so the
frontend Settings screen can read and persist the CreatorContext
(Sprint 3 backend already wired the read path into the LLM stage's
editorial hint).

Design notes:
- The route is intentionally separated from /api/channels because
  channels are per-channel-folder configuration; CreatorContext is the
  app-wide creator persona (singleton creator_prefs row). Sprint 3.6+
  may extend this with multi-creator routing.
- Request body uses a Pydantic model so FastAPI emits clean OpenAPI
  docs and rejects garbage payloads with 422. The Pydantic model
  mirrors the CreatorContext dataclass field-for-field; defaults
  exactly match so an empty PUT body wipes the persisted context.
- GET always returns 200 with a JSON body — never 404. An unconfigured
  creator returns the default-shaped object so the frontend can render
  the form unconditionally.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db.creator_repo import (
    get_creator_context,
    get_job_retention_days,
    upsert_creator_context,
    upsert_job_retention_days,
)
from app.domain.creator_context import CreatorContext


router = APIRouter(prefix="/api/settings", tags=["settings"])


class CreatorContextPayload(BaseModel):
    """Request body / response shape for /api/settings/creator-context.

    Mirrors `app.domain.creator_context.CreatorContext` 1:1. Defaults
    exactly match so a PUT with `{}` clears every field. extra="ignore"
    protects against unknown payload keys from older / newer clients —
    same backward-compat pattern Sprint 1.2 introduced on
    PrepareSourceRequest.
    """
    model_config = ConfigDict(extra="ignore")

    creator_id: str = ""
    channel_name: str = ""
    brand_voice: str = ""
    target_audience: str = ""
    content_pillars: list[str] = Field(default_factory=list)
    market: str = ""
    language: str = ""
    notes: str = ""

    def to_domain(self) -> CreatorContext:
        return CreatorContext(
            creator_id=self.creator_id,
            channel_name=self.channel_name,
            brand_voice=self.brand_voice,
            target_audience=self.target_audience,
            content_pillars=list(self.content_pillars),
            market=self.market,
            language=self.language,
            notes=self.notes,
        )

    @classmethod
    def from_domain(cls, ctx: Optional[CreatorContext]) -> "CreatorContextPayload":
        """Map a persisted CreatorContext (or None) to the wire payload.

        None — i.e. the creator has never configured anything — produces
        a default-shaped payload so the frontend can always render the
        form. The frontend distinguishes "default" via the
        `is_configured` flag in CreatorContextEnvelope below.
        """
        if ctx is None:
            return cls()
        return cls(
            creator_id=ctx.creator_id,
            channel_name=ctx.channel_name,
            brand_voice=ctx.brand_voice,
            target_audience=ctx.target_audience,
            content_pillars=list(ctx.content_pillars),
            market=ctx.market,
            language=ctx.language,
            notes=ctx.notes,
        )


class CreatorContextEnvelope(BaseModel):
    """Response shape — wraps the payload with a boolean that tells the
    frontend whether the values came from the DB or are merely the
    defaults. Keeps the empty-state UX trivial."""
    is_configured: bool
    creator_context: CreatorContextPayload


@router.get("/creator-context", response_model=CreatorContextEnvelope)
def get_settings_creator_context() -> CreatorContextEnvelope:
    """Return the persisted CreatorContext (or defaults when none).

    Never 404 — the response always carries a valid envelope so the
    frontend renders the same form for both empty and configured states.
    """
    try:
        ctx = get_creator_context()
    except Exception as exc:
        # Repo helpers already swallow exceptions, but belt-and-braces:
        # a 500 here would block the entire Settings screen, which is a
        # worse UX than serving defaults with is_configured=False.
        raise HTTPException(status_code=500, detail=f"creator_context read failed: {exc}")
    return CreatorContextEnvelope(
        is_configured=ctx is not None and not ctx.is_empty(),
        creator_context=CreatorContextPayload.from_domain(ctx),
    )


@router.put("/creator-context", response_model=CreatorContextEnvelope)
def put_settings_creator_context(payload: CreatorContextPayload) -> CreatorContextEnvelope:
    """Persist the CreatorContext and return what was actually saved.

    Posting an empty body clears the field (every default value is
    empty / 0 / []). The repo helper handles None semantics: when the
    domain object is empty, it ends up persisted as a creator_context
    key with an empty payload, which deserialises back to an empty
    CreatorContext on read — `is_configured` will then be False.
    """
    try:
        saved = upsert_creator_context(payload.to_domain())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"creator_context write failed: {exc}")
    # upsert_creator_context returns the readback so what we send back
    # is the canonical persisted value.
    return CreatorContextEnvelope(
        is_configured=saved is not None and not saved.is_empty(),
        creator_context=CreatorContextPayload.from_domain(saved),
    )


# ── Batch 10R (MT-7 UI) — data-retention endpoints ─────────────────────


class DataRetentionPayload(BaseModel):
    """Request body / response shape for /api/settings/data-retention.

    ``job_retention_days``: 0 = retention disabled (jobs accumulate
    forever — the safe default), 1-365 = jobs older than N days are
    pruned by the periodic cleanup loop. Values outside the range are
    clamped server-side; the FE renders the clamped value back.
    """
    model_config = ConfigDict(extra="ignore")

    job_retention_days: int = Field(default=0, ge=0, le=365)


class DataRetentionEnvelope(BaseModel):
    """Response shape — like CreatorContextEnvelope, carries an
    ``is_configured`` flag so the FE distinguishes "user picked 0
    deliberately" from "first boot, no setting persisted yet"."""
    is_configured: bool
    data_retention: DataRetentionPayload


@router.get("/data-retention", response_model=DataRetentionEnvelope)
def get_settings_data_retention() -> DataRetentionEnvelope:
    """Return the persisted ``job_retention_days`` or 0 default.

    Never 404 — like /creator-context, the response carries a valid
    envelope for both empty and configured states.
    """
    try:
        days = get_job_retention_days()
    except Exception as exc:  # pragma: no cover — repo helper is defensive
        raise HTTPException(status_code=500, detail=f"data_retention read failed: {exc}")
    return DataRetentionEnvelope(
        is_configured=days is not None,
        data_retention=DataRetentionPayload(job_retention_days=days or 0),
    )


@router.put("/data-retention", response_model=DataRetentionEnvelope)
def put_settings_data_retention(payload: DataRetentionPayload) -> DataRetentionEnvelope:
    """Persist ``job_retention_days`` and return what was actually saved.

    Out-of-range values are clamped by Pydantic (ge=0, le=365) before
    they reach the repo. The repo clamps again as a safety net so a
    manually-edited DB blob can't push the cleanup loop into deleting
    too much. ``is_configured`` is True after any successful PUT.
    """
    try:
        saved = upsert_job_retention_days(payload.job_retention_days)
    except Exception as exc:  # pragma: no cover — repo helper is defensive
        raise HTTPException(status_code=500, detail=f"data_retention write failed: {exc}")
    return DataRetentionEnvelope(
        is_configured=saved is not None,
        data_retention=DataRetentionPayload(job_retention_days=saved or 0),
    )
