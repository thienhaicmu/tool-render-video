# Normalization Few-Shot Examples

These examples show the expected transformation from raw request to normalized task.
Use them to calibrate output quality.

---

## Example 1: Bug Fix

**Raw Prompt:**
```
The download sometimes only gets 360p video instead of 1080p.
This happens intermittently and I'm not sure why.
```

**Normalized Output:**
```json
{
  "task_type": "bugfix",
  "title": "Fix intermittent 360p download instead of 1080p",
  "objective": "Ensure yt-dlp always attempts 1080p+ adaptive streams before falling back to combined low-resolution streams.",
  "business_context": "Users expect 1080p output. Getting 360p silently produces low-quality clips that fail the content quality bar.",
  "project_context_needed": ["docs/architecture.md"],
  "scope_in": [
    "backend/app/services/downloader.py: download strategy and format selectors",
    "backend/app/services/downloader.py: cleanup between retry attempts"
  ],
  "scope_out": [
    "render_engine.py",
    "Any changes to ffmpeg encoding settings",
    "UI changes"
  ],
  "constraints": [
    "Do not add new yt-dlp client types without documenting them",
    "Must preserve the 4-attempt fallback chain",
    "Must not break existing download tests"
  ],
  "assumptions": [
    "ios client is the most reliable without PO Token as of 2026-04",
    "360p rejection threshold at < 480p is acceptable"
  ],
  "related_files": [
    "backend/app/services/downloader.py",
    "backend/app/services/bin_paths.py"
  ],
  "acceptance_criteria": [
    "download_youtube() returns height >= 1080 for a standard 1080p YouTube video",
    "If 360p is the only available format, download proceeds without infinite retry",
    "_cleanup_partial() removes all source* files, not just empty ones",
    "Each download attempt logs client, format string, and result height"
  ],
  "logging_requirements": [
    "Log each attempt: client name, format selector, outcome",
    "Log final selected height and fps on success"
  ],
  "review_checkpoints": [
    "Verify _cleanup_partial removes non-empty partial files",
    "Verify 360p rejection logic does not cause infinite loop",
    "Verify format selector strings are syntactically valid yt-dlp format selectors"
  ],
  "expected_deliverables": [
    "Modified downloader.py with fixed format strategy",
    "Test case demonstrating 1080p selection over 360p"
  ],
  "risk_flags": [
    "YouTube client availability changes frequently — ios client may stop working"
  ],
  "estimated_complexity": "small",
  "raw_task_ref": "tasks/raw/fix-360p-download.md"
}
```

---

## Example 2: Feature Implementation

**Raw Prompt:**
```
Add a way to see how long each pipeline stage took in the UI.
```

**Normalized Output:**
```json
{
  "task_type": "feature",
  "title": "Display per-stage duration in render progress UI",
  "objective": "Show elapsed time for each completed pipeline stage in the render view's progress panel.",
  "business_context": "Operators need to identify slow stages to debug performance issues and estimate completion times.",
  "project_context_needed": ["docs/architecture.md", "docs/project-overview.md"],
  "scope_in": [
    "backend/app/services/db.py: add stage_started_at, stage_completed_at to job_parts",
    "backend/app/routes/jobs.py: include stage timing in WebSocket/HTTP response",
    "backend/static/index.html: display timing in renderParts() function"
  ],
  "scope_out": [
    "render_engine.py internals beyond adding timing calls",
    "Upload pipeline",
    "Historical job list view"
  ],
  "constraints": [
    "Must not change the shape of existing job or part status fields",
    "Timing display is informational only — no logic depends on it"
  ],
  "assumptions": [
    "SQLite can store ISO 8601 strings for timing without schema migration issues",
    "Browser renders timing updates in real time without layout thrash"
  ],
  "related_files": [
    "backend/app/services/db.py",
    "backend/app/routes/jobs.py",
    "backend/static/index.html"
  ],
  "acceptance_criteria": [
    "Each job_part in the WebSocket response includes duration_seconds when completed",
    "Completed stages show duration in the UI (e.g., '12.3s')",
    "In-progress stages show elapsed time, updating every WebSocket tick",
    "UI change is backward-compatible with responses that omit duration"
  ],
  "logging_requirements": [
    "No additional logging required for this feature"
  ],
  "review_checkpoints": [
    "Verify duration is calculated server-side, not client-side",
    "Verify UI gracefully handles missing duration field"
  ],
  "expected_deliverables": [
    "Modified db.py with timing fields",
    "Modified jobs.py response shape",
    "Modified index.html with duration display"
  ],
  "risk_flags": [
    "Schema migration may be needed if job_parts table needs new columns"
  ],
  "estimated_complexity": "medium",
  "raw_task_ref": "tasks/raw/stage-timing-ui.md"
}
```

