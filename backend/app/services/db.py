# Thin backwards-compat facade for legacy ``from app.services.db import …``
# call sites. New code should import directly from ``app.db.*``.
#
# Audit FINDING-A14 sunset progress (2026-06-06):
# - download_repo helpers were removed from the facade — Phase 1 sweep
#   confirmed every caller already imports from ``app.db.download_repo``
#   directly. Re-exporting them just bloated the facade's surface.
# - creator_repo helpers were removed for the same reason (only two
#   call sites, both direct).
# - jobs_repo + feedback_repo helpers stay re-exported because they
#   still have callers using the facade path; those will migrate in
#   follow-up batches.
#
# Test ``test_services_db_facade_surface.py`` pins the current surface
# so any re-introduction of a removed re-export is caught in CI.
import logging

from app.db.connection import (
    close_thread_conn,
    db_conn,
    get_conn,
    init_db,
    _json_dumps,
    _json_loads,
    _thread_conn,
    _utc_now,
    _utc_now_iso,
)

from app.db.jobs_repo import (
    clear_part_output,
    delete_job,
    get_job,
    list_job_parts,
    list_job_parts_bulk,
    list_jobs,
    list_jobs_page,
    save_error_kind,
    update_job_progress,
    upsert_job,
    upsert_job_part,
)

from app.db.feedback_repo import (
    upsert_clip_feedback,
    get_clip_feedback,
    list_feedback_for_channel,
    delete_clip_feedback,
)

logger = logging.getLogger("app.db")
