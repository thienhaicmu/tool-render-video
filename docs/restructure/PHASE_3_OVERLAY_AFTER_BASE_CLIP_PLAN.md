# Phase 3 — Overlay After Base Clip
## Implementation Plan

**Date**: 2026-05-22  
**Branch**: restructure/output-timeline-architecture  
**Status**: PLANNING — no code implemented

---

## 1. Current Phase 2 Behavior

```
FEATURE_BASE_CLIP_FIRST=0:
  render_part_smart() → final_clip.mp4
  (sole output path; base clip never generated)

FEATURE_BASE_CLIP_FIRST=1:
  render_base_clip() → base_clip.mp4   [parallel artifact only]
  render_part_smart() → final_clip.mp4 [sole final output]
  base_clip.mp4 is NOT used as input to any render step
```

`render_part_smart()` continues to produce the user-visible final output in Phase 2.  
`base_clip.mp4` is written to `work_dir/part_N/base_clip.mp4` and recorded in
`BaseClipManifest.base_clip_*` fields for future use.

---

## 2. Target Phase 3 Behavior

```
FEATURE_BASE_CLIP_FIRST=1
FEATURE_OVERLAY_AFTER_BASE_CLIP=0:  (Phase 2 preserved)
  render_base_clip() → base_clip.mp4
  render_part_smart() → final_clip.mp4

FEATURE_BASE_CLIP_FIRST=1
FEATURE_OVERLAY_AFTER_BASE_CLIP=1:  (Phase 3 active)
  render_base_clip() → base_clip.mp4
  composite_overlays_on_base_clip(base_clip.mp4) → final_clip.mp4
  render_part_smart() → fallback only if overlay composite fails
```

In Phase 3A (first sub-phase), `composite_overlays_on_base_clip()` applies
subtitle overlay only — no text_layers, no TTS, no BGM — so the scope is bounded.
Phase 3B adds text layers. Phase 3C adds TTS/BGM.

---

## 3. Feature Flag Strategy

### Flags

```python
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
```

Both default **OFF**.

### Dependency rule

`FEATURE_OVERLAY_AFTER_BASE_CLIP=1` is only meaningful when
`FEATURE_BASE_CLIP_FIRST=1`. If the overlay flag is set without the base clip
flag, the pipeline logs a warning and falls back to `render_part_smart()`.

### Decision matrix

| BASE_CLIP_FIRST | OVERLAY_AFTER_BASE_CLIP | Final output produced by |
|---|---|---|
| 0 | 0 | `render_part_smart()` |
| 0 | 1 | `render_part_smart()` (overlay flag ignored — no base clip) |
| 1 | 0 | `render_part_smart()` (base clip is parallel artifact only) |
| 1 | 1 | `composite_overlays_on_base_clip()`, fallback to `render_part_smart()` |

### No frontend/API/schema changes

Both flags are read from environment variables. No `RenderRequest` schema change.
No frontend change. No WebSocket payload change. No DB schema change.

---

## 4. Overlay Responsibilities Audit

All overlay-like responsibilities identified in the current pipeline,
classified by Phase 3 disposition.

### 4.1 In-render overlays (applied INSIDE FFmpeg encode by render_part_smart)

| Overlay | Current position in vf_chain | Phase 3 disposition |
|---|---|---|
| `ass=` subtitle burn-in | Before `setpts` | **A — move to overlay composite in 3A** |
| `drawtext=` title overlay | Before `setpts` | **B — stay legacy until 3B** |
| `text_layers` (user, hook, CTA hint) | Before `setpts` | **B — stay legacy until 3B** |
| `setpts=PTS/speed` | Speed step | **D — never moves; already applied in base_clip** |
| `atempo=speed` (audio) | Audio filter | **D — never moves; already applied in base_clip** |
| scale/crop/reframe | Video geometry | **D — never moves; already applied in base_clip** |
| color grading / denoise / effect | Visual finish | **D — never moves; already applied in base_clip** |
| fade-in transition | Visual finish | **D — never moves; already applied in base_clip** |

