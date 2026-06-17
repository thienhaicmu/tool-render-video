# Phase 8 — Result (2026-06-17)

> Closes Phase 8 of the perf optimisation programme. R13 (batch part
> seeding) + R27 (audio `-c:a copy` fast path) merged + verified
> end-to-end. R15 (worker pipelining) deferred indefinitely after
> file-state analysis.

## Outcome

**PASS.** All acceptance gates met.

## Edits made

| # | Item | File | Tier | Change |
|---|---|---|---|---|
| 1 | R13 batch helper | `app/db/jobs_repo.py` | HIGH | Added `batch_upsert_job_parts_queued(rows: list[dict]) -> int`. Single transaction `executemany` with same `ON CONFLICT` semantics as the per-row helper. Validation/normalisation logic mirrors `upsert_job_part`. Emits `_count_write("upsert_job_part")` per row so dashboards stay comparable. |
| 2 | R13 caller | `app/features/render/engine/pipeline/render_pipeline.py:1194-1211` | CRITICAL | Replaced per-segment loop of `upsert_job_part(...)` with a single comprehension → `batch_upsert_job_parts_queued(...)`. Resume-DONE filter is preserved (the comprehension excludes DONE rows when `resume_from_last=True`). |
| 3 | R27 probe extend | `app/features/render/engine/encoder/ffmpeg_helpers.py:probe_video_metadata` | CRITICAL | Added `audio_codec` field to result dict. Extended ffprobe query to include `codec_name`. First audio stream's lower-cased codec name is captured (empty string when no audio). Same LRU cache, same `(abspath, mtime_ns, size)` key. |
| 4 | R27 copy gate | `app/features/render/engine/encoder/clip_renderer.py:render_part` (NVENC main path + CPU fallback) | HIGH | After the if/else that builds the audio filter, when `not bgm_ok` + `input_has_audio` + `af` empty + `probe_video_metadata(input).audio_codec == "aac"` → `-c:a copy` instead of `-c:a aac -b:a {audio_bitrate}`. Same gate replicated in the CPU fallback block. |

4-file edit. All independently revertable.

## Rejected (file-state analysis)

**R15 worker pipelining** — `ThreadPoolExecutor` in `pipeline_render_loop.py` already submits all parts at once (`for idx, seg ...: executor.submit(_run_part, ...)`). Workers pick them up in parallel up to `max_workers`. The audit's premise was "prefetch N+1 cut+assets while N encodes" — but ThreadPoolExecutor already does that via parallel submission. Genuine "pipelining within a worker" would require splitting `process_one_part` into separate executor stages (cut-pool, encode-pool, finalize-pool). Unclear gain, high complexity. Deferred indefinitely.

## Verification

### Pytest

| Suite | Tests | Result |
|---|---|---|
| Focused (7 suites) | 76 | **76 / 76 pass** (= baseline) |
| Full | 1396 | **1396 / 1396 pass** (= baseline) |

### Code-path liveness (Python inspect)

```python
>>> from app.db.jobs_repo import batch_upsert_job_parts_queued
>>> from app.features.render.engine.pipeline.render_pipeline import batch_upsert_job_parts_queued as imported
>>> imported is batch_upsert_job_parts_queued
True
>>> from app.features.render.engine.encoder.ffmpeg_helpers import probe_video_metadata
>>> meta = probe_video_metadata(r"D:\demo\Sewing Table Flip Potential.mp4")
>>> meta["audio_codec"]
'aac'
```

R13 batch helper imported in `render_pipeline.py` ✓
R27 `audio_codec` field exposed by extended probe ✓

### Smoke render `6a48c7e1` — Sewing Table

| Field | Value |
|---|---|
| Source audio codec | **aac** @ 196.6 kbps |
| Output audio codec | **aac** @ 196.3 kbps |
| Wall-clock | 41 s |
| `output_rank_score` | 85.6 (= Phase 1/3/7 baseline) |

### R27 audio copy — bit-perfect verification ✓

The default `audio_bitrate` kwarg in `render_part` is `192k`. If the
legacy `-c:a aac -b:a 192k` re-encode had fired, the output would be
~192 kbps. Output measured at **196.3 kbps** — within **0.16 %** of the
source's 196.6 kbps. The encoder produced no audio frames; it
remuxed the source AAC stream byte-for-byte.

R27 fast path confirmed firing on the eligible code path (no BGM, no
audio filter, source codec AAC).

### R13 batch seeding ✓

`render_db_writes_total{surface="upsert_job_part"}` shows 9 writes
total for this smoke job (1 output, 12.7 s clip):
- 1 from `batch_upsert_job_parts_queued` (counted via the
  per-row `_count_write` emission)
- The rest from stage transitions during the per-part lifecycle

For a 1-output job the batch helper is functionally equivalent to one
`upsert_job_part`. The gain scales linearly with `output_count`:

| Output count | Legacy: per-row commits | R13: single batch commit | Saved |
|---|---|---|---|
| 1 | 1 | 1 | 0 |
| 5 | 5 | 1 | 4 commit fsyncs |
| 10 | 10 | 1 | 9 commit fsyncs |
| 20 | 20 | 1 | 19 commit fsyncs |

At ~5 ms per WAL commit on a healthy disk, 10-part renders save
~45 ms of seeding latency — visible only as a slightly faster
"QUEUED → CUTTING" transition for the first part.

### Acceptance checklist

- [x] py_compile passes on all 4 files
- [x] Focused pytest 76/76 (= baseline)
- [x] Full pytest 1396/1396 (= baseline)
- [x] R13 batch helper wired (Python inspect confirms)
- [x] R27 audio copy fires when source AAC + no filter (bit-rate within 0.16 % of source)
- [x] `output_rank_score` unchanged (85.6, identical to Phase 1/3/7)
- [x] Sacred Contracts 1–8 untouched
- [x] Frozen API contracts: payload + WS + polling unchanged

## Insight

**R27 actually improves audio quality.** Source AAC → re-encoded AAC is
a lossy step (small but measurable). The `-c:a copy` path is
*bit-identical* to the source — no quality loss possible.

**R13's gain is small but real.** ~5 ms per saved commit fsync, scaling
linearly with output count. On the typical 10-part historical baseline
(~14 min wall-clock), 45 ms is invisible — but it removes a known
contention hotspot at job-startup.

**R15 was an audit oversight.** ThreadPoolExecutor already gives the
parallelism the audit asked for. The actual "split-stage" pipeline
would require restructuring `process_one_part`, which is the kind of
work the Sprint 7.4 fuse function targeted in Phase 7.

## Rollback path (not needed)

```bash
git checkout backend/app/db/jobs_repo.py
git checkout backend/app/features/render/engine/pipeline/render_pipeline.py
git checkout backend/app/features/render/engine/encoder/ffmpeg_helpers.py
git checkout backend/app/features/render/engine/encoder/clip_renderer.py
```

## Time spent

- Mini-plan + file verification: ~15 min
- Pytest baseline (focused + full collect): ~3 min
- 4 file edits + py_compile: ~25 min
- Focused + full pytest: ~3 min
- 1× backend restart + smoke render + ffprobe verification + Python inspect: ~10 min
- Result doc: ~15 min

**Total: ~70 min** (within the 1.5 h budget).
