# COMPAT shim — canonical: app.jobs.manager
from app.jobs.manager import *  # noqa: F401, F403
from app.jobs.manager import (  # noqa: F401
    submit_job, is_running, active_count, pending_count,
    shutdown, recover_pending_render_jobs,
    _lock, _cond, _executor, _stopping,
    _pending, _pending_job_ids, _active_job_ids, _get_executor,
)