---

## Example 3: Refactor (Rejected — Too Vague)

**Raw Prompt:**
```
Clean up the render engine, it's getting messy.
```

**Normalizer Output:**
```json
{
  "error": "insufficient_context",
  "message": "The request 'clean up the render engine' has no measurable objective or scope boundary.",
  "questions": [
    "Which specific functions or patterns in render_engine.py are the problem?",
    "Is there a performance issue, a readability issue, or a correctness issue?",
    "Is there a specific metric that defines 'clean' for this context?"
  ]
}
```

---

## Example 4: Refactor (Valid — Scoped)

**Raw Prompt:**
```
The render_engine.py file has a single function called run_pipeline() that is
750 lines long. It handles downloading, trimming, encoding, and uploading all
in one block. It's impossible to test. Break it into smaller functions.
```

**Normalized Output:**
```json
{
  "task_type": "refactor",
  "title": "Decompose run_pipeline() into single-responsibility functions",
  "objective": "Split the 750-line run_pipeline() function into focused, independently testable sub-functions by stage.",
  "business_context": "The monolithic function makes it impossible to unit-test individual stages, slowing down debugging and increasing regression risk on every change.",
  "project_context_needed": ["docs/architecture.md", "docs/coding-standards.md"],
  "scope_in": [
    "backend/render_engine.py: extract _download_stage(), _trim_stage(), _encode_stage(), _upload_stage() from run_pipeline()",
    "backend/render_engine.py: pass shared state as explicit arguments, not implicit globals",
    "tests/test_render_engine.py: add unit tests for each new sub-function"
  ],
  "scope_out": [
    "Any changes to function behavior or output — this is a pure structural refactor",
    "Callers of run_pipeline() — the public signature must remain identical",
    "backend/app/routes/jobs.py",
    "Database layer"
  ],
  "constraints": [
    "run_pipeline() public API must not change — callers must require zero modification",
    "No behavioral changes allowed",
    "All existing integration tests must pass unchanged after refactor"
  ],
  "assumptions": [
    "run_pipeline() has no undocumented side effects that are order-sensitive beyond the obvious pipeline sequence",
    "The existing test suite covers the integration path end-to-end"
  ],
  "related_files": [
    "backend/render_engine.py",
    "tests/test_render_engine.py"
  ],
  "acceptance_criteria": [
    "run_pipeline() body is 50 lines or fewer after refactor",
    "Each extracted sub-function is independently callable and has its own unit test",
    "All pre-existing tests pass without modification",
    "Each sub-function has a docstring describing its single responsibility",
    "No global or module-level mutable state is introduced"
  ],
  "logging_requirements": [
    "Existing log statements must be preserved and moved into the appropriate sub-function"
  ],
  "review_checkpoints": [
    "Confirm run_pipeline() signature is unchanged",
    "Confirm no logic was accidentally dropped or reordered during extraction",
    "Confirm each sub-function has at least one unit test covering the happy path"
  ],
  "expected_deliverables": [
    "Refactored backend/render_engine.py",
    "New unit tests in tests/test_render_engine.py"
  ],
  "risk_flags": [
    "Implicit ordering dependencies inside the original function may not be obvious — review carefully before splitting"
  ],
  "estimated_complexity": "medium",
  "raw_task_ref": "tasks/raw/refactor-run-pipeline.md"
}
```

---

## Example 5: Infra / DevOps Task

**Raw Prompt:**
```
The Docker container keeps running out of disk space in prod because old render
artifacts and temp files are never cleaned up. Add something to prune them
automatically.
```

