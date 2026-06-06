# 27 — Future Roadmap

Derived from Phases 1–9 findings. Each item cites the originating finding(s). Sequenced for risk reduction × delivery cost.

---

## Immediate (≤ 2 weeks)

### IM-1 — Centralise NVENC semaphore (R01 / BR04)

Move acquire/release into `_run_ffmpeg_with_retry`, conditioned on `_argv_uses_nvenc(command)` (curated set `{"h264_nvenc","hevc_nvenc","av1_nvenc"}`, not string search). Removes "all encodes crash together" cluster failure.

Files: [features/render/engine/encoder/ffmpeg_helpers.py](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py), audit the 3 current callers in `clip_renderer.py` + `overlay_compositor.py`.

### IM-2 — Add `Lock` around `_PREVIEW_SESSIONS` (BR01)

Wrap every mutation. Pattern already used by neighbouring `_PROBE_CACHE_LOCK`.

Files: [features/render/engine/preview/session_service.py](../../backend/app/features/render/engine/preview/session_service.py).

### IM-3 — Delete dead `app.ai.rag.sqlite_store` import (DC01)

Replace with static "not available" branch.

Files: [features/render/ai/diagnostics.py:74](../../backend/app/features/render/ai/diagnostics.py).

### IM-4 — Delete 15 unused upload Pydantic models (DC02)

`models/schemas.py:479-877`. Single-PR cleanup.

### IM-5 — Delete the 3 ghost dirs (B01)

`backend/app/{ai,orchestration,quality}/`. Update CLAUDE.md to remove the stale CRITICAL listings.

### IM-6 — LLM provider retry (AI05 / BR02)

Wrap each provider's `select_segments` and `select_render_plan` in a 2-attempt retry with `Retry-After` honour. Half-day per provider.

### IM-7 — Enforce `openapi-typescript` drift in CI (T05)

Add `.github/workflows/ci.yml` step that runs `npm run check:openapi-drift` and fails on diff. Prerequisite for IM-12.

### IM-8 — Decide on cloud API key policy (F07 / C02)

Either: (a) reject any `*_api_key` field on `RenderRequest`, force `.env` only; or (b) ship an encrypted-envelope path. **Do not ship plaintext into `payload_json` for another release.**

### IM-9 — One-shot DB `ANALYZE` at startup (DB08)

Add `conn.execute("ANALYZE")` at end of `init_db`. Improves planner stability over the DB's lifetime.

### IM-10 — Fix `target_platform` default mismatch (C05)

Pick `'youtube_shorts'` or `'tiktok'`; update both FE and BE.

### IM-11 — Add validator on `RenderRequest.part_order` (C01)

Reject unknown values OR wire `'sequential'` into the ranking stage. Either fix the contract or fix the implementation; don't ship the silent gap.

### IM-12 — First batch of Sacred-Contract tests (TEST02/04/05)

Three tests cover most of the regression risk:

