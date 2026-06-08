# 13 — API Catalog

Complete enumeration of every HTTP/WS endpoint actually registered on the FastAPI app, cross-referenced against FE callers.

> Numbers in this doc were obtained by reading the `@router.{get|post|put|delete|websocket}` decorators across `routes/*.py` + `features/*/router.py` + `features/*/editing/router.py`. FE callers were verified by grepping `frontend/src/api/*.ts` for `apiFetch(`, `apiFetchFormData(`, raw `fetch(`, and WebSocket constructions.

---

## A. Master endpoint table

### `/api/channels` — [backend/app/routes/channels.py](../../backend/app/routes/channels.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| GET | `/api/channels` | `get_channels` | — | UNCALLED |
| GET | `/api/channels/root` | `get_channels_root` | — | UNCALLED |
| GET | `/api/channels/scan` | `scan_channels` | — | UNCALLED |
| POST | `/api/channels` | `create_channel` | — | UNCALLED |
| GET | `/api/channels/{channel_code}` | `channel_info` | — | UNCALLED |
| GET | `/api/channels/{channel_code}/config` | `channel_config` | — | UNCALLED |

### `/api/render` — [backend/app/features/render/router.py](../../backend/app/features/render/router.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| GET | `/api/render/queue-status` | `get_queue_status` | — | UNCALLED |
| GET | `/api/render/system-info` | `get_system_info` | — | UNCALLED |
| POST | `/api/render/cache/clear` | `clear_render_cache` | — | UNCALLED |
| GET | `/api/render/ai-diagnostics` | `get_ai_diagnostics` | — | UNCALLED |
| POST | `/api/render/prepare-source` | `prepare_source` | `render.ts::prepareSource` | USED |
| DELETE | `/api/render/prepare-source/{session_id}` | `cancel_prepare_source` | `render.ts::cancelPrepareSource` | USED |
| GET | `/api/render/preview-video/{session_id}` | `preview_video` | `render.ts::getPreviewVideoUrl` | USED |
| GET | `/api/render/preview-transcript/{session_id}` | `preview_transcript` | `render.ts::getPreviewTranscript` | USED |
| POST | `/api/render/process` | `create_render_job` | `render.ts::submitRender` | USED |
| POST | `/api/render/upload-local` | `upload_local_video` | — | UNCALLED |
| POST | `/api/render/test-cloud-ai` | `test_cloud_ai` | `render.ts::testCloudAi` | USED |
| POST | `/api/render/quick-process` | `quick_process` | — | UNCALLED |
| POST | `/api/render/resume/{job_id}` | `resume_render_job` | `render.ts::resumeRender` | USED |
| POST | `/api/render/retry/{job_id}` | `retry_failed_parts` | `render.ts::retryRender` | USED |
| POST | `/api/render/{job_id}/cancel` | `cancel_render_job` | `render.ts::cancelRender` | USED |
| GET | `/api/render/jobs/{job_id}` | `get_render_job` | — | DUPLICATE-of `/api/jobs/{id}` |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/media` | `stream_render_part_media` | — | UNCALLED (overlaps `jobs.py`) |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/thumbnail` | `get_render_part_thumbnail` | — | UNCALLED |
| GET | `/api/render/subtitle-preview` | `api_subtitle_preview` | — | UNCALLED |

