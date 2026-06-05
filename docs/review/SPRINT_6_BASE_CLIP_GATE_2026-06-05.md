# Sprint 6 P0 HIGH — `_base_clip_out` Gate Tightening

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline:** Pytest 2346 passed / 1 skipped / 0 failed @ `bad635b` (Sprint 5.4 close)
**Tier:** CRITICAL — Render Edit Protocol 9 steps followed end-to-end.

## Purpose

Stop rendering the `base_clip.mp4` intermediate when no downstream consumer will read it. The previous gate was `if _FEATURE_BASE_CLIP_FIRST:` — that wrote a 50-150 MB throwaway artefact AND ran a full motion-crop FFmpeg encode per part even when nothing read the result.

## What changed

`backend/app/orchestration/stages/part_render_encode.py` — old gate:

```python
if _FEATURE_BASE_CLIP_FIRST:
    _base_clip_out = ctx.work_dir / f"part_{idx}" / "base_clip.mp4"
    ...
```

New gate:

```python
_base_clip_consumer_active = (
    _FEATURE_OVERLAY_AFTER_BASE_CLIP or _FEATURE_BASE_CLIP_VALIDATION_ARTIFACT
)
if _FEATURE_BASE_CLIP_FIRST and _base_clip_consumer_active:
    _base_clip_out = ctx.work_dir / f"part_{idx}" / "base_clip.mp4"
    ...
```

Three env-flag truth-table rows are affected; one is the new opt-in.

| `FEATURE_BASE_CLIP_FIRST` | `FEATURE_OVERLAY_AFTER_BASE_CLIP` | `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` | Pre-Sprint-6 behavior | Post-Sprint-6 behavior |
|---|---|---|---|---|
| 0 | 0 | 0 | skip base_clip | skip base_clip (unchanged) |
| 0 | 0 | 1 | skip base_clip | skip base_clip (unchanged) |
| 0 | 1 | 0 | skip base_clip + warning at part_render_setup.py:324 | unchanged |
| **1** | **0** | **0** | render base_clip → throwaway | **SKIP base_clip — Sprint 6 P0 HIGH win** |
| **1** | **0** | **1** | (flag did not exist) | **render base_clip — new opt-in for A/B forensics** |
| 1 | 1 | 0 | render base_clip → composite_overlays_on_base_clip reads it | unchanged |
| 1 | 1 | 1 | (flag did not exist) | render base_clip → composite reads it (validation flag redundant here) |

## ROI claim

Session-recap claim of 4.5-7.5 GB / 50-part was a conflation of `raw_part` + `_base_clip_out` from the Sprint 1.4 `TEMP_FILE_AUDIT_2026-06-04.md`. Audit numbers (re-verified by Planner):

- `_base_clip_out`: 50-150 MB per part × 50 parts = **2.5-7.5 GB**, but ONLY when `FEATURE_BASE_CLIP_FIRST=1`.
- `raw_part`: 20-50 MB per part × 50 parts = 1.0-2.5 GB (this is the default-config disk burn; NOT addressed by Sprint 6 P0 HIGH).

**Default-config users (both flags OFF) see zero disk savings from this gate** — `_base_clip_out` was already never written. **The win lands on users running `FEATURE_BASE_CLIP_FIRST=1`:**
- They previously paid 50-150 MB disk + one full motion-crop FFmpeg encode per part.
- The throwaway is gone unless they opt back in via `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1`.
- `render_part_smart()` still produces the final output (unchanged behaviour for that user cohort).

The GPU/CPU time win is arguably larger than the disk win — one full motion-crop NVENC encode per part removed.

## Backward compatibility — `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT`

The new env var preserves the legacy A/B forensics workflow for any operator who relied on `base_clip.mp4` being written as a parallel artefact:

```bash
# Pre-Sprint-6 behaviour (write base_clip.mp4 as throwaway artefact):
FEATURE_BASE_CLIP_FIRST=1
FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1
```

Without setting `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1`, an operator who has `FEATURE_BASE_CLIP_FIRST=1` set today (but `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`) sees the disk write disappear. This is a behaviour change for them. The render output is byte-identical because `render_part_smart()` was already producing the final video in this code path.

**Sacred Contract #2 disposition:** the new env var defaults to `0` (disabled), which is the "no validation artefact" path. Users who relied on the artefact must explicitly set the flag — a one-line configuration. Documented in this audit doc; the gate change is otherwise transparent.

## Sacred Contracts walk

| Contract | Touched? | Outcome |
|---|---|---|
| #1 result_json keys (`output_rank_score`, `is_best_output`, `is_best_clip`) | No | unchanged |
| #2 RenderRequest defaults / new fields default disabled | Yes — new env var `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` defaults to `0` | compliant |
| #3 AI returns None / never raises | No | n/a |
| #4 Frozen job stage names | No | unchanged |
| #5 Frozen part stage names | No | unchanged |
| #6 `_emit_render_event` signature | No | unchanged — `visual_finish_applied` and all other events still fire from `render_part_smart` path |
| #7 `data/app.db` sole authority | No | unchanged |
| #8 `qa_pipeline.py` never bypassed | **Verified clean** | qa_pipeline.py reads only the final `output_path`. It does not read `base_clip.mp4` or `raw_part.mp4`. The gate change does NOT affect validation. |

