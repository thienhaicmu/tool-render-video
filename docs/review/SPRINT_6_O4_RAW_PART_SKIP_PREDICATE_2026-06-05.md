# Sprint 6 audit O-4 — `raw_part` Skip Predicate (Commit 1 + deferred Commit 2 plan)

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline at decision:** Pytest 2376 passed / 1 skipped / 0 failed @ `054fd0e` (Sprint 6 P1 close)
**Commit 1 tag:** `sprint-6-o4-commit1-2026-06-05`
**Commit 1 final pytest:** 2397 passed (+21 new) / 1 skipped / 0 failed

## Purpose

Audit row O-4 from `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` §6 is the **genuine remaining audit-ranked P0** after the Sprint 6 P1 cycle closed 3-for-3 DEFERs on pre-audit predictions (see `docs/review/SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md`). This sprint scopes the narrowest viable option — Option E "skip-when-no-subtitle" per the Sprint 6 P0 HIGH Planner finding — and ships it as a two-commit chain to keep Render Edit Protocol prudence honest.

Commit 1 (this commit, `20800ae`) ships **telemetry only** — the predicate + log emission. Zero render behavior change. This lets the predicate be validated against real workloads BEFORE the actual `cut_video` bypass is wired.

Commit 2 (deferred to a separate sprint after manual visual review) ships the actual fuse — bypassing `cut_video` and threading `(source_path, start, dur)` into a sibling `render_part_from_source` helper.

## Skip predicate (Commit 1)

```python
def _should_skip_raw_part_write(
    *,
    part_subtitle_enabled: bool,
    feature_base_clip_first: bool,
    feature_overlay_after_base_clip: bool,
    feature_base_clip_validation_artifact: bool,
) -> bool:
    base_clip_will_render = feature_base_clip_first and (
        feature_overlay_after_base_clip or feature_base_clip_validation_artifact
    )
    return (not part_subtitle_enabled) and (not base_clip_will_render)
```

Lives at `backend/app/orchestration/stages/part_cut.py` next to `run_cut_stage`. Pure function — no I/O, no side effects, keyword-only signature. 21 test cases pin the four-input truth table.

### Why these two gates

`raw_part` has **3 consumers** at present:

| ID | Site | Gated by | Gate name |
|---|---|---|---|
| C1 | `part_asset_planner.py:209` per-part Whisper | `subtitle_enabled_by_idx[idx]` | `part_subtitle_enabled` |
| C2 | `part_render_encode.py:185` `render_base_clip` | Sprint 6 P0 HIGH consumer gate at `part_render_encode.py:171-174` | `_base_clip_consumer_active` |
| C3 | `part_render_encode.py:308` `render_part_smart` | Always — unconditional | (the consumer the Commit 2 fuse will replace) |

C1 ungated → predicate False (`part_subtitle_enabled=True`).
C2 ungated → predicate False (`feature_base_clip_first AND (overlay OR validation)=True`).
Only C3 ungated → predicate True; safe to skip the raw_part write and fuse cut+render into one FFmpeg call.

`motion_aware_crop` does NOT change the predicate. `render_part_smart` reads its single `input_path` regardless of the motion branch (`base_clip_renderer.py:618` and `:660`).

## Commit 1 telemetry

When the predicate fires inside `run_cut_stage`:

```python
_job_log(
    ctx.effective_channel, ctx.job_id,
    f"raw_part_skip_eligible part={idx} predicate=true "
    f"subtitle_enabled=False base_clip_consumer=False",
    kind="debug",
)
```

Debug level — production logs stay quiet by default. Turn on render debug logging to see per-part predicate state. Pin: `tests/test_raw_part_skip_predicate.py::TestSourcePin::test_run_cut_stage_emits_telemetry_when_predicate_true`.

## Sacred Contracts walk (Commit 1)

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json keys | No | unchanged |
| #2 RenderRequest defaults | No new field this commit | n/a for Commit 1 |
| #3 AI returns None | No | n/a |
| #4 Job stage frozen | No | unchanged |
| #5 Part stage frozen | No | `CUTTING` upsert + `cut_video()` still run on every part |
| #6 `_emit_render_event` shape | No | telemetry uses `_job_log`, not `_emit_render_event` — no event-shape touch |
| #7 `data/app.db` | No | unchanged |
| #8 `qa_pipeline` | No | unchanged (`qa_pipeline` reads `final_part`, not `raw_part`) |
| NVENC Performance Protection | No | `cut_video` still runs as stream-copy (no NVENC); `render_part_smart` semaphore acquire unchanged |

## Commit 1 ROI

ZERO render behavior change. The win is informational: ops can grep for `raw_part_skip_eligible` in render logs to estimate Commit 2's actual savings on the user's workload before Commit 2 ships.

