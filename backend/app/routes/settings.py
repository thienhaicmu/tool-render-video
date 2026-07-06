"""
routes/settings.py — User-facing settings endpoints.

Ships GET/PUT /api/settings/creator-context so the frontend Settings
screen can read and persist the CreatorContext (the read path is wired
into the LLM stage's editorial hint).

Design notes:
- The route is intentionally separated from /api/channels because
  channels are per-channel-folder configuration; CreatorContext is the
  app-wide creator persona (singleton creator_prefs row). This may later
  be extended with multi-creator routing.
- Request body uses a Pydantic model so FastAPI emits clean OpenAPI
  docs and rejects garbage payloads with 422. The Pydantic model
  mirrors the CreatorContext dataclass field-for-field; defaults
  exactly match so an empty PUT body wipes the persisted context.
- GET always returns 200 with a JSON body — never 404. An unconfigured
  creator returns the default-shaped object so the frontend can render
  the form unconditionally.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.creator_repo import (
    get_creator_context,
    get_creator_context_for_channel,
    get_default_output_dir,
    get_job_retention_days,
    get_performance_prefs,
    get_render_defaults,
    get_stock_keys,
    upsert_creator_context,
    upsert_creator_context_for_channel,
    upsert_default_output_dir,
    upsert_job_retention_days,
    upsert_performance_prefs,
    upsert_render_defaults,
    upsert_stock_keys,
)
from app.domain.creator_context import CreatorContext


router = APIRouter(prefix="/api/settings", tags=["settings"])


class CreatorContextPayload(BaseModel):
    """Request body / response shape for /api/settings/creator-context.

    Mirrors `app.domain.creator_context.CreatorContext` 1:1. Defaults
    exactly match so a PUT with `{}` clears every field. extra="ignore"
    protects against unknown payload keys from older / newer clients —
    the same backward-compat pattern used on PrepareSourceRequest.
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
def get_settings_creator_context(channel_code: str = "") -> CreatorContextEnvelope:
    """Return the persisted CreatorContext (or defaults when none).

    When channel_code is provided, returns the per-channel row (falling
    back to the global singleton when none exists). Empty channel_code
    (default) returns the global singleton — backward compatible.

    Never 404 — the response always carries a valid envelope so the
    frontend renders the same form for both empty and configured states.
    """
    try:
        ctx = (
            get_creator_context_for_channel(channel_code)
            if channel_code
            else get_creator_context()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"creator_context read failed: {exc}")
    return CreatorContextEnvelope(
        is_configured=ctx is not None and not ctx.is_empty(),
        creator_context=CreatorContextPayload.from_domain(ctx),
    )


@router.put("/creator-context", response_model=CreatorContextEnvelope)
def put_settings_creator_context(
    payload: CreatorContextPayload, channel_code: str = ""
) -> CreatorContextEnvelope:
    """Persist the CreatorContext and return what was actually saved.

    When channel_code is provided, writes to the per-channel table only
    (global singleton untouched). Empty channel_code (default) writes to
    the global singleton — backward compatible.

    Posting an empty body clears the field. The repo helper handles None
    semantics: an empty domain object → is_configured=False on readback.
    """
    try:
        if channel_code:
            upsert_creator_context_for_channel(channel_code, payload.to_domain())
            saved = get_creator_context_for_channel(channel_code)
        else:
            saved = upsert_creator_context(payload.to_domain())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"creator_context write failed: {exc}")
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


# ── Output directory preference endpoints ───────────────────────────────


class OutputDirPayload(BaseModel):
    """Request body / response shape for /api/settings/output-dir.

    ``path``: absolute path to the user's preferred output directory.
    Empty string clears the setting (next render will require an explicit
    output_dir in the request payload).
    """
    model_config = ConfigDict(extra="ignore")

    path: str = ""


class OutputDirEnvelope(BaseModel):
    """Response shape — carries ``is_configured`` so the frontend can
    distinguish "not yet set" from an explicit empty path."""
    is_configured: bool
    output_dir: OutputDirPayload


