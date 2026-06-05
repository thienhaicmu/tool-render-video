# Sprint 6 P1 Audit Cycle Summary — Meta-Finding

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Tag at close:** `sprint-6-p1-close-2026-06-05`
**Final pytest:** 2376 passed / 1 skipped / 0 failed @ `a5ff855`

## Meta-finding

**SPRINT_PLAN_2026-06-04.md §253-266 listed four "Dự đoán P0" (predicted P0) line items for Sprint 6 P1. The empirical Sprint 1.4 audit (`docs/review/TEMP_FILE_AUDIT_2026-06-04.md`) endorsed exactly one of them. Validation rate: 1/4 = 25%.**

This summary captures the four cycles as a single audit-ledger entry so future Sprint Plan authors can index from the empirical audit rather than from pre-audit predictions.

## Validation table

| # | Sprint Plan §253-266 prediction | Audit endorsement | Final disposition | Audit doc |
|---|---|---|---|---|
| 1 | Skip per-part Whisper re-extract audio | NOT ranked | DEFER (PIN load-bearing + manual visual review required + ROI absorbed by transcription cache) + parked N.2 H3 quality fix | `SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md` |
| 2 | Inline subtitle ASS qua filter graph | `TEMP_FILE_AUDIT §6 line 148` explicitly says "not feasible" | DEFER (FFmpeg `ass=` filter calls `fopen()` directly; no inline mechanism exists; verified on Windows + all 5 alternative paths DOA) | `SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` |
| 3 | Pipe TTS audio → mix | NOT ranked | DEFER (1-10 MB per-part ROI; audio cleanup adapter is path-based by design; Windows pipe deadlock risk; cleanup bypass = silent quality regression) | `SPRINT_6_P1_TTS_PIPE_DEFER_2026-06-05.md` |
| 4 | Render cache prune (`maintenance.py` Issue 3) | Audit row S-11 endorsed | **RESOLVED** (Sprint 5.2 already shipped most; Sprint 6 P1 wired periodic loop + added `freed_bytes` metric + closed CLAUDE.md Issue 3) | `SPRINT_6_P1_CACHE_PRUNE_2026-06-05.md` |

Also addressed in this Sprint 6 P1 cycle but not on the original prediction list:

| Item | Provenance | Disposition |
|---|---|---|
| N.2 H3 quality fix — lift `SUBTITLE_PER_PART_MODEL` default | Surfaced from the Whisper defer audit (per-part Whisper hard-coded "small" while source-level uses `tuned["whisper_model"]` = "large-v3" on quality/best profiles) | **SHIPPED** as commit `2f2c8ab`. Pure additive 1-line config change. Fixes the quality regression that existed before Sprint 6 P1. |

## Per-item context

### #1 Whisper-skip — DEFER

Per-part Whisper at `part_asset_planner.py:208-216` is technically removable. The H1 invariant ("subtitle timestamps must start at 0 for the ass filter that runs before setpts") is real but satisfied equally by `slice_srt_by_time(rebase_to_zero=True, apply_playback_speed=False)`. The sliced-source-SRT replacement is already proven in two adjacent code paths (`part_voice_mix.py:127,221` and `part_render_encode.py:242-248`).

**Blocker:** The PIN at `tests/test_phase0_hotfixes.py:64-85` is load-bearing for the current implementation. SPRINT_PLAN risk register (line 302) flags Sprint 6 temp optimization as CRITICAL requiring manual visual review on 3-5 sample renders. 30s-8min/render saving is largely absorbed by `_transcription_cache_put` on re-runs. Conservative bias for user-facing subtitle quality.

**Parked H3 quality fix shipped:** lifting `SUBTITLE_PER_PART_MODEL` default to match source-level model. This is the genuine user-visible improvement that surfaced from the audit, and it shipped without requiring the full swap.

### #2 Inline ASS — DEFER (technical impossibility)

FFmpeg 7.1.1 `ass=` and `subtitles=` filters accept only a `filename` parameter opened via `fopen()`. libass does not route through libavformat, so input protocol/scheme handlers (`pipe:`, `data:`, `file:`, etc.) are unreachable from the filter argument. Every alternative mechanism (FIFO/mkfifo, stdin pipe:0, data URI, subtitles= inline, /proc/self/fd) is either not supported by the filter, not available on Windows, or both.

**Independent corroboration:** `TEMP_FILE_AUDIT_2026-06-04.md` §6 line 148 already concluded "the `ass` filter requires a libass-readable file on disk, so a true inline replacement is not feasible." That was written before SPRINT_PLAN §259 was drafted.

**N.1 (content-addressable ASS cache) parked as a separate scoping target.** Not shipped this sprint.

### #3 TTS pipe — DEFER

Edge-TTS streaming API exists (`Communicate.stream()`). XTTS does not (uses `tts_to_file(file_path=str)`). The codebase has no subprocess CLI TTS engines, so the SPRINT_PLAN wording "Pipe TTS" mismatches the library-mode architecture.

**Real blocker:** the audio cleanup adapter (`backend/app/services/audio/cleanup_adapters.py:65-77`) uses DeepFilterNet's `df.enhance.load_audio(str)` / `save_audio(str)` API which is path-based by design. Piping TTS → mix means either skipping cleanup (silent quality regression) or materializing a temp WAV (defeats the purpose).

**ROI**: 1-10 MB per part, 50-500 MB worst case for 50 parts, millisecond-class time win. `xtts_cache` (Sprint 6 P0 commit `1db0df3`) already covers the repeat-synthesis disk concern.

### #4 Render cache prune — RESOLVED

The only audit-endorsed prediction. Most of the work shipped in Sprint 5.2; Sprint 6 P1 closed the residual gap (periodic-loop wire + `freed_bytes` metric + closure of CLAUDE.md Issue 3).

