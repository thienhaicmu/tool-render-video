# Sprint 6 P1 Whisper Skip — DEFERRED

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline at decision:** Pytest 2363 passed / 1 skipped / 0 failed @ `e961533` (Sprint 6 P0 HIGH close)
**Decision:** DEFER full per-part Whisper removal. Redirect Sprint 6 P1 to "Inline ASS qua filter graph" (audit-supported).

## Purpose

Record the Sprint 6 P1 Whisper audit so future agents do not re-attempt the swap without understanding why the conservative call was made, and so the actual quality-improvement opportunity (H3) is captured for follow-up scoping.

## Original target

Per `docs/review/SPRINT_PLAN_2026-06-04.md:259`:

> Dự đoán P0:
> - Skip per-part Whisper re-extract audio
> - Inline subtitle ASS qua filter graph (không write file)
> - Pipe TTS audio → mix (không write WAV intermediate)
> - Render cache prune (`maintenance.py` Issue 3 CLAUDE.md)

The phrase "Dự đoán" (predicted) is load-bearing. The Sprint 1.4 audit (`docs/review/TEMP_FILE_AUDIT_2026-06-04.md`) did **not** rank per-part Whisper among empirical P0/P1 targets. The Sprint Plan line 257-261 was a guess written before the audit completed.

## Dual-Whisper inventory (current state)

### Source-level Whisper
- **File:** `backend/app/orchestration/render_pipeline.py:718-726` (post-cut) + `backend/app/orchestration/parallel_analysis.py:322` (early-parallel, pre-cut)
- **Audio:** full `source_path` (line 719)
- **Model:** `tuned["whisper_model"]` resolved in `backend/app/orchestration/pipeline_config.py:23-29`. Defaults: `base` (fast), `small` (balanced), `large-v3` (quality / best)
- **Output:** `full_srt = work_dir / f"{source['slug']}_full.srt"` (`llm_pipeline.py:136`, `render_pipeline.py:424`)
- **Cached:** `_transcription_cache_put` at `render_pipeline.py:749` keyed by `(source_path, model, engine_key)` — survives re-renders

### Per-part Whisper
- **File:** `backend/app/orchestration/stages/part_asset_planner.py:208-216`
- **Audio:** `str(raw_part)` — the per-part stream-copy cut produced by `part_cut.py:214`
- **Model:** `os.getenv("SUBTITLE_PER_PART_MODEL", "small")` at `part_asset_planner.py:206`. **Independent of `tuned["whisper_model"]`. Hard-codes `small`.**
- **Cache:** resume-only via `srt_part.exists()` check at line 200

## Hypothesis testing — why does the dual-Whisper path exist?

The Planner pre-read brief listed five hypotheses. Code-level evidence:

| Hypothesis | Status | Evidence |
|---|---|---|
| **H1** Timing alignment (per-part timestamps natural 0) | PARTIALLY confirmed | The invariant "SRT timestamps must start at 0 for the ass filter that runs before setpts" is real. It is pinned by `tests/test_phase0_hotfixes.py:43-62` (ass-before-setpts ordering) + `:64-85` (the `str(raw_part)` PIN). But the invariant is satisfied EQUALLY by `slice_srt_by_time(start=_effective_start, end=seg["end"], rebase_to_zero=True, apply_playback_speed=False)`. The PIN at lines 80-85 enforces the *current implementation*, not the underlying correctness contract. |
| **H2** Source SRT might be missing | NO evidence | `part_asset_planner.py:192-194` already skips per-part subtitles when `raw_part` is missing. There is no code path where per-part wants subtitles but source-level SRT is unavailable. |
| **H3** Different model | **CONFIRMED + IRONIC** | Per-part hard-codes `small` (`part_asset_planner.py:206`). Source uses `tuned["whisper_model"]` which is `large-v3` on quality/best profiles. **For users on quality/best profiles, the per-part path produces LOWER-quality subtitles than source-level Whisper would. This is a quality regression baked into the codebase.** Skipping per-part Whisper and slicing source SRT would IMPROVE subtitle quality for those profiles. |
| **H4** Audio drift | NO evidence | `raw_part` is produced via FFmpeg `-c copy` (`part_cut.py:214`). Audio is byte-identical to the source slice. Whisper output should match. |
| **H5** Vestigial | CONFIRMED | Sliced-source-SRT replacement is already proven in two adjacent code paths: `part_voice_mix.py:127, 221` (voice/TTS path uses sliced source SRT, no per-part Whisper); `part_render_encode.py:242-248` (base-clip-first overlay path uses sliced source SRT, gated by `FEATURE_BASE_CLIP_FIRST=1 + FEATURE_OVERLAY_AFTER_BASE_CLIP=1`). The per-part Whisper only feeds the legacy `render_part_smart` path's `ass_part`. |

