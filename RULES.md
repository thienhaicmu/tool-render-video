# RULES.md

## Do
- Keep request handlers thin; move logic to `services/`.
- Queue render work via `job_manager.submit_job`.
- Persist job + part progress for long tasks.
- Keep path compatibility (`video_out` + legacy `upload/video_output`).
- Log stage changes and errors with actionable detail.
- Bound concurrency for CPU/GPU-heavy operations.

## Don't
- Do not run full render/upload workflows inline in request handlers.
- Do not break API fields/status enums without coordinated updates.
- Do not hardcode machine-specific absolute paths.
- Do not remove fallback paths (NVENC->CPU, motion->standard, copy->reencode).
- Do not swallow exceptions affecting correctness.
- Do not weaken Electron security (`contextIsolation`, `nodeIntegration`).

## Gate
- Same input/settings => deterministic output.
- Every failure path must set clear terminal status.
- New settings require validation + safe defaults.