### 4.2 Post-render assembly (applied AFTER render_part_smart returns)

| Assembly step | Current position | Phase 3 disposition |
|---|---|---|
| TTS narration audio mix (`mix_narration_audio`) | Post-render, audio-only rewrite | **C — Phase 3C; remains separate audio pass** |
| Remotion hook intro prepend | Post-render, ffmpeg concat | **C — stays post-render assembly; no timeline conflict** |
| Asset intro prepend | Post-render, ffmpeg concat | **C — stays post-render assembly** |
| Asset outro append | Post-render, ffmpeg concat | **C — stays post-render assembly** |
| Asset logo watermark | Post-render, ffmpeg overlay | **C — stays post-render assembly** |

### 4.3 SRT/ASS preparation (pre-encode, pre-render)

| Step | Description | Phase 3 disposition |
|---|---|---|
| `slice_srt_by_time(apply_playback_speed=False)` | Produces source-clip-time SRT for legacy burn-in | Legacy path unchanged |
| `srt_to_ass_bounce()` / `srt_to_ass_karaoke()` | Converts source-clip SRT → ASS | Legacy path unchanged |
| CTA block appended to SRT | Already in output-timeline seconds | Needs re-examination for Phase 3A |

---

## 5. What Moves in Phase 3

### Phase 3A (first implementation sub-phase): Subtitle overlay only

**Subtitle overlay composite:**
- Input: `base_clip.mp4` (already speed-adjusted)
- Input: output-timeline ASS subtitle (`subtitle_output_timeline.ass`)
- Output: `final_clip.mp4`

The overlay composite uses `libx264` with `-c:v` re-encode for ASS burn-in.
No setpts. No atempo. No crop. No color pass.

### Phase 3B: Text layer overlay

**Text layer composite (after 3A is stable):**
- Input: `base_clip.mp4` + output-timeline text layer definitions
- The text layer `start_time` / `end_time` fields must be expressed in
  output-timeline seconds (not source-clip seconds as they are currently)
- Requires explicit conversion: `output_t = source_clip_t / speed`
- Hook overlay end_time: currently `1.5 * speed` source seconds → becomes `1.5` output seconds

### Phase 3C: TTS/BGM composite (later)

**Audio pass on composite output:**
- Input: `final_clip.mp4` from Phase 3A or 3B
- Input: TTS narration audio
- Uses `mix_narration_audio()` with `playback_speed=1.0` (base_clip audio is
  already speed-adjusted; narration must match output duration)
- No atempo re-application to the video
- BGM mix follows the same pattern if applicable

---

## 6. What Does NOT Move in Phase 3

The following must NOT be applied during overlay composite:

1. `setpts=PTS/speed` — already applied in `render_base_clip()`. Re-applying
   would further compress timestamps by `1/speed` again.
2. `atempo=speed` — already applied to the audio track in `render_base_clip()`.
   Re-applying would produce audio at `speed^2` rate.
3. Scale/crop/reframe — already applied. Re-applying would double-scale.
4. Color grading / denoise / effects — already baked into base_clip pixels.
5. Remotion intro / asset intro / asset outro / logo — these are post-render
   concatenation steps that remain unchanged in Phase 3.

The overlay composite function must contain **no crop filter, no setpts filter,
no atempo filter, and no color/effect filter**. It applies only:
- `ass=` subtitle burn-in (output-timeline timestamps)
- `drawtext=` text overlays (Phase 3B, output-timeline timestamps)
- Audio pass-through (or narration mix in Phase 3C)

---

## 7. Subtitle Output Timeline Strategy

### The timing invariant

**Legacy path** (`render_part_smart`):
```
ASS timestamps = source-clip seconds
setpts = PTS / speed
→ subtitle appears at output t = source_clip_t / speed  ✓
```