**Net conclusion:** H1's invariant does not require per-part Whisper. H3 actually argues FOR removing it (current implementation caps subtitle quality at `small`). H5 confirms the replacement is proven elsewhere in the codebase. **The technical case for the swap is strong.**

But — **the PIN at `test_phase0_hotfixes.py:64-85` is load-bearing for the current implementation.** Rewriting it requires a HIGH-CRITICAL change to `part_asset_planner.py`, plus 3+ new pins for the new path, plus full pytest validation, plus manual visual review on 3-5 sample renders per `SPRINT_PLAN_2026-06-04.md:302` risk register.

## Why DEFER

1. **Audit doc mismatch.** `TEMP_FILE_AUDIT_2026-06-04.md` does not list per-part Whisper among empirical P0/P1 ranked items. The Sprint Plan prediction was unverified.

2. **ROI is modest.** Time win: 30 s – 8 min per render depending on parts + model. Largely absorbed by `_transcription_cache_put` on re-runs of the same source. Disk win: marginal (per-part WAV is a few MB, cleaned up in finally block per audit row S-1).

3. **Risk register flags it CRITICAL.** Sprint Plan line 302 explicitly classifies Sprint 6 temp optimization as CRITICAL with "qa_pipeline + manual visual review on 3-5 sample videos" required. For a 30 s – 8 min/render saving, the manual-review overhead dominates the engineering budget.

4. **Conservative bias for user-facing quality.** Subtitle quality is what the end user sees in the rendered video. Any change here without sample-render validation is a regression risk class the project has not budgeted.

5. **Better Sprint 6 P1 targets exist.** Audit-ranked items include `xtts_cache` prune, `text_overlay` cleanup (both already partially handled in commit `1db0df3`), inline subtitle ASS via filter graph, and TTS pipe. The user-selected redirect is **inline ASS via filter graph** — audit-supported and lower-risk.

## What this audit does NOT defer

**H3 (the quality irony) is a separate concern.** The per-part Whisper currently caps at `small` even when the source is `large-v3`. This is a documented quality regression for quality/best profiles. A future MEDIUM-risk Sprint can ship a **partial safe fix** that does not remove per-part Whisper:

- Change `SUBTITLE_PER_PART_MODEL` default from `"small"` to `tuned["whisper_model"]`.
- Pure additive — no PIN change, no signature change, no Sacred Contract surface touched.
- Brings per-part subtitle quality in line with source-level on quality/best profiles.
- Time cost: per-part Whisper goes from ~3-10 s/part to ~5-15 s/part (larger model). The user already accepted that cost for source-level Whisper.

This partial fix is parked here as a separate follow-up scoping target. **Not part of Sprint 6 P1.**

## Redirected scope

User chose to redirect Sprint 6 P1 to **"Inline ASS qua filter graph"** (`SPRINT_PLAN_2026-06-04.md:259` — original Sprint 6 P1 line item #2).

Next Planner cycle will audit:
- Current ASS file write site(s) — likely in `part_asset_planner.py` and `part_render_encode.py`
- Whether `ass=` filter accepts content via stdin / data URI / non-file source
- Compatibility with `libass` rendering quality + font loading
- Sacred Contract risk + test strategy + ROI

That is a separate Planner cycle and a separate sprint deliverable.

## What this commit does

Single commit, single file — this audit doc. No code change. Pytest baseline (2363/1/0) unchanged.

## Cross-references

- Sprint 6 P1 Planner brief and findings: this conversation's plan stage
- `docs/review/SPRINT_PLAN_2026-06-04.md:253-266` — Sprint 6 outline + risk register
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` — Sprint 1.4 empirical audit (the document the Sprint Plan prediction superseded)
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` — sibling Sprint 6 P0 HIGH doc (the gate change that closed cleanly)
- `backend/tests/test_phase0_hotfixes.py:43-86` — the existing per-part Whisper PIN (left untouched by this audit)
- `backend/app/orchestration/stages/part_asset_planner.py:204-258` — the per-part Whisper call site (left untouched by this audit)
- `backend/app/orchestration/render_pipeline.py:718-726` — source-level Whisper call site
- `backend/app/orchestration/pipeline_config.py:23-29` — `tuned["whisper_model"]` resolver
- `docs/RENDER_PIPELINE.md:311` — the documented desired end-state (full SRT generated once, sliced per part) which the current implementation does NOT match
- `CLAUDE.md` Sacred Contracts §5 (frozen part-stage names), §6 (event signature), §8 (qa_pipeline not bypassed)

## What future sprints should NOT do

- Do not delete this audit doc. It is the audit-ledger record that the dual-Whisper path was reviewed and the swap was rejected on risk grounds, not on technical impossibility.
- Do not attempt the full swap (Option C in the Planner output) without first running a manual visual review on 3-5 sample renders covering quality/best/balanced/fast profiles.
- Do not silently lift `SUBTITLE_PER_PART_MODEL` default — bundle the H3 partial fix into its own scoped sprint with a single-commit + audit-doc deliverable.
