# RULES.md

## Do
- Keep request handlers thin; move logic to `orchestration/` or `services/`.
- Queue render work via `job_manager.submit_job`.
- Persist job + part progress for long tasks.
- Keep path compatibility (`video_out` + `video_output`).
- Log stage changes and errors with actionable detail.
- Bound concurrency for CPU/GPU-heavy operations.
- Pass session callbacks as arguments — never import `routes/` from `orchestration/`.

## Don't
- Do not run full render/upload workflows inline in request handlers.
- Do not break API fields/status enums without coordinated updates.
- Do not hardcode machine-specific absolute paths.
- Do not remove fallback paths (NVENC→CPU, motion→standard, copy→reencode).
- Do not swallow exceptions affecting correctness.
- Do not weaken Electron security (`contextIsolation`, `nodeIntegration`).
- Do not place render pipeline logic in `routes/render.py` — it belongs in `orchestration/render_pipeline.py`.
- Do not dispatch on `source_mode` before checking `edit_session_id` — the session check must come first.
- Do not silently re-download when `edit_session_id` is present but the session cannot be found — raise and fail the job clearly.

## Gate
- Same input/settings => deterministic output.
- Every failure path must set clear terminal status.
- New settings require validation + safe defaults.
- Session-based renders must either reuse the session or fail — never fall back to downloading.