### `/api/jobs` — [backend/app/routes/jobs.py](../../backend/app/routes/jobs.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| GET | `/api/jobs` | `api_list_jobs` | — | DEPRECATED (use `/history`) |
| GET | `/api/jobs/history` | `api_jobs_history` | `jobs.ts::getJobHistory` | USED |
| GET | `/api/jobs/queue/status` | `api_queue_status` | `jobs.ts::getQueueStatus` | USED |
| GET | `/api/jobs/{job_id}` | `api_get_job` | `jobs.ts::getJob` | USED |
| GET | `/api/jobs/{job_id}/parts` | `api_get_job_parts` | `jobs.ts::getJobParts` | USED |
| GET | `/api/jobs/{job_id}/ai-summary` | `api_get_job_ai_summary` | `jobs.ts::getJobAiSummary` | USED |
| GET | `/api/jobs/{job_id}/logs` | `api_get_job_logs` | — | UNCALLED |
| GET | `/api/jobs/{job_id}/parts/{part_no}/quality` | `api_get_part_quality` | `jobs.ts::getJobPartQuality` | USED |
| GET | `/api/jobs/{job_id}/quality` | `api_get_job_quality` | `jobs.ts::getJobQualitySummary` | USED |
| GET | `/api/jobs/{job_id}/parts/{part_no}/stream` | `stream_part` | — | DEPRECATED (see FINDING-API01) |
| WS | `/api/jobs/{job_id}/ws` | `ws_job_progress` | `RenderSocketClient` | USED |
| POST | `/api/jobs/cleanup/logs` | `api_cleanup_logs` | — | UNCALLED |
| DELETE | `/api/jobs/{job_id}/parts/{part_no}/output` | `delete_part_output_endpoint` | `jobs.ts::deletePartOutput` | USED |
| DELETE | `/api/jobs/{job_id}` | `delete_job_endpoint` | `jobs.ts::deleteJob` | USED |

### Editing — [backend/app/features/render/editing/router.py](../../backend/app/features/render/editing/router.py) (mounted under `/api/jobs`)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| POST | `/api/jobs/{job_id}/parts/{part_no}/trim` | `api_trim_part` | `editing.ts::trimJobPart` | USED |
| POST | `/api/jobs/{job_id}/parts/{part_no}/rerender` | `api_rerender_part` | `editing.ts::rerenderSelection` | USED |
| POST | `/api/jobs/{job_id}/parts/{part_no}/export` | `api_export_part` | `editing.ts::exportClip` | USED |

### `/api/feedback` — [backend/app/routes/feedback.py](../../backend/app/routes/feedback.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| POST | `/api/feedback/jobs/{job_id}/parts/{part_no}` | `submit_feedback` | `feedback.ts::submitClipFeedback` | USED |
| GET | `/api/feedback/jobs/{job_id}/parts/{part_no}` | `get_feedback` | `feedback.ts::getClipFeedback` | USED |
| DELETE | `/api/feedback/jobs/{job_id}/parts/{part_no}` | `remove_feedback` | `feedback.ts::deleteClipFeedback` | USED |
| GET | `/api/feedback/channel/{channel_code}` | `channel_feedback_summary` | — | UNCALLED |

### `/api/upload-file` — [backend/app/routes/files.py](../../backend/app/routes/files.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| POST | `/api/upload-file` | `upload_file` | `upload.ts::uploadFile` | USED |

### `/api/downloader` — [backend/app/features/download/router.py](../../backend/app/features/download/router.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| GET | `/api/downloader/info` | `get_info` | `platformDownloader.ts::getVideoInfo` | USED |
| POST | `/api/downloader/start` | `start_download` | `platformDownloader.ts::startDownload` | USED |
| POST | `/api/downloader/batch` | `start_batch` | `platformDownloader.ts::startBatch` | USED |
| GET | `/api/downloader/jobs` | `list_jobs` | `platformDownloader.ts::listJobs` | USED |
| GET | `/api/downloader/jobs/{job_id}` | `get_job` | `platformDownloader.ts::getJob` | USED |
| DELETE | `/api/downloader/jobs/{job_id}` | `cancel_job` | `platformDownloader.ts::cancelJob` | USED but inconsistent semantics |
| WS | `/api/downloader/jobs/{job_id}/ws` | `job_progress_ws` | `platformDownloader.ts::subscribeJob` | USED |
| POST | `/api/downloader/refresh-cookies` | `refresh_cookies` | — | UNCALLED |
| POST | `/api/downloader/import-cookies` | `import_cookies` | — | UNCALLED |
| GET | `/api/downloader/cookie-status` | `cookie_status` | — | UNCALLED |