@router.get("/output-dir", response_model=OutputDirEnvelope)
def get_settings_output_dir() -> OutputDirEnvelope:
    """Return the persisted default output directory.

    Never 404 — returns ``is_configured=False`` with an empty path when
    nothing has been saved yet, so the frontend can always render the
    directory picker unconditionally.
    """
    try:
        path = get_default_output_dir()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"output_dir read failed: {exc}")
    return OutputDirEnvelope(
        is_configured=bool(path),
        output_dir=OutputDirPayload(path=path or ""),
    )


@router.put("/output-dir", response_model=OutputDirEnvelope)
def put_settings_output_dir(payload: OutputDirPayload) -> OutputDirEnvelope:
    """Persist the default output directory and return what was saved.

    Sending ``{"path": ""}`` or ``{}`` clears the setting.
    """
    try:
        saved = upsert_default_output_dir(payload.path or None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"output_dir write failed: {exc}")
    return OutputDirEnvelope(
        is_configured=bool(saved),
        output_dir=OutputDirPayload(path=saved or ""),
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
    return _data_retention_envelope_after_put(saved)


# ── Performance toggles (P0 QSV encode / P3 hwaccel decode) ──────────────


def apply_performance_env(hwdecode: bool, qsv: bool) -> None:
    """Push the perf toggles into the process env that the encode helpers read
    (encoder_helpers.qsv_enabled / clip_renderer._hwdecode_enabled). Clears the
    QSV runtime-probe cache so a toggle takes effect on the next render without
    a restart. Never raises."""
    os.environ["ENABLE_HWDECODE"] = "1" if hwdecode else "0"
    os.environ["ENABLE_QSV"] = "1" if qsv else "0"
    try:
        from app.features.render.engine.encoder.encoder_helpers import qsv_runtime_ready
        qsv_runtime_ready.cache_clear()
    except Exception:
        pass


class PerformancePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    hwdecode: bool = False   # P3 — iGPU source decode (quality-neutral)
    qsv: bool = False        # P0 — iGPU QSV encode (faster; slight quality trade)


class PerformanceEnvelope(BaseModel):
    is_configured: bool
    performance: PerformancePayload


@router.get("/performance", response_model=PerformanceEnvelope)
def get_settings_performance() -> PerformanceEnvelope:
    """Return the saved perf toggles, or (when never configured) the EFFECTIVE
    env state so the UI shows the real current value (e.g. a .env ENABLE_HWDECODE=1)."""
    pref = get_performance_prefs()
    if pref is None:
        eff = PerformancePayload(
            hwdecode=os.getenv("ENABLE_HWDECODE", "0").strip() == "1",
            qsv=os.getenv("ENABLE_QSV", "0").strip() == "1",
        )
        return PerformanceEnvelope(is_configured=False, performance=eff)
    return PerformanceEnvelope(is_configured=True, performance=PerformancePayload(**pref))


@router.put("/performance", response_model=PerformanceEnvelope)
def put_settings_performance(payload: PerformancePayload) -> PerformanceEnvelope:
    """Persist the perf toggles and apply them to the live process immediately."""
    try:
        saved = upsert_performance_prefs(payload.hwdecode, payload.qsv)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"performance write failed: {exc}")
    apply_performance_env(saved["hwdecode"], saved["qsv"])
    return PerformanceEnvelope(is_configured=True, performance=PerformancePayload(**saved))


# ── P3.1-C: stock visual-provider API keys (Pexels / Pixabay) ─────────────
#
# Lets the user configure the FREE stock-image providers from the Settings UI
# instead of hand-editing .env. Keys are persisted in creator_prefs and pushed
# into os.environ (which provider_stock reads) at startup + on save.
#
# SECURITY: the raw keys are NEVER returned by GET — only "set / not set"
# booleans (reflecting the effective env, saved OR .env). PUT accepts the raw
# keys. Nothing here logs a key value.