**Phase 3 overlay path** (`composite_overlays_on_base_clip`):
```
base_clip.mp4 already has speed applied
Frame at output t=8.7s was at source clip t=10.0s (for speed=1.15)
ASS timestamps must be in OUTPUT-timeline seconds
→ subtitle for source clip t=10s must have ASS t = 10.0 / 1.15 = 8.7s
```

### How to produce output-timeline ASS

The pipeline already has the mechanism: `slice_srt_by_time(..., apply_playback_speed=True)`.
This is currently unused because the legacy path sets `apply_playback_speed=False`.

For Phase 3, a new call with `apply_playback_speed=True` produces an output-timeline SRT:

```python
# Produces output-timeline SRT (timestamps in output seconds)
slice_srt_by_time(
    str(full_srt),
    str(srt_output_timeline_path),   # new file: subtitle_output_timeline.srt
    _effective_start,
    seg["end"],
    rebase_to_zero=True,
    playback_speed=_part_timeline.effective_speed,
    apply_playback_speed=True,       # divide by speed → output timeline
)
```

This SRT is then converted to ASS using the same `srt_to_ass_bounce()` /
`srt_to_ass_karaoke()` functions, producing `subtitle_output_timeline.ass`.

### Artifact naming

Output-timeline artifacts use explicit names to prevent confusion:
```
work_dir/part_N/subtitle_output_timeline.srt   (output-timeline SRT)
work_dir/part_N/subtitle_output_timeline.ass   (output-timeline ASS)
```

The legacy artifacts are unchanged:
```
work_dir/{slug}_part_NNN.srt   (source-clip-time SRT, legacy)
work_dir/{slug}_part_NNN.ass   (source-clip-time ASS, legacy)
```

### Option evaluation

Three options were considered:

**Option A**: New `convert_srt_to_output_timeline()` wrapper around `slice_srt_by_time`.
- Pros: explicit, named well, easy to test.
- Cons: thin wrapper — adds an extra function for minimal gain.

**Option B**: Call `slice_srt_by_time` directly with `apply_playback_speed=True`.
- Pros: reuses existing tested function, no new abstraction.
- Cons: the `apply_playback_speed` flag is not self-documenting at the call site.

**Option C**: New `slice_srt_to_output_timeline()` that takes a `TimelineMap`.
- Pros: self-documenting, timeline-aware, future-safe.
- Cons: slightly more code, but directly expresses the architecture.

**Recommendation**: Option C — `slice_srt_to_output_timeline(srt_path, output_path, timeline)`.
Uses `timeline.effective_speed` internally. Makes it impossible to accidentally
pass the wrong speed. Easy to test with TimelineMap directly.

### No mutation of legacy SRT

The full-video SRT (`full_srt`) must not be modified. The output-timeline SRT
is a new artifact written to a new path. The legacy `srt_part` remains unchanged.

### CTA block timing

The `_append_cta_block_to_srt()` function appends CTA text with timestamps
expressed as clip-relative seconds (already output-timeline style because CTA
timing is defined in terms of perceived output duration). For Phase 3A,
CTA blocks should be re-examined after the base output-timeline SRT is created.
The safest initial approach: do not append CTA to the output-timeline SRT in
Phase 3A, and re-evaluate CTA timing in Phase 3B.

---

## 8. Text Layer Timing Strategy

### Current timing model

Text layer `start_time` / `end_time` fields in `text_overlay.py` are expressed
in **source-clip seconds** (pre-setpts). The `drawtext` filter's
`enable='gte(t,start_t)*lt(t,end_t)'` uses frame PTS before setpts transforms it.

Evidence: the hook overlay explicitly multiplies by speed:
```python
# end_time is pre-setpts, so multiply by speed so the overlay
# shows for ~1.5 s of perceived output time at any playback rate.
_hook_end_t = round(min(2.5, 1.5 * _hook_spd), 3)
```

