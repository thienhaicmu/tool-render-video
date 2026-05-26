# Subtitle Per-Part Transcription — Architecture Change 2026-05-26

## Finding

The previous subtitle pipeline transcribed the full source video once
(TRANSCRIBING_FULL stage, Whisper on source_path) and then used
`slice_srt_by_time(..., rebase_to_zero=True)` inside `_prepare_part_assets()`
to extract and rebase subtitle timestamps for each output clip.

This introduced a timing risk: `apply_playback_speed=False` was hardcoded,
meaning platform speed adjustments (TikTok +0.08, Reels -0.06) were NOT
reflected in the sliced SRT timestamps. Additionally, the rebase arithmetic
depended on `_effective_start` being identical between `cut_video()` and
`slice_srt_by_time()` — any divergence would cause drift.

## Decision

Replace `slice_srt_by_time` in `_prepare_part_assets()` with a call to
`transcribe_with_adapter(str(raw_part), str(srt_part), ...)`.

Whisper reads the already-cut clip (`raw_part.mp4`), which starts at t=0.
Subtitle timestamps are therefore naturally zero-based — no rebase, no
slice, no drift risk.

The TRANSCRIBING_FULL stage is preserved to supply transcript context to AI
Director and S4 candidate intelligence (boundary refinement, retention proxy,
natural cut detection). It is no longer used as the source for subtitle rendering.

## Files Changed

- `backend/app/orchestration/render_pipeline.py`
  - `_prepare_part_assets()`: added `raw_part` parameter
  - Guard changed from `not full_srt_available` to `not raw_part.exists()`
  - `slice_srt_by_time` block replaced with `transcribe_with_adapter(str(raw_part), ...)`
  - Per-part model controlled via `SUBTITLE_PER_PART_MODEL` env var (default: "small")
- `backend/tests/test_phase0_hotfixes.py`
  - `test_slice_srt_apply_playback_speed_false_in_pipeline` updated to
    `test_per_part_subtitle_transcribes_raw_clip` reflecting new invariant

## Prior Reference

Prior timing analysis documented in BRUTAL_REVIEW_SUMMARY.md (C2) and
TECHNICAL_DEBT_REPORT.md. The original invariant (apply_playback_speed=False
is correct because FFmpeg `ass` filter runs before `setpts`) still holds for
the render_engine vf_chain — it is now irrelevant to subtitle generation since
timestamps come directly from Whisper on the cut clip.
