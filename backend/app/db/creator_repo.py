"""creator_repo.py — singleton creator_prefs row CRUD.

Sprint 5.3 (audit 2026-06-02 P2-D9): migrated from raw get_conn() + manual
close to db_conn() context manager. Same exception-safety guarantee that
jobs_repo.py has had. After Sprint 5.4 db_conn() also auto-commits/
rollbacks, so explicit conn.commit() here is redundant — left in place
for the cleanup pass in a follow-up sprint.

Sprint 3 (RenderPlan / Creator Context Builder): adds nested
get_creator_context() / upsert_creator_context() helpers that
read/write CreatorContext JSON under the existing prefs_json blob.
No schema change — the column was already TEXT JSON, so we just store
the new payload at a nested key. Backward compat: prefs that omit
"creator_context" return None and the AI layer behaves identically to
pre-Sprint-3.
"""
import json
import logging
from typing import Optional

from app.db.connection import (
    _json_dumps,
    _json_loads,
    db_conn,
)
from app.domain.creator_context import CreatorContext


logger = logging.getLogger("app.db")


# Key inside prefs_json under which the CreatorContext payload is stored.
# Kept as a module constant so future refactors / tests have one stable
# string to grep for.
_CREATOR_CONTEXT_KEY = "creator_context"

# Batch 10R (MT-7 UI): nested key for the data-retention settings the
# Settings screen writes. Stores ``{"job_retention_days": int}`` (0 =
# disabled). The periodic cleanup loop in main.py reads from here on
# each tick and falls back to the ``JOB_RETENTION_DAYS`` env var when
# the key is absent (first-boot / no UI configuration).
_DATA_RETENTION_KEY = "data_retention"


def get_creator_prefs() -> dict:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT prefs_json FROM creator_prefs WHERE id = 1"
        ).fetchone()
    if not row:
        return {}
    return _json_loads(row["prefs_json"], default={})


def upsert_creator_prefs(prefs: dict) -> dict:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO creator_prefs (id, prefs_json, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                prefs_json = excluded.prefs_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (_json_dumps(prefs),),
        )
        conn.commit()
    return get_creator_prefs()


# ── Sprint 3 — CreatorContext helpers ────────────────────────────────────


def get_creator_context() -> Optional[CreatorContext]:
    """Return the persisted CreatorContext or None when none is configured.

    Backward-compat: when the prefs blob predates Sprint 3 (no
    `creator_context` key) the caller sees None, and the AI layer
    behaves identically to the pre-Sprint-3 pipeline. Never raises;
    logs a warning and returns None on any DB or deserialise error so
    a transient repo failure cannot crash a live render.
    """
    try:
        prefs = get_creator_prefs()
    except Exception as exc:
        logger.warning("get_creator_context: get_creator_prefs failed: %s", exc)
        return None
    nested = prefs.get(_CREATOR_CONTEXT_KEY)
    if nested is None:
        return None
    # The nested value is already a dict (because prefs_json round-trips
    # through json). Convert by way of from_json so we reuse the same
    # defensive coercion path used everywhere else.
    try:
        return CreatorContext.from_json(_json_dumps(nested))
    except Exception as exc:
        logger.warning("get_creator_context: deserialise failed: %s", exc)
        return None


def upsert_creator_context(context: Optional[CreatorContext]) -> Optional[CreatorContext]:
    """Persist a CreatorContext under the singleton creator_prefs row.

    Passing None clears the field (nested key removed from prefs_json).
    Other top-level prefs keys are preserved verbatim. Never raises;
    returns the value that was actually persisted (or None on error).
    """
    try:
        current = get_creator_prefs()
    except Exception as exc:
        logger.warning("upsert_creator_context: read failed: %s", exc)
        current = {}
    if context is None:
        current.pop(_CREATOR_CONTEXT_KEY, None)
    else:
        # Round-trip through to_json then back to dict so the persisted
        # shape is exactly what from_json would consume on read. Keeps
        # the on-disk blob normalised even if the dataclass picks up
        # transient values that don't survive serialisation.
        try:
            current[_CREATOR_CONTEXT_KEY] = _json_loads(context.to_json(), default={})
        except Exception as exc:
            logger.warning("upsert_creator_context: serialise failed: %s", exc)
            return None
    try:
        upsert_creator_prefs(current)
    except Exception as exc:
        logger.warning("upsert_creator_context: write failed: %s", exc)
        return None
    return get_creator_context()