## Commit 2 deferred plan (separate sprint)

### Approved scope (per user 4/4 recommended choices)

1. **Scope:** Option E only. Motion-aware-crop=True deferred. (Motion-aware branch could be added in a future Commit 3 once Commit 2 settles.)
2. **Commit chain:** 2-commit (Commit 1 today, Commit 2 separate sprint after visual review).
3. **Feature flag:** `FEATURE_RAW_PART_SKIP=0` default. 30-day settling window like `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT`.
4. **Implementation pattern:** Sibling helper `render_part_from_source(source_path, start, dur, ...)` in `services/render/base_clip_renderer.py`. Additive only — `render_part_smart` signature stays frozen per the Sprint 5.2 merge.

### Files Commit 2 will touch

| File | Change |
|---|---|
| `backend/app/services/render/base_clip_renderer.py` | NEW `render_part_from_source(...)` helper — same vf-chain construction as `render_part`/`render_part_smart` but with `-ss start -t dur -i source_path` input-side seek. Shares vf-chain helpers verbatim. |
| `backend/app/orchestration/stages/part_cut.py` | Gate `cut_video()` on `FEATURE_RAW_PART_SKIP and skip_predicate(...)`. Replace telemetry log with the actual skip + a different log message marking the skip happened. |
| `backend/app/orchestration/stages/part_render_encode.py` | When `raw_part` does NOT exist (predicate fired + flag ON), call `render_part_from_source(ctx.source_path, effective_start, effective_end - effective_start, ...)` instead of `render_part_smart(str(raw_part), ...)`. |
| `backend/app/orchestration/render_pipeline.py` | Add `_FEATURE_RAW_PART_SKIP` env read alongside the existing three feature flags. |
| Mirror sites — `part_renderer.py`, `part_render_setup.py`, `part_render_encode.py`, `part_cut.py` | Mirror the new env read for drift prevention. |
| New audit doc | `docs/review/SPRINT_6_O4_COMMIT2_2026-06-XX.md` capturing the Render Edit Protocol 9-step trail + manual visual review results. |

### Commit 2 risk gates

Per `SPRINT_PLAN_2026-06-04.md` risk register line 302:

- Manual visual review on **3-5 sample renders** covering:
  - First-frame quality with no `force_accurate_cut` (verify input-side `-ss` keyframe alignment is acceptable).
  - Audio sync at part boundaries (verify `-c:a aac` re-encode + `atempo` filter is byte-identical to the cut-then-render path).
  - Duration accuracy ±0.35s vs the current keep-path behavior.
  - Subtitle-disabled + base_clip-disabled config (the default skip case).
  - A control render with `FEATURE_RAW_PART_SKIP=0` to confirm the flag gates correctly.
- Sacred Contract #5 verification: `CUTTING` upsert still fires unconditionally (preserved by Commit 1 telemetry as a witness — the upsert lives outside the cut_video() call).
- Sacred Contract #6 verification: `silence_trim_applied` / `first_frame_shift_applied` / `accurate_cut_forced` still fire when applicable (they read from `ctx.source_path` probes, not from `raw_part`).
- NVENC budget: confirm total `NVENC_SEMAPHORE` acquires per part stays at 1 (it was 1 before Commit 2 — cut was stream-copy).

### Commit 2 ROI projection (per audit row O-4)

- raw_part 20-50 MB × 50 parts = 1.0-2.5 GB **cumulative** (transient — unlinked at part DONE).
- Peak instantaneous (parallel_workers=4) ≈ 200 MB.
- `cut_video` time: 5-15s/part × 50 parts × skip-fire-rate.
- Realistic default-config subtitle-off batch: **~1.5 GB transient + ~12 min wall-time / 50-part render.**

