# Phase 8 — Pre-edit Baseline (2026-06-17)

## Pytest state

| Suite | Tests | Result |
|---|---|---|
| Full pytest collect | **1396** | |
| Focused (7 suites) | **76** | **all pass** |

Focused set:
- `test_jobs_repo_stage_validation.py`
- `test_render_pipeline_contract.py`
- `test_render_pipeline_integration.py`
- `test_render_duration_metric.py`
- `test_pipeline_qa.py`
- `test_sacred_contract_8_qa_thresholds.py`
- `test_jobs_ai_summary_status.py`

## Verified scope

| # | Item | Action |
|---|---|---|
| 1 | R13 batch seeding | `app/db/jobs_repo.py` add `batch_upsert_job_parts_queued` + `render_pipeline.py:1194-1211` switch from per-row loop to batch call |
| 2 | R27 audio fast path | `ffmpeg_helpers.py:probe_video_metadata` add `audio_codec` field + `clip_renderer.py:render_part` add `-c:a copy` gate (main NVENC path + CPU fallback) |

## Rejected (audit item)

- **R15 worker pipelining** — ThreadPoolExecutor already submits all parts at once; workers pick them up in parallel up to `max_workers`. The audit's "pipeline within a worker" would require restructuring `process_one_part` into separate executor stages. Unclear gain, high complexity. Deferred indefinitely.

## Acceptance gate

- [ ] py_compile on 4 files
- [ ] Focused pytest 76/76
- [ ] Full pytest 1396/1396
- [ ] After smoke: source audio AAC → output audio bitrate matches source (bit-perfect copy, not re-encoded to target 192k)
- [ ] R13 wired confirmed via Python inspect
- [ ] `output_rank_score` unchanged