## Why the 1/4 rate?

The Sprint Plan was drafted at the start of the migration roadmap (`SPRINT_PLAN_2026-06-04.md` dated 2026-06-04) based on intuitive predictions of what optimisations would matter. The empirical Sprint 1.4 audit (`TEMP_FILE_AUDIT_2026-06-04.md`) ran later and produced a different ranking grounded in actual file inventories + sizes. The pre-audit predictions were not updated against the post-audit findings — they were left as-is in the Sprint Plan even though three of four were no longer ranked.

Three patterns explain the prediction failures:

1. **Prediction outpaced architecture audit.** Inline-ASS (#2) and TTS-pipe (#3) hit hard architectural blockers (libass `fopen()`, DeepFilterNet path-based API) that would have been visible at audit time. The predictions were generated without reading the consumer side of the relevant APIs.

2. **Prediction conflated "could be removed" with "should be removed".** Whisper-skip (#1) is technically possible but the quality+risk trade-off doesn't favour it. The prediction assumed any disk-write was worth eliminating; the audit ranked the entry MEDIUM because the lazy-eviction in `pipeline_cache.py` already handled the user-visible disk concern.

3. **Prediction missed that some "remaining" work was already in flight.** Render cache prune (#4) had its core implementation shipped in Sprint 5.2 already; Sprint 6 P1's role was a 5-LOC residual wire, not a from-scratch implementation. CLAUDE.md documentation lag made the prediction look like new scope.

## Implication for future Sprint Plans

**Recommendation: future sprint authors should index sprint scope from `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` §6 (the empirical audit's P0/P1 ranking) rather than from `SPRINT_PLAN_2026-06-04.md:257-261` (the pre-audit "Dự đoán P0" prediction list).**

Specifically: any line in the SPRINT_PLAN under "Dự đoán" should be treated as a hypothesis to validate against the audit, not as scoped work. When the audit doesn't endorse the prediction, the cycle should be:

1. Planner cycle (1 day)
2. DEFER doc shipped (single-commit)
3. Move to next item

This is exactly the pattern Sprint 6 P1 ran for items #1, #2, #3 — with the meta-finding being that all three audit cycles produced the same DEFER outcome.

## Audit-ranked P0 items still on the table

For Sprint 6 P2 and beyond, the audit (`TEMP_FILE_AUDIT_2026-06-04.md` §6) ranks the following P0/P1 items that have NOT been addressed yet:

| Audit row | Item | Risk tier | Approx ROI | Status |
|---|---|---|---|---|
| O-4 | `raw_part` in-memory staging (skip per-part raw clip write) | HIGH-CRITICAL | 1.0-2.5 GB / 50-part default config | NOT shipped — recommended Sprint 6 P2 target |
| O-10 | `_base_clip_out` gating | HIGH-CRITICAL | 2.5-7.5 GB on `FEATURE_BASE_CLIP_FIRST=1` audience | **SHIPPED** as Sprint 6 P0 HIGH commit `e961533` |
| S-5 | `xtts_cache` bounding | LOW | bounded growth | **SHIPPED** as Sprint 6 P0 LOW commit `1db0df3` |
| S-7 | text_overlay cleanup | LOW | bounded growth | **SHIPPED** as Sprint 6 P0 LOW commit `1db0df3` |
| S-11 | render cache TTL prune | LOW | < 300 MB cumulative | **SHIPPED** as Sprint 6 P1 commits `d1162d8` + `f1a3d4b` |

**O-4 is the genuine remaining audit-ranked P0 item.** Future scoping should pursue option E (skip-when-no-subtitle) per the deferred Sprint 6 P0 HIGH Planner finding — narrower blast radius than pipe/BytesIO variants.

Parked but NOT audit-ranked:
- **N.1** Content-addressable ASS cache (from Inline ASS audit). MEDIUM risk. Win only on re-renders.
- **Mixed DB connection model unification** (from Sprint 5.4 audit). HIGH risk. Gated on per-frame benchmark.

## Sprint 6 P1 close declaration

With this summary doc shipped:
- **Sprint 6 P1 line items #1, #2, #3 are DEFERRED** with individual audit docs.
- **Sprint 6 P1 line item #4 is RESOLVED** with closure ledger.
- **Sprint 6 P1 N.2 H3 quality fix shipped** as a parked item from item #1's audit.

Sprint 6 P1 is **closed**. Final commit chain:
- `ca4d7b2` — Whisper DEFER doc
- `29de28c` — Inline ASS DEFER doc
- `2f2c8ab` — N.2 H3 quality fix (the actual user-visible improvement from item #1's audit)
- `d1162d8` — Cache prune wire + freed_bytes metric (item #4)
- `f1a3d4b` — CLAUDE.md Issue 3 RESOLVED + cache prune closure ledger
- `a5ff855` — TTS pipe DEFER doc (this commit's parent)
- `<this commit>` — Sprint 6 P1 audit cycle summary (meta-finding)

Tag `sprint-6-p1-close-2026-06-05` follows.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-04.md:253-266` — the prediction list this summary validates against
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` §6 — the empirical audit whose ranking should drive future sprint scoping
- `docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md` — item #1 audit
- `docs/review/SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` — item #2 audit
- `docs/review/SPRINT_6_P1_TTS_PIPE_DEFER_2026-06-05.md` — item #3 audit
- `docs/review/SPRINT_6_P1_CACHE_PRUNE_2026-06-05.md` — item #4 closure
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` — Sprint 6 P0 HIGH success
- `CLAUDE.md` — Issue 3 updated to RESOLVED in Sprint 6 P1 cache prune commit
