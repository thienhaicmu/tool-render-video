# 11 — Bug Risk Report

Findings classified as **CONFIRMED** (verified in code), **PROBABLE** (code looks vulnerable; needs a test to prove), or **ASSUMPTION** (needs investigation). Severity HIGH/MED/LOW.

Each finding includes file:line evidence. Phase 1/2/3 already established the threading model, DB connection patterns, and Sacred Contracts.

---

## HIGH

### FINDING-BR01 — `_PREVIEW_SESSIONS` unprotected (CONFIRMED, HIGH)

[features/render/engine/preview/session_service.py:18-82](../../backend/app/features/render/engine/preview/session_service.py).

Module-level dict mutated from multiple call sites without a lock:
- `register_session(...)` — write.
- `get_session(...)` — read.
- `_evict_stale_preview_sessions(...)` — bulk eviction (lines 27-32 compute `min(...)` then delete).
- Re-exported and called from [features/render/router.py:46-49](../../backend/app/features/render/router.py) preview handlers.

The neighbouring `_PROBE_CACHE` (an `OrderedDict`) has `_PROBE_CACHE_LOCK` — the lock discipline is inconsistent. `_PREVIEW_SESSIONS` is not under any lock today.

**Race:** two requests arriving on different uvicorn workers (or two WS subscribers + the eviction thread) can interleave a read and a delete. Observable as `KeyError` or stale session reference.

**Fix:** add `_PREVIEW_SESSIONS_LOCK = threading.Lock()` and wrap every mutation.

### FINDING-BR02 — LLM pipeline kills the job on a single transient error (CONFIRMED, HIGH)

[features/render/engine/pipeline/llm_pipeline.py:88-448](../../backend/app/features/render/engine/pipeline/llm_pipeline.py) plus [features/render/ai/llm/providers/{claude,openai,gemini}.py](../../backend/app/features/render/ai/llm/providers/).

