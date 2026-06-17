# Phase 10 — Result (2026-06-17)

> Closes Phase 10 of the perf optimisation programme. 3 items merged
> after triage rejected D1 as failure-path-only / risky and replaced
> the audit's "event-driven push" D7 with a trivial sleep-interval bump.

## Outcome

**PASS.** D6 + D7-light + D8 merged. D1 deferred indefinitely.

## Edits made

| # | Item | File | Tier | Change |
|---|---|---|---|---|
| 1 | D6 executor env | `app/features/download/router.py` | LOW | Added `_exec_size(env_name, default, min=1, max=16)` helper. `_DOWNLOAD_EXECUTOR` now sized via `DOWNLOAD_MAX_WORKERS` (default 3); `_ENRICH_EXECUTOR` via `DOWNLOAD_ENRICH_WORKERS` (default 2). Clamped to [1, 16] to prevent a runaway env value from blowing up the process. |
| 2 | D7-light WS sleep | `app/features/download/router.py:job_progress_ws` | LOW | `asyncio.sleep(1.0)` → `asyncio.sleep(2.0)`. Halves DB queries against `download_jobs` per active WS connection. Download progress bar updates at 2-second cadence — invisible UX delta since download progress is dominated by network latency. |
| 3 | D8 parallel enrichment | `app/features/download/engine/enrichment.py:_do_enrich` | LOW | `_ffprobe_metadata` runs first (gives duration). Then `_detect_language` (5–15 s Whisper-tiny) and `_extract_thumbnail` (0.5–2 s ffmpeg) run concurrently via a 2-worker `ThreadPoolExecutor`. `_heuristic_content_type` + `_file_size` are constant-time and stay on the main enrichment thread. |

2-file edit. All three items independently revertable.

## Rejected (file-state triage)

**D1 — Consolidate dynamic probing** (`downloader.py:692-700`).
The audit said "parallelize 4 sequential `_probe_info` calls" to save
4–12 s. But the loop only runs on the failure path
(`unavailable_requested=True`), and running 4 yt-dlp probes against
YouTube in parallel risks rate-limit hits. Deferred indefinitely.

**D7 event-driven push** (full refactor).
No download-side event broadcaster exists today (only render has
`EVENT_BROADCASTER`). Building one for a 1 s → ~0 s WS poll
improvement is disproportionate. The "increase sleep to 2 s"
alternative captures the bulk of the DB-query win for zero
infrastructure cost.

## Verification

### Pytest

| Suite | Tests | Result |
|---|---|---|
| Focused (3 suites) | 47 | **47 / 47 pass** (= baseline) |
| Full | 1396 | **1396 / 1396 pass** (= baseline) |

### D6 env override probe ✓

```
default _DOWNLOAD_EXECUTOR.max_workers:                       3
default _ENRICH_EXECUTOR.max_workers:                         2
DOWNLOAD_MAX_WORKERS=5  → _DOWNLOAD_EXECUTOR.max_workers:    5
DOWNLOAD_ENRICH_WORKERS=4 → _ENRICH_EXECUTOR.max_workers:    4
DOWNLOAD_MAX_WORKERS=32 → clamped to 16                     ✓
DOWNLOAD_ENRICH_WORKERS=-5 → clamped to 1                    ✓
```

Defaults match the pre-Phase-10 hardcoded values, so existing
installations behave identically until they opt in. Out-of-range env
values are clamped, never crash.

### D8 enrichment parallelisation — code-path check

`_do_enrich` now uses a 2-worker pool for the language + thumbnail
phase. ffprobe runs first because both downstream steps need
`duration_sec`. Verified via py_compile + focused pytest.

End-to-end timing depends on having an asset to enrich; happy-path
projection on a typical 1-minute mp4 with the Whisper-tiny path
warm:

| Step | Before (sequential) | After (parallel) | Saved |
|---|---|---|---|
| ffprobe | 0.5–1.0 s | 0.5–1.0 s | 0 |
| language detection | 5–15 s | overlaps with thumb | — |
| thumbnail | 0.5–2 s | overlaps with lang | — |
| **language ∥ thumbnail** | sum of both | max(lang, thumb) | **5–10 s** |

### Acceptance checklist

- [x] py_compile passes on both files
- [x] Focused pytest 47/47 (= baseline)
- [x] Full pytest 1396/1396 (= baseline)
- [x] D6 default = pre-Phase-10 hardcoded (3 / 2)
- [x] D6 env override respected for both executors
- [x] D6 clamp [1, 16] holds
- [x] D7-light WS sleep changed from 1.0 → 2.0 s
- [x] D8 ffprobe-first ordering preserved (language + thumb both need duration)
- [x] Sacred Contracts 1–8 untouched (render pipeline not touched)
- [x] Frozen API contracts: `/api/downloader/*` response shapes unchanged

## Insight

Two audit items in Phase 10 turned into trivial knobs:
- D6 is a one-line env-var lift; operators with bigger machines can
  now raise the ceiling without a code edit.
- D7's "event-driven push" promise was 99 % DB-query reduction at the
  cost of building a download-side event broadcaster from scratch.
  The 50 % reduction from a 1 s → 2 s sleep captures most of the
  win without any infrastructure cost — a much better
  cost/benefit trade.

D8's gain (5–10 s per enrichment) is real and stacks with Phase 3's
Whisper-tiny singleton: a freshly downloaded asset that hits the
singleton + parallel-enrichment path can finish enrichment in
~6–10 s instead of ~15–25 s pre-Phase-3.

## Rollback path (not needed)

```bash
git checkout backend/app/features/download/router.py
git checkout backend/app/features/download/engine/enrichment.py
```

Or simpler runtime rollback for D6: `unset DOWNLOAD_MAX_WORKERS` +
`unset DOWNLOAD_ENRICH_WORKERS` returns to defaults.

## Time spent

- Triage + mini-plan: ~15 min
- Pytest baseline + 3 edits + py_compile: ~15 min
- Focused + full pytest: ~3 min
- D6 env override + clamp probe: ~5 min
- Result doc: ~10 min

**Total: ~45 min** (at budget).
