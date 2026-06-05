# Sprint 6 P1 Inline ASS — DEFERRED (technical impossibility)

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline at decision:** Pytest 2363 passed / 1 skipped / 0 failed @ `ca4d7b2` (Sprint 6 P1 Whisper defer close)
**Decision:** DEFER full inline-ASS replacement. **Mechanism does not exist in FFmpeg.** Sibling P1 item to the just-deferred Whisper P1 — both pre-audit SPRINT_PLAN predictions that the empirical audit did not endorse.

## Purpose

Record the Sprint 6 P1 Inline ASS audit so future agents do not re-attempt a replacement that FFmpeg's filter architecture forbids, and so the actual MEDIUM-risk follow-ups (content-addressable ASS cache, H3 Whisper quality fix) are captured for follow-up scoping.

## Original target

Per `docs/review/SPRINT_PLAN_2026-06-04.md:259`, line item #2 of Sprint 6 P1:

> Dự đoán P0:
> - Skip per-part Whisper re-extract audio
> - Inline subtitle ASS qua filter graph (không write file)
> ...

The phrase "Dự đoán" (predicted) is load-bearing. The Sprint 1.4 audit (`docs/review/TEMP_FILE_AUDIT_2026-06-04.md`) §6 line 148 **explicitly stated** the conclusion this Planner cycle re-reached independently:

> "the `ass` filter requires a libass-readable file on disk, so a true inline replacement is **not feasible**."

The audit ranked the ASS optimisation as MEDIUM, not P0. The SPRINT_PLAN line 259 was a guess written before the audit completed.

## Why inline ASS is impossible — FFmpeg evidence

