import logging

from app.core.stage import JobPartStage, JobStage
from app.db.connection import (
    _json_dumps,
    _thread_conn,
    db_conn,
)
from app.services.metrics import DB_WRITES_TOTAL

logger = logging.getLogger("app.db")


def _count_write(surface: str) -> None:
    """Perf-opt Phase 0 — emit render_db_writes_total{surface}. Never raises."""
    try:
        DB_WRITES_TOTAL.labels(surface=surface).inc()
    except Exception:
        pass


# Audit FINDING-BR05 / C06 closure (Batch 3, 2026-06-06).
#
# The Sacred Contracts #4 and #5 freeze the job-stage and per-part status
# strings. The JobStage / JobPartStage enums encode the frozen set in
# app/core/stage.py, but writers historically pass raw strings — a typo
# (`"compleated"` for "completed") would silently corrupt every consumer
# (FE labels, status filters, recovery loops) with no error from SQLite.
#
# These constants give the repo a single source of truth that the
# writers can be checked against. Validation is WARN-LEVEL, not raising,
# because:
#  - It must never break a live render. The orchestrator above expects
#    its write to succeed; a hard rejection would surface as a render
#    failure that the user can't diagnose.
#  - "kind" and ad-hoc legacy values still appear in stored payloads
#    (see Sacred Contract #2 — replay must not break). A WARN log surfaces
#    drift without crashing.
# A future migration may promote this to SQL `CHECK(status IN (...))`,
# but that requires a clean DB scan first.
_VALID_JOB_STATUSES = frozenset({
    "queued",
    "running",
    # Strategic-6 — Audit 2026-06-08 closure (Batch A V9-F5). The
    # cancel route (features/render/routers/lifecycle.py:563) writes
    # status="cancelling" as the transient state between operator
    # click and the in-process cancel event landing. Pre-Strategic-6
    # the string was written by the route but absent from the valid
    # set, so every cancel produced a WARN log line at write time and
    # the recovery loop at jobs/manager.py:328 ignored the state on
    # restart (stuck-cancelling jobs). Adding it here legitimises the
    # transient label; recover_pending_render_jobs now transitions
    # cancelling → cancelled on startup so the operator's intent
    # persists across server restarts.
    "cancelling",
    "completed",
    "completed_with_errors",
    "failed",
    "interrupted",
    "cancelled",
})
_VALID_JOB_STAGES = frozenset(s.value for s in JobStage)
_VALID_JOB_PART_STAGES = frozenset(s.value for s in JobPartStage)


def _normalize_enum_value(raw, allow_empty: bool = False) -> str:
    """Coerce a JobStage/JobPartStage enum or raw string to its string value.

    Pass-through for raw strings; ``.value`` extraction for enum members.
    Returns '' when ``raw`` is None/empty and ``allow_empty=True``.
    """
    if raw is None:
        return "" if allow_empty else ""
    if hasattr(raw, "value"):
        try:
            return str(raw.value)
        except Exception:  # pragma: no cover — defensive only
            pass
    return str(raw)


def _warn_unknown_value(label: str, value: str, allowed: frozenset[str]) -> None:
    """Log WARN when a writer passes a value outside the frozen contract."""
    if not value:
        return
    if value not in allowed:
        logger.warning(
            "jobs_repo: unknown %s=%r (not in contract). "
            "Allowed: %s. Sacred Contracts #4/#5.",
            label, value, sorted(allowed),
        )


def upsert_job(job_id: str, kind: str, channel_code: str, status: str,
               payload=None, result=None, stage: str = '', progress_percent: int = 0,
               message: str = '', priority: int = 0):
    status = _normalize_enum_value(status, allow_empty=True)
    stage = _normalize_enum_value(stage, allow_empty=True)
    _warn_unknown_value("status", status, _VALID_JOB_STATUSES)
    _warn_unknown_value("stage", stage, _VALID_JOB_STAGES)
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage, progress_percent, message, payload_json, result_json, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                kind=excluded.kind,
                channel_code=excluded.channel_code,
                status=excluded.status,
                stage=excluded.stage,
                progress_percent=excluded.progress_percent,
                message=excluded.message,
                payload_json=excluded.payload_json,
                result_json=excluded.result_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (job_id, kind, channel_code, status, stage, progress_percent, message, _json_dumps(payload), _json_dumps(result), priority)
        )
        conn.commit()
    _count_write("upsert_job")


