# 28 — Executive Summary

**Audit date:** 2026-06-06
**Branch:** `feature/ai-workflow-upgrade` @ `f3b6858`
**Methodology:** source code only — `README`, `CLAUDE.md`, `docs/review/**`, and the prior architecture docs were deliberately ignored except where cross-cited as findings.
**Phases covered:** 11 of 11 (Phase 1 Discovery → Phase 11 Roadmap).
**Deliverables:** 28 markdown files in `docs/audit-2026-06-06/`.

---

## Current architecture score: **5.4 / 10**

Mid-grade. Strong intent and consistent contracts undermined by accumulated complexity (god files, ghost dirs, stale docs) and an under-invested test surface.

Per-dimension scores (Phase 3 §6):

| Dimension | Score | One-line take |
|---|---|---|
| Scalability | 4 | offline-first by design; single SQLite + single process |
| Maintainability | 5 | 8 god files, 3 ghost dirs, 18-caller facade, CLAUDE.md actively misleading |
| Readability | 6 | good module names, big functions, Sacred Contracts by number only |
| Extensibility | 6 | LLM/subtitle/audio pluggable; render stage sticky |
| Testability | 4 | 17 BE tests for 180 modules; **0 FE tests** |
| Reliability | 6 | contracts honored, QA solid; no FK, no LLM retry, NVENC sem gap |
| Observability | 7 | Prometheus + per-job log + AI summary — excellent for a desktop app |

---

## What is in good shape

- **Sacred contracts honored where they're checked.** #1 (result_json keys) tested. #8 (QA gate) tested. #3 (AI returns None) verified by audit. #6 (WS shape) verified by audit. #4/#5 (stage names) frozen by convention.
- **Database layer is mature.** WAL, atomic deletes, indexes correctly cover query shapes, additive-only migrations, atomic backups. The Phase 1 "missing index" alarm was retracted — the implicit composite index covers the lookup.
- **Offline-first verified.** Zero cloud storage SDKs, zero external queue, zero vector DB. The risk surface is genuinely small for the design intent.
- **Per-feature folder layout.** Phase 1-18 migration successfully isolated `features/render/` and `features/download/`. Stage helpers under `engine/stages/` are reasonably small.
- **AI dispatch + provider abstraction is clean.** Three LLM providers, all lazy-imported, all return None on failure. Adding a fourth provider is a single-file change.

---

## Critical findings (top 5 — must address)

| # | Finding | Where | Why critical |
|---|---|---|---|
| 1 | **Cloud LLM API keys in plaintext throughout the system** (F07/C02) | FE localStorage → `RenderRequest` body → `jobs.payload_json` DB column + per-job logs | Single support-bundle export leaks the key forever. Plaintext credentials in tracked storage. |
| 2 | **LLM pipeline is HARD-FAIL with no retry and no fallback** (AI07/BR02/S07) | `llm_pipeline.py:88-448` | One transient 503 from Gemini = a 40-minute render dies. FE shows generic "failed". No user-visible recovery path. |
| 3 | **NVENC semaphore not centralized** (R01/BR04) | `ffmpeg_helpers.py` + 3 acquire sites; multiple other FFmpeg call sites bypass | If any non-acquiring path passes `*_nvenc` argv, all active NVENC sessions fail together. Cluster failure with opaque error. |
| 4 | **`_PREVIEW_SESSIONS` race condition** (BR01) | `preview/session_service.py:18-82` | Concurrent WS subscriber + eviction loop = KeyError / stale session. Unprotected dict mutation. |
| 5 | **CLAUDE.md is stale and actively misleading** | references `backend/app/orchestration/render_pipeline.py` — file does not exist | New agents protect the wrong files, miss the actual god files, and propagate ghost-dir confusion. |

---

## HIGH-severity findings (15)

In addition to the top 5: U01 (zero auth), DC01 (dead import), DC02 (15 dead Pydantic), T01 (MediaPipe silent degrade), T05 (no codegen drift gate), API09 (`extra="ignore"` drops new fields), C01 (`part_order` enum unenforced), C03 (`JobPart` undocumented fields), C04 (no strict/lenient split), TEST02/03/04/05 (critical untested code paths), TEST09 (zero FE tests), TEST10 (CI verification missing).

---

## Technical debt — estimated effort

| Bucket | Effort | Scope |
|---|---|---|
| 1 week | 12 items | risk-reduction + cleanup (IM-1 to IM-12 in [roadmap](27_future_roadmap.md)) |
| 1 month | 15 items | refactor + observability + first FE tests (ST-1 to ST-15) |
| 3 months | 9 items | god-file decomposition + FK + integration tests (MT-1 to MT-9) |
| 6 months | 6 items | strategic decisions (V2 routers, multi-host story, auth path) |