User-supplied text layers have `start_time`/`end_time` set by the creator
without explicit speed awareness. Their intended semantics are ambiguous —
they may intend "seconds into the perceived output" or "seconds into the
source clip."

### Migration complexity

Text layer timing migration is more complex than subtitle migration because:
1. Hook overlay timing is explicitly speed-compensated (multiply by speed for pre-setpts).
2. User-supplied layer timing is assumed to be clip-relative but semantics are unclear.
3. The drawtext filter `enable` expression uses PTS directly.

For overlay on base_clip.mp4 (output timeline), the correct text layer timing is:
```
output_t = source_clip_t / speed       (for layers defined in source-clip time)
output_t = source_clip_t               (for layers defined in output/perceived time)
```

The hook end_time would become:
```python
# Legacy: 1.5 * speed (source-clip seconds, to show 1.5s of perceived output)
# Phase 3B: 1.5       (output seconds directly)
```

### Recommendation: staged rollout

- **Phase 3A**: No text layers in overlay composite. Subtitles only.
  `composite_overlays_on_base_clip()` accepts `text_layers=None` in Phase 3A.
- **Phase 3B**: Add text layer support. Introduce explicit output-timeline
  timing semantics for layer definitions. Update hook overlay construction
  to use output-timeline seconds (remove the `* speed` factor).
- **Phase 3B manifest addition**: Add `base_clip_overlay_text_layers` to
  `BaseClipManifest` to record which layers were applied with what timing.

---

## 9. Audio / TTS / BGM Strategy

### Current state

The audio in `base_clip.mp4` has already had:
- `atempo=speed` applied (speed-adjusted audio)
- `loudnorm` applied if enabled
- BGM mix applied if enabled (reup_bgm path)

TTS narration is mixed AFTER `render_part_smart()` returns, via `mix_narration_audio()`.
This call uses `playback_speed=float(_render_speed)` to apply atempo to the narration.

### Phase 3A audio rule

**No audio changes in Phase 3A.**

`composite_overlays_on_base_clip()` in Phase 3A must:
- Pass through the audio from `base_clip.mp4` unchanged (`-c:a copy`)
- Not apply atempo
- Not apply loudnorm
- Not mix narration

### Phase 3C: TTS narration on overlay composite

When the overlay composite is the final output (not render_part_smart), TTS narration
must be mixed into the overlay composite output, not into render_part_smart output.

The TTS narration audio file (`narration_path` in manifest) is already at natural
speaking speed. The video in `base_clip.mp4` is already at playback_speed.

For Phase 3C, `mix_narration_audio()` should be called with:
```python
mix_narration_audio(
    video_path=str(overlay_output),
    narration_audio_path=str(narration_path),
    mix_mode=payload.voice_mix_mode,
    output_path=str(final_with_narration),
    playback_speed=_part_timeline.effective_speed,  # atempo applied to narration only
)
```

The narration atempo is correct here: the video is already speed-adjusted, and the
narration must be compressed to match the shorter output duration.

**Risk**: If `mix_narration_audio()` is applied BOTH in the overlay composite path
AND in the post-render TTS path (legacy), narration is mixed twice. Phase 3C must
gate the TTS post-render step explicitly to avoid this.

### BGM / SFX

BGM is mixed during `render_base_clip()` when `reup_bgm_enable=True`. It is
already baked into the base_clip audio. No BGM re-mix in overlay composite.

---

## 10. Proposed New Functions / Modules

### 10.1 `slice_srt_to_output_timeline()` in `subtitle_engine.py`

```python
def slice_srt_to_output_timeline(
    source_srt_path: str,
    output_srt_path: str,
    source_start: float,
    source_end: float,
    timeline: TimelineMap,
) -> dict:
    """Slice and convert SRT to output-timeline timestamps.

    Output-timeline timestamps account for playback speed so that subtitles
    can be burned directly onto a base_clip.mp4 (already speed-adjusted).

    Equivalent to slice_srt_by_time(..., apply_playback_speed=True) but
    takes a TimelineMap so the speed is always authoritative.
    """
```

