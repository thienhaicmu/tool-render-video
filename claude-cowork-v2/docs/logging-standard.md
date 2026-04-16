# Logging Standard

## Format

All pipeline logs are structured JSON (NDJSON — one object per line).

Each log line is a `LogEvent` object:

```json
{
  "timestamp": "2026-04-16T10:23:45.123Z",
  "task_id": "task-lp3k2m-a1b2c3d4",
  "run_id": "run-lp3k3x-e5f6g7h8",
  "session_id": "sess-uuid-here",
  "component": "normalize-prompt",
  "event_name": "task.normalized",
  "actor": "system",
  "level": "info",
  "status": "completed",
  "message": "Task normalized successfully",
  "metadata": {
    "task_type": "bugfix",
    "complexity": "small",
    "duration_ms": 1240
  }
}
```

## Event Taxonomy

| Event Name | Trigger |
|------------|---------|
| `pipeline.started` | Pipeline invoked for a task |
| `task.received` | Raw task ingested and validated |
| `task.normalized` | LLM normalization completed |
| `task.validation.failed` | Schema validation rejected output |
| `task.packaged` | Task pack markdown rendered |
| `task.execution.started` | Executor invoked |
| `task.execution.completed` | Executor returned successfully |
| `task.execution.failed` | Executor returned error or timeout |
| `task.review.started` | Reviewer invoked |
| `task.review.completed` | Review report generated |
| `task.summary.generated` | Final summary markdown created |
| `artifact.archived` | Artifact folder sealed |
| `pipeline.completed` | Full pipeline run finished |
| `pipeline.failed` | Pipeline aborted due to critical error |

## Log Files

| File | Contents |
|------|----------|
| `logs/events/<task-id>.ndjson` | All events for a task, in order |
| `logs/prompts/<task-id>-normalize.json` | Full normalization prompt + response |
| `logs/executions/<task-id>-<run-id>.json` | Execution trace |
| `logs/reviews/<task-id>-<run-id>.json` | Review prompt + response |

## What NOT to Log

- API keys, tokens, passwords
- Full file contents of code being reviewed (reference paths instead)
- PII of any kind
- Raw HTTP response bodies from external services (log status code + summary only)

## Retention

Default: 30 days. Controlled by `RETENTION_DAYS` env var.
Artifacts in `artifacts/` follow the same retention policy.
Log rotation is the operator's responsibility (logrotate, cloud log service, etc.).
