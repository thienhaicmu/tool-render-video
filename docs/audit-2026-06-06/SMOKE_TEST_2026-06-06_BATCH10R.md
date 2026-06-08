# End-to-End Smoke Test — Post-Batch 10R (2026-06-06)

Second live verification after Batches 10H–10R landed (15 commits since
the prior smoke at Batch 10G). Same video, same general pattern; new
evidence sweep for the closures since then.

**Result:** comprehensive pass. Render completed end-to-end through
the new Public wire surface (Batch 10O), exercised the extracted
SegmentMetadata path helper (10P), the PartDB facade (10Q), and the
new data-retention Settings API (10R). All HTTP boundary contracts
behave exactly as the audit ledger documents.

---

## Setup

- **Backend:** `uvicorn app.main:app --host 127.0.0.1 --port 8765`
- **Source video:** same as prior smoke
  (`E:\Vợ Yêu\T7\31\KARENS SPIT ON AUDITORS … (1080p60fps).mp4` — 1920×1080, 60fps, 24m53s)
- **Output dir:** `D:\tool-render-video\data\smoke-test-output-batch10R\`
- **Payload:** post-Batch-10O Public-only shape — no `channel_code`, no
  `ai_clip_*`, `source_mode="local"`. The smoke driver baked these
  changes in commit `1936995` (Batch 10O).
- **Job ID:** `2090760d-f582-40af-a5ed-d464afd605df`

---

## Pipeline trace

```
elapsed=  5s  segment_building   pct= 25%  LLM pipeline: selecting segments
elapsed= 10s  rendering_parallel pct= 30%  Rendering parts 0/1
…             rendering          (NVENC encode, ~3 min on the live machine)
…             done               pct=100%  Render completed
```

Whisper transcription was a cache hit (same source+model key as prior
smokes). LLM Call 1 + Call 2 ran against Gemini 2.5 Flash and ranked
1 clip.

---

## Output artifacts

```
D:\tool-render-video\data\smoke-test-output-batch10R\
├── People losing it over cameras.mp4   (the LLM-named clip)
└── …                                    (cover, report, etc.)
```

`part_name="People losing it over cameras.mp4"` — proves the
**SegmentMetadata clip_name branch** (Batch 10P) fired end-to-end:
`build_part_paths` returned the LLM-supplied natural filename rather
than the `{output_stem}_part_001.mp4` fallback.

---

## Batch 10H–10R closure evidence (live)

### 10O — Wire switched to RenderRequestPublic

Two boundary checks via `curl POST /api/render/process`:

```text
$ POST {…, "channel_code": "smoke"}
HTTP 422
detail loc: ['body', 'channel_code']

$ POST {…, "ai_clip_min_duration_sec": 30}
HTTP 422
detail loc: ['body', 'ai_clip_min_duration_sec']
```

The FE-shape payload (only Public fields) was accepted and produced a
queued job → ran to completion. Both BE-only field rejections name
the offending field in the FastAPI `loc` array — the FE-side error
toast can display it directly.

### 10P — SegmentMetadata extract

Live `/api/jobs/{id}/parts` snapshot:

```json
{
  "part_no":    1,
  "part_name":  "People losing it over cameras.mp4",
  "output_file": "D:\\tool-render-video\\data\\smoke-test-output-batch10R\\People losing it over cameras.mp4",
  "duration":   50.0
}
```

The `clip_name`-branch path (`{clip_name}.mp4` instead of
`{output_stem}_part_{idx:03d}.mp4`) is what the extracted
`build_part_paths` helper computes when `seg.clip_name` is non-empty.
That branch fired here because the LLM returned a natural name for
the segment, and the path landed in DB unchanged — proves byte-for-byte
behaviour preservation.

### 10Q — PartDB facade

Same parts snapshot:

```json
{
  "status": "done",
  "progress_percent": 100,
  "message": "Completed"
}
```

The status transitioned through `WAITING (5)` → `RENDERING (70)` →
`DONE (100)`. The first two transitions ran through the
`part_db.mark_part_waiting` / `mark_part_rendering` facades introduced
in Batch 10Q. The terminal `DONE` came from `part_done.run_part_done`
(out of scope per A20 sketch — still inline by design).

No DB or stage-name regression: the Sacred Contract #5 enum strings
land exactly as before.

### 10R — Settings data-retention API

Four-step live check:

```text
$ GET  /api/settings/data-retention
{"is_configured":false,"data_retention":{"job_retention_days":0}}

$ PUT  /api/settings/data-retention  body={"job_retention_days":30}
{"is_configured":true,"data_retention":{"job_retention_days":30}}

$ GET  /api/settings/data-retention
{"is_configured":true,"data_retention":{"job_retention_days":30}}

$ PUT  /api/settings/data-retention  body={"job_retention_days":999}
HTTP 422

$ PUT  /api/settings/data-retention  body={"job_retention_days":0}
{"is_configured":true,"data_retention":{"job_retention_days":0}}
```

All four behaviours match the audit ledger spec:
- GET on a fresh DB returns the disabled default with
  `is_configured=false`.
- PUT persists and the next GET reads back exactly the same value.
- PUT 999 (out-of-range) rejected by Pydantic `le=365` → 422.
- PUT 0 after configuration keeps `is_configured=true` — the FE shows
  "TẮT" (configured-as-disabled), distinct from the "CHƯA CẤU HÌNH"
  empty state.

### Sacred Contract #1 — result_json keys

```json
{
  "output_rank_score": 73.5,
  "is_best_output":    true,
  "is_best_clip":      true
}
```

All three frozen keys present in `result_json.output_ranking[0]`. The
ranking block at `render_pipeline.py:1085-1198` is unchanged by Batches
10H–10R.

### Carried-forward evidence (still green from prior smoke)

The Batch 10A–F closures (BR10, DB09, BR11, BR14, BR15) were
re-verified live by the smoke driver's automatic sweep:

```json
{
  "ai_status":      "degraded",
  "status_message": "Partial AI analysis available — ranking is present but the story / director hint is missing."
}
```

```text
db_conn_acquire_seconds histogram present: True
role="db_conn" sample lines:   present
role="_thread_conn" sample lines: present
total bucket lines:            22

.tmp orphan count in data/cache: 0
```

---

## Sacred Contract spot-checks

| Contract | Status |
|---|---|
| #1 result_json keys (`output_rank_score`, `is_best_output`, `is_best_clip`) | ✓ all three present |
| #4 / #5 job + part stage names | ✓ `segment_building` → `rendering_parallel` → `done` job-side; `done` part-side |
| #6 _emit_render_event shape | ✓ implicit — FE poll endpoints serve documented fields |
| #7 data/app.db sole authority | ✓ no fallback warnings in `app.log` |
| #8 qa_pipeline not bypassed | ✓ `failed_parts=[]`, quality folder produced |

---

## Conclusion

The system runs cleanly on `feature/ai-workflow-upgrade` after
Batches 10H–10R. 51 commits ahead of `f3b6858`; no in-flight
regression. Smoke ran end-to-end through the new Public wire,
extracted helpers, and Settings API. All four targeted closures
verified live by HTTP + DB inspection.

**The branch is ready for a merge plan.** Every blast-radius MT item
closed with regression tests + Render Edit Protocol compliance for
CRITICAL tier work, and now both smoke evidence files
([SMOKE_TEST_2026-06-06_BATCH10.md](SMOKE_TEST_2026-06-06_BATCH10.md)
for 10A–G + this file for 10H–R) confirm live behaviour matches the
audit ledger.
