# Download-Feature Review Fixes — 2026-06-18

> **Append-only audit record.** New file. Closes the 10 findings from a
> full-module code review of `backend/app/features/download/` (19 files,
> ~2567 LOC). Companion to `PERF_REVIEW_FIXES_2026-06-18.md`.
> Baseline pytest before edits: **1401 passed**. After edits (−21 deleted
> `test_download_service` cases, +23 new regression tests): **1403 passed,
> 0 failed.**

## Context

The review found 3 high-severity (functional/correctness), 4 medium, and 3
low-severity issues. The user approved fixing all 10, and chose the
recommended architecture for the #1/#4 pair: **delete the unused
adapter-chain subsystem and add `quality` support to the live
`engine.download_video` path** (rather than wiring the router onto the
adapters).

## Findings & closures

### F1 (HIGH) — `quality` selector was a no-op (all downloads ≤1080p "best")
- **Files:** `engine/engine.py`, `router.py`
- **Defect:** `DownloadStartRequest.quality` was never forwarded;
  `engine.download_video` had no `quality` param and `_base_opts` always
  capped at ≤1080p. `dl_job_start` hardcoded `quality="best"`.
- **Fix:** Added `_quality_to_format(quality)` (best|1080p|720p|480p →
  format string), a `quality` kwarg on `download_video`, and forwarded
  `req.quality` through `_run_download`. `best` is now genuinely uncapped.

### F2 (HIGH) — Download-tab cancel did not stop the download
- **Files:** `engine/engine.py`, `router.py`
- **Defect:** `cancel_job` only updated/deleted the DB row; the worker's
  yt-dlp kept running (no cancel signal on this path).
- **Fix:** Added a `cancel_event` kwarg to `download_video` (the progress
  hook raises when set, aborting yt-dlp). Router keeps a
  `_CANCEL_EVENTS{job_id}` map, created in `_run_download`, set by
  `cancel_job`, cleared in the worker's `finally`.

### F3 (HIGH) — `/batch` bypassed in-flight dedup + clobbered the marker
- **File:** `router.py`
- **Defect:** `start_batch` never consulted `_INFLIGHT_URLS`, so the same
  URL across batch+single (or two batches) spawned duplicate downloads;
  every worker's `finally` popped the marker unconditionally, so one job
  could clear another job's reservation.
- **Fix:** Extracted `_reserve_inflight` / `_release_inflight`; both
  `/start` and `/batch` reserve atomically. The `finally` now pops only if
  the marker still points at *this* job.

### F4 (MEDIUM) — ~700 LOC dead adapter subsystem
- **Files removed:** `service.py`, `adapters/` (8 files),
  `tests/test_download_service.py`
- **Defect:** A second `download_video`/`get_adapter` adapter chain was
  re-exported by the package `__init__` but invoked by nothing (the live
  path is `engine.download_video`).
- **Fix:** Deleted the subsystem and its test; `download/__init__.py` now
  re-exports the live `engine.download_video` / `get_video_info`.

### F5 (MEDIUM) — live download path had no wall-clock ceiling
- **Files:** `engine/engine.py`, `engine/downloader.py`
- **Defect:** `engine.download_video` relied only on `socket_timeout=60`;
  the dead `download_public_video` (FB/IG) had neither.
- **Fix:** Wrapped the yt-dlp call in `download_video` with a
  `_DL_WALLCLOCK_TIMEOUT` ceiling (env `DOWNLOAD_WALLCLOCK_TIMEOUT`,
  default 1800s) run on a 1-worker pool with `shutdown(wait=False)` in
  `finally`. Deleted the dead `download_public_video` /
  `detect_public_video_source` / `_resolve_download_filepath` /
  `SUPPORTED_PUBLIC_SOURCES` chain (+ the unused `re` import).

### F6 (MEDIUM) — cookie_extractor temp-file leak + insecure `mktemp`
- **File:** `engine/cookie_extractor.py`
- **Defect:** Strategy-2 used `tempfile.mktemp()` (insecure) and, when the
  smoke-test failed, returned `None` without unlinking the copied `.db`.
- **Fix:** `tempfile.mkstemp()` + an `except` that closes the connection
  and unlinks the temp file on any pre-close failure.

### F7 (MEDIUM) — `download_youtube` wall-clock pool leaked on success
- **File:** `engine/downloader.py`
- **Defect:** `_timeout_pool.shutdown()` ran only on the failure path; the
  two success `return`s (and the wall-clock `raise`s) leaked the worker
  thread until GC.
- **Fix:** Wrapped the attempt waterfall in `try/finally` so the pool is
  always reaped.

### F8 (LOW) — `_INFLIGHT_LOCK` held across mkdir + DB I/O
- **File:** `router.py`
- **Defect:** `start_download` did `_validate_output_dir` (mkdir) and
  `create_download_job` (DB write) inside the lock, serialising all
  concurrent `/start` calls behind I/O.
- **Fix:** Only the atomic dedup check/reserve stays under the lock;
  filesystem + DB work moved outside (with marker rollback on failure).

### F9 (LOW) — cookie host filter dropped subdomain cookies
- **File:** `engine/cookie_extractor.py`
- **Defect:** SQL fetched `%youtube%`/`%google%` but Python kept only 3
  exact hosts, discarding `accounts.google.com`, `music.youtube.com`, etc.
- **Fix:** `_is_youtube_auth_host` keeps any host that equals or is a
  subdomain of `youtube.com` / `google.com` (leading-dot suffix match —
  no lookalike bypass).

### F10 (LOW) — platform_detect rejected legit subdomains; inconsistent caching
- **File:** `engine/platform_detect.py`
- **Defect:** `removeprefix("www.").removeprefix("m.")` + exact match
  rejected `music.youtube.com` etc.; `detect_platform` was cached but
  `is_allowed_url` was not.
- **Fix:** Shared `_platform_for_host` with exact-or-subdomain matching
  (leading-dot suffix, so `youtube.com.evil.com` still resolves to
  `other`). `is_allowed_url` now derives from the same matcher.

## Verification

- Baseline full pytest: **1401 passed**.
- After edits: deleted `test_download_service.py` (21 collected cases),
  added `tests/test_download_review_fixes_2026_06_18.py` (23 cases
  covering F1, F3, F9, F10 incl. allowlist-bypass guards).
- Final: **1403 passed, 0 failed.** `py_compile` + import smoke-tests
  clean on every changed module.

## Files changed

```
backend/app/features/download/__init__.py
backend/app/features/download/router.py
backend/app/features/download/engine/engine.py
backend/app/features/download/engine/downloader.py
backend/app/features/download/engine/cookie_extractor.py
backend/app/features/download/engine/platform_detect.py
backend/tests/test_download_review_fixes_2026_06_18.py   (new)
backend/app/features/download/service.py                 (deleted)
backend/app/features/download/adapters/**                (deleted, 8 files)
backend/tests/test_download_service.py                   (deleted)
```
