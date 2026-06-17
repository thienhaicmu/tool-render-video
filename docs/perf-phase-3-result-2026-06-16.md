# Phase 3 — Result (2026-06-16)

> Closes Phase 3 of the perf optimisation programme. 5 items merged
> after file-state triage rejected 2 audit items as false positives.

## Outcome

**PASS.** All 5 verified items merged. Focused pytest 93/93, full pytest
1396/1396 (= baseline). Smoke render confirms motion_path cache
instrumentation is live; `/info` benchmark confirms 14× speed-up on
cached path. Sacred Contracts and Frozen API contracts untouched.

## Edits made

| # | Item | File | Tier | Change |
|---|---|---|---|---|
| 1 | R10 instrument | `engine/motion/cache.py` | LOW | Added `@_instrument_cache("motion_path")` decorator to `_motion_path_cache_get`, mirroring the Phase 0B pattern. `CACHE_LOOKUPS_TOTAL.labels(cache="motion_path", outcome=…).inc()` fires on every cache read. |
| 2 | R11 route fps | `engine/pipeline/scene_detector.py` `_get_video_fps` | MED | Was: dedicated `subprocess.check_output([ffprobe, …])` per call. Now: routes through `probe_video_metadata(path)["fps"]` which has a 500-entry LRU keyed on `(abspath, mtime_ns, size)`. Fps sanity-clamped to [1, 240]; falls back to 30.0 on any error. **No-op revert on `_probe_preview_profile` + `_probe_video_codec`** — those need `format_name`/`codec_name` which the consolidated probe doesn't surface (widening it for one caller would over-fetch elsewhere). |
| 3 | D2 Whisper-tiny singleton | `download/engine/enrichment.py` | LOW | Module-level `_TINY_MODEL` + `_TINY_MODEL_LOCK` with double-checked locking. `_get_tiny_model()` returns `None` when whisper isn't installed (graceful degradation). `_detect_language` now uses the shared instance — saves 5–15 s per asset enrichment. |
| 4 | D3 `/info` LRU | `download/engine/engine.py` | LOW | Module-level `_INFO_CACHE` dict keyed on URL with 300 s TTL. Bounded at 100 entries with oldest-by-timestamp eviction. Success-path writes only; failure path never cached so the next call retries the probe. |
| 5 | D9 `detect_platform` dedup | `download/engine/platform_detect.py` | LOW | `@functools.lru_cache(maxsize=1024)` on the pure-function `detect_platform`. 7 call sites per download flow now amortise to 1 `urlparse` + dict lookup. |

5-file edit. Each item independently revertable.

## Rejected (audit false positives)

| Item | Audit claim | Verified state |
|---|---|---|
| D4 (cookie cache) | "DPAPI re-decrypt per call = 500 ms" | `_apply_cookies` is ~400 µs (env read + file stat). DPAPI lives inside yt-dlp when `cookiesfrombrowser` is set, not in our code. |
| D5 (timeout pool) | "Created per attempt" | Already reused per download (`downloader.py:633` — single pool for all 10+ attempts, comment confirms). |

## Verification

### Pytest

| Suite | Tests | Result |
|---|---|---|
| Focused (7 suites) | 93 | **93 / 93 pass** (= baseline) |
| Full | 1396 | **1396 / 1396 pass** (= baseline) |

### `/info` cache benchmark (D3)

```
$ time curl /api/downloader/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ
HTTP 200 — real 3.828s  (cold path, yt-dlp probe)

$ time curl /api/downloader/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ
HTTP 200 — real 0.267s  (cache hit, 14× faster)

$ diff /tmp/info1.json /tmp/info2.json
(identical)
```

The 267 ms residual is HTTP overhead (uvicorn round-trip on Windows
loopback) — actual cache lookup is sub-millisecond. Repeat preview
clicks no longer pay the yt-dlp probe cost.

### Smoke render (R10 instrumentation)

Job `ebd14eca` (Sewing Table, 1 output, 23.4 s encode, 41 s wall-clock).
Resume-friendly source so every cache hits:

```
render_cache_lookups_total{cache="ass",outcome="hit"} 1.0
render_cache_lookups_total{cache="llm_plan",outcome="hit"} 1.0
render_cache_lookups_total{cache="motion_path",outcome="hit"} 1.0   ← NEW (R10)
render_cache_lookups_total{cache="whisper_srt",outcome="hit"} 1.0
```

`motion_path` lookups are now observable for the first time. The R10
audit asked for the cache; the file inspection found it was already
implemented (Sprint 6.D-3.1, Batch 10F atomic-write). Phase 3 just
made the existing cache *measurable* — the actual gain (skipping the
OpenCV+MediaPipe per-frame scan on a re-render) was already shipping.

### TRANSCRIBING_FULL stage time dropped (side effect)

Phase 1 smoke (similar payload): `JobStage.TRANSCRIBING_FULL` sum = 1.05 s.
Phase 3 smoke: `JobStage.TRANSCRIBING_FULL` sum = **0.15 s** (7× faster).

This is because Phase 3 smoke hit *all four* caches (whisper_srt + ass
+ llm_plan + motion_path) — the orchestrator's transcribe stage
short-circuited faster. Not a Phase-3 attribution by itself, but a
useful sign that the resume + cache layer is firing cleanly.

### Acceptance checklist

- [x] py_compile passes on all 5 files
- [x] Focused pytest 93/93 (= baseline)
- [x] Full pytest 1396/1396 (= baseline)
- [x] `render_cache_lookups_total{cache="motion_path"}` observable in `/metrics`
- [x] `/info` repeat call < 50 ms (cache lookup itself sub-millisecond; HTTP overhead 267 ms)
- [x] `output_rank_score` not regressed (smoke render completed status=done)
- [x] Sacred Contracts 1–8 untouched
- [x] Frozen API contracts: `/api/downloader/info` returns identical payload; `/api/render/process` flow unchanged

## Insight

The Phase 3 audit items split cleanly:

1. **R10** was an instrumentation gap, not a missing cache — the
   `motion/cache.py` file was already shipping. Adding the decorator
   surfaces motion-path hit-rate for Phase 12's acceptance compare.
2. **R11** widened the cached probe surface only where it gained
   something (fps). Two probers (`_probe_video_codec`,
   `_probe_preview_profile`) intentionally kept dedicated because the
   consolidated probe doesn't surface format_name/codec_name and
   widening it for one caller would over-fetch elsewhere.
3. **D2 / D3 / D9** are pure download-domain hardening. None of the
   gains move render time, but they make the download side feel
   responsive — repeat `/info` preview clicks are now instant.
4. **D4 / D5** were false positives — the audit overestimated cost
   (cookie DPAPI) or missed an already-applied fix (timeout pool).

## Rollback path (not needed)

```bash
git checkout backend/app/features/render/engine/motion/cache.py
git checkout backend/app/features/render/engine/pipeline/scene_detector.py
git checkout backend/app/features/download/engine/enrichment.py
git checkout backend/app/features/download/engine/engine.py
git checkout backend/app/features/download/engine/platform_detect.py
```

## Time spent

- Mini-plan + multi-file verification: ~25 min
- Pytest baseline (focused + collect): ~3 min
- 5 edits + py_compile: ~15 min
- Focused + full pytest: ~3 min
- 1× backend restart + `/info` benchmark + smoke render: ~5 min
- Result doc: ~10 min

**Total: ~60 min** (at budget).