# ── Sprint I-B — Per-channel CreatorContext ──────────────────────────────


def get_creator_context_for_channel(channel_code: str) -> Optional[CreatorContext]:
    """Return CreatorContext for channel_code, falling back to global singleton.

    Priority:
      1. creator_prefs_channel WHERE channel_code = ?
      2. global get_creator_context() (existing singleton)
      3. None

    Never raises — returns None on any DB or deserialise error.
    """
    try:
        if channel_code:
            with db_conn() as conn:
                row = conn.execute(
                    "SELECT prefs_json FROM creator_prefs_channel WHERE channel_code = ?",
                    (channel_code,),
                ).fetchone()
            if row:
                data = json.loads(row["prefs_json"] or "{}")
                ctx = CreatorContext.from_json(json.dumps(data.get(_CREATOR_CONTEXT_KEY) or {}))
                if ctx is not None and not ctx.is_empty():
                    return ctx
        return get_creator_context()
    except Exception as exc:
        logger.warning("get_creator_context_for_channel(%r) failed: %s", channel_code, exc)
        return None


_WHISPER_MODEL_KEY = "whisper_model"


def get_whisper_model_for_channel(channel_code: str) -> Optional[str]:
    """Return the preferred whisper model for a channel, or None when not set.

    Reads from creator_prefs_channel.prefs_json[whisper_model].
    Never raises — returns None on any DB or parse error.
    """
    try:
        if not channel_code:
            return None
        with db_conn() as conn:
            row = conn.execute(
                "SELECT prefs_json FROM creator_prefs_channel WHERE channel_code = ?",
                (channel_code,),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["prefs_json"] or "{}")
        model = (data.get(_WHISPER_MODEL_KEY) or "").strip()
        return model if model else None
    except Exception as exc:
        logger.warning("get_whisper_model_for_channel(%r) failed: %s", channel_code, exc)
        return None


def upsert_whisper_model_for_channel(channel_code: str, model: str) -> None:
    """Persist preferred whisper model for a channel.

    Merges into the existing creator_prefs_channel row (preserving
    other keys like creator_context). Swallows exceptions.
    """
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT prefs_json FROM creator_prefs_channel WHERE channel_code = ?",
                (channel_code,),
            ).fetchone()
        data = json.loads(row["prefs_json"] or "{}") if row else {}
        data[_WHISPER_MODEL_KEY] = model.strip()
        with db_conn() as conn:
            conn.execute(
                """INSERT INTO creator_prefs_channel (channel_code, prefs_json, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(channel_code) DO UPDATE SET
                       prefs_json = excluded.prefs_json,
                       updated_at = datetime('now')""",
                (channel_code, json.dumps(data)),
            )
    except Exception as exc:
        logger.warning("upsert_whisper_model_for_channel(%r) failed: %s", channel_code, exc)


def list_creator_context_channels() -> list:
    """Return channel_codes that have a row in creator_prefs_channel, newest first.

    Never raises — returns [] on any DB error.
    """
    try:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT channel_code FROM creator_prefs_channel ORDER BY updated_at DESC"
            ).fetchall()
            return [r["channel_code"] for r in rows]
    except Exception as exc:
        logger.warning("list_creator_context_channels() failed: %s", exc)
        return []


def delete_creator_context_for_channel(channel_code: str) -> bool:
    """Delete the creator_prefs_channel row for channel_code.

    Returns True when a row was found and deleted, False otherwise.
    Never raises.
    """
    try:
        with db_conn() as conn:
            cur = conn.execute(
                "DELETE FROM creator_prefs_channel WHERE channel_code = ?",
                (channel_code,),
            )
            return (cur.rowcount or 0) > 0
    except Exception as exc:
        logger.warning("delete_creator_context_for_channel(%r) failed: %s", channel_code, exc)
        return False


def upsert_creator_context_for_channel(
    channel_code: str, context: CreatorContext
) -> None:
    """Write per-channel creator context. Does NOT touch the global singleton.

    Swallows exceptions so a DB failure can never propagate to the caller
    (Settings endpoint, render pipeline).
    """
    try:
        prefs = {_CREATOR_CONTEXT_KEY: json.loads(context.to_json())}
        with db_conn() as conn:
            conn.execute(
                """INSERT INTO creator_prefs_channel (channel_code, prefs_json, updated_at)
                   VALUES (?, ?, datetime('now'))
                   ON CONFLICT(channel_code) DO UPDATE SET
                       prefs_json = excluded.prefs_json,
                       updated_at = datetime('now')""",
                (channel_code, json.dumps(prefs)),
            )
    except Exception as exc:
        logger.warning("upsert_creator_context_for_channel(%r) failed: %s", channel_code, exc)