def apply_stock_keys_env(pexels: str, pixabay: str) -> None:
    """Push the stock API keys into the process env that provider_stock reads
    (os.getenv PEXELS_API_KEY / PIXABAY_API_KEY). Only NON-EMPTY values are set —
    a blank saved value must not clobber a key provided via .env. Never raises."""
    try:
        if (pexels or "").strip():
            os.environ["PEXELS_API_KEY"] = pexels.strip()
        if (pixabay or "").strip():
            os.environ["PIXABAY_API_KEY"] = pixabay.strip()
    except Exception:
        pass


class StockKeysPayload(BaseModel):
    """PUT body — the raw stock API keys. Empty string = leave as-is (a blank
    save never wipes a .env-provided key). extra='ignore' for fwd/back-compat."""
    model_config = ConfigDict(extra="ignore")
    pexels: str = ""
    pixabay: str = ""


class StockKeysStatus(BaseModel):
    """GET/PUT response — masked. Booleans only; the raw keys are never sent."""
    pexels_set: bool
    pixabay_set: bool


def _stock_keys_status() -> StockKeysStatus:
    """Effective set/not-set from the live env (covers both a saved pref applied
    at startup AND a .env-provided key)."""
    return StockKeysStatus(
        pexels_set=bool((os.getenv("PEXELS_API_KEY") or "").strip()),
        pixabay_set=bool((os.getenv("PIXABAY_API_KEY") or "").strip()),
    )


@router.get("/stock-keys", response_model=StockKeysStatus)
def get_settings_stock_keys() -> StockKeysStatus:
    """Report whether each stock key is configured (never returns the raw key)."""
    return _stock_keys_status()


@router.put("/stock-keys", response_model=StockKeysStatus)
def put_settings_stock_keys(payload: StockKeysPayload) -> StockKeysStatus:
    """Persist + apply the stock keys, then return the masked status. A blank
    field leaves the existing key untouched (see apply_stock_keys_env)."""
    # Merge: a blank field keeps the previously-SAVED key rather than wiping it
    # (matches "empty = leave as-is"). A key that lives only in .env is not copied
    # into the saved blob — apply_stock_keys_env's non-empty guard preserves it.
    existing = get_stock_keys() or {"pexels": "", "pixabay": ""}
    pexels = payload.pexels.strip() or existing.get("pexels", "")
    pixabay = payload.pixabay.strip() or existing.get("pixabay", "")
    try:
        saved = upsert_stock_keys(pexels, pixabay)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"stock-keys write failed: {exc}")
    apply_stock_keys_env(saved["pexels"], saved["pixabay"])
    return _stock_keys_status()


def _data_retention_envelope_after_put(saved) -> "DataRetentionEnvelope":
    return DataRetentionEnvelope(
        is_configured=saved is not None,
        data_retention=DataRetentionPayload(job_retention_days=saved or 0),
    )


# ── S2.1 (Sprint 2 UX) — render-defaults endpoints ─────────────────────
#
# Lets the Configure step of the render workflow pre-fill from saved
# user preferences instead of forcing a re-pick every render. Wire
# shape is a strict subset of RenderRequestPublic so it can be merged
# directly into the FE form state without any field-name translation.
#
# All fields are Optional and default to None — Sacred Contract #2 is
# unaffected because this payload is NEVER merged into RenderRequest
# server-side. The FE applies it as form pre-fill only; the actual
# render submit still validates against RenderRequestPublic.


class RenderDefaultsPayload(BaseModel):
    """User-presetable subset of RenderRequestPublic.

    Every field is Optional → null means "no preference, ask user". A
    PUT with `{}` clears the entire saved-defaults blob. Unknown keys
    are silently ignored (extra='ignore') so older / newer FE builds
    don't break each other.
    """
    model_config = ConfigDict(extra="ignore")

    # Aspect / format
    aspect_ratio: Optional[str] = None       # "9:16" | "16:9" | "1:1" | "3:4" | "4:5" | ...
    preset: Optional[str] = None             # e.g. "viral" | "story" | "tutorial"

    # Voice / TTS
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None

    # Subtitle
    subtitle_style: Optional[str] = None

    # AI provider
    llm_provider: Optional[str] = None       # "gemini" | "openai" | "claude"

    def to_dict(self) -> dict:
        """Return a dict with only non-null, non-empty fields."""
        return {
            k: v for k, v in self.model_dump().items()
            if v is not None and v != ""
        }