This function is the only new function required for Phase 3A subtitle support.
It wraps `slice_srt_by_time` with `apply_playback_speed=True` and
`playback_speed=timeline.effective_speed`.

### 10.2 `composite_overlays_on_base_clip()` in `render_engine.py`

```python
def composite_overlays_on_base_clip(
    base_clip_path: str,
    output_path: str,
    timeline: TimelineMap,
    subtitle_ass: str | None = None,      # output-timeline ASS (Phase 3A)
    text_layers: list[dict] | None = None, # output-timeline text layers (Phase 3B)
    title_text: str | None = None,         # title overlay (Phase 3B)
    video_codec: str = "h264",
    video_crf: int = 18,
    video_preset: str = "slow",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    ffmpeg_threads: int | None = None,
) -> dict:
    """Composite subtitle/text overlays onto a pre-encoded base clip.

    The base clip has already been speed-adjusted, cropped, and color-graded.
    This function applies only overlay filters:
    - ass= subtitle burn-in (output-timeline ASS, Phase 3A)
    - drawtext= text layers (Phase 3B)

    MUST NOT apply: setpts, atempo, scale, crop, color, denoise, effect.
    Audio is passed through unchanged (-c:a copy) in Phase 3A.
    
    Returns a metadata dict: path, duration, fps, width, height, has_audio.
    """
```

**vf_chain for Phase 3A** (subtitle only):
```
ass='{output_timeline_ass}'
fps={target_fps}   ← last filter; normalizes CFR output
```

No setpts. No crop. No scale. No color. The `fps` filter ensures CFR output
for platform compatibility. The codec is re-encode (not stream copy) because
ASS burn-in requires frame-level writes.

**Audio** (Phase 3A): `-c:a copy` — pass through the base_clip audio unchanged.

**NVENC**: NVENC semaphore must be acquired/released as in `render_part()`.

### 10.3 Feature flag in `render_pipeline.py`

```python
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
```

Added adjacent to `_FEATURE_BASE_CLIP_FIRST`.

### 10.4 No new modules

No new Python module files are required for Phase 3A. The new functions live in
existing modules (`subtitle_engine.py`, `render_engine.py`) where their
sibling functions already reside.

---

## 11. Manifest Evolution Plan

### Phase 3A additions to `BaseClipManifest`

New Optional fields to track the output-timeline subtitle artifact:

```python
# Output-timeline subtitle artifacts (Phase 3A)
overlay_srt_path: Optional[str] = field(default=None)   # output-timeline SRT
overlay_ass_path: Optional[str] = field(default=None)   # output-timeline ASS
overlay_rendered_path: Optional[str] = field(default=None)  # overlay composite output
```

Backward-compat: all use `field(default=None)` and `from_dict()` uses `.get()`.

### Phase 3B additions (planned)

```python
overlay_text_layers_applied: Optional[int] = field(default=None)  # count of layers applied
```

### Naming

No `phase3_` or `p3_` prefixes. Names describe purpose: `overlay_srt_path`,
`overlay_ass_path`, `overlay_rendered_path`.

---

## 12. Final Output Compatibility Strategy

### Output file

When `FEATURE_OVERLAY_AFTER_BASE_CLIP=1`, the overlay composite output is
written to:
```
work_dir/part_N/overlay_final.mp4
```

This file is then moved/renamed to `final_part` path that the rest of the
pipeline (narration mix, creator asset injection, QA, thumbnail) expects.

The existing post-render steps (intro/outro/logo prepend/append) operate on
`final_part` regardless of whether it came from `render_part_smart()` or
`composite_overlays_on_base_clip()`. No changes needed to those steps.

### Codec compatibility