# ── Output directory preference ─────────────────────────────────────────

_OUTPUT_DIR_KEY = "output_dir"


def get_default_output_dir() -> Optional[str]:
    """Return the persisted default output directory or None when not set.

    Never raises — returns None on any DB or parse error so a transient
    failure cannot break the Settings screen.
    """
    try:
        prefs = get_creator_prefs()
    except Exception as exc:
        logger.warning("get_default_output_dir: read failed: %s", exc)
        return None
    nested = prefs.get(_OUTPUT_DIR_KEY)
    if not isinstance(nested, dict):
        return None
    raw = nested.get("path")
    if not raw or not str(raw).strip():
        return None
    return str(raw).strip()


def upsert_default_output_dir(path: Optional[str]) -> Optional[str]:
    """Persist the default output directory. None or empty string clears the setting.

    Returns the value that was actually persisted, or None on error.
    Other top-level prefs keys are preserved verbatim.
    """
    try:
        current = get_creator_prefs()
    except Exception as exc:
        logger.warning("upsert_default_output_dir: read failed: %s", exc)
        current = {}
    if not path or not str(path).strip():
        current.pop(_OUTPUT_DIR_KEY, None)
    else:
        current[_OUTPUT_DIR_KEY] = {"path": str(path).strip()}
    try:
        upsert_creator_prefs(current)
    except Exception as exc:
        logger.warning("upsert_default_output_dir: write failed: %s", exc)
        return None
    return get_default_output_dir()


# ── Batch 10R (MT-7 UI) — data-retention helpers ────────────────────────

# Hard bounds the API enforces. 0 = retention disabled (Sacred Contract
# safety net: a fresh DB starts at 0 so jobs accumulate until the user
# opts in). 365 caps the upper bound at 1 year — past that, RAG of
# render_plan_json starts to dominate disk usage per the audit.
_RETENTION_MIN_DAYS = 0
_RETENTION_MAX_DAYS = 365


def get_job_retention_days() -> Optional[int]:
    """Return the persisted ``job_retention_days`` (0–365) or None when
    the user hasn't configured anything via the Settings screen.

    Caller is expected to fall back to the ``JOB_RETENTION_DAYS`` env
    var when this returns None. Never raises — defensive about every
    DB / JSON / type-coercion step so a transient repo failure can't
    crash the cleanup loop.
    """
    try:
        prefs = get_creator_prefs()
    except Exception as exc:
        logger.warning("get_job_retention_days: read failed: %s", exc)
        return None
    nested = prefs.get(_DATA_RETENTION_KEY)
    if not isinstance(nested, dict):
        return None
    raw = nested.get("job_retention_days")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    # Clamp on read too — a manually-edited DB blob shouldn't trip the
    # cleanup loop into deleting too much.
    return max(_RETENTION_MIN_DAYS, min(_RETENTION_MAX_DAYS, value))


def upsert_job_retention_days(days: int) -> Optional[int]:
    """Persist ``job_retention_days`` under the singleton creator_prefs
    row. Other top-level prefs keys are preserved verbatim.

    Returns the value that was actually persisted (after clamping), or
    None on error. Setting 0 is "retention disabled" — kept as 0 rather
    than removing the key so the UI can show the user their last
    setting (0 is a deliberate choice).
    """
    clamped = max(_RETENTION_MIN_DAYS, min(_RETENTION_MAX_DAYS, int(days)))
    try:
        current = get_creator_prefs()
    except Exception as exc:
        logger.warning("upsert_job_retention_days: read failed: %s", exc)
        current = {}
    nested = current.get(_DATA_RETENTION_KEY)
    if not isinstance(nested, dict):
        nested = {}
    nested["job_retention_days"] = clamped
    current[_DATA_RETENTION_KEY] = nested
    try:
        upsert_creator_prefs(current)
    except Exception as exc:
        logger.warning("upsert_job_retention_days: write failed: %s", exc)
        return None
    return get_job_retention_days()
