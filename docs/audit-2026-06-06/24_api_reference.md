# 24 — API Reference

70 endpoints registered. Full catalog with FE caller cross-reference in [13_api_catalog.md](13_api_catalog.md). This document is the canonical "what's the contract" list, summarized by surface.

## REST surfaces

### Render

`/api/render/...` — [features/render/router.py](../../backend/app/features/render/router.py).

USED:
- `POST /api/render/prepare-source` → `{session_id, duration, title, export_dir}`
- `DELETE /api/render/prepare-source/{session_id}` → `{cancelled, session_id}`
- `GET /api/render/preview-video/{session_id}` → MP4 stream
- `GET /api/render/preview-transcript/{session_id}` → `{segments[], status?}`
- `POST /api/render/process` (RenderRequest) → `{job_id, status, resume_mode}`
- `POST /api/render/test-cloud-ai` → `{ok, provider, model, latency_ms, error?}`
- `POST /api/render/resume/{job_id}` → `{job_id, status, resume_mode}`
- `POST /api/render/retry/{job_id}` → `{job_id, status, failed_parts_count}`
- `POST /api/render/{job_id}/cancel` → `{job_id, status}`

UNCALLED (admin/diagnostics — Phase 6 API07): `queue-status`, `system-info`, `cache/clear`, `ai-diagnostics`, `upload-local`, `quick-process`, `jobs/{id}` (dup), `jobs/{id}/parts/{n}/media` (dup), `jobs/{id}/parts/{n}/thumbnail`, `subtitle-preview`.

### Jobs

`/api/jobs/...` — [routes/jobs.py](../../backend/app/routes/jobs.py) + editing router.

USED:
- `GET /api/jobs/history?limit=&offset=` → `{items[], limit, offset, has_more}`
- `GET /api/jobs/queue/status` → `{max_concurrent, active, pending, available_slots}`
- `GET /api/jobs/{job_id}` → `JobStatusResponse`
- `GET /api/jobs/{job_id}/parts` → `{items[]}`
- `GET /api/jobs/{job_id}/ai-summary` → `JobAiSummary` (Phase 7 C03 fields warning)
- `GET /api/jobs/{job_id}/parts/{part_no}/quality` → `QualityReport`
- `GET /api/jobs/{job_id}/quality?include_reports=` → `QualitySummary`
- `WS /api/jobs/{job_id}/ws` → `{job, parts, summary}` on change
- `DELETE /api/jobs/{job_id}?delete_files=` → cleanup result
- `DELETE /api/jobs/{job_id}/parts/{part_no}/output` → `{job_id, part_no, deleted}`
- `POST /api/jobs/{job_id}/parts/{part_no}/trim` (TrimRequest)
- `POST /api/jobs/{job_id}/parts/{part_no}/rerender` (RerenderRequest)
- `POST /api/jobs/{job_id}/parts/{part_no}/export` (ExportRequest)

DEPRECATED: `GET /api/jobs` (unbounded), `GET /api/jobs/{id}/parts/{n}/stream` (use `/media`).

UNCALLED: `GET /api/jobs/{id}/logs`, `POST /api/jobs/cleanup/logs`.

### Downloader

`/api/downloader/...` — [features/download/router.py](../../backend/app/features/download/router.py).

USED:
- `GET /api/downloader/info?url=` → `VideoInfo`
- `POST /api/downloader/start` → `{job_id, platform}`
- `POST /api/downloader/batch` → `{jobs[]}`
- `GET /api/downloader/jobs` → `DownloadJob[]`
- `GET /api/downloader/jobs/{job_id}` → `DownloadJob`
- `DELETE /api/downloader/jobs/{job_id}` (cancel; see Phase 6 API04 semantics) → `{ok}`
- `WS /api/downloader/jobs/{job_id}/ws` → `DownloadJob` per tick

UNCALLED: `refresh-cookies`, `import-cookies`, `cookie-status`.

### Settings

USED:
- `GET /api/settings/creator-context` → `CreatorContextEnvelope`
- `PUT /api/settings/creator-context` (CreatorContextPayload)

### Feedback

USED:
- `POST /api/feedback/jobs/{job_id}/parts/{part_no}` (FeedbackSubmit)
- `GET /api/feedback/jobs/{job_id}/parts/{part_no}`
- `DELETE /api/feedback/jobs/{job_id}/parts/{part_no}`

UNCALLED: `/api/feedback/channel/{channel_code}`.

### Files

USED:
- `POST /api/upload-file` (multipart) → `{path}`

### Channels — all 6 UNCALLED

`GET /api/channels`, `GET /api/channels/root`, `GET /api/channels/scan`, `POST /api/channels`, `GET /api/channels/{code}`, `GET /api/channels/{code}/config`.

### Voice — UNCALLED

`GET /api/voice/profiles`.

### Operator

- `GET /metrics` — Prometheus scrape.
- `POST /api/dev/command` — env-gated shell exec (`ENABLE_DEVTOOLS=1`).

## WebSocket reference

| Endpoint | Polling | Diffing | Backpressure | FE client |
|---|---|---|---|---|
| `/api/jobs/{id}/ws` | 500 ms | fingerprint diff | one frame per change + 25 s ping | `RenderSocketClient.ts` |
| `/api/downloader/jobs/{id}/ws` | 500 ms | **no diff — sends every tick** | none | `platformDownloader.ts::subscribeJob` |

WS shape (Sacred Contract #6):

```json
{
  "job": { "job_id": "...", "kind": "...", "status": "...", "stage": "...", "progress_percent": 0, "message": "...", "error_kind": "...", ... },
  "parts": [{"part_no": 1, "status": "...", "progress_percent": 0, "output_file": "...", "viral_score": 0, "hook_score": 0, "motion_score": 0, ... }],
  "summary": {"total_parts": 0, "completed_parts": 0, "failed_parts": 0, "pending_parts": 0, "processing_parts": 0, "overall_progress_percent": 0, "active_parts": [...], "stuck_parts": [...]}
}
```

## Auth

**None.** Single-user localhost. The only protection is `127.0.0.1` binding + CSP header. See [10_known_issues.md](26_known_issues.md) for the security implications.

## Drift detection

`frontend/package.json` has `npm run check:openapi-drift` but no CI gate (Phase 5 T05). Phase 11 roadmap action.

End of 24_api_reference.md.
