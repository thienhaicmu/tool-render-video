# TIMELINE_SEMANTICS.md

**Source of truth for timing contract across the render pipeline.**
**Last updated**: 2026-05-22 (post Phase 3B)

---

## Two Timelines

Every timestamp in the pipeline belongs to exactly one of two timelines.

### Source Timeline

Timestamps in seconds from the start of `source.mp4`.

```
source.mp4:  0s ─────────────────────────────── 3600s
                  ↑ seg["start"]    ↑ seg["end"]
                  │
                  ↑ _effective_start = seg["start"] + silence_trim + visual_trim
```

Used by:
- Scene detection boundaries
- SRT slicing (`slice_srt_by_time()`)
- Video cut boundaries (`cut_video()`)
- ASS file timestamps (legacy path)

### Output Timeline

Timestamps in seconds from the start of the rendered output clip.

```
output_part_N.mp4:  0s ──────────── ~28s
                                      ↑
                    source_duration / effective_speed
```

Used by:
- `base_clip.mp4` PTS (overlay path)
- All overlay timing expressions in `composite_overlays_on_base_clip()`
- Hook layer `end_time = 1.5` in overlay path
- Title `enable='lt(t,3)'` in overlay path
- User text_layer start_time/end_time

---

## Conversion Formula

```
output_t = (source_t - source_start) / effective_speed

Where:
  effective_speed = payload.playback_speed + platform_delta
  effective_speed clamped to [0.5, 1.5]
  platform_delta  = _PLATFORM_PROFILES[platform]["speed_delta"]
    TikTok:          +0.08
    YouTube Shorts:   0.0
    Instagram Reels: +0.05
```

Implemented by `TimelineMap` in `backend/app/domain/timeline.py`.

---

## Legacy Path: ass-before-setpts Contract

In `render_part_smart()`, the FFmpeg vf_chain order is:

```
ass='{source_time_ass}'   ← burns subtitle at source-clock PTS
...
setpts=PTS/{speed}        ← re-clocks ALL frames to output timeline
fps={target_fps}          ← always last
```

Because `ass=` runs BEFORE `setpts`:
- ASS timestamps in source-clip seconds are correct — FFmpeg burns them onto the right frames
- `setpts` then re-clocks those frames so they appear at the right output time
- A subtitle at source t=10.0s appears at output t=10.0/1.15 ≈ 8.7s — correctly synced with sped-up audio

**This order MUST NOT change.** Any reordering breaks subtitle sync.

Known limitation: subtitle **display duration** is compressed proportionally to speed. A 3.0s subtitle block is shown for 3.0/1.15 ≈ 2.6s at 1.15x. This is a legibility concern, not a synchronization error.

---

## Overlay Path: Output-Timeline PTS Contract

In the overlay path, `base_clip.mp4` is produced by `render_base_clip()` which applies `setpts=PTS/{speed}` internally. When `composite_overlays_on_base_clip()` receives `base_clip.mp4`:

- Frame PTS is already in output-timeline seconds (no `setpts` applied again)
- All timing expressions must be in output seconds
- `enable='lt(t,3)'` means "first 3 output seconds" — same expression as legacy, correct on both paths

**Do NOT apply setpts inside composite_overlays_on_base_clip().** The base clip is already at output speed.

---

## Per-Layer Timing Rules

### Subtitle (ASS)

| Path | ASS file | Timestamps in |
|---|---|---|
| Legacy | `part_N.ass` | Source-clip seconds (re-clocked by setpts) |
| Overlay | `subtitle_output_timeline.ass` | Output seconds (base_clip PTS) |

### Hook Text Layer

| Path | `end_time` formula | Meaning |
|---|---|---|
| Legacy `_part_text_layers` | `round(min(2.5, 1.5 × speed), 3)` | Source-clip seconds (will be re-clocked by setpts) |
| Overlay `_part_text_layers_overlay` | `1.5` (constant) | Output seconds on base_clip PTS |

At speed=1.0, both equal 1.5 — they diverge at all other speeds.

**NEVER multiply the overlay hook `end_time` by speed.** The base_clip PTS is already at output speed.

### Title Drawtext

```python
enable='lt(t,3)'    # first 3 seconds
```