def update_job_progress(job_id: str, stage: str, progress_percent: int, message: str = '', status: str | None = None):
    stage = _normalize_enum_value(stage, allow_empty=True)
    _warn_unknown_value("stage", stage, _VALID_JOB_STAGES)
    if status is not None:
        status = _normalize_enum_value(status, allow_empty=True)
        _warn_unknown_value("status", status, _VALID_JOB_STATUSES)
    conn = _thread_conn()
    cur = conn.cursor()
    if status:
        cur.execute(
            'UPDATE jobs SET stage = ?, progress_percent = ?, message = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?',
            (stage, progress_percent, message, status, job_id),
        )
    else:
        cur.execute(
            'UPDATE jobs SET stage = ?, progress_percent = ?, message = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?',
            (stage, progress_percent, message, job_id),
        )
    conn.commit()
    _count_write("update_job_progress")


def save_error_kind(job_id: str, kind: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "UPDATE jobs SET error_kind = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (kind, job_id),
        )
        conn.commit()


def update_render_plan(job_id: str, plan_json: str | None) -> None:
    """Persist the RenderPlan JSON blob for a job (Sprint 2.1).

    `plan_json` is expected to be the output of `RenderPlan.to_json()` or
    None when the plan should be cleared. The column is nullable —
    passing None is a valid 'no plan present' state and is preserved
    verbatim. Never raises; logs a warning and returns on DB error so
    a failure to persist does not crash a live render.
    """
    try:
        with db_conn() as conn:
            conn.execute(
                "UPDATE jobs SET render_plan_json = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (plan_json, job_id),
            )
            conn.commit()
        _count_write("update_render_plan")
    except Exception as exc:
        logger.warning("update_render_plan failed for job_id=%s: %s", job_id, exc)


def get_render_plan(job_id: str) -> str | None:
    """Return the raw RenderPlan JSON blob for a job, or None when the row
    has no plan (NULL column) or the job doesn't exist.

    The caller is expected to feed the result to
    `RenderPlan.from_json(...)` which is itself defensive — so any
    malformed payload becomes None there, not here. Never raises.
    """
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT render_plan_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            value = row[0] if isinstance(row, tuple) else row["render_plan_json"]
            return value if isinstance(value, str) and value else None
    except Exception as exc:
        logger.warning("get_render_plan failed for job_id=%s: %s", job_id, exc)
        return None


def update_recap_plan(job_id: str, plan_json: str | None) -> None:
    """Persist the RecapPlan JSON blob for a job (recap mode). None clears it.
    Never raises — logs and returns on DB error so a failure to persist does
    not crash a live render."""
    try:
        with db_conn() as conn:
            conn.execute(
                "UPDATE jobs SET recap_plan_json = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (plan_json, job_id),
            )
            conn.commit()
        _count_write("update_recap_plan")
    except Exception as exc:
        logger.warning("update_recap_plan failed for job_id=%s: %s", job_id, exc)


def get_recap_plan(job_id: str) -> str | None:
    """Return the raw RecapPlan JSON blob for a job, or None. Feed the result
    to RecapPlan.from_json() (itself defensive). Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT recap_plan_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            value = row[0] if isinstance(row, tuple) else row["recap_plan_json"]
            return value if isinstance(value, str) and value else None
    except Exception as exc:
        logger.warning("get_recap_plan failed for job_id=%s: %s", job_id, exc)
        return None


def delete_job(job_id: str) -> None:
    """Permanently delete a job and all its parts from the database."""
    with db_conn() as conn:
        conn.execute("DELETE FROM job_parts WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()


def upsert_job_part(job_id: str, part_no: int, part_name: str, status: str,
                    progress_percent: int = 0, start_sec: float = 0, end_sec: float = 0,
                    duration: float = 0, viral_score: float = 0, motion_score: float = 0,
                    hook_score: float = 0, output_file: str = '', message: str = ''):
    status = _normalize_enum_value(status, allow_empty=True)
    _warn_unknown_value("part_status", status, _VALID_JOB_PART_STAGES)
    conn = _thread_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO job_parts (job_id, part_no, part_name, status, progress_percent, start_sec, end_sec, duration, viral_score, motion_score, hook_score, output_file, message, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(job_id, part_no) DO UPDATE SET
            part_name=excluded.part_name,
            status=excluded.status,
            progress_percent=excluded.progress_percent,
            start_sec=excluded.start_sec,
            end_sec=excluded.end_sec,
            duration=excluded.duration,
            viral_score=excluded.viral_score,
            motion_score=excluded.motion_score,
            hook_score=excluded.hook_score,
            output_file=excluded.output_file,
            message=excluded.message,
            updated_at=CURRENT_TIMESTAMP
        """,
        (job_id, part_no, part_name, status, progress_percent, start_sec, end_sec, duration, viral_score, motion_score, hook_score, output_file, message)
    )
    conn.commit()
    _count_write("upsert_job_part")


