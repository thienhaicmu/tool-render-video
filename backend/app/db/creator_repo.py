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
