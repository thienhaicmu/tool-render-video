"""Migration 0002: rewrite stored payload_json groq_* keys to llm_* canonical keys.

Sprint 5.4 (Sub-B): permanently translate the legacy ``groq_*`` aliases that
the ``_coerce_groq_to_llm`` Pydantic validator at ``schemas.py:466-482``
re-maps every replay. Once every existing DB row has been migrated, the
validator + alias fields become provably dead and can be retired in a
follow-up sprint (see ``docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md``).

Mapping is bit-identical to the validator semantics: copy the groq value
into the llm key only when the llm key is missing or NULL; otherwise leave
the llm value untouched (validator's ``if self.llm_* is None`` guard).
After the copy, the groq alias key is deleted from payload_json so the
column reflects the new canonical shape.

Two groq_* keys deliberately stay in payload_json:
  - ``groq_only_mode`` — has no llm_* equivalent.
  - ``groq_api_key``   — ``groq`` remains a valid LLM provider in
                          ``schemas.py:386``, so the per-provider key
                          is still live input. Not a migration target.

Sacred Contract #2 honoured: behavior is preserved 1:1 — every replayed
RenderRequest deserializes to the same model_dump() before and after
the migration (pinned by test 7 in
``tests/test_migration_0002_groq_to_llm.py``).

Sacred Contract #7 honoured: additive in column terms (no DROP, RENAME,
or ALTER). Only mutates payload_json content. Each migration runs inside
the runner's BEGIN/commit/rollback block, so a mid-pass crash rolls back
to the pre-migration state and next startup retries from scratch.

Idempotency: the ``schema_versions`` runner sentinel skips the migration
on every subsequent startup. The body itself is also idempotent — a
second pass on already-migrated payloads is a no-op because the only
condition that triggers a write is ``groq_key in payload``, and that
key was deleted by the first pass.

NULL/malformed payload_json is silent-skipped at DEBUG level. The
migration must never crash the runner on a row Pydantic would later
tolerate via ``extra="ignore"``.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any


VERSION = 2
NAME = "jobs_rewrite_groq_to_llm"

# Bit-identical to the (groq_*, llm_*) pairs in
# backend/app/models/schemas.py:466-482.
_MAPPING: tuple[tuple[str, str], ...] = (
    ("groq_analysis_enabled",   "llm_enabled"),
    ("groq_model",              "llm_model"),
    ("groq_content_language",   "llm_language"),
    ("groq_min_quality_score",  "llm_min_quality"),
    ("groq_selection_strategy", "llm_mode"),
)

logger = logging.getLogger(__name__)


def _rewrite_payload(payload: dict[str, Any]) -> bool:
    """Apply the groq_*→llm_* coercion in place.

    Returns True iff the payload was mutated (any groq_* key was present).
    """
    mutated = False
    for groq_key, llm_key in _MAPPING:
        if groq_key not in payload:
            continue
        # Validator semantics: copy only when the canonical llm key is
        # missing or explicitly None. An existing llm_* value (even False
        # or 0.0) is preserved as user intent.
        if payload.get(llm_key) is None:
            payload[llm_key] = payload[groq_key]
        del payload[groq_key]
        mutated = True
    return mutated


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    # Defensive: this migration runs after init_db() builds the baseline
    # jobs table, so the table is guaranteed to exist. Still guard against
    # exotic fixtures (e.g. a test DB seeded without the jobs table at all).
    tables = {row[0] for row in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "jobs" not in tables:
        return

    cur.execute("SELECT job_id, payload_json FROM jobs")
    rows = cur.fetchall()

    updated = 0
    skipped = 0
    for job_id, payload_text in rows:
        if not payload_text:
            skipped += 1
            continue
        try:
            payload = json.loads(payload_text)
        except (TypeError, ValueError):
            # Malformed JSON — leave untouched. Pydantic deserialize will
            # surface the issue (or extra="ignore" will silently drop it)
            # at the next replay attempt.
            logger.debug("0002_jobs_rewrite_groq_to_llm: skipping malformed payload_json for job_id=%s", job_id)
            skipped += 1
            continue
        if not isinstance(payload, dict):
            skipped += 1
            continue

        if not _rewrite_payload(payload):
            skipped += 1
            continue

        cur.execute(
            "UPDATE jobs SET payload_json = ? WHERE job_id = ?",
            (json.dumps(payload, ensure_ascii=False), job_id),
        )
        updated += 1

    logger.info(
        "0002_jobs_rewrite_groq_to_llm: updated=%d skipped=%d total=%d",
        updated, skipped, len(rows),
    )