FFmpeg 7.1.1 (the project's bundled binary at `C:\Program Files\FFmpeg\bin`) `-h filter=ass` and `-h filter=subtitles` output:

```
filename <string>  set the filename of file to read
f        <string>  set the filename of file to read
```

That is the only input mechanism either filter accepts. **libass calls `fopen()` on the path string directly — the filter is NOT routed through libavformat.** This means the input protocol/scheme machinery (data:, pipe:, http:, file:, etc.) is unreachable: the filter never asks libavformat to open the input, so libavformat's protocol handlers never see the path.

## Mechanism options and verdicts

| Option | Status | Why |
|---|---|---|
| **A. Named pipe / FIFO** | DOA on Windows | `os.mkfifo` is POSIX-only (Python docs: "Availability: Unix, not WASI"). Verified locally: `'mkfifo' in dir(os)` returns `False` on Windows. CLAUDE.md "Project Identity" line 39 explicitly classes this as a Windows offline-first desktop app. |
| **B. stdin via `pipe:0`** | DOA universally | `pipe:0` is a libavformat input protocol for the `-i` argv slot. The `ass` filter doesn't go through libavformat — it `fopen()`s the path. A filter argument cannot reference a pipe descriptor. |
| **C. `data:` URI** | DOA universally | Same root cause as B. libavformat supports `data:` as an input scheme via the `data` protocol handler; the filter doesn't delegate to libavformat. |
| **D. `subtitles=` filter** | DOA universally | The same `-h filter=subtitles` output shows identical `filename`/`f` option set. Same `fopen()` constraint. The `force_style` option modifies styling but does not provide an inline payload sink. |
| **E. `/proc/self/fd/N`** | DOA on Windows | Linux-only. Windows has no `/proc` filesystem. Even on Linux, libass `fopen()` may not accept the symlink target reliably across distributions. |

Every mechanism is either (a) not supported by the filter, (b) not available on Windows, or (c) both.

## Current ASS write-site inventory

For completeness — the audit catalogued 4 production + 1 preview write sites and 5 FFmpeg `ass=` consumer sites:

| # | Write site | Producer |
|---|---|---|
| W-1 | `backend/app/orchestration/stages/part_renderer.py:92` (`ass_part` path declaration) | path string only, no content |
| W-2 | `backend/app/orchestration/stages/part_asset_planner.py:597-623` | `srt_to_ass_karaoke` / `srt_to_ass_bounce` writes 50-500 KB text per part |
| W-3 | `backend/app/orchestration/stages/part_render_encode.py:236-269` (`_overlay_ass`) | `srt_to_ass_bounce` for output-timeline overlay, gated on `FEATURE_BASE_CLIP_FIRST=1 + FEATURE_OVERLAY_AFTER_BASE_CLIP=1` |
| W-4 | `backend/app/services/subtitles/ass_core.py:398-423` (`render_subtitle_preview`) | tempdir-scoped preview |
| (preview standalone) | `routes/render.py` indirect | tempdir-scoped |

| # | FFmpeg consumer | `_safe_filter_path` applied? |
|---|---|---|
| F-1 | `backend/app/services/render/base_clip_renderer.py:391-397` (`render_part`) | YES |
| F-2 | `backend/app/services/render/overlay_compositor.py:84-90` (`composite_overlays_on_base_clip`) | YES |
| F-3 | `backend/app/services/motion_crop/__init__.py:517-523` (motion-aware crop branch) | YES |
| F-4 | `backend/app/services/subtitles/ass_core.py:347-360` (`burn_subtitle_onto_video`) | YES |
| F-5 | `backend/app/services/subtitles/ass_core.py:425-430` (`render_subtitle_preview`) | YES |

All consumer sites use `_safe_filter_path` from `services/encoder_helpers.py:165-166`. This is the CLAUDE.md "FFmpeg Path Helpers — Mandatory Usage" Sacred Contract surface. Any inline mechanism that injected raw ASS content into the filter graph would bypass this safety helper — but the question is moot because no such mechanism exists.

## ROI verification

Per `TEMP_FILE_AUDIT_2026-06-04.md` row O-6: ASS files are 50–500 KB per part. For a 50-part render the total ASS payload on disk is **≈ 2.5–25 MB**, cleaned up by the per-job `shutil.rmtree(work_dir)` at `render_pipeline.py:220-221` or the periodic maintenance pruner.

Time cost of ASS writes: a single buffered text write of <500 KB is millisecond-class. For a 50-part render the cumulative write+open+read I/O cost is **sub-second** against per-part FFmpeg encodes of 10–60 s. The patch budget would be dominated by manual visual-review overhead per the Sprint Plan risk register, not by engineering work.

## Sacred Contract walk

- **#6 `_emit_render_event`** — `part_asset_planner.py:660-687` emits `subtitle_style_applied`; `subtitle_part_sync` at L235-258 carries `part_srt_path`. No ASS path is in any event shape that would change under an inline mechanism (the question is moot).
- **#8 qa_pipeline** — `backend/app/orchestration/qa_pipeline.py` validates the final MP4 only (file size, video stream, audio stream, duration). Does NOT inspect ASS files. Safe.
- **CLAUDE.md "FFmpeg Path Helpers — Mandatory Usage"** — all 5 consumer sites already comply. Bypass would be auto-reject per CLAUDE.md Performance Protections. Not relevant here because no viable inline mechanism exists.

## Why DEFER

1. **Technical impossibility, not policy choice.** FFmpeg's `ass`/`subtitles` filters accept only a `filename` parameter opened via `fopen()`. No alternative mechanism is exposed. This is a property of libass + the FFmpeg filter architecture — not something this codebase can re-engineer.

2. **Audit-document corroboration.** `TEMP_FILE_AUDIT_2026-06-04.md` §6 line 148 reached the same conclusion in the original Sprint 1.4 audit. The SPRINT_PLAN line 259 prediction is in direct conflict with the audit it was supposed to supersede.

3. **ROI sub-second per render** vs **CRITICAL-tier files touched** (`base_clip_renderer.py`, `overlay_compositor.py`, `motion_crop/__init__.py`). Even if a mechanism existed, the manual visual-review cost (Sprint Plan risk register line 302 — "3-5 sample videos") would dominate.

4. **Sibling pattern with Whisper defer.** Per `docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md`, the previous Sprint 6 P1 line item was also a pre-audit prediction that the empirical audit did not endorse. Two-for-two on SPRINT_PLAN §253-261 predictions failing audit validation.

## Adjacent follow-up targets (NOT part of this sprint)

Two narrower, audit-supported wins parked for future scoping:

### N.1 Content-addressable ASS cache (MEDIUM risk)
Hash the produced ASS body (UTF-8) and reuse `cache/ass/{sha256}.ass`. Saves re-writes on re-renders of identical source+style. Pure-additive next to W-2 in `part_asset_planner.py`. Effort: ~1 day. Estimated win: zero on first render; ms-class on cache-hit re-renders. Lower priority than other Sprint 6 P1 candidates.

### N.2 Lift `SUBTITLE_PER_PART_MODEL` default to match `tuned["whisper_model"]` (the H3 fix)
Per `docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md` §"What this audit does NOT defer", the per-part Whisper hard-codes `small` while source-level uses `tuned["whisper_model"]` which is `large-v3` on quality/best profiles. This is a documented quality regression. Lifting the default is pure-additive, single-line, no PIN change. **This is the highest-value follow-up identified in either P1 audit.**

**N.2 is shipped in the next commit after this audit doc.** Rationale: the user explicitly approved it as a separate Sprint 6 P1 commit alongside this DEFER decision, recognising that it delivers user-visible subtitle quality improvement that no inline-ASS mechanism could ever match.

## What this commit does

Single commit, single file: this audit doc. No code change. Pytest baseline (2363/1/0) unchanged.

The N.2 fix follows in a separate commit immediately after.

## Cross-references

- Sprint 6 P1 Inline ASS Planner brief and findings: this conversation's plan stage
- `docs/review/SPRINT_PLAN_2026-06-04.md:253-266` — Sprint 6 outline + risk register (the predicted P0 list that empirical audit revised)
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` §6 line 148 — the empirical audit's "not feasible" verdict on inline ASS
- `docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md` — sibling P1 defer doc with same pre-audit-prediction provenance and matching DEFER outcome
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` — Sprint 6 P0 HIGH success case (the optimisation that DID ship in Sprint 6)
- `backend/app/services/render/base_clip_renderer.py:391-397` — F-1 `ass=` consumer reference
- `backend/app/services/render/overlay_compositor.py:84-90` — F-2 reference
- `backend/app/services/motion_crop/__init__.py:517-523` — F-3 reference
- `backend/app/orchestration/stages/part_asset_planner.py:597-623` — W-2 write reference
- `CLAUDE.md` Project Identity §39 (Windows offline-first), Performance Protections §"FFmpeg Path Helpers — Mandatory Usage"

## What future sprints should NOT do

- Do not delete this audit doc. It records that the inline-ASS swap was investigated and rejected on FFmpeg-architecture grounds, not on developer-effort grounds.
- Do not attempt to inject ASS content via stdin, `data:` URI, named pipes, `/proc/self/fd`, or any other "clever" mechanism. The `ass`/`subtitles` filter calls `fopen()` directly. Re-prosecuting this question without modifying FFmpeg or libass itself is wasted effort.
- Do not silently retry under a future FFmpeg version without re-running `-h filter=ass` and `-h filter=subtitles`. If a future FFmpeg release adds a memory-input option, that would be the gate to re-open this scope — but the absence is structural to libass.
