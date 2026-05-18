# PRODUCT STATE — QUALITY-UP15: Smart Cover Intelligence

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): smart cover intelligence`
**Status:** Shipped

---

## Summary

After each render, the tool automatically selects and exports a smart thumbnail
frame from the rendered clip. No scrubbing. No manual frame search. The clip
card thumbnail and the exported JPEG both show a purposeful frame — not just
second-one of the clip.

No new models. No face scoring. No image generation. No emotion AI.
Signal-based frame selection using existing pipeline data.

---

## Part A — Frame Scoring

`_select_cover_frame_time()` is a pure function. Zero I/O, zero new dependencies.
Five candidate offsets are scored using only existing segment signals.

### Candidate pool
Five offsets sampled across the clip: 10%, 20%, 32%, 44%, 58% of clip duration.
Floors at 0.5s, ceiling at (duration − 0.5s). Never picks the very start (cut
artifact) or near the end (outro).

### Scoring components

| Component | Effect |
|---|---|
| **Position score** | Peak at `preferred_pos`, falls off with distance (weight: 10pts max) |
| **Hook bonus** | High hook_score → earlier frames preferred (weight: up to 5pts) |
| **Stability bonus** | Middle range [22%–60%] gets +1.5pts (fewer transition artifacts) |
| **Subtitle penalty** | Frame inside first subtitle block → −6pts (avoid text-cluttered frame) |

### Platform position preference (`preferred_pos`)

| Platform | Preferred fraction | Rationale |
|---|---|---|
| TikTok | 0.15 | Early hook frame — attention-grabbing |
| YouTube Shorts | 0.30 | Balanced — good story context |
| Instagram Reels | 0.48 | Mid-clip — polished, settled moment |

### Variant nudge

| Variant | Nudge | Result |
|---|---|---|
| Aggressive | −0.10 | Even earlier — hook-forward |
| Story-first | +0.10 | Slightly later — payoff moment |
| Balanced | 0 | Platform default |

---

## Part B — Cover Export

After the render engine (`render_part_smart`) completes and the final video exists:

1. `_select_cover_frame_time()` computes the best offset
2. `extract_thumbnail_frame(final_part, offset_sec, width=640)` extracts the JPEG  
   (uses existing FFmpeg `-vcodec mjpeg` pipe — same function already used by thumbnail API)
3. JPEG bytes are written to `output_dir`:
   - Multi-variant: `{stem}_{variant_type}_cover.jpg` (e.g. `clip_aggressive_cover.jpg`)
   - Standard: `{stem}_part_{idx:03d}_cover.jpg`
4. `seg["cover_file"]` and `seg["cover_frame_offset"]` are set on the segment dict
5. Cover info flows into the ranking entry via `_r_seg.get("cover_file")`

Cover extraction is wrapped in `try/except` — any failure logs a warning and
the render continues normally. The cover is **never blocking**.

---

## Part C — Platform and Variant Coverage

Each variant gets its own cover with a different frame offset:
- Aggressive cover: earlier hook moment (platform bias + −0.10 nudge)
- Balanced cover: platform-default position
- Story-first cover: slightly later payoff moment (+0.10 nudge)

Multi-variant output directory example:
```
clip_aggressive.mp4
clip_aggressive_cover.jpg   ← early hook frame
clip_balanced.mp4
clip_balanced_cover.jpg     ← mid-clip balanced frame
clip_story_first.mp4
clip_story_first_cover.jpg  ← slightly later payoff frame
```

---

## Part D — Output Experience

### Clip card thumbnail
The clip card `<img>` now uses `?t={cover_frame_offset}` instead of the fixed
`?t=1`. This hits the existing cached thumbnail API — no new route required.
The thumbnail the creator sees in the panel matches the exported cover JPEG.

### "Cover" button
When a cover file was successfully extracted, a **Cover** button appears in the
clip card action row (alongside Preview / Download / Folder / Compare).
Clicking it opens the cover JPEG in the file system (same `openClipFile()`
mechanism as the Folder button) — one click to see and use the thumbnail.

---

## Part E — Observability

A `cover_frame_selected` event is emitted after each successful extraction:
```
event: cover_frame_selected
context: {
  part_no: 1,
  cover_file: "/output/clip_aggressive_cover.jpg",
  frame_offset: 1.234,
  cover_reason: "pos=0.12 preferred=0.05 hook=84.0 platform=tiktok variant=aggressive score=9.8",
  target_platform: "tiktok",
  variant_type: "aggressive"
}
```

The `cover_reason` string is also written to the job log for grep-based QA.

Grep: `cover_frame_selected` in job log to audit frame decisions.

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/orchestration/render_pipeline.py` | `extract_thumbnail_frame` import; `_select_cover_frame_time()` pure function; cover extraction block in `_process_one_part`; `cover_file`/`cover_frame_offset` in ranking entry |
| `backend/static/js/render-ui.js` | `coverOffset`/`coverFile` in `_rankMap`; smart `?t=` in thumbHtml; Cover button in clip card actions |
| `docs/render/PRODUCT_STATE_QUALITY_UP15.md` | This file |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| MediaPipe face detection for frame scoring | `motion_crop.py` has face detection but requires per-frame scan; adds 2–5s per clip; deferred until face quality becomes the dominant scoring signal |
| Per-frame motion blur detection | Requires extracting multiple frames and comparing; adds ffprobe overhead; the stability bonus (middle-third) is a lightweight proxy |
| Emotion / expression scoring | Explicitly excluded — "NO creepy face scoring" |
| Thumbnail generation / composition (text overlay on frame) | Separate task; frame selection is the prerequisite |
| Custom cover selection by creator | Creator can open the Cover file and use any frame they want; custom picker is a future UX feature |
| Cover for re-up mode | Re-up clips have different semantics; deferred |

---

## Manual QA Checklist

### Auto export

- [ ] After render completes, `{stem}_cover.jpg` (or `{stem}_{variant}_cover.jpg`) exists in output directory
- [ ] Cover JPEG is a valid image (≥ 10KB, opens in image viewer)
- [ ] Log shows `cover_frame_selected` event with `frame_offset`, `cover_reason`, `platform`

### Clip card thumbnail

- [ ] Clip card `<img>` uses the smart offset (inspect src URL: `?t=X.XXX` not `?t=1`)
- [ ] Thumbnail shows a non-trivial frame (not black, not cut-transition artifact)
- [ ] Hook-strong clips: thumbnail is from earlier in the clip vs. low-hook clips

### Platform behavior

- [ ] TikTok render: cover offset < 30% of clip duration (early hook)
- [ ] Instagram Reels: cover offset > 35% of clip duration (mid-clip)
- [ ] YouTube Shorts: cover offset is between TikTok and Instagram values

### Variant behavior

- [ ] Aggressive variant: earlier frame than Balanced for same source clip
- [ ] Story-first variant: later frame than Balanced for same source clip
- [ ] Each variant's clip card shows a different thumbnail

### Cover button

- [ ] "Cover" button appears in clip card action row after successful render
- [ ] Clicking Cover opens the cover JPEG in file system / viewer
- [ ] No "Cover" button when render failed or cover extraction failed silently

### Safety

- [ ] Cover extraction failure (e.g., very short clip): warning logged, render succeeds normally
- [ ] Zero regression on: cancel, resume, retry, queue, render speed
- [ ] `cover_frame_selected` event NOT emitted when extraction failed
- [ ] Existing thumbnail API (`?t=0.5`) still works independently of UP15
