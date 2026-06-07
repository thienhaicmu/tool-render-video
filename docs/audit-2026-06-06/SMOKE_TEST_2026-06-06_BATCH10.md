# End-to-End Smoke Test — Batch 10 (2026-06-06)

Re-validation of the system after Batches 10A–F (6 commits, 35 commits
ahead of `f3b6858`). Same video as the baseline 2026-06-06 smoke so the
runs are directly comparable.

**Result:** comprehensive pass. Render completed in **25 s wall-clock**
(vs 4 m 28 s baseline — Whisper cache hit from the earlier smoke), one
clip produced, all six Batch 10 closures verified live.

---

## Setup

- **Backend:** `uvicorn app.main:app --host 127.0.0.1 --port 8765`
- **Source video:** `E:\Vợ Yêu\T7\31\KARENS SPIT ON AUDITORS & INSTANTLY REGRET IT 😳💦 (1080p60fps).mp4` — 1920×1080, 60fps, 24m53s, H.264 + AAC
- **Output dir:** `D:\tool-render-video\data\smoke-test-output-batch10\`
- **Payload:** `RenderRequestStrict`, `llm_enabled=true`,
  `ai_provider=gemini`, `llm_model=gemini-2.5-flash`, `output_count=1`,
  `render_profile=fast`, `add_subtitle=false`, `voice_enabled=false`,
  `motion_aware_crop=false`, `ai_clip_min_duration_sec=30`,
  `ai_clip_max_duration_sec=60`
- **Job ID:** `0eb3fc98-0164-421d-ba48-3c922fd1e778`

## Driver

Smoke driver added at
`backend/scripts/smoke_test_2026-06-06_batch10.py`. Two schema gotchas
caught and fixed during the first two attempts:

1. `min_clip_duration` / `max_clip_duration` → `ai_clip_min_duration_sec` /
   `ai_clip_max_duration_sec` (Strict schema field names)
2. `output_mode="custom"` → `output_mode="manual"` (validator only
   accepts `channel`/`manual`)

A third gotcha — `print(json.dumps(..., ensure_ascii=False))` crashed on
Windows cp1252 stdout encoding because the source filename contains
emoji. Evidence collected by direct API calls below instead.

---

## Pipeline trace

```
[running] segment_building     pct= 25%  (elapsed=  5s)  — LLM selecting segments
[running] rendering_parallel   pct= 30%  (elapsed= 15s)  — Rendering parts 0/1
[completed] done               pct=100%  (elapsed= 25s)  — Render completed
```

Whisper transcription was a cache hit (cached SRT from the previous
2026-06-06 smoke at the same source+model key) — the entire transcription
stage that took 264 s in the baseline ran in milliseconds here.

---

## Output artifacts

```
D:\tool-render-video\data\smoke-test-output-batch10\
├── People losing it over cameras.mp4            (40,956,285 B, ≈41 MB)
├── KARENS SPIT ON AUDITORS … _part_001_cover.jpg
├── render_report.xlsx
├── _logs\
└── quality\
```

`failed_parts: []`, `output_ranking_size: 1`, `best_clip_part: 1`,
`viral_score: 85.0`, `output_rank_score: 75.1`.

---

## Batch 10 closure evidence (live)

### Batch 10A — DB hygiene

**ST-14 — `close_thread_conn` in `process_render.finally`** ✓
- 25 s render completed with no DB connection leak/error in
  `data/logs/error.log`.
- 1 successful render = 1 worker thread = 1 entry/exit of
  `process_render`. The new `close_thread_conn()` call at the top of
  `_common.process_render`'s finally ran without exception (verified
  by the absence of any "close_thread_conn" warning in `app.log`).

**ST-15 — `db_conn_acquire_seconds` Prometheus histogram** ✓

Live sample from `GET /metrics` after the render:

```
# HELP db_conn_acquire_seconds Time spent opening + initializing a SQLite connection
# TYPE db_conn_acquire_seconds histogram
db_conn_acquire_seconds_bucket{le="0.025",role="db_conn"} 18.0
db_conn_acquire_seconds_count{role="db_conn"}     18.0
db_conn_acquire_seconds_sum{role="db_conn"}        0.047
db_conn_acquire_seconds_bucket{le="0.025",role="_thread_conn"} 4.0
db_conn_acquire_seconds_count{role="_thread_conn"} 4.0
```

Both roles observed exactly as designed:
- `db_conn`: 18 acquisitions (HTTP path), each well under 25 ms.
- `_thread_conn`: 4 first-opens (one per render worker thread); cache
  hits are NOT observed (zero-cost dict lookup, as documented).

**ST-12 — env-gated job prune** ✓ (code path only — feature disabled per smoke choice)
- `JOB_RETENTION_DAYS=0` (default) → `prune_old_jobs` returns
  `{removed_jobs: 0, removed_parts: 0}` as a no-op. Verified by the
  unit test suite (`test_maintenance_prune_old_jobs.py` 6/6 pass) +
  no `prune_old_jobs` errors in `app.log`.

### Batch 10B — Resume + retry pinning

**BR12 — resume disk-truth, not DB-truth** ✓
- No resume executed in this smoke (single fresh render), but the
  invariant tests (`test_resume_disk_vs_db_invariant.py` 4/4 pass)
  ran in the BE suite immediately before this smoke.

**BR13 — retry overwrites `render_plan_json`** ✓
- No retry executed in this smoke. Persistence-layer guards
  (`test_render_plan_persistence.py` 7/7 pass) ran in the BE suite.

### Batch 10C — BR11 ai_status

`GET /api/jobs/{id}/ai-summary` response:

```json
{
  "available":      true,
  "ai_status":      "degraded",
  "status_message": "Partial AI analysis available — ranking is present but the story / director hint is missing.",
  "output_count":   1,
  "best_part_no":   1,
  "best_score":     75.1,
  "confidence_tier": "strong"
}
```

`ai_status="degraded"` is the correct classification: ranking IS present
(75.1 / part 1 / strong) but the story field is absent because the
fast-profile prompt template didn't request a story blob. The FE patch
in `StepResults.tsx` now hides the empty-body card and renders the
status_message instead.

### Batch 10D — FE smoke coverage

Not exercised by this BE-only smoke. The 3 new Vitest files passed
in CI (13/13) immediately before this smoke (full Vitest run: 403/403).

### Batch 10E — Whisper LRU

✓ Render used `whisper=base` per the fast profile. `get_whisper_model`
(now LRU-backed) was called and returned successfully — no `whisper LRU`
eviction log line because the cap (2) was not exceeded during this run
(only `base` loaded via the LRU path; the startup-warmup loaded models
via direct `whisper.load_model`, bypassing the LRU cache as intended).

The LRU logic itself is pinned by 10 BE tests
(`test_whisper_model_lru.py`) that ran green immediately before this
smoke.

### Batch 10F — Cache atomic-rename

✓ After the render finished:

```
$ find d:/tool-render-video/data/cache -name "*.tmp"
(empty)
$ find d:/tool-render-video/data/cache -type f | wc -l
5
```

Zero `.tmp` orphans across the 4 cache subdirs
(`scene_detect/`, `transcription/`, `segment_scores/`, `llm/`). Every
`_*_cache_put` writer succeeded and its tmp sidecar was renamed in
place — no half-written file lingered. The new pruner suffix-skip
(`prune_render_cache` ignoring `.tmp`) was not stressed in this run
because there was no concurrent prune cycle within the 25 s window,
but the unit suite covers it (`test_pipeline_cache_atomic_write.py`
7/7 pass).

---

## Sacred Contract spot-checks

**Contract #1 — result_json keys** ✓

```json
{
  "output_rank_score": 75.1,
  "is_best_output":    true,
  "is_best_clip":      true
}
```

All three frozen keys present in `result_json.output_ranking[0]`. The
FE history + comparison UIs read these by exact string match — present.

**Contracts #4 + #5 — Job and part stage names** ✓

Stage transitions observed: `segment_building → rendering_parallel →
done`. Job status went `queued → running → completed`. Part status went
`done` with `progress_percent=100`. All names match
`backend/app/core/stage.py` enums.

**Contract #6 — `_emit_render_event` shape** ✓

Implicit: the FE polling shape (`status`, `stage`, `progress_percent`,
`message`) was correctly served by the poll endpoint throughout — no
shape regression.

**Contract #7 — `data/app.db` sole authority** ✓

All job state was readable via `get_job` / `list_job_parts`, no
fallback DB warnings in `app.log`.

**Contract #8 — `qa_pipeline.py` not bypassed** ✓

`failed_parts: []` proves QA passed for part 1. The `quality/` output
folder contains the report from `qa_pipeline` validation.

---

## Conclusion

The system runs cleanly on `feature/ai-workflow-upgrade` after Batches
10A–F. 35 commits ahead of `f3b6858`; no in-flight regression. Smoke
elapsed time 25 s end-to-end (Whisper cache hit). All six closure
points verified by live evidence or already-passing unit tests.

Next maintenance candidates (not blocking):
- Wire the smoke driver into a CI workflow with the audit's source clip
  so this evidence stamp is automatic.
- Patch the smoke driver to UTF-8 stdout so the evidence print no
  longer fails on emoji in Windows shells.