- Legacy: `t` is source-clip PTS (before setpts); filter is inside vf_chain before setpts — `lt(t,3)` means first 3 source seconds, which appear at output t=3/speed ≈ 2.6s at 1.15x
- Overlay: `t` is base_clip PTS (output-timeline); `lt(t,3)` means first 3 output seconds

The expression string is identical in both paths. No conversion needed. The semantic is slightly different (source-s vs output-s) but both produce "show title during intro".

### User Text Layers

User-authored `start_time` and `end_time` represent **creator intent = perceived/output time**.

```
overlay path: pass through AS-IS
legacy path:  pass through AS-IS
```

No conversion. No TimelineMap transformation. The creator expects their times to map to what the viewer sees.

### CTA / Market Hook Text

These remain on the subtitle path (ASS). They are NOT migrated to the overlay path. Do not touch their timing.

---

## TimelineMap Role

`TimelineMap` is the authoritative per-clip timing record. It:
1. Stores the source boundaries and effective speed for the clip
2. Provides `source_to_output()` and `output_to_source()` conversion methods
3. Is embedded in `BaseClipManifest` and written to `manifest.json`
4. Is consumed by `composite_overlays_on_base_clip()` (passed as `timeline` param)

The manifest write is the canonical timing record. Do NOT recompute speed from raw payload fields after the manifest is created.

---

## Speed Clamp Consistency

| Location | Clamp | Notes |
|---|---|---|
| `render_pipeline._get_effective_playback_speed()` | [0.5, 1.5] | Entry point — pipeline speed |
| `render_engine._sanitize_speed()` | [0.5, 1.5] | FFmpeg entry point |
| `TimelineMap.__post_init__()` | [0.5, 1.5] | Domain model |
| `audio_mix_service.py` | [0.5, 2.0] | FFmpeg atempo filter range — separate concern |

The `[0.5, 2.0]` in `audio_mix_service.py` is NOT a pipeline speed range — it is FFmpeg's hardware atempo constraint. Do not change it to [0.5, 1.5].

---

## Things That MUST NEVER Happen

1. **setpts inside `composite_overlays_on_base_clip()`** — base_clip already has output-timeline PTS; applying setpts again would double-speed the output
2. **atempo inside `composite_overlays_on_base_clip()`** — audio was already speed-adjusted in `render_base_clip()`; double-atempo destroys audio sync
3. **Overlay hook `end_time` multiplied by speed** — 1.5 output-seconds is the constant; no speed factor on base_clip PTS
4. **TimelineMap conversion for user text_layers** — user times are already output seconds; conversion would create wrong timings
5. **Reordering `ass` and `setpts` in legacy vf_chain** — breaks subtitle sync for all renders
6. **Deriving `effective_speed` from payload after TimelineMap is created** — use `timeline.effective_speed`

---

## Diagram: Timeline Through the Render Passes

```
source.mp4 (source timeline, 0→source_duration)
    │
    ├── [Legacy path]
    │   slice_srt_by_time()           → SRT in source-clip seconds
    │   srt_to_ass()                  → ASS in source-clip seconds
    │   cut_video(source_start..end)  → raw_cut.mp4 (source timeline)
    │   render_part_smart()
    │       ass=part.ass              → subtitles burned at source PTS
    │       setpts=PTS/speed          → ALL frames re-clocked to output
    │       fps=target_fps
    │   → final_part.mp4 (output timeline PTS)
    │
    └── [Overlay path]
        slice_srt_to_output_timeline() → SRT in output seconds
        srt_to_ass()                   → ASS in output seconds
        cut_video(source_start..end)   → raw_cut.mp4 (source timeline)
        render_base_clip()
            setpts=PTS/speed           → output timeline baked into PTS
        → base_clip.mp4 (output timeline PTS)
        composite_overlays_on_base_clip(base_clip.mp4)
            ass=subtitle_output_timeline.ass   → overlay at output PTS ✓
            drawtext=title, enable=lt(t,3)     → output PTS ✓
            drawtext=hook, end_time=1.5        → output PTS ✓
            fps=target_fps
            -c:a copy                          → audio unchanged
        → final_part.mp4 (output timeline PTS)
```
