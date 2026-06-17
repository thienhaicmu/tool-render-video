# Phase 1 — Pre-edit Baseline (2026-06-16)

> Captured per Render Edit Protocol step 4, BEFORE any `render_pipeline.py` /
> `part_renderer.py` edit. Compared against the post-edit run in
> `docs/perf-phase-1-result-2026-06-16.md` to confirm zero regression.

## Pytest state

| Suite | Tests | Result |
|---|---|---|
| Full pytest collect | **1396** | (collect only, no execution) |
| Focused (Phase 1 adjacent) | **154** | **all pass** |

Focused set:
- `test_render_pipeline_contract.py`
- `test_render_pipeline_integration.py`
- `test_pipeline_qa.py`
- `test_pipeline_ranking.py`
- `test_sacred_contract_3_ai_return_none.py`
- `test_sacred_contract_6_ws_shape.py`
- `test_sacred_contract_8_qa_thresholds.py`
- `test_stages_asset_planner.py`
- `test_stages_analyzing_scene_detection_emitted.py`
- `test_llm_pipeline_hard_fail.py`
- `test_jobs_repo_stage_validation.py`
- `test_render_duration_metric.py`
- `test_process_render_thread_conn_safety.py`

## File snapshot

| File | Lines | Tier |
|---|---|---|
| `backend/app/features/render/engine/stages/part_renderer.py` | 357 | CRITICAL |
| `backend/app/features/render/engine/pipeline/render_pipeline.py` | 1700+ | CRITICAL |

## Planned edit

1. **part_renderer.py** — modify `_stage_end` (lines 47–52) to also call
   `RENDER_STAGE_DURATION.labels(stage=f"per_part_{name}").observe(elapsed)`
   inside a try/except.
2. **render_pipeline.py** — modify `_set_stage` closure (lines 477–491) to
   track `_stage_t0`. On stage transition, observe elapsed time for the
   outgoing stage. Reset `_stage_t0`. All wrapped in try/except.

## Sacred Contracts to preserve

1, 2, 3, 4, 5, 6, 7, 8 — none touched. The edit adds observation, never
changes state-machine logic, return values, DB writes, or WS event shape.

## Acceptance gate (compared in result doc)

- [ ] py_compile passes on both files
- [ ] Full pytest count = 1396
- [ ] Focused pytest 154/154 pass
- [ ] Smoke render: `/metrics` shows ≥ 7 `per_part_*` labels + ≥ 4 job-level stage labels
- [ ] `output_rank_score` of smoke-render output unchanged vs pre-edit