class RenderDefaultsEnvelope(BaseModel):
    """Response shape — `is_configured` lets the FE distinguish "user
    deliberately cleared" (False, empty payload) from "first boot,
    nothing saved" (also False, also empty)."""
    is_configured: bool
    render_defaults: RenderDefaultsPayload


@router.get("/render-defaults", response_model=RenderDefaultsEnvelope)
def get_settings_render_defaults() -> RenderDefaultsEnvelope:
    """Return the persisted render-defaults blob or empty defaults.

    Never 404 — like the sibling settings endpoints, always returns a
    valid envelope so the FE can render the form unconditionally.
    """
    try:
        stored = get_render_defaults()
    except Exception as exc:  # pragma: no cover — repo helper is defensive
        raise HTTPException(status_code=500, detail=f"render_defaults read failed: {exc}")
    if stored:
        return RenderDefaultsEnvelope(
            is_configured=True,
            render_defaults=RenderDefaultsPayload(**stored),
        )
    return RenderDefaultsEnvelope(
        is_configured=False,
        render_defaults=RenderDefaultsPayload(),
    )


@router.put("/render-defaults", response_model=RenderDefaultsEnvelope)
def put_settings_render_defaults(payload: RenderDefaultsPayload) -> RenderDefaultsEnvelope:
    """Persist render-defaults and return what was actually saved.

    A PUT with `{}` (or every field null) clears the saved defaults.
    """
    try:
        saved = upsert_render_defaults(payload.to_dict())
    except Exception as exc:  # pragma: no cover — repo helper is defensive
        raise HTTPException(status_code=500, detail=f"render_defaults write failed: {exc}")
    if saved:
        return RenderDefaultsEnvelope(
            is_configured=True,
            render_defaults=RenderDefaultsPayload(**saved),
        )
    return RenderDefaultsEnvelope(
        is_configured=False,
        render_defaults=RenderDefaultsPayload(),
    )


# ── H-1: A/B scores read endpoint ────────────────────────────────────────────

@router.get("/scores/{channel_code}")
def get_channel_scores(channel_code: str, limit: int = 100, offset: int = 0) -> list:
    """Return recent A/B scores for a channel (newest first, max 500 rows)."""
    from app.db.ab_scores_repo import list_channel_scores
    return list_channel_scores(channel_code, limit=min(limit, 500), offset=max(offset, 0))


# ── L-B: Channel creator-context CRUD ────────────────────────────────────────

@router.get("/channels/creator-context")
def get_creator_context_channels() -> list:
    """List all channels that have a per-channel creator context configured."""
    from app.db.creator_repo import list_creator_context_channels
    return list_creator_context_channels()


@router.delete("/creator-context/{channel_code}")
def delete_channel_creator_context(channel_code: str) -> dict:
    """Remove the per-channel creator context row for a channel."""
    from app.db.creator_repo import delete_creator_context_for_channel
    if not delete_creator_context_for_channel(channel_code):
        raise HTTPException(status_code=404, detail=f"No per-channel context found for: {channel_code}")
    return {"channel_code": channel_code, "deleted": True}


# ── K-B: Whisper per-channel endpoints ───────────────────────────────────────

_ALLOWED_WHISPER_MODELS = {
    "auto",
    "tiny", "tiny.en",
    "base", "base.en",
    "small", "small.en",
    "medium", "medium.en",
    "large", "large-v1", "large-v2", "large-v3", "large-v3-turbo",
    "turbo",
}


class WhisperModelPayload(BaseModel):
    whisper_model: str

    @field_validator("whisper_model")
    @classmethod
    def _validate_whisper_model(cls, v: str) -> str:
        m = str(v).strip()
        if not m or m not in _ALLOWED_WHISPER_MODELS:
            raise ValueError(
                f"Unknown whisper_model {m!r}. Allowed: {sorted(_ALLOWED_WHISPER_MODELS)}"
            )
        return m