def batch_upsert_job_parts_queued(rows: list[dict]) -> int:
    """Perf-opt Phase 8 (R13) — seed N parts in a single transaction.

    Replaces the loop of N ``upsert_job_part(JobPartStage.QUEUED, …)`` calls
    used at job startup. Same ON CONFLICT semantics as the per-row helper,
    so callers can safely retry an already-seeded job (idempotent). All
    inserts share one ``_thread_conn`` commit, cutting the WAL fsync cost
    from N down to 1.

    Each row dict must carry:
      job_id, part_no, part_name, start_sec, end_sec, duration,
      viral_score, motion_score, hook_score
    Optional keys default to the same values as ``upsert_job_part``.

    Returns the row count. Validation is WARN-level (matches
    ``upsert_job_part``) so a stray status string never aborts seeding.
    """
    if not rows:
        return 0
    status = _normalize_enum_value(JobPartStage.QUEUED, allow_empty=True)
    _warn_unknown_value("part_status", status, _VALID_JOB_PART_STAGES)
    conn = _thread_conn()
    cur = conn.cursor()
    sql = """
        INSERT INTO job_parts (
            job_id, part_no, part_name, status, progress_percent,
            start_sec, end_sec, duration,
            viral_score, motion_score, hook_score,
            output_file, message, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(job_id, part_no) DO UPDATE SET
            part_name=excluded.part_name,
            status=excluded.status,
            progress_percent=excluded.progress_percent,
            start_sec=excluded.start_sec,
            end_sec=excluded.end_sec,
            duration=excluded.duration,
            viral_score=excluded.viral_score,
            motion_score=excluded.motion_score,
            hook_score=excluded.hook_score,
            output_file=excluded.output_file,
            message=excluded.message,
            updated_at=CURRENT_TIMESTAMP
    """
    # The ``or 0`` guards mirror the defensive coercion used everywhere these
    # scores are read (e.g. pipeline_segment_selection.py) — an explicit None
    # score value must coerce to 0.0, not raise. The pre-R13 per-row
    # upsert_job_part bound the raw value (None -> SQL NULL), so this keeps
    # the batch path equally tolerant and stops one bad row aborting the whole
    # seeding transaction.
    payload = [
        (
            r["job_id"], int(r["part_no"]), r["part_name"], status, 0,
            float(r.get("start_sec", 0.0) or 0.0), float(r.get("end_sec", 0.0) or 0.0),
            float(r.get("duration", 0.0) or 0.0),
            float(r.get("viral_score", 0) or 0),
            float(r.get("motion_score", 0) or 0),
            float(r.get("hook_score", 0) or 0),
            str(r.get("output_file", "") or ""),
            str(r.get("message", "") or ""),
        )
        for r in rows
    ]
    cur.executemany(sql, payload)
    conn.commit()
    # Emit one counter increment per row so existing dashboards keep
    # comparing apples to apples vs the per-row path.
    for _ in payload:
        _count_write("upsert_job_part")
    return len(payload)


def update_job_asset_id(job_id: str, asset_id: str) -> None:
    """Link a render job to an Asset Library record. Phase C — Asset Library."""
    with db_conn() as conn:
        conn.execute(
            "UPDATE jobs SET asset_id = ? WHERE job_id = ?",
            (asset_id, job_id),
        )
        conn.commit()


def get_job(job_id: str):
    with db_conn() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs():
    with db_conn() as conn:
        rows = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC').fetchall()
        return [dict(r) for r in rows]


def list_jobs_page(limit: int, offset: int) -> list[dict]:
    """Return a page of jobs ordered by updated_at DESC, created_at DESC.

    Executes a single query with SQL-level LIMIT/OFFSET so only the requested
    rows are transferred from SQLite, regardless of total table size.
    """
    with db_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?',
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def list_job_parts_bulk(job_ids: list[str]) -> dict[str, list[dict]]:
    """Fetch parts for multiple jobs in a single query, keyed by job_id.

    Replaces N individual list_job_parts() calls with one IN (...) query,
    eliminating the N+1 problem in the history endpoint.
    Returns an empty list for any job_id that has no parts.
    """
    if not job_ids:
        return {}
    placeholders = ','.join('?' * len(job_ids))
    with db_conn() as conn:
        rows = conn.execute(
            f'SELECT * FROM job_parts WHERE job_id IN ({placeholders}) ORDER BY job_id, part_no ASC',
            job_ids,
        ).fetchall()
        result: dict[str, list[dict]] = {jid: [] for jid in job_ids}
        for r in rows:
            d = dict(r)
            jid = d.get('job_id', '')
            if jid in result:
                result[jid].append(d)
        return result


def list_job_parts(job_id: str):
    with db_conn() as conn:
        rows = conn.execute('SELECT * FROM job_parts WHERE job_id = ? ORDER BY part_no ASC', (job_id,)).fetchall()
        return [dict(r) for r in rows]