### `/api/settings` — [backend/app/routes/settings.py](../../backend/app/routes/settings.py)

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| GET | `/api/settings/creator-context` | `get_settings_creator_context` | `creatorContext.ts::getCreatorContext` | USED |
| PUT | `/api/settings/creator-context` | `put_settings_creator_context` | `creatorContext.ts::putCreatorContext` | USED |

### Misc

| Method | Path | Handler | FE caller | Status |
|---|---|---|---|---|
| GET | `/api/voice/profiles` | `routes/voice.py::get_voice_profile_catalog` | — | UNCALLED |
| GET | `/metrics` | `routes/metrics.py::metrics` | — (Prometheus scrape) | OPERATOR |
| POST | `/api/dev/command` | `routes/devtools.py::run_dev_command` | — | INTERNAL (env-gated) |

V2 routers (`ENABLE_V2=1`) live at `v2.api.routes.download` and `v2.api.routes.render`. They were not enumerated because they are not enabled by default and were not in the migration history that's visible from `main.py:142-147`. Phase 11 should decide if V2 remains a roadmap item.

---

## B. Summary counts

| Bucket | Count | % |
|---|---|---|
| **USED** (FE caller exists) | 36 | 51 % |
| **UNCALLED** (no FE caller, not deprecated) | 24 | 34 % |
| **DEPRECATED** (kept for backward compat) | 2 | 3 % |
| **DUPLICATE** (same data via two paths) | 2 | 3 % |
| **OPERATOR / INTERNAL** (Prometheus + devtools) | 2 | 3 % |
| **WebSocket** | 2 | 3 % |
| **Total registered** | **70** (excluding V2) | 100 % |

(The earlier 78 number from the sub-agent overcounted because it double-counted the editing `/api/jobs/...` routes once under `/api/jobs` and once under `/api/render`.)

---

## C. WebSocket endpoints

### `WS /api/jobs/{job_id}/ws` ([routes/jobs.py:644](../../backend/app/routes/jobs.py))