Each provider returns `None` on exception (Sacred Contract #3 honored at module boundary). `run_llm_segment_selection` returns `None` on failure. But `run_llm_pre_render` then raises `LLMPipelineError` — which propagates all the way to `run_render_pipeline`'s outer try, marking the whole job `failed`.

There is **no retry**. There is **no fallback path** (Sprint 4.H deleted the legacy heuristic).

**Impact:** a 503 from Gemini at minute 4 of a 40-minute render = the whole 40-minute render dies. User must restart.

**Fix:** 2-attempt retry with `Retry-After`-aware backoff inside each provider; if all retries fail, surface a structured error code via `error_kind` so the FE can offer "switch provider + retry".

### FINDING-BR03 — `delete_job` cascade is not atomic across tables (CONFIRMED, MED→HIGH if FK ever broken)

[backend/app/db/jobs_repo.py:104-109](../../backend/app/db/jobs_repo.py): two separate `DELETE` statements (`job_parts` then `jobs`) inside one `db_conn()` ctxmgr.

The `db_conn` ctxmgr commits on normal exit. Both deletes happen inside one transaction → atomic. **Good.**

BUT: phase 1 verified there is NO `FOREIGN KEY` constraint on `job_parts.job_id`. If a future writer ever deletes from `jobs` without using `delete_job` (e.g., a manual SQL fix-up), orphan `job_parts` survive forever. Defense-in-depth gap: add SQL FK in a future baseline.

**Severity raised to HIGH** because Sacred Contract #7 mandates `data/app.db` as the sole authority — even maintenance scripts should never bypass the helper.

### FINDING-BR04 — NVENC semaphore acquired at only 3 sites (CONFIRMED, HIGH — repeat of Phase 3 FINDING-R01)

`NVENC_SEMAPHORE` defined at [features/render/engine/encoder/ffmpeg_helpers.py:27-28](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py).

Acquired only by:
- `render_base_clip` (clip_renderer.py:98)
- `render_part_smart` motion-crop branch
- `composite_overlays_on_base_clip` (overlay_compositor.py:133)

Other FFmpeg invocations — `clip_ops.cut_video`, `mixer.mix_narration_audio`, `preview/ffmpeg_probers`, `motion/crop` ad-hoc — call FFmpeg without consulting the semaphore. If any of those paths happens to use an `*_nvenc` codec (intentionally or due to a config typo) it bypasses the cap. NVENC's hardware limit causes **all active** NVENC encode sessions to fail together.

**Fix:** centralize acquire/release in `_run_ffmpeg_with_retry`, conditioned on `_argv_uses_nvenc(command)`. Note the current `_argv_uses_nvenc` is a string search — fragile against e.g. argv = `["-c:v", "h264_nvenc"]` (works) but a future encoder name addition silently bypasses. Use a curated `NVENC_CODECS = {"h264_nvenc", "hevc_nvenc", "av1_nvenc"}` set.

### FINDING-BR05 — Status enums are TEXT, not enum/CHECK (CONFIRMED, MED→HIGH long-tail)

Phase 1 FINDING-D02. Job/part status strings are frozen by contract (Sacred Contracts #4, #5) but enforced only Python-side. A typo on a writer = silent corruption of every consumer.

**Fix:** introduce `enum.StrEnum` for `JobStage`, `JobPartStage`; add `CHECK(status IN (…))` to the tables in a future baseline.

---

## MEDIUM

### FINDING-BR06 — WS handler blocks event loop with sync DB calls (PROBABLE, MED)

[routes/jobs.py:644-696](../../backend/app/routes/jobs.py): the WS coroutine awaits `get_job`, `list_job_parts`, `_compute_progress_summary` — all **synchronous** SQLite calls. SQLite reads under WAL are fast (< 1 ms typical) so this rarely matters. But: under contention with the render thread's `_thread_conn` writer (or while a 500 ms-cadence Whisper transcribe holds a heavy lock), the WS poll can stall, delaying every WS subscriber on that loop.

**Fix:** offload to `asyncio.to_thread(...)` or accept the trade (single user, single host = no issue).

### FINDING-BR07 — FFmpeg `child.wait()` post-terminate unbounded (PROBABLE, MED)

[features/render/engine/encoder/ffmpeg_helpers.py:~252-258](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py).

`_run_ffmpeg_with_retry` polls cancel every 1.0 s; when set, calls `child.terminate()` (SIGTERM on POSIX, terminates on Windows). The next `child.wait()` has no timeout — if FFmpeg ignores SIGTERM, the helper hangs forever.

**Fix:** `child.wait(timeout=5.0)`; on TimeoutExpired, `child.kill()` + final wait.

### FINDING-BR08 — `asyncio.run()` inside worker thread (PROBABLE, MED)

[features/render/engine/audio/tts.py:257](../../backend/app/features/render/engine/audio/tts.py): `asyncio.run(_run())`.

Called from a `ThreadPoolExecutor` worker thread (render path: `pipeline_render_loop → process_one_part → part_voice_mix → generate_narration_mp3 → asyncio.run`).

Worker threads don't have a running event loop by default — so `asyncio.run` *typically* works. But:

- If `generate_narration_mp3` is ever called from the main thread (e.g., from a FastAPI sync endpoint, or a notebook test), and that thread already has a loop, `asyncio.run` raises `RuntimeError`.
- Each call creates a new loop, runs to completion, closes. Repeated calls within one render are correct but pay set-up cost (~1 ms each).

**Fix:** use `asyncio.new_event_loop()` + `loop.run_until_complete()` + `loop.close()`, OR (better) hold a per-thread cached loop.

### FINDING-BR09 — Cache key collision risk on Windows mtime (PROBABLE, MED)

[features/render/engine/pipeline/pipeline_cache.py:28, 58](../../backend/app/features/render/engine/pipeline/pipeline_cache.py): cache key includes file `mtime` and `size`.

Windows FAT/exFAT mtime resolution is 2 s. If a user re-encodes the same source video to the same size with a difference smaller than 2 s, the same key is reused → stale cache hit. NTFS resolution is 100 ns so the practical risk is small.

Same applies to Whisper transcription cache.

**Fix:** add file hash (XXHash) of the first MB to the key.

### FINDING-BR10 — `_thread_conn` leak on thread death (PROBABLE, MED)

`_thread_conn()` in `db/connection.py:150` caches a SQLite connection in `threading.local()`. `close_thread_conn()` at [features/render/engine/pipeline/render_pipeline.py:1357](../../backend/app/features/render/engine/pipeline/render_pipeline.py) releases it in the outer `finally`. ✓ for the normal case.

But: if a worker thread dies with an unhandled exception **before** reaching `run_render_pipeline`'s try block (e.g., during `setup_render_pipeline`), the conn is never closed. The conn lives until the thread is garbage-collected or the process exits. Cumulative leak across thousands of jobs on a long-lived process.

**Fix:** wrap the conn allocation in a context-manager helper. Or call `close_thread_conn()` in `ThreadPoolExecutor` worker finally (requires a `concurrent.futures.thread._threads_queues`-style hook — easier: stop using thread-local entirely).

---

## LOW

### FINDING-BR11 — `attach_ai_visibility_summaries` returns silently if no summary (PROBABLE, LOW)

[features/render/ai/visibility/ai_visibility_summary.py:182+](../../backend/app/features/render/ai/visibility/ai_visibility_summary.py): if no per-part scored data exists (e.g., LLM failed mid-render), the function returns early. The FE then shows an empty AI Summary card without explanation. Cosmetic.

### FINDING-BR12 — Resume-from-last: `output_file` empty-string vs NULL (ASSUMPTION, LOW)

Resume relies on `job_parts.output_file` being present. Some upserts write `""` (default). Phase 1 verified the schema default is `''`. Resume logic checks `output_file and Path(output_file).exists()` — empty string is falsy, so it correctly re-renders. ✓ for current code. Document for future maintainers.

### FINDING-BR13 — Stale render-plan-json after retry (ASSUMPTION, LOW)

When `POST /api/render/retry/{job_id}` runs, the existing `jobs.render_plan_json` is left untouched. Phase 2 didn't explicitly verify whether the retry path overwrites the plan or reuses it. If the retry is meant to incorporate creator-context updates, stale plan is a bug; if it's meant to "redo the same plan exactly", correct. **Investigation needed.**

### FINDING-BR14 — Two `prune_render_cache` invocations may race (PROBABLE, LOW)

[main.py:210, 241](../../backend/app/main.py): cache pruning runs at startup AND every 1800 s. If the periodic invocation overlaps with a concurrent cache-write (Whisper finishing transcription), the writer may unlink the target dir mid-write. The pruner reads mtime and deletes — if the target is being written, the timing window is narrow. Probable race; mitigated by per-file `os.replace` semantics. **Confirm with a stress test.**

### FINDING-BR15 — Whisper model never unloaded (CONFIRMED, LOW)

Whisper model loaded in process memory at [features/render/engine/subtitle/transcription/whisper.py:26-32](../../backend/app/features/render/engine/subtitle/transcription/whisper.py). No unload path. For a desktop app with `MAX_CONCURRENT_JOBS = cpu_count//2`, this is a couple of GB resident — acceptable. If multiple Whisper sizes are mixed (`tiny` for preview + `large-v3` for main), both stay resident simultaneously. **Fix:** LRU eviction when model count > 2.

---

## Notes that turned out NOT to be bugs

- `close_thread_conn()` IS called in the outer `finally` of `run_render_pipeline` ([line 1357](../../backend/app/features/render/engine/pipeline/render_pipeline.py)). The Phase 4 sub-agent's claim that it wasn't was wrong. Real risk = pre-pipeline thread death (FINDING-BR10).
- `domain/` is a true leaf — no reverse imports. Architecture stays clean.
- `_emit_render_event` signature is frozen and all 22+ call sites use keyword-only invocation.

---

## Summary

| ID | Severity | Class | Topic |
|---|---|---|---|
| BR01 | HIGH | CONFIRMED | `_PREVIEW_SESSIONS` race |
| BR02 | HIGH | CONFIRMED | LLM no-retry kills render |
| BR03 | HIGH | CONFIRMED | FK absence → orphan risk |
| BR04 | HIGH | CONFIRMED | NVENC semaphore bypass risk |
| BR05 | HIGH | CONFIRMED | TEXT status enums |
| BR06 | MED | PROBABLE | WS loop blocked by sync DB |
| BR07 | MED | PROBABLE | FFmpeg `wait()` no timeout |
| BR08 | MED | PROBABLE | `asyncio.run` inside worker |
| BR09 | MED | PROBABLE | Windows mtime granularity |
| BR10 | MED | PROBABLE | Thread-local conn leak |
| BR11–15 | LOW | mixed | misc UX/resource leak |

End of 11_bug_risk_report.md.