def clear_part_output(job_id: str, part_no: int) -> None:
    """Clear output_file for a single part (file deleted by caller)."""
    with db_conn() as conn:
        conn.execute(
            "UPDATE job_parts SET output_file='', updated_at=CURRENT_TIMESTAMP WHERE job_id=? AND part_no=?",
            (job_id, part_no),
        )
        conn.commit()


def update_part_output_path(job_id: str, part_no: int, new_path: str) -> None:
    """Update output_file to a new path (used by archive move operation)."""
    with db_conn() as conn:
        conn.execute(
            "UPDATE job_parts SET output_file=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=? AND part_no=?",
            (new_path, job_id, part_no),
        )
        conn.commit()


def update_job_part_cover_quality(job_id: str, part_no: int, reasons: list) -> None:
    """Persist cover frame quality tags for a job part (Phase V2).

    Stores the quality reason list (e.g. ["sharp_frame", "good_exposure"])
    returned by thumbnail_quality.select_best_thumbnail() as JSON so
    per-channel visual quality trends can be aggregated by
    get_channel_cover_quality_summary(). Never raises.
    """
    import json
    try:
        with db_conn() as conn:
            conn.execute(
                "UPDATE job_parts SET cover_quality_json = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE job_id = ? AND part_no = ?",
                (json.dumps(reasons), job_id, part_no),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("update_job_part_cover_quality failed job_id=%s part_no=%s: %s", job_id, part_no, exc)


def get_channel_segment_repeat_rate(channel_code: str, limit: int = 200) -> dict:
    """Compute segment repeat rate for a channel (Phase V3 — Content Fingerprinting).

    Identifies (asset_id, start_sec, end_sec) tuples that appear in more than
    one render for the channel. A high repeat rate signals content recycling.
    Only considers parts where jobs.asset_id is known (non-null, non-empty).

    Returns:
      segment_repeat_pct  float — fraction of unique segment positions reused (0.0–1.0)
      repeat_sample_size  int   — count of unique (asset, start, end) groups analysed

    Never raises — returns zeros on error or no data.
    """
    _empty = {"segment_repeat_pct": 0.0, "repeat_sample_size": 0}
    try:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                   AS total_groups,
                    SUM(CASE WHEN cnt > 1 THEN 1 ELSE 0 END)  AS repeated_groups
                FROM (
                    SELECT j.asset_id, jp.start_sec, jp.end_sec, COUNT(*) AS cnt
                    FROM job_parts jp
                    JOIN jobs j ON j.job_id = jp.job_id
                    WHERE j.channel_code = ?
                      AND j.asset_id IS NOT NULL
                      AND j.asset_id != ''
                    GROUP BY j.asset_id, jp.start_sec, jp.end_sec
                    LIMIT ?
                ) sub
                """,
                (channel_code, limit),
            ).fetchone()
        if row is None or row[0] == 0:
            return _empty
        total = int(row[0])
        repeated = int(row[1] or 0)
        return {
            "segment_repeat_pct": round(repeated / total, 4),
            "repeat_sample_size": total,
        }
    except Exception as exc:
        logger.warning(
            "get_channel_segment_repeat_rate failed channel=%s: %s", channel_code, exc
        )
        return _empty


def get_channel_cover_quality_summary(channel_code: str, limit: int = 100) -> dict:
    """Aggregate cover quality tags from recent completed parts for a channel.

    Returns:
      pct_sharp_cover    float  — fraction of parts with "sharp_frame" tag (0.0–1.0)
      pct_face_cover     float  — fraction with "good_face_visibility" tag (0.0–1.0)
      quality_sample_size int   — number of parts with quality data considered

    Never raises — returns zeros on error or no data.
    """
    import json
    _empty = {"pct_sharp_cover": 0.0, "pct_face_cover": 0.0, "quality_sample_size": 0}
    try:
        with db_conn() as conn:
            rows = conn.execute(
                """
                SELECT jp.cover_quality_json
                FROM job_parts jp
                JOIN jobs j ON j.job_id = jp.job_id
                WHERE j.channel_code = ?
                  AND jp.cover_quality_json IS NOT NULL
                ORDER BY jp.updated_at DESC
                LIMIT ?
                """,
                (channel_code, limit),
            ).fetchall()
        if not rows:
            return _empty
        total = len(rows)
        sharp_count = 0
        face_count = 0
        for r in rows:
            try:
                tags = json.loads(r[0])
                if "sharp_frame" in tags:
                    sharp_count += 1
                if "good_face_visibility" in tags:
                    face_count += 1
            except Exception:
                pass
        return {
            "pct_sharp_cover": round(sharp_count / total, 4),
            "pct_face_cover": round(face_count / total, 4),
            "quality_sample_size": total,
        }
    except Exception as exc:
        logger.warning("get_channel_cover_quality_summary failed channel=%s: %s", channel_code, exc)
        return _empty