**Normalized Output:**
```json
{
  "task_type": "infra",
  "title": "Add automated cleanup of stale render artifacts and temp files",
  "objective": "Implement a scheduled cleanup routine that removes render artifacts and temporary files older than the configured retention period.",
  "business_context": "Uncontrolled artifact accumulation causes out-of-disk failures in production, resulting in container restarts and lost in-progress renders.",
  "project_context_needed": ["docs/architecture.md", "docs/project-overview.md"],
  "scope_in": [
    "backend/app/services/cleanup.py: new module implementing prune_old_artifacts(max_age_days, dry_run=False)",
    "backend/app/main.py: register cleanup as a daily background task",
    "docker-compose.yml: confirm artifact volume path matches cleanup config",
    ".claude-cowork/config.json: cleanup must read and respect the existing retention_days value"
  ],
  "scope_out": [
    "Database records — only filesystem artifacts are in scope",
    "Logs directory — log rotation is handled separately",
    "Any changes to the render pipeline itself"
  ],
  "constraints": [
    "Must not delete artifacts for jobs with status 'in_progress' or 'pending'",
    "Must use retention_days from config.json — no hardcoded values",
    "Cleanup failures must not crash or block the main application process",
    "Must work inside a Docker container with no host cron daemon"
  ],
  "assumptions": [
    "Artifacts are stored under the path defined in config.json artifact_root",
    "Job status is reliably stored in the database and can be queried before deletion",
    "APScheduler or equivalent background task runner is available in the runtime"
  ],
  "related_files": [
    "backend/app/services/cleanup.py",
    "backend/app/main.py",
    "backend/app/services/db.py",
    ".claude-cowork/config.json",
    "docker-compose.yml"
  ],
  "acceptance_criteria": [
    "prune_old_artifacts() deletes artifact directories for completed/failed jobs older than retention_days",
    "prune_old_artifacts() skips any job with status 'in_progress' or 'pending'",
    "Cleanup runs automatically once per day without manual intervention",
    "dry_run=True logs what would be deleted without deleting anything",
    "Cleanup errors are caught, logged at WARNING level, and do not raise to the caller"
  ],
  "logging_requirements": [
    "Log start and end of each cleanup run with count of directories examined",
    "Log each deleted path at DEBUG level",
    "Log skipped in-progress jobs at DEBUG level",
    "Log total bytes freed at INFO level after each run"
  ],
  "review_checkpoints": [
    "Verify the in-progress guard queries the database, not just the filesystem",
    "Verify retention_days is read from config at runtime, not imported at module load",
    "Verify cleanup does not traverse outside the configured artifact_root directory",
    "Verify dry_run=True produces log output without any filesystem mutation"
  ],
  "expected_deliverables": [
    "New backend/app/services/cleanup.py module",
    "Scheduler registration in backend/app/main.py",
    "Unit tests covering happy path, in-progress guard, and dry_run mode"
  ],
  "risk_flags": [
    "Race condition possible if a job transitions to in_progress after the status check but before deletion — skip jobs modified in the last 10 minutes as a safety margin",
    "If artifact_root is a mounted Docker volume, deletion may not reclaim host disk space until the volume is pruned"
  ],
  "estimated_complexity": "medium",
  "raw_task_ref": "tasks/raw/infra-artifact-cleanup.md"
}
```

---

## Normalization Anti-Patterns (Do Not Reproduce)

| Anti-Pattern | Problem | Correct Approach |
|---|---|---|
| `"objective": "Fix all the download bugs"` | Multiple objectives, not testable | One primary objective per task |
| `"scope_in": ["everything in downloader.py"]` | Unbounded scope | Name specific functions or classes |
| `"acceptance_criteria": ["code is cleaner"]` | Not measurable | Define a concrete, observable outcome |
| `"scope_out": []` (empty on a non-trivial task) | Missing exclusions invite scope creep | Always name at least 2 explicit exclusions |
| `"estimated_complexity": "large"` for a 1-line fix | Miscalibrated estimate | Use the LOC/file count matrix defined in the system prompt |
| `"risk_flags": []` for a DB migration or auth change | Missing critical risk signal | Always flag schema, auth, payment, and public API changes |
| `"raw_task_ref"` omitted | Breaks traceability to source task | Always include path to originating raw task file |