The overlay composite uses the same codec as the base clip (h264/h264_nvenc
with `-c:v` re-encode for subtitle burn-in). Audio is `-c:a copy` in Phase 3A.
This preserves the codec profile expected by downstream platform upload.

### Frame rate

`fps={target_fps}` is the last vf filter in the overlay composite, same as in
`render_part()`. This guarantees CFR output.

### Duration tolerance

Phase 3 output duration must match `base_clip.mp4` duration within ±1%.
The ±20% legacy QA tolerance is inappropriate for overlay composite validation.
See §14 QA strategy.

---

## 13. Fallback Strategy

Fallback activates when `composite_overlays_on_base_clip()` raises any exception.

```python
if _FEATURE_BASE_CLIP_FIRST and _FEATURE_OVERLAY_AFTER_BASE_CLIP:
    try:
        _ov_meta = composite_overlays_on_base_clip(
            base_clip_path=str(_base_clip_out),
            output_path=str(final_part),
            timeline=_part_timeline,
            subtitle_ass=str(overlay_ass_part) if overlay_subtitle_enabled else None,
            ...
        )
        # Update manifest with overlay_rendered_path
        _part_manifest.overlay_rendered_path = str(final_part)
        write_manifest(work_dir, _part_manifest)
        logger.info("overlay_composite_rendered part=%d", idx)
    except Exception as _ov_err:
        logger.warning(
            "overlay_composite_failed part=%d err=%s — falling back to render_part_smart",
            idx, _ov_err,
        )
        # Fall through to render_part_smart() below

# render_part_smart() runs as fallback if overlay composite failed,
# or unconditionally when FEATURE_OVERLAY_AFTER_BASE_CLIP=0.
if not _overlay_composite_succeeded:
    try:
        render_part_smart(...)
    finally:
        ...
```

The fallback is explicit and logged. The render job always completes.
`render_part_smart()` is the authoritative fallback in all cases.

---

## 14. QA Strategy

### Current QA (legacy)

`_validate_render_output()` checks:
- File exists and size > 0
- Duration within ±20% of expected

### Required QA additions for overlay composite output

1. **Duration match vs base_clip**: overlay output duration must be within ±1% of
   `base_clip.mp4` duration. If they diverge by more than 1%, the overlay composite
   has introduced timing corruption.

2. **Audio stream presence**: overlay output must have an audio stream. `-c:a copy`
   from base_clip guarantees this, but the check must verify it.

3. **Video stream codec match**: overlay output codec must match the requested codec
   (h264 / h264_nvenc). No unintended downgrade to flv or mpeg4.

4. **FPS match**: overlay output FPS must equal target_fps. The `fps=` filter
   guarantees this; the check verifies it.

5. **Resolution match**: overlay output width/height must equal base_clip
   width/height. No accidental scaling in the overlay composite.

6. **No black frame on first output frame**: same check as legacy `detect_bad_first_frame()`.

Implementation: a new `_validate_overlay_composite_output()` function, or
extend `_validate_render_output()` with an optional `reference_path` parameter
that enables comparison against `base_clip.mp4`.

---

## 15. Test Strategy

### Phase 3A test file: `backend/tests/test_composite_overlays.py`

Required tests:

1. `composite_overlays_on_base_clip()` FFmpeg command contains `ass=` filter.
2. `composite_overlays_on_base_clip()` FFmpeg command does NOT contain `setpts=`.
3. `composite_overlays_on_base_clip()` FFmpeg command does NOT contain `atempo=`.
4. `composite_overlays_on_base_clip()` FFmpeg command does NOT contain `scale=` or `crop=`.
5. `composite_overlays_on_base_clip()` audio flag is `-c:a copy`.
6. `composite_overlays_on_base_clip()` `fps=` is the last video filter.
7. `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`: `composite_overlays_on_base_clip()` not called.
8. `FEATURE_OVERLAY_AFTER_BASE_CLIP=1` + success: `render_part_smart()` not called.
9. `FEATURE_OVERLAY_AFTER_BASE_CLIP=1` + failure: `render_part_smart()` called as fallback.
10. Return dict contains `path`, `duration`, `fps`, `width`, `height`, `has_audio`.

