# 26 — Known Issues

Consolidated open issues at audit time (2026-06-06). All findings from Phases 1–9. Sorted by severity then phase.

## HIGH / CRITICAL

| Phase | ID | Issue |
|---|---|---|
| 1 | F07 / C02 | Cloud LLM API keys live in `localStorage` plaintext on FE, then ride in `RenderRequest` body, then persist in `jobs.payload_json` forever. Leaks via any DB dump or support bundle. |
| 1 | U01 | Zero auth anywhere. Anything running locally on the host hits any endpoint. `routes/devtools.py` is shell-exec gated only by `ENABLE_DEVTOOLS=1` env. |
| 2 / 4 | AI07 / BR02 / S07 | `llm_pipeline.py` raises `LLMPipelineError` on any of 7 failure modes (missing key, Whisper failure, etc.). No retry, no fallback. One transient 503 from Gemini = 40-minute render dies. FE shows generic "failed". |
| 2 / 4 | R01 / BR04 | `NVENC_SEMAPHORE` acquired at only 3 sites. `clip_ops.cut_video`, `mixer.mix_narration_audio`, `motion/*`, `preview/ffmpeg_probers` don't consult it. If any path passes `*_nvenc` argv, all active NVENC sessions fail together. |
| 4 | BR01 | `_PREVIEW_SESSIONS` dict mutated from multiple call sites without a lock. Race window in eviction logic. KeyError or stale session under concurrent WS subscribers. |
| 4 | BR05 / D02 | Status enums are TEXT, no `CHECK` constraint. A writer typo silently corrupts every consumer. |
| 4 | DC01 | `features/render/ai/diagnostics.py:74` imports `app.ai.rag.sqlite_store` — module does not exist. Silent try/except → AI diagnostics always reports SQLite unavailable. |
| 5 | T01 | MediaPipe is the preferred subject detector. Without AI extras installed, motion-aware crop silently degrades to OpenCV Haar (weaker). No FE indicator. |
| 5 | T05 | `openapi-typescript` codegen has a script but no CI enforcement. FE compiles against stale types. |
| 6 | API09 | `RenderRequest.model_config = ConfigDict(extra="ignore")`. New FE fields silently dropped on phased rollouts; debugging is hours. |
| 7 | C01 | `RenderRequest.part_order` allows `"sequential"` from FE but BE never branches on it. Silent UX-vs-behavior mismatch. |
| 7 | C03 | `JobPart` FE type declares `clip_name`, `ai_title`, `ai_reason`, `source` — not in DB column or route response. Origin unknown. |
| 9 | TEST02 / TEST03 / TEST04 / TEST05 | Critical files untested: `render_pipeline.py` (1357 LOC), `llm_pipeline.py` (448 LOC), WS handler in `routes/jobs.py`. Sacred Contracts #3 and #6 not verified by automated tests. |
| 9 | TEST09 | Zero FE tests; Vitest installed and unused. |
| 9 | TEST10 | CI gate on `pytest`/`vitest` not verified — existing 2,444 LOC of tests may not gate any PR. |

## MEDIUM

| Phase | ID | Issue |
|---|---|---|
| 1 | B01 | Ghost dirs `backend/app/{ai,orchestration,quality}/` — zero `.py` files, only `__pycache__`. CLAUDE.md still lists them as CRITICAL. |
| 1 | F03 | No FE auth/session store. |
| 1 | F06 / U07 | Two surfaces for the same data: standalone `editor/` vs trim modal inside `clip-studio/`, standalone `downloader/` vs DOWNLOAD tab. |
| 2 | AI05 | LLM providers have no retry. Single network blip kills the job (subset of AI07). |
| 2 | AI06 | LLM response not cached. Re-render pays full LLM cost again. |
| 2 | R02 | 4 active render feature flags = 16 combinations; cross-combinations untested. |
| 3 | A01 | `services/dev_commands.py` (1542 LOC) — god file handling 10+ concerns. |
| 3 | A03 / A21 | `features/render/router.py` (1195 LOC) — 15+ endpoints in one file. |
| 3 | A08 | `download` ↔ `render` cross-feature import (asymmetric). |
| 3 | A11, A12, A13 | Hidden coupling via module globals (`NVENC_SEMAPHORE`, `_PREVIEW_SESSIONS`, thread-local cancel). |
| 3 | A15 / A16 | `services/maintenance.py` and `services/warmup.py` know render details — feature leakage. |
| 3 | A20 | `process_one_part()` mixes parsing + DB + events + orchestration. |
| 4 | BR03 | `delete_job` cascade transactional but no SQL FK; orphan risk if maintenance bypasses helper. |
| 4 | BR06 | WS handler `await` blocks on sync DB calls; rare blocker under stress. |
| 4 | BR07 | FFmpeg `child.wait()` post-terminate has no timeout. |
| 4 | BR08 | `asyncio.run()` inside ThreadPoolExecutor worker (tts.py). |
| 4 | BR09 | Cache key collision risk on Windows mtime granularity. |
| 4 | BR10 | `_thread_conn` leak if worker thread dies pre-pipeline. |
| 4 | DC02 / DC06 | 15 + 2 unused upload/download Pydantic models in `models/schemas.py`. |
| 4 | DC04 / DC05 | ~70 orphan `.pyc` files in `services/__pycache__/` and ghost-dir caches. |
| 4 | DC07 | FE upload.ts documents 7 removed endpoints — verify FE has no shadow callers. |
| 4 | DUP01 | JobId regex/validator triplicated in 3 files. |
| 4 | DUP03 | `output_dir` validation duplicated between router and pipeline_setup. |
| 4 | DUP05 | Three different progress-percent formulas. |
| 5 | T02 | Three unused AI optional deps: `sentence-transformers`, `faiss-cpu`, `librosa`. |
| 5 | T03 | Playwright Python SDK declared but no Python importer; used only as Chromium installer. |
| 6 | API02 / API03 | Duplicate media streaming endpoints; duplicate job-status endpoint. |
| 6 | API05 | 6 channel endpoints all UNCALLED. |
| 6 | API06 | 3 cookie endpoints UNCALLED. |
| 6 | API07 | 9 admin/diagnostics endpoints orphaned (cache/clear, system-info, ai-diagnostics, voice/profiles, thumbnail, subtitle-preview, logs, …). |
| 7 | C04 / C06 | Strict-vs-lenient model split missing; `kind`/`status` unenumerated. |
| 7 | C05 | `target_platform` default mismatch (`'tiktok'` FE vs `'youtube_shorts'` BE). |
| 7 | C07 | `confidence_tier` may be empty when `available=true`. |
| 8 | DB06 | `list_jobs()` unbounded helper still exposed. |

## LOW

(See per-phase docs — too many to list here. Cosmetic, refactor candidates, or one-line cleanups.)

## Resolved / corrected during the audit

- Phase 1 D-I.1 (HIGH "missing index on job_parts.job_id") — corrected in Phase 8 DB01. SQLite serves the lookup via the leftmost prefix of the UNIQUE composite index. Not actually missing.
- Phase 4 BR05 (HIGH "_thread_conn leak in finally") — corrected. `close_thread_conn()` IS called at [render_pipeline.py:1357](../../backend/app/features/render/engine/pipeline/render_pipeline.py). The real residual risk is BR10 (pre-pipeline thread death) which is MED.

End of 26_known_issues.md.