- Emits `{job, parts, summary}` on fingerprint change (Sacred Contract #6).
- Keepalive `{"type":"ping"}` every 25 s.
- Closes on terminal status (`completed/failed/cancelled/interrupted`).
- Polls DB every 500 ms (Phase 2 FINDING-S02).
- FE: `RenderSocketClient` (`frontend/src/websocket/RenderSocketClient.ts:104`).
- Reconnect: 20 attempts, 2 s → 30 s backoff.

### `WS /api/downloader/jobs/{job_id}/ws` ([features/download/router.py:238](../../backend/app/features/download/router.py))

- Emits full `DownloadJob` dict per tick (no fingerprint diffing — sends every poll).
- Closes on `done` / `failed`.
- Polls every 500 ms.
- FE: `platformDownloader.ts::subscribeJob`.

**FINDING-API01 (LOW):** the downloader WS handler sends on every poll without diffing. With a 60-minute download that's 7,200 frames carrying the same payload twice per second. Cheap individually but wasteful. Recommend adopting the render WS's fingerprint pattern.

---

## D. Findings

### FINDING-API02 (MED) — Duplicate media streaming endpoints

Two paths serve the same video clip with HTTP Range support:

- [features/render/router.py:1075](../../backend/app/features/render/router.py) — `GET /api/render/jobs/{id}/parts/{n}/media`
- [routes/jobs.py:611](../../backend/app/routes/jobs.py) — `GET /api/jobs/{id}/parts/{n}/stream` (marked deprecated in code comments)

The FE doesn't call either by name; the HTML5 `<video>` tag receives a URL constructed in `jobs.ts:185+`. Pick one canonical path and remove the other.

### FINDING-API03 (MED) — Duplicate job-status endpoint

[features/render/router.py:1065](../../backend/app/features/render/router.py) `GET /api/render/jobs/{job_id}` returns the same payload as [routes/jobs.py:360](../../backend/app/routes/jobs.py) `GET /api/jobs/{job_id}`. The FE only calls the latter. Render-scoped alias adds no value.

### FINDING-API04 (LOW) — Inconsistent cancel semantics

- Render: `POST /api/render/{job_id}/cancel` — POST for a signal (idiomatic).
- Downloader: `DELETE /api/downloader/jobs/{job_id}` — DELETE used to *cancel*, not just delete.

Recommend renaming downloader's to `POST /api/downloader/jobs/{id}/cancel` and reserving `DELETE` for true post-completion deletion.

### FINDING-API05 (MED) — 6 orphan channel endpoints

All `/api/channels/*` endpoints have zero FE callers (Phase 1 also noted FE has no channel-management screen — only a string typed into render config). They're either dead surface OR an "admin / dev tool" that's never been wired up. Recommend either:
- delete all 6 routes (and the `routes/channels.py` file), OR
- build the channels management screen in Phase 11 roadmap and document it.

### FINDING-API06 (MED) — 3 cookie management endpoints not wired

`refresh-cookies`, `import-cookies`, `cookie-status` are all UNCALLED. The cookie flow ends up either reading Chrome's cookies file directly (`cookie_extractor.py`) or relying on yt-dlp's internal handling. The endpoints are incomplete features. Either ship the UI button or delete them.

### FINDING-API07 (MED) — Unintegrated diagnostics/admin endpoints

| Path | What it does | Suggestion |
|---|---|---|
| `/api/render/queue-status` | active/max render slots | wire into Settings/troubleshooting screen |
| `/api/render/system-info` | DB/cache size, jobs count | same |
| `/api/render/ai-diagnostics` | AI runtime + provider status | same |
| `/api/render/cache/clear` | manual cache cleanup | wire as a "Clear caches" button in Settings |
| `/api/jobs/{id}/logs` | tail job logs | log viewer for failed jobs |
| `/api/jobs/cleanup/logs` | log prune | admin-only button |
| `/api/voice/profiles` | voice profile catalog | FE narration voice picker |
| `/api/render/subtitle-preview` | ASS style preview | editor preview pane |
| `/api/render/jobs/{id}/parts/{n}/thumbnail` | frame extraction | clip grid hero image |

These are useful endpoints orphaned by an unfinished UI. Phase 11 should decide which to ship in the next FE iteration vs. retire.

### FINDING-API08 (LOW) — Deprecated `GET /api/jobs` still registered

[routes/jobs.py:315](../../backend/app/routes/jobs.py) defines `api_list_jobs` despite the FE having an explicit ban comment (`jobs.ts:184`). Keeping it allows accidental misuse by a future API consumer. Recommend respond `410 Gone` or remove entirely.

### FINDING-API09 (HIGH if any external API client exists) — `extra="ignore"` on RenderRequest silently drops typos

[backend/app/models/schemas.py:117](../../backend/app/models/schemas.py): `model_config = ConfigDict(extra="ignore")` for `RenderRequest`. Sacred Contract #2 justifies this for backward-compat replay of stored payloads, but a fresh API call from any external client (curl, Postman, V2 of FE) gets *unknown fields silently dropped* — no 422. Combined with the lack of automated OpenAPI drift detection (Phase 5 FINDING-T05), this is a real risk for FE/BE divergence. Recommend adding a structured warning log when extras are received from a *fresh* request (vs. stored payload).

---

## E. Cross-reference notes for Phase 7

The FE-↔-BE contract audit (Phase 7) should focus on:

1. **Used endpoints (36)** — compare actual Pydantic models vs FE TS types in `frontend/src/types/api.ts` and `openapi-generated.ts`.
2. **Optional vs required field mismatches** — particularly `RenderRequest` (892 LOC of Pydantic).
3. **Response field renames** — e.g., `ranking_summary` shape in `getJobAiSummary` vs `JobAiSummary` interface ([jobs.ts:147-164](../../frontend/src/api/jobs.ts)).
4. **WS event shape** — Sacred Contract #6 `{job, parts, summary}`.

End of 13_api_catalog.md.