### Phase 3A subtitle test file: `backend/tests/test_slice_srt_to_output_timeline.py`

Required tests:

1. `slice_srt_to_output_timeline()` timestamps equal source-clip timestamps divided by speed.
2. `slice_srt_to_output_timeline()` is rebased to zero (relative to clip start).
3. Round-trip: source subtitle at t=10s with speed=1.15 → output t=8.7s.
4. `TimelineMap.effective_speed` is used (not payload speed directly).
5. Output SRT is valid parseable SRT format.
6. Empty SRT produces empty output SRT without raising.

---

## 16. Risk Checklist

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Double setpts (speed applied twice) | High without care | Video duration halved | `composite_overlays_on_base_clip()` has no setpts; review asserted in tests |
| Double atempo (audio compressed twice) | High without care | Audio pitch/speed wrong | Phase 3A uses `-c:a copy`; no atempo in overlay composite |
| Double crop/scale | Medium | Resolution mismatch | Function has no crop/scale filters; test asserts crop= absent |
| Subtitle timing wrong on base_clip | Medium | Subtitles not synced | `slice_srt_to_output_timeline()` divides by speed; covered by tests |
| Output duration mismatch vs base_clip | Medium | QA failure / platform rejection | ±1% tolerance check; `fps=` last filter |
| Fallback not triggering on failure | Low | Silent wrong output | Explicit try/except in pipeline; test verifies fallback |
| Legacy render unchanged by flag=0 | Low risk if implemented correctly | Regression for all users | Feature flags default OFF; full suite run gates merge |
| Text layer timing wrong in 3B | Medium | Hook text too early/late | Phase 3A has no text_layers; timing migration explicit in 3B |
| TTS narration double-mixed in 3C | High risk if not gated | Distorted audio | Explicit flag gate for TTS mix path; not implemented until 3C |
| ASS file reuse (output-timeline vs legacy) | High | Wrong subtitle sync | Separate file paths: `overlay_ass_path` vs `ass_path` in manifest |

---

## 17. Exact Implementation Order

### Phase 3A — Subtitle overlay composite only

**Step 1**: Add `slice_srt_to_output_timeline()` to `backend/app/services/subtitle_engine.py`.
  - Signature: `(source_srt_path, output_srt_path, source_start, source_end, timeline) -> dict`
  - Wraps `slice_srt_by_time(..., apply_playback_speed=True, playback_speed=timeline.effective_speed)`
  - Add tests: `test_slice_srt_to_output_timeline.py`

**Step 2**: Add 3 manifest fields to `BaseClipManifest`:
  - `overlay_srt_path`, `overlay_ass_path`, `overlay_rendered_path`
  - Update `to_dict()` / `from_dict()` with None defaults
  - Add backward-compat tests to `test_base_clip_manifest.py`

**Step 3**: Add `composite_overlays_on_base_clip()` to `backend/app/services/render_engine.py`.
  - Signature as documented in §10.2
  - Phase 3A: subtitle only; `text_layers=None`, `-c:a copy`
  - NVENC semaphore handling
  - Returns metadata dict
  - Add tests: `test_composite_overlays.py`

**Step 4**: Add `_FEATURE_OVERLAY_AFTER_BASE_CLIP` constant to `render_pipeline.py`.
  - Default OFF: `os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"`
  - Add feature flag validation: warn if overlay=1 without base_clip=1

**Step 5**: Insert overlay composite block into per-part pipeline in `render_pipeline.py`.
  - Placement: AFTER base clip block, BEFORE render_part_smart() try block
  - Generates `subtitle_output_timeline.srt` and `subtitle_output_timeline.ass`
  - Calls `composite_overlays_on_base_clip()`
  - On success: sets `_overlay_composite_succeeded = True`; writes manifest
  - On failure: logs warning; `_overlay_composite_succeeded = False`
  - `render_part_smart()` runs only if `not _overlay_composite_succeeded`