---

## Production risks (ranked)

1. **Credential leak via plaintext API key in DB** — CRITICAL if any user enables cloud LLM.
2. **NVENC cluster failure under concurrent renders** — HIGH on any GPU host.
3. **LLM hard-fail under transient network conditions** — HIGH; renders silently die on cloud blip.
4. **Status-string typos corrupting the state machine** — MEDIUM; one bad Python line takes down every consumer.
5. **`_PREVIEW_SESSIONS` race under multi-tab usage** — MEDIUM; rare but real.
6. **Missing CI gates on test + OpenAPI drift** — HIGH long-term; current tests gate nothing if PRs don't run them.
7. **Feature-flag explosion** — MEDIUM; 2^4 untested combinations in render pipeline.
8. **18 callers of `services/db.py` facade** — MEDIUM-LOW; schema changes ripple across the codebase.
9. **FE clip_name/ai_title/ai_reason fields with no BE producer** — LOW; FE renders `undefined` silently.
10. **Stale CLAUDE.md misdirecting future agents** — MEDIUM; will keep causing rework until rewritten.

---

## Recommended next actions — Top 20 by ROI

Each bullet cites the originating finding. Effort tag: `[hour] / [day] / [week] / [sprint]`. Risk tier: `[L/M/H]`.

1. `[hour]` `[H]` Delete dead `app.ai.rag.sqlite_store` import in `diagnostics.py:74` (DC01).
2. `[hour]` `[H]` Add `Lock` around `_PREVIEW_SESSIONS` mutations (BR01).
3. `[hour]` `[H]` Delete 3 ghost dirs `backend/app/{ai,orchestration,quality}/` (B01).
4. `[hour]` `[H]` Delete 15 unused upload Pydantic models in `schemas.py:479-877` (DC02).
5. `[hour]` `[M]` Add validator on `RenderRequest.part_order` enum (C01).
6. `[hour]` `[M]` Add `ANALYZE` to `init_db` (DB08).
7. `[hour]` `[L]` Align `target_platform` default in FE+BE (C05).
8. `[day]` `[H]` Centralize NVENC semaphore in `_run_ffmpeg_with_retry` (R01/BR04).
9. `[day]` `[H]` Reject cloud API keys in `RenderRequest`, force `.env` (F07/C02).
10. `[day]` `[H]` LLM provider 2-attempt retry with `Retry-After` honour (AI05/BR02).
11. `[day]` `[H]` Add CI gate on `pytest`, `vitest`, and `check:openapi-drift` (TEST10/T05).
12. `[day]` `[H]` Write 3 Sacred Contract tests: #3 (provider None), #6 (WS shape), #8 (qa thresholds) (TEST04/05).
13. `[day]` `[H]` Rewrite or delete CLAUDE.md sections that reference dead files (top-line finding).
14. `[day]` `[M]` Migrate `download_repo` callers off `services/db.py` (A14, start of sunset).
15. `[sprint]` `[H]` Split `RenderRequest` into Strict (POST) + Lenient (replay) (C04).
16. `[sprint]` `[H]` Promote stage/status to `enum.StrEnum` + SQL `CHECK` (BR05/C06).
17. `[sprint]` `[M]` Write render-pipeline smoke test (TEST02).
18. `[sprint]` `[M]` Split `features/render/router.py` into 4 sub-routers (A03/A21).
19. `[sprint]` `[M]` Eliminate `editor/` standalone screen — keep trim modal in `clip-studio/` (F06).
20. `[sprint]` `[M]` Build a Maintenance screen wiring 4 orphan admin endpoints (queue-status, system-info, ai-diagnostics, cache/clear) (API07).

---

## Closing note

The system has a clear identity (offline-first desktop, AI-assisted clip studio) and a defensible architecture for that intent. The biggest risk is not the architecture; it's the **gap between the system as documented and the system as written**. CLAUDE.md, the Sacred Contract list, and roughly half of `docs/review/**` describe paths that no longer exist or invariants that aren't tested. Closing that gap — through this audit + Phase 11 roadmap items 13 (rewrite CLAUDE.md), 11 (CI gates), and 12 (contract tests) — buys back more reliability per engineer-day than any refactor.

The Top 20 actions above will reduce HIGH-severity findings from 15 → 4 and lift the architecture score from 5.4 to roughly 6.5 within one sprint of investment. Beyond that, the Medium-term work in [27_future_roadmap.md](27_future_roadmap.md) targets a 7.5–8.0 score over a quarter.

End of 28_executive_summary.md.
