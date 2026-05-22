# OVERLAY_PIPELINE.md

**Source of truth for the overlay composite pipeline.**
**Last updated**: 2026-05-22 (post Phase 3B)

---

## Overview

The overlay pipeline is the path taken when both feature flags are ON:

```
FEATURE_BASE_CLIP_FIRST=1
FEATURE_OVERLAY_AFTER_BASE_CLIP=1
```

It separates render responsibility into two dedicated passes:
1. `render_base_clip()` — speed, crop, color, audio (no overlays)
2. `composite_overlays_on_base_clip()` — subtitle + text overlays only (no re-encoding of base)

---

## composite_overlays_on_base_clip() Contract

**File**: `backend/app/services/render_engine.py`

### Signature

```python
composite_overlays_on_base_clip(
    base_clip_path: str,
    output_path: str,
    timeline: TimelineMap,
    subtitle_ass: str | None = None,
    text_layers: list[dict] | None = None,
    title_text: str | None = None,
    video_codec: str = "h264_nvenc",
    ...
)
```

### Stream Copy Path

When ALL of `subtitle_ass`, `text_layers`, and `title_text` are absent/empty:

```
FFmpeg: -c:v copy -c:a copy
```

No re-encode. Zero quality loss. Fast.

### Encode Path

When any overlay is present:

```
FFmpeg:
  -i base_clip.mp4
  -vf <vf_chain>
  -c:v <codec>  (NVENC or libx264)
  -c:a copy      ← audio is ALWAYS stream-copied
```

vf_chain is built in this fixed order:

```
1. ass='{subtitle_ass}'              (if subtitle_ass present)
2. drawtext=title...enable='lt(t,3)'  (if title_text present)
3. drawtext=layer_1...enable=...      (for each text_layer)
   drawtext=layer_2...
   ...
4. fps={base_clip_fps}               (ALWAYS last — probed from base_clip)
```

### Audio Rule

Audio is **always** stream-copied (`-c:a copy`). No atempo. No loudnorm. No BGM.

The base_clip already has correctly speed-adjusted audio from `render_base_clip()`. Applying any audio filter again would:
- Double-speed the audio (double atempo)
- Corrupt sync

### Forbidden Filters

These filters MUST NEVER appear in the overlay vf_chain:

| Filter | Reason |
|---|---|
| `setpts=PTS/...` | Base clip already at output-timeline PTS; applying again double-speeds |
| `atempo=...` | Audio already speed-adjusted in render_base_clip(); double-atempo destroys sync |
| `scale=`, `crop=` | Spatial transforms are render_base_clip()'s responsibility |
| `eq=`, `unsharp=`, `colorbalance=` | Color/effect are render_base_clip()'s responsibility |
| `fade=` | Temporal effects are render_base_clip()'s responsibility |

---

## vf_chain Filter Order Invariant

```
ass → title drawtext → text_layer drawtext(s) → fps
```

The `fps=` filter is always last. It is probed from base_clip_path using `probe_video_metadata()`.

This order is required because:
- `ass=` must precede drawtext filters (subtitle layer is lowest in z-order)
- `fps=` must be last (rate normalization must follow all visual filters)

---

## Overlay Artifacts in Manifest

After a successful composite, these `BaseClipManifest` fields are set:

| Field | Value |
|---|---|
| `overlay_srt_path` | Path to `subtitle_output_timeline.srt` |
| `overlay_ass_path` | Path to `subtitle_output_timeline.ass` |
| `overlay_rendered_path` | Path to final composite `final_part_NNN.mp4` |
| `overlay_text_layers_applied` | `len(_part_text_layers_overlay)` (0 if no layers) |

`rendered_path` is also set to the overlay output path (it is the final output).

---

## Fallback Behavior

If `composite_overlays_on_base_clip()` raises any exception:

```python
try:
    _oc_meta = composite_overlays_on_base_clip(...)
    _overlay_composite_succeeded = True
except Exception as e:
    logger.warning("overlay_composite_failed part=%d: %s", idx, e)
    _overlay_composite_succeeded = False
finally:
    # timer always stopped here
```

When `_overlay_composite_succeeded = False`:
- `render_part_smart()` runs as fallback
- The render job still completes
- The final output uses the legacy all-in-one render
- `overlay_rendered_path` remains None

---

## Text Layer Timing in Overlay Path

All timing values in text_layers must be in **output seconds** (base_clip PTS).

### Hook Layer

```python
{
    "start_time": 0.0,
    "end_time": 1.5,    # output seconds — constant, no speed factor
    ...
}
```

Variable name in pipeline: `_part_text_layers_overlay`. Do not confuse with `_part_text_layers` (legacy).

### User Layers

```python
{
    "start_time": user_supplied_value,  # output/perceived seconds, pass through AS-IS
    "end_time": user_supplied_value,
    ...
}
```

No conversion. No TimelineMap transformation.

### Title Drawtext

```python
enable='lt(t,3)'    # t is base_clip output-timeline PTS; means first 3 output seconds
```

### Subtitle (ASS)

The `subtitle_output_timeline.ass` file is generated from `slice_srt_to_output_timeline()` which produces output-second timestamps. No further timestamp adjustment at composite time.

---

## Subtitle ASS Files — Two Distinct Files

The pipeline creates two separate ASS files per part when the overlay flag is ON:

| File | Timing | Used by |
|---|---|---|
| `part_N.ass` | Source-clip seconds | `render_part_smart()` (legacy + fallback) |
| `subtitle_output_timeline.ass` | Output seconds | `composite_overlays_on_base_clip()` |

Do NOT swap these. Using `part_N.ass` in the composite would show subtitles at wrong timestamps.

---

## Overlay Render Flow Diagram

```
base_clip.mp4  (output-timeline PTS: 0 → output_duration)
    │
    ├── subtitle_output_timeline.ass  (output-time ASS)
    ├── title_text                    (drawtext, enable='lt(t,3)' output-s)
    └── _part_text_layers_overlay     (drawtext per layer, enable=gte*lt output-s)
    │
    ▼
composite_overlays_on_base_clip()
    FFmpeg vf_chain:
      ass=subtitle_output_timeline.ass
      drawtext=title:enable='lt(t\,3)'
      drawtext=hook_overlay_1:enable='gte(t\,0)*lt(t\,1.5)'
      drawtext=user_layer_1:enable='gte(t\,2)*lt(t\,8)'
      fps=60
    audio: -c:a copy
    │
    ▼
final_part_001.mp4  (output-timeline PTS, overlays applied)
```

---

## Phase 3C Placeholder

Phase 3C (not yet implemented) will add TTS narration and BGM to the overlay path. Until Phase 3C ships:
- TTS/BGM are only on `render_part_smart()` (legacy path)
- The overlay path uses stream-copied audio from base_clip
- Do not add audio mixing to `composite_overlays_on_base_clip()`