1. WS payload shape (Sacred #6): assert any `_emit_render_event` call produces `{job, parts, summary}`.
2. AI provider None-on-failure (Sacred #3): parametrized test for all 3 providers.
3. `qa_pipeline` thresholds (Sacred #8): boundary tests around 10 KB / duration tolerance.

Estimated: 1 day total.

---

## Short term (1–2 months)

### ST-1 — Split `RenderRequest` into `Strict` (POST) and `Lenient` (replay) (C04)

Eliminates the silent-drop hazard for new fields during phased rollout while preserving Sacred Contract #2 for stored payloads.

### ST-2 — Promote stage/status to `enum.StrEnum` + assert-on-write (BR05 / C06)

Either reject typos in Python OR add SQL `CHECK(status IN (…))` in the next baseline.

### ST-3 — Surface AI fallback in FE (S05)

Display the `render.plan.ai_fallback` and `render.plan.persisted` event status in the rendering screen so the user knows the AI did or didn't drive the plan.

### ST-4 — Split `features/render/router.py` (A03 / A21)

Four sub-routers: `prepare/`, `render/`, `preview/`, `utility/`, all mounted under `/api/render`.

### ST-5 — Move cross-feature utilities to `app/core/` (A08)

`slugify`, `workflow_trace`, anything else that crosses the feature wall.

### ST-6 — Make `services/maintenance.py` and `services/warmup.py` feature-agnostic (A15 / A16)

Pull render-specific knowledge into `features/render/services/maintenance.py` + `warmup.py`. The non-feature `services/` modules call into feature-supplied hooks.

### ST-7 — Migrate `download_repo` callers off `services/db.py` (A14)

Then start sun-setting the facade. Smaller per-step blast radius than deleting all 18 callers at once.

### ST-8 — LLM response cache (AI06)

Content-addressable cache keyed by `(provider, model, srt_hash, params_hash)`. Re-renders pay zero LLM cost.

### ST-9 — Eliminate the `editor/` vs trim-modal duplication (F06)

Pick one surface for trimming. Phase 3 verdict: keep the trim modal inside `clip-studio/`; sun-set the standalone editor screen.

### ST-10 — Eliminate the `downloader/` vs DOWNLOAD-tab duplication (F06)

Same as above for the downloader.

### ST-11 — Delete duplicate API endpoints (API02 / API03 / API05 / API06)

- Pick one of the two media-streaming paths.
- Remove `/api/render/jobs/{id}` (duplicate of `/api/jobs/{id}`).
- Delete the 6 unused `/api/channels/*` (or build the management screen).
- Delete the 3 unused cookie endpoints (or build the UI button).

### ST-12 — Wire orphan diagnostics endpoints into Settings (API07)

`queue-status`, `system-info`, `ai-diagnostics`, `cache/clear` deserve a "Maintenance" screen. Cheap UI win; no API change.

### ST-13 — FE smoke test set (TEST09)

5 Vitest cases: `RenderWorkflow.tsx` step navigation, `RenderSocketClient.ts` reconnect, settings form CRUD, history list pagination, downloader URL paste flow.

### ST-14 — `_thread_conn` allocation safety (BR10)

Wrap conn allocation in a context manager that registers cleanup on worker-thread death. Eliminates the leak window before `run_render_pipeline` reaches its `try`.

### ST-15 — Add Prometheus histograms for DB lock-acquire time (DB09)

Visibility under concurrent renders. Small change inside `db_conn` and `_thread_conn`.

---

## Medium term (3–6 months)

### MT-1 — Decompose `services/dev_commands.py` (A01)

The 1542-LOC dev-tooling monolith into `services/dev/{router,registry,log,bug,autofix,test}.py`. Improves the audit experience for everyone using the dev-tool.

### MT-2 — Split `models/schemas.py` (A04 / C10)

Group: `models/render.py`, `models/jobs.py`, `models/feedback.py`, `models/download.py`, `models/settings.py`. Re-export from `models/__init__.py` for backward compat.

### MT-3 — `RenderRequest` decomposition (C10)

Split into `RenderRequestPublic` (FE-facing, ~30 fields) and `RenderRequestInternal` (server-derived). The 50+ BE-only fields become an explicit internal surface.

### MT-4 — `process_one_part` extraction (A20)

Per Phase 3 sketch: `SegmentMetadata`, `PartDB`, `PartEvents`, `PartOrchestrator`. Improves testability of per-part flow.

### MT-5 — Full render-pipeline integration test (TEST02)

Mock LLM + Whisper + FFmpeg, drive a 2-part render end-to-end, assert all stage transitions, all DB writes, all WS payload changes.

### MT-6 — Foreign keys + cascade in next baseline (BR03 / D-I.4)

Define `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE` on `job_parts` and `clip_feedback` in a baseline rewrite (new installs only) AND have the migration step add them via SQLite's `pragma foreign_keys=off; PRAGMA foreign_keys=on;` trick.

### MT-7 — DB row retention (DB05)

Optional auto-prune of completed jobs older than N days. With a setting in the Settings screen. `render_plan_json` is the biggest growth contributor.

### MT-8 — JobPart fields cleanup (C03)

Either inject `clip_name`, `ai_title`, `ai_reason`, `source` from `result_json` server-side, or remove from FE type.

### MT-9 — Optional: redesign WS to actual push (S02)

The current "poll DB at 500 ms + diff and send" works. Moving to a real in-process pub/sub (queue) would lower DB read load and improve latency. Only worth it if FE adds multi-window support.

---

## Long term (6–12 months)

### LT-1 — Consider multi-process / multi-host story

If the product ever wants to run renders on a beefy build machine while users edit on a laptop, the offline-first SQLite-only architecture becomes a hard ceiling. Sacred Contract #7 needs revisiting. Architectural choice: stay desktop-only (status quo, simplicity wins) or invest in a server-mode database + queue (Phase-G-scale change).

### LT-2 — V2 routers decision (`ENABLE_V2`)

`v2.api.routes.{download,render}` are present in `main.py` but conditional and undocumented. Either commit to V2 and migrate, or delete the conditional + the V2 directory.

### LT-3 — Remotion adapter renaming (T04)

`pipeline/remotion_adapter.py` doesn't invoke the Remotion npm framework. Rename to clarify intent or actually integrate Remotion.

### LT-4 — Replace ad-hoc dev_commands with a real CLI

Once MT-1 splits the file, consider a proper CLI library (Typer / Click).

### LT-5 — FE: introduce URL routing

If the FE ever ships in a browser (not just Electron), refresh-survival via real URLs becomes essential. The panel-based router is a deep desktop assumption.

### LT-6 — Auth path

If the product ever exposes a remote endpoint (collaborative review, render farms, …), the no-auth assumption needs a complete rework. Until then, document the localhost-only constraint clearly in the README so no one accidentally publishes it.

---

## Summary table

| Bucket | Items | Theme |
|---|---|---|
| Immediate | 12 | risk reduction + cheap wins |
| Short term | 15 | refactor + observability + tests |
| Medium term | 9 | architecture cleanup |
| Long term | 6 | strategic / paradigm-level |

End of 27_future_roadmap.md.