**Step 6**: Run targeted tests. Run full suite. Verify 0 new failures.

**Step 7**: Commit and push. Tag as Phase 3A complete.

### Phase 3B — Text layer overlay composite

After Phase 3A is stable:

**Step 8**: Add output-timeline timing semantics to text layer definitions.
  - Add a flag or transform function for Phase 3B layer timing.
  - Update hook overlay construction: remove `* speed` factor when in overlay mode.
  - Add text_layers support to `composite_overlays_on_base_clip()`.

**Step 9**: Add manifest field: `overlay_text_layers_applied`.

**Step 10**: Run tests. Commit Phase 3B.

### Phase 3C — TTS/BGM audio composite

After Phase 3B is stable:

**Step 11**: Gate TTS narration mix: only runs on overlay composite output
  when `FEATURE_OVERLAY_AFTER_BASE_CLIP=1`. Use `playback_speed=1.0` for
  narration atempo (base_clip audio already speed-adjusted).

**Step 12**: Verify no double atempo. Run tests. Commit Phase 3C.

---

## 18. What Must NOT Change

The following must remain byte-for-byte identical regardless of Phase 3 flags:

- `render_part_smart()` function body — no modification
- `render_base_clip()` function body — no modification (already correct)
- `slice_srt_by_time()` function — no modification
- `mix_narration_audio()` function — no modification
- All `_maybe_*` creator asset functions — no modification
- `backend/app/models/schemas.py` — no API schema change
- `backend/app/routes/` — no route change
- `backend/app/services/db.py` — no DB schema change
- `backend/static*/` — no frontend change
- WebSocket payload fields — no change
- Job status / stage names — no change

When `FEATURE_BASE_CLIP_FIRST=0` (the default), the pipeline is bit-for-bit
identical to the pre-Phase-2 pipeline.

---

## 19. Phase 3A / 3B / 3C Split Recommendation

**Phase 3A (mandatory first)**: Subtitle overlay only.
- Scope is bounded: one new function, one new SRT path, one ASS path.
- Timing conversion is fully understood and tested.
- Fallback is reliable.
- Audio passes through unchanged.

**Phase 3B (after 3A is stable in production)**: Text layer overlay.
- Requires explicit timing model decision for user-supplied layers.
- Hook overlay timing change is a behavior change (remove `* speed` factor).
- Should not block Phase 3A.

**Phase 3C (after 3B is stable)**: TTS/BGM audio composite.
- Risk of double atempo is real; requires careful gating.
- Lower priority than 3A and 3B (audio sync is already working in legacy path).

**Recommendation**: Implement Phase 3A first. Gate on `FEATURE_OVERLAY_AFTER_BASE_CLIP`.
Validate subtitle sync in real renders before opening Phase 3B scope.

---

## Summary

| Property | Value |
|---|---|
| New flags | `FEATURE_OVERLAY_AFTER_BASE_CLIP` (default OFF) |
| New functions (Phase 3A) | `slice_srt_to_output_timeline()`, `composite_overlays_on_base_clip()` |
| New manifest fields (Phase 3A) | `overlay_srt_path`, `overlay_ass_path`, `overlay_rendered_path` |
| Double setpts risk | Eliminated by design: no setpts in composite function |
| Double atempo risk | Eliminated in Phase 3A: `-c:a copy` |
| Subtitle timing | Source-clip SRT → output-timeline SRT via `/ speed` conversion |
| Text layer timing | Deferred to Phase 3B; timing model requires explicit decision |
| TTS/BGM | Deferred to Phase 3C |
| Legacy fallback | `render_part_smart()` always available; triggered on any overlay failure |
| Frontend/API/DB impact | Zero |