@router.get("/whisper/{channel_code}")
def get_channel_whisper_model(channel_code: str) -> dict:
    """Return the preferred whisper model for a channel, or null when not set."""
    from app.db.creator_repo import get_whisper_model_for_channel
    return {"channel_code": channel_code, "whisper_model": get_whisper_model_for_channel(channel_code)}


@router.put("/whisper/{channel_code}")
def put_channel_whisper_model(channel_code: str, payload: WhisperModelPayload) -> dict:
    """Persist preferred whisper model for a channel and return the saved value."""
    from app.db.creator_repo import upsert_whisper_model_for_channel, get_whisper_model_for_channel
    upsert_whisper_model_for_channel(channel_code, payload.whisper_model)
    return {"channel_code": channel_code, "whisper_model": get_whisper_model_for_channel(channel_code)}


# ── J-B: Channel list endpoint ───────────────────────────────────────────────

@router.get("/channels")
def get_channels() -> list:
    """Return distinct channels that have A/B score rows, newest activity first."""
    from app.db.ab_scores_repo import list_channels
    return list_channels()


# ── J-A: Channel score summary endpoint ──────────────────────────────────────

@router.get("/scores/{channel_code}/summary")
def get_channel_score_summary(
    channel_code: str, since: Optional[str] = None
) -> list:
    """Return per-structure_bias aggregate scores for a channel.

    ``since``: optional ISO-8601 datetime string to filter by ``created_at``.
    When omitted, all rows for the channel are included.
    """
    from app.db.ab_scores_repo import channel_score_summary
    return channel_score_summary(channel_code, since=since)


# ── K-A: Score delete endpoint ────────────────────────────────────────────────

@router.delete("/scores/{job_id}")
def delete_scores_for_job(job_id: str) -> dict:
    """Delete all A/B score rows for a specific job. Returns count deleted."""
    from app.db.ab_scores_repo import delete_job_scores
    deleted = delete_job_scores(job_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No score rows found for job: {job_id}")
    return {"job_id": job_id, "deleted": deleted}


# ── H-3: A/B score feedback rating PATCH ─────────────────────────────────────

class FeedbackRatingPayload(BaseModel):
    rating: int


@router.patch("/scores/{job_id}/{part_no}/rating")
def patch_score_feedback_rating(
    job_id: str, part_no: int, payload: FeedbackRatingPayload
) -> dict:
    """Set user feedback rating (0–5) on a specific render output score row."""
    from app.db.ab_scores_repo import update_feedback_rating
    updated = update_feedback_rating(job_id=job_id, part_no=part_no, rating=payload.rating)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Score row not found: {job_id}/{part_no}")
    return {"job_id": job_id, "part_no": part_no, "rating": payload.rating}


# ── Clear history / reset ────────────────────────────────────────────────────

class ClearHistoryPayload(BaseModel):
    """Body for POST /api/settings/clear-history.

    ``clear_cache`` also wipes the render cache (scene/whisper/llm/etc.).
    ``preserve_active`` (default True) keeps in-flight render/download jobs so
    a running job is never orphaned — Sacred Contract #7. Settings, presets,
    and migration state are ALWAYS preserved.
    """
    model_config = ConfigDict(extra="ignore")

    clear_cache: bool = False
    preserve_active: bool = True


@router.post("/clear-history")
def clear_history_endpoint(payload: ClearHistoryPayload) -> dict:
    """Delete job/download/asset history (and optionally the render cache).

    Preserves creator settings, render presets, and schema/migration state.
    Returns per-table delete counts and (if requested) cache stats.
    """
    from app.db.history_repo import clear_history
    deleted = clear_history(preserve_active=payload.preserve_active)
    out: dict = {
        "ok": True,
        "deleted": deleted,
        "total_deleted": sum(deleted.values()),
        "preserve_active": payload.preserve_active,
    }
    if payload.clear_cache:
        from app.services.maintenance import clear_all_cache
        from app.core.config import CACHE_DIR
        out["cache"] = clear_all_cache(CACHE_DIR)
    return out