The skip fire rate depends on workload:
- `payload.add_subtitle=False` master switch off → 100% of parts skip.
- `add_subtitle=True` + `subtitle_only_viral_high=True` + cutoff → ~50-70% of parts skip (the parts that don't pass the viral filter).
- `add_subtitle=True` without viral cutoff → 0% skip (all parts get subtitle by safety fallback at `render_pipeline.py:630-639`).

### Commit 2 resume/retry interaction (verified safe)

- `part_renderer.py:147-156`: resume on `final_part` exists + DONE + valid → skip whole part. Unchanged.
- `part_cut.py:254`: existing resume guard `raw_part exists` — in skip-path raw_part never exists → guard is bypassed naturally → fused render fires.
- Resume on interrupted prior-run keep-path → new-run skip-path: orphan `raw_part` from prior run is cleaned by `part_done.py:216` when `cleanup_temp_files=True`. No staleness risk.
- Retry: process_one_part recomputes from scratch — no held state.

### Why DEFER Commit 2 to a separate sprint

1. Manual visual review is the dominant cost item. It's not a CI gate — it's a human-time gate. Splitting commits means the predicate ships to production logs immediately and the visual-review prerequisite isn't blocked on a single-commit decision.
2. Sprint Plan risk register line 302 specifically calls out this class of optimization as CRITICAL requiring 3-5 sample reviews. Pretending we can ship both in one sprint while honoring the gate is dishonest scoping.
3. Real workloads inform the priority of motion-aware-crop sub-scope. If the predicate fires on a tiny fraction of parts in production, Commit 2 might never be worth shipping. The telemetry tells us.

## Audit-ranked items still on the table after Commit 1

| Audit row | Item | Status |
|---|---|---|
| O-4 | `raw_part` skip — Commit 1 (telemetry) | **SHIPPED** (this commit, `20800ae`) |
| O-4 | `raw_part` skip — Commit 2 (actual fuse) | DEFERRED to separate sprint after visual review |
| O-4 | Motion-aware-crop sub-scope | DEFERRED (out of Option E scope) |
| O-10 | `_base_clip_out` gating | SHIPPED Sprint 6 P0 HIGH `e961533` |
| S-5 | `xtts_cache` bounding | SHIPPED Sprint 6 P0 LOW `1db0df3` |
| S-7 | `text_overlay` cleanup | SHIPPED Sprint 6 P0 LOW `1db0df3` |
| S-11 | Render cache TTL | SHIPPED Sprint 6 P1 `d1162d8` + `f1a3d4b` |

After Commit 1 ships, the audit-ranked P0/P1 backlog is **down to just O-4 Commit 2** — all other ranked items are shipped.

## Parked items from prior audits

For context completeness, the following parked items are out of audit scope but recorded for future sprint authors:

- **N.1 Content-addressable ASS cache** (from `SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md`). MEDIUM risk. Win only on re-renders.
- **N.2 Lift `SUBTITLE_PER_PART_MODEL` default** — SHIPPED in `2f2c8ab`. No follow-up.
- **Mixed DB connection model unification** (from `SPRINT_5_4_DB_CONNECTION_AUDIT_2026-06-05.md`). HIGH risk. Gated on per-frame benchmark.

## What this commit (the audit doc) does

Single commit, single new doc file. No code change. Pytest baseline (2397/1/0) unchanged.

Sibling code commit `20800ae` ships the predicate + telemetry.

## Cross-references

- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` §6 row O-4 — the empirical audit ranking that scoped this work
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` §"What was DEFERRED — raw_part in-memory" — the prior Sprint 6 P0 HIGH planner finding that recommended Option E as the narrowest scope
- `docs/review/SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md` — meta-finding that Sprint Plan predictions failed 3-for-3 against the empirical audit, leaving O-4 as the only remaining audit-ranked P0
- `backend/app/orchestration/stages/part_cut.py` — predicate + telemetry implementation
- `backend/tests/test_raw_part_skip_predicate.py` — 21-case truth-table + source pins
- `backend/app/orchestration/stages/part_asset_planner.py:209` — C1 consumer
- `backend/app/orchestration/stages/part_render_encode.py:185` — C2 consumer
- `backend/app/orchestration/stages/part_render_encode.py:308` — C3 consumer (the one Commit 2's fuse will replace)
- `CLAUDE.md` Sacred Contracts §5 (frozen part stages — preserved), §6 (event shape — preserved), §8 (qa_pipeline — preserved)
- `SPRINT_PLAN_2026-06-04.md:302` — risk register entry requiring 3-5 sample visual reviews for Sprint 6 temp optimizations

## What future sprints should do (when picking up Commit 2)

1. **Read the production logs first.** Grep `raw_part_skip_eligible` across recent renders. If the fire rate is sub-10%, deprioritise Commit 2 — there's not enough disk/time to justify the visual-review cost.
2. **Confirm the gate set hasn't drifted.** Re-grep `_should_skip_raw_part_write` to verify the predicate hasn't been quietly extended.
3. **Run the manual visual review.** Three samples minimum: subtitle-off + base_clip-off + motion-aware-off (the predicate-true default case), subtitle-on (keep-path control), and one with `FEATURE_BASE_CLIP_FIRST=1` to verify the consumer gate still holds.
4. **Ship Commit 2 commit chain.** Per the file inventory above.
5. **Author the Commit 2 closure doc.** `docs/review/SPRINT_6_O4_COMMIT2_<date>.md` with the visual-review screenshots/durations + pytest delta + Sacred Contract walk repeat.
