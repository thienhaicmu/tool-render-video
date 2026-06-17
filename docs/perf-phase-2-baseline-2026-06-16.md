# Phase 2 — Pre-edit Baseline (2026-06-16)

## Pytest state

| Suite | Tests | Result |
|---|---|---|
| Full pytest collect | **1396** | (collect-only) |
| Focused (4 suites) | **42** | **all pass** |

Focused set:
- `test_render_pipeline_contract.py`
- `test_sacred_contract_6_ws_shape.py`
- `test_pipeline_qa.py`
- `test_event_broadcaster_t31.py`

## DB write baseline from Phase 1 smoke

Job `dd17780f` (1 output, 12.7 s clip, 22 s encode):
- `upsert_job_part`: **9**
- `update_job_progress`: 10
- `upsert_job`: 3
- `update_render_plan`: 1
- `upsert_ab_score`: 1

The 9 `upsert_job_part` writes break down as:
- 1 WAITING transition
- 1 CUTTING (from `run_cut_stage`)
- 1 TRANSCRIBING (from `prepare_part_assets`)
- 1 RENDERING start
- ~3 progress ticks from `_render_progress_timer` (every 3 s during 22 s encode)
- 1 DONE terminal

Phase 2 target: cut the **~3 progress ticks** down to **1–2** for this short
render via 10 s OR 10 % coalescing. For longer encodes (e.g., 60 s the
historical baselines see), tick count would otherwise be ~20 → ~3.

## Planned edit

[render_events.py:286–390](backend/app/features/render/engine/pipeline/render_events.py#L286-L390) — add two constants and a coalescing gate inside `_render_progress_timer`. Single-file edit.

## Acceptance gate (compared in result doc)

- [ ] py_compile passes
- [ ] Focused pytest 42/42 pass
- [ ] Full pytest 1396 pass
- [ ] Smoke render: `upsert_job_part` count for an equivalent ~22 s encode drops vs baseline
- [ ] HTTP polling still returns progress
- [ ] `output_rank_score` unchanged