## Performance protections

| Protection | Impact |
|---|---|
| `NVENC_SEMAPHORE` (CLAUDE.md Performance Protections) | **Strictly improved.** One fewer NVENC acquire per part when `FEATURE_BASE_CLIP_FIRST=1 && FEATURE_OVERLAY_AFTER_BASE_CLIP=0` (the common opt-in config). |
| `NVENC_MAX_SESSIONS` ceiling | Unchanged — fewer encodes attempted per part means less semaphore pressure. |
| `MAX_RENDER_JOBS` / per-part worker concurrency | Unchanged — no new memory cost, no new disk peak. |
| FFmpeg path helpers (`safe_filter_path`, etc.) | Unchanged — same call patterns. |

## What was DEFERRED — `raw_part` in-memory

Planner audit found that the three `raw_part` consumers (Whisper transcription in `part_asset_planner.py:209`, `render_base_clip` at `part_render_encode.py:164`, `render_part_smart` at `part_render_encode.py:287`) all accept `str(path)` arguments. None accept `BytesIO`, none reliably accept FFmpeg pipe stdin under Whisper. Every feasible variant (FFmpeg pipe, BytesIO, tmpfs, skip-when-no-subtitle) requires CRITICAL-tier signature changes or platform-specific OS features (Windows lacks native tmpfs).

Real default-config `raw_part` ROI is 1.0-2.5 GB transient — every `raw_part.mp4` is deleted in the part DONE stage. Risk/reward unfavourable for Sprint 6 prudence.

`raw_part` in-memory is therefore deferred to a separate Planner cycle. Recommended next target (per Planner): option E (skip-when-no-subtitle) — narrower blast radius than the pipe variants.

## Test coverage

`backend/tests/test_part_render_encode_base_clip_gate.py` — 14 cases across four classes:

1. **TestGateTruthTable** (6 cases) — direct boolean exercise of the gate condition. Mirrors the production `if first and (overlay or validation)` expression.
2. **TestPipelineBlockGate** (4 cases) — simulate-the-pipeline-block style identical to `test_render_base_clip.py:248-316` (matching pattern). Confirms `render_base_clip` is mock-called in exactly the right configurations.
3. **TestValidationArtifactFlagDefault** (2 cases) — Sacred Contract #2 pin: the new env var defaults to `0`.
4. **TestModuleLevelFlagReadsCoherent** (5 cases) — pin that all 4 modules that hold a per-process copy of the flag read the same env var name + source-pin that the gate boolean variable name (`_base_clip_consumer_active`) and the new flag still participate in the gate.

`tests/test_render_base_clip.py`, `tests/test_base_clip_manifest.py`, `tests/test_overlay_compositor.py`, `tests/test_composite_overlays.py` continue to pass unchanged — the `render_base_clip` helper itself is untouched.

## Deprecation timeline

`FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` is a transitional opt-in. **Scheduled for removal 2026-07-05** (30-day settling period). After the settling period:

1. New ledger doc records the removal decision.
2. The env var is deleted from all 4 module-level reads.
3. The gate simplifies to `if _FEATURE_BASE_CLIP_FIRST and _FEATURE_OVERLAY_AFTER_BASE_CLIP:`.
4. Operators who still want the validation artefact at that point must justify the use case; per Planner there is no current consumer.

If between 2026-06-05 and 2026-07-05 an actual consumer of the validation artefact surfaces, the deprecation can be paused with a follow-up audit doc — the flag stays opt-in indefinitely until a planner cycle confirms zero consumers.

## What this commit does NOT do

- It does NOT change `render_base_clip()` itself. The helper is untouched.
- It does NOT change `composite_overlays_on_base_clip()`. The overlay path is untouched.
- It does NOT change `render_part_smart()`. The default render path is untouched.
- It does NOT touch `raw_part` write/read sites.
- It does NOT alter any frozen API contract.

## Cross-references

- Sprint 6 P0 HIGH Planner brief and findings: this conversation's plan stage
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` — Sprint 1.4 audit O-4 (raw_part) + O-10 (base_clip)
- `docs/review/SPRINT_PLAN_2026-06-04.md:253-266` — Sprint 6 outline (the predicted P0 list was superseded by the audit's empirical ranking)
- `backend/app/services/render/base_clip_renderer.py` — `render_base_clip` impl (Sprint 5.2 merged into this file)
- `backend/app/orchestration/stages/part_render_encode.py` — gate site, this sprint's surgical change
- `CLAUDE.md` Sacred Contracts §2 (new flag defaults disabled), §6 (event signature unchanged), §8 (qa_pipeline not bypassed)
- `CLAUDE.md` Performance Protections / `NVENC_SEMAPHORE` — strictly improved
