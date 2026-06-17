# Phase 7 — Pre-edit Baseline (2026-06-17)

> Captured per Render Edit Protocol step 4. Wire Sprint 7.4/7.8 fuse
> function (already-built, currently dead code) into the per-part pipeline
> behind a feature flag.

## Pytest state

| Suite | Tests | Result |
|---|---|---|
| Full pytest collect | **1396** | |
| Focused (7 suites) | **102** | **all pass** |

Focused set:
- `test_motion_crop.py`
- `test_motion_crop_quality_indicator.py`
- `test_render_pipeline_contract.py`
- `test_sacred_contract_8_qa_thresholds.py`
- `test_render_pipeline_integration.py`
- `test_pipeline_qa.py`
- `test_stages_asset_planner.py`

## Phase 3 smoke reference (job `ebd14eca`, motion_crop OFF, subtitle ON)

| Stage | Sum (s) |
|---|---|
| `per_part_cut` | 13.38 |
| `per_part_encode` | 23.45 |
| **per-part total** | **~38** |
| `output_rank_score` (smoke) | 85.6 (within historical 80.5–89.9 band) |

Phase 7 target after fuse flag ON:
- `per_part_cut` → drop near 0 (skipped when fuse-safe)
- `per_part_encode` → similar or slightly higher (now includes cut work)
- Total per-part: drop by ~10–15 s

## Planned edits

| File | Lines | Edit |
|---|---|---|
| `app/features/render/engine/stages/part_render_encode.py` | 111–144 (the `render_part_smart(str(raw_part), …)` call) | Branch: when `_fuse_safe` → `render_part_from_source(str(ctx.source_path), str(final_part), source_start, source_duration, …)`; else legacy path |
| `app/features/render/engine/stages/part_cut.py` | 233–253 | Branch: when `_fuse_safe` → skip `cut_video` + manifest update unchanged; else legacy path |

New env var: `RENDER_FUSE_CUT` (default `"0"` = OFF; opt-in via `"1"`).

Safe-conditions function (resolved once in part_cut, re-resolved in part_render_encode):
```python
def _fuse_safe(ctx, idx, seg, force_accurate_cut) -> bool:
    if os.getenv("RENDER_FUSE_CUT", "0") != "1":
        return False
    if force_accurate_cut:
        return False   # accurate cut path needs the raw_part write semantics
    if ctx.payload.resume_from_last:
        return False   # resume semantics depend on raw_part existing
    # subtitle path: per-part Whisper fallback would need source — fuse is fine
    # because source_path is read directly; the only risk is full_srt slice failure.
    # The fast path always succeeds when full_srt_available=True (cached or fresh).
    return True
```

## Acceptance gate (compared in result doc)

- [ ] py_compile passes on both files
- [ ] Focused pytest 102/102 (= baseline)
- [ ] Full pytest 1396/1396 (= baseline)
- [ ] Smoke render with `RENDER_FUSE_CUT=0` (or unset): identical to Phase 3 (`per_part_cut` ~13 s, `per_part_encode` ~23 s)
- [ ] Smoke render with `RENDER_FUSE_CUT=1`: `per_part_cut` near 0; per-part total reduced; `output_rank_score` within ±0.5 % of OFF run
- [ ] raw_part.mp4 NOT created when fuse path taken
- [ ] No regression in any Sacred Contract or Frozen API contract

## Rollback

```bash
git checkout backend/app/features/render/engine/stages/part_render_encode.py
git checkout backend/app/features/render/engine/stages/part_cut.py
```

Or simpler runtime rollback: `unset RENDER_FUSE_CUT` (default OFF = legacy path).
