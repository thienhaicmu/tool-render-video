"""Sprint 5.4 (Sub-B) — test migration 0002: jobs.payload_json groq_*→llm_* rewrite.

Pins:
- 5-pair mapping bit-identical to _coerce_groq_to_llm validator
- llm_* value already set wins (validator semantics)
- NULL / empty / malformed / non-dict payload_json silently skipped
- groq_only_mode + groq_api_key preserved (no llm_ equivalent)
- Idempotent — second pass is a no-op
- Runner discovery + schema_versions sentinel
- Replay parity — RenderRequest(**pre).model_dump() == RenderRequest(**post).model_dump()
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "db"
    / "migration_steps"
    / "0002_jobs_rewrite_groq_to_llm.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0002", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            channel_code TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT DEFAULT '',
            progress_percent INTEGER DEFAULT 0,
            message TEXT DEFAULT '',
            payload_json TEXT,
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _insert_job(conn: sqlite3.Connection, job_id: str, payload: object) -> None:
    """Insert one row. payload may be a dict (json-dumped), a string (stored raw),
    or None (NULL payload_json)."""
    if payload is None:
        text = None
    elif isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload)
    conn.execute(
        "INSERT INTO jobs (job_id, kind, channel_code, status, payload_json) VALUES (?, ?, ?, ?, ?)",
        (job_id, "render", "test", "completed", text),
    )
    conn.commit()


def _get_payload(conn: sqlite3.Connection, job_id: str):
    row = conn.execute(
        "SELECT payload_json FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return json.loads(row[0])


# ---------------------------------------------------------------------------
# Section 1: identity sanity
# ---------------------------------------------------------------------------


def test_migration_version_and_name():
    m = _load_migration()
    assert m.VERSION == 2
    assert m.NAME == "jobs_rewrite_groq_to_llm"


# ---------------------------------------------------------------------------
# Section 2: mapping bit-identical to validator
# ---------------------------------------------------------------------------


def test_each_groq_pair_is_translated():
    """Each (groq_*, llm_*) pair: groq present, llm absent → llm gets groq value, groq deleted."""
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", {"groq_analysis_enabled": True})
        _insert_job(conn, "j2", {"groq_model": "groq/llama-3"})
        _insert_job(conn, "j3", {"groq_content_language": "vi"})
        _insert_job(conn, "j4", {"groq_min_quality_score": 0.78})
        _insert_job(conn, "j5", {"groq_selection_strategy": "top_3"})

        m.up(conn)

        assert _get_payload(conn, "j1") == {"llm_enabled": True}
        assert _get_payload(conn, "j2") == {"llm_model": "groq/llama-3"}
        assert _get_payload(conn, "j3") == {"llm_language": "vi"}
        assert _get_payload(conn, "j4") == {"llm_min_quality": 0.78}
        assert _get_payload(conn, "j5") == {"llm_mode": "top_3"}
    finally:
        conn.close()


def test_existing_llm_value_wins_over_groq():
    """If llm_* is already set, validator does NOT overwrite. Migration must match."""
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", {
            "groq_analysis_enabled": True,
            "llm_enabled": False,
        })
        _insert_job(conn, "j2", {
            "groq_model": "groq/old",
            "llm_model": "claude-sonnet",
        })

        m.up(conn)

        # llm_enabled stays False even though groq_analysis_enabled was True.
        payload = _get_payload(conn, "j1")
        assert payload == {"llm_enabled": False}
        # llm_model stays claude-sonnet; groq_model dropped.
        payload2 = _get_payload(conn, "j2")
        assert payload2 == {"llm_model": "claude-sonnet"}
    finally:
        conn.close()


def test_explicit_none_llm_value_is_overwritten():
    """llm_* explicitly null in payload counts as absent (matches validator `is None` check)."""
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", {
            "groq_analysis_enabled": True,
            "llm_enabled": None,
        })
        m.up(conn)
        payload = _get_payload(conn, "j1")
        assert payload == {"llm_enabled": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Section 3: defensive — NULL / empty / malformed / non-dict
# ---------------------------------------------------------------------------


def test_null_payload_is_skipped():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", None)
        m.up(conn)
        assert _get_payload(conn, "j1") is None
    finally:
        conn.close()


def test_empty_string_payload_is_skipped():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", "")
        m.up(conn)
        row = conn.execute("SELECT payload_json FROM jobs WHERE job_id='j1'").fetchone()
        assert row[0] == ""
    finally:
        conn.close()


def test_malformed_json_payload_is_skipped():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", "{not json")
        m.up(conn)
        row = conn.execute("SELECT payload_json FROM jobs WHERE job_id='j1'").fetchone()
        assert row[0] == "{not json"
    finally:
        conn.close()


def test_non_dict_payload_is_skipped():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", "[1, 2, 3]")
        m.up(conn)
        row = conn.execute("SELECT payload_json FROM jobs WHERE job_id='j1'").fetchone()
        assert row[0] == "[1, 2, 3]"
    finally:
        conn.close()


def test_payload_with_no_groq_keys_is_untouched():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", {"llm_enabled": True, "render_profile": "quality"})
        m.up(conn)
        assert _get_payload(conn, "j1") == {"llm_enabled": True, "render_profile": "quality"}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Section 4: keys without llm_ equivalent must be preserved
# ---------------------------------------------------------------------------


def test_groq_only_mode_and_api_key_preserved():
    """groq_only_mode and groq_api_key have no llm_ equivalent — must remain in payload."""
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", {
            "groq_only_mode": True,
            "groq_api_key": "sk-test",
            "groq_analysis_enabled": True,
        })
        m.up(conn)
        payload = _get_payload(conn, "j1")
        # groq_analysis_enabled was translated and removed.
        # groq_only_mode + groq_api_key stay.
        assert payload == {
            "groq_only_mode": True,
            "groq_api_key": "sk-test",
            "llm_enabled": True,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Section 5: idempotency
# ---------------------------------------------------------------------------


def test_second_pass_is_noop():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        _insert_job(conn, "j1", {"groq_analysis_enabled": True})
        m.up(conn)
        first = _get_payload(conn, "j1")
        m.up(conn)
        second = _get_payload(conn, "j1")
        assert first == second == {"llm_enabled": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Section 6: runner integration + schema_versions sentinel
# ---------------------------------------------------------------------------


def test_runner_discovers_and_records_version():
    """Invoke via run_pending_migrations; assert version 2 ends up in schema_versions."""
    from app.db.migrations import run_pending_migrations, applied_versions

    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)
        result = run_pending_migrations(conn)
        assert 2 in result["applied"]
        assert 2 in applied_versions(conn)
        # Second invocation: skipped, not re-applied.
        result2 = run_pending_migrations(conn)
        assert 2 in result2["skipped"]
        assert 2 not in result2["applied"]
    finally:
        conn.close()


def test_migration_skipped_when_no_jobs_table():
    """Edge: empty DB without `jobs` table. Migration must no-op, not raise."""
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        # Deliberately no _seed_jobs_table.
        m.up(conn)  # must not raise
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "jobs" not in tables
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Section 7: replay parity — the load-bearing behavioral pin
# ---------------------------------------------------------------------------


def test_replay_parity_with_validator():
    """Pipeline-relevant fields (the canonical llm_* set the pipeline actually
    reads — see schemas.py:466-482) must be bit-identical between a
    RenderRequest deserialized from the pre-migration payload and one
    deserialized from the post-migration payload.

    The full model_dump() differs on the groq_* fields themselves (they
    revert to their default values once removed from payload_json), but
    no production code reads groq_* — only the validator does, and the
    migration's purpose is to make that validator a no-op. So the
    semantic contract is: post-migration llm_* fields match
    pre-migration validator-derived llm_* fields exactly."""
    from app.models.schemas import RenderRequest

    _LLM_FIELDS = (
        "llm_enabled", "llm_model", "llm_language",
        "llm_min_quality", "llm_mode",
    )

    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_jobs_table(conn)

        cases = [
            {"groq_analysis_enabled": True},
            {"groq_model": "groq/llama-3"},
            {"groq_content_language": "vi"},
            {"groq_min_quality_score": 0.78},
            {"groq_selection_strategy": "top_3"},
            {
                "groq_analysis_enabled": True,
                "groq_model": "groq/llama-3",
                "groq_content_language": "vi",
                "groq_min_quality_score": 0.78,
                "groq_selection_strategy": "top_3",
            },
            # llm-already-set guard
            {"groq_analysis_enabled": True, "llm_enabled": False},
            # mixed with unrelated fields
            {"groq_analysis_enabled": True, "render_profile": "quality"},
        ]

        for i, pre in enumerate(cases):
            job_id = f"j{i}"
            _insert_job(conn, job_id, pre)

        m.up(conn)

        for i, pre in enumerate(cases):
            job_id = f"j{i}"
            post = _get_payload(conn, job_id)
            pre_model = RenderRequest(**pre).model_dump()
            post_model = RenderRequest(**(post or {})).model_dump()
            pre_llm = {k: pre_model[k] for k in _LLM_FIELDS}
            post_llm = {k: post_model[k] for k in _LLM_FIELDS}
            assert pre_llm == post_llm, (
                f"replay parity broken for case {i}: "
                f"pre_llm={pre_llm} post_llm={post_llm} pre={pre} post={post}"
            )
    finally:
        conn.close()
