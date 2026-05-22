# Phase 3B — Text Layer Overlay After Base Clip
## Implementation Plan

**Date**: 2026-05-22
**Branch**: restructure/output-timeline-architecture
**Status**: PLANNING — no code implemented
**Predecessor**: Phase 3A (subtitle overlay, commit 8db0295), Phase 3A.5 (validation, commit bab429c)

---

## 1. Current Phase 3A Behavior

```
FEATURE_BASE_CLIP_FIRST=1
FEATURE_OVERLAY_AFTER_BASE_CLIP=1:

  render_base_clip()                      → base_clip.mp4
    (speed + crop + color + audio already baked)
  slice_srt_to_output_timeline()          → subtitle_output_timeline.srt
  srt_to_ass_bounce/karaoke()             → subtitle_output_timeline.ass
  composite_overlays_on_base_clip()       → final_part.mp4
    vf_chain: ass='subtitle_output_timeline.ass'
    audio:    -c:a copy
    NO setpts, NO atempo, NO crop, NO scale, NO color

  fallback if composite raises:
    render_part_smart()                   → final_part.mp4
```

`composite_overlays_on_base_clip()` currently accepts:
- `subtitle_ass: str | None` — output-timeline ASS
- `text_layers` — **not yet supported**
- `title_text` — **not yet supported**

---

## 2. Target Phase 3B Behavior

```
FEATURE_BASE_CLIP_FIRST=1
FEATURE_OVERLAY_AFTER_BASE_CLIP=1:

  render_base_clip()                      → base_clip.mp4
  slice_srt_to_output_timeline()          → subtitle_output_timeline.srt
  srt_to_ass_bounce/karaoke()             → subtitle_output_timeline.ass
  [build output-timeline text layers]
  composite_overlays_on_base_clip()       → final_part.mp4
    vf_chain: ass=...
              drawtext=title (if title enabled, lt(t,3) output seconds)
              drawtext=layer_1 ... drawtext=layer_N (output-timeline enable)
    audio:    -c:a copy
    NO setpts, NO atempo, NO crop, NO scale, NO color

  fallback if composite raises:
    render_part_smart()                   → final_part.mp4
```

Key difference from Phase 3A: `composite_overlays_on_base_clip()` now accepts and
applies `text_layers` and `title_text` in output-timeline seconds.

---

## 3. Text Overlay Responsibility Audit

### 3.1 Title overlay (`title_text` / `overlay_title`)

**Where built**: `render_pipeline.py` line ~4288:
```python
overlay_title = (payload.title_overlay_text or "").strip() or source["title"]
```
Passed to `render_part_smart()` as `title_text` argument.

**Where filter is generated**: `render_engine.py` lines 992–999 inside `render_part_smart()`:
```python
drawtext = f"drawtext=text='{safe_title}':...:enable='lt(t\\,3)'"
```

**Current timing**: `enable='lt(t,3)'` — the `t` variable is source-clip PTS (because
the filter appears in the vf_chain BEFORE `setpts=PTS/speed`). So the title shows
for the first 3 source-clip seconds, which at speed=1.15 is 3/1.15 ≈ 2.6 output seconds.

**Overlay path timing**: On `base_clip.mp4`, the frame PTS is already output-timeline.
`t` in the drawtext expression is output-timeline seconds. So `enable='lt(t,3)'`
means "show for first 3 output seconds" — which is exactly the intended behavior.

**Conversion needed**: **None.** The same `lt(t,3)` expression is semantically
correct in the overlay path. No speed factor adjustment required.

**Classification**: **A — safe to move in Phase 3B, no timing conversion.**

---

### 3.2 Hook overlay (prepended to `_part_text_layers`)

**Where built**: `render_pipeline.py` lines ~4228–4253:
```python
_hook_spd = max(0.5, min(1.5, float(payload.playback_speed or 1.07)))
# end_time is pre-setpts, so multiply by speed so the overlay
# shows for ~1.5 s of perceived output time at any playback rate.
_hook_end_t = round(min(2.5, 1.5 * _hook_spd), 3)
_part_text_layers = [{"id": f"hook_overlay_{idx}", ..., "end_time": _hook_end_t}] + _part_text_layers
```

**Current timing**: `end_time = 1.5 * speed` source-clip seconds. After `setpts=PTS/speed`,
the drawtext shows until output t = (1.5 × speed) / speed = 1.5 output seconds.
The `* speed` multiplication is intentional and documented.

**Overlay path timing**: On `base_clip.mp4`, PTS is output-timeline. Hook must show
for 1.5 output seconds, so `end_time = 1.5` directly. The `* speed` factor is wrong
in the overlay context and would cause the hook to show for a shorter time.

**Conversion needed**: **Yes.** Remove `* speed` from `_hook_end_t` when building
overlay-path layers. Use `1.5` unconditionally.

**Classification**: **B — move with explicit conversion (remove speed factor).**

---

### 3.3 User text_layers (`payload.text_layers`)

**Where built**: `render_pipeline.py` line ~1919:
```python
normalized_text_layers = _validate_text_layers_or_400(payload)
```
Normalized once per job. Per-segment `_part_text_layers` is a copy with hook prepended.

**Creator-supplied timing**: `start_time`/`end_time` from the creator's request.
The creator thinks in perceived/output seconds ("show from 2 to 5 seconds into the clip").

**Current timing**: In legacy `render_part_smart()`, the drawtext `enable` expression uses
these values as source-clip seconds (pre-setpts). At speed=1.15, a layer set to
"0–5 output seconds" actually shows 0–(5/1.15)=4.35 output seconds. This is a
pre-existing timing error in the legacy path — it is NOT fixed in Phase 3B.

**Overlay path timing**: On `base_clip.mp4`, PTS is output-timeline. Using the
creator's values directly gives "show 0–5 output seconds" — which is correct.

**Conversion needed**: **None.** Creator-supplied times are semantically output-timeline.
Use them as-is in the overlay path. The legacy path timing error is not addressed here.

**Classification**: **A — safe to move in Phase 3B, no timing conversion.**

---

### 3.4 Market hook text (`apply_market_hook_text_to_srt`)

**What it does**: Replaces the text content of the first subtitle SRT block with the
creator's hook phrase. Does NOT create a drawtext overlay. Timing is unchanged.

**Where applied**: `render_pipeline.py` line ~3910, into `_ass_srt_source` (the source-clip
SRT that feeds the legacy ASS conversion).

**Phase 3 disposition**: Already handled by Phase 3A subtitle path. When
`slice_srt_to_output_timeline()` runs, the modified SRT (with hook text applied) is
converted to output-timeline — the hook text replacement is preserved.

**Classification**: **Not applicable for Phase 3B** — subtitle path concern, not text_layers.

---

### 3.5 CTA text (`_append_cta_block_to_srt`)

**What it does**: Appends a CTA subtitle block near the end of the clip to the SRT file.
This is a subtitle block — NOT a drawtext overlay.

**Where applied**: `render_pipeline.py` line ~4093, appended to `_ass_srt_source`.

**Timing complexity**: `cta_start = max(last_sub_end + 0.3, eff_dur - 3.0)` where
`eff_dur = raw_duration / speed` (output seconds). This means CTA timestamps mix
source-clip-time `last_sub_end` with output-duration-relative `eff_dur`. This is a
pre-existing inconsistency. The CTA timing is approximately correct at typical speeds
because the CTA appears near clip end and both coordinates converge there.

**Phase 3 disposition**: Phase 3A subtitle path handles CTA — `slice_srt_to_output_timeline()`
divides CTA timestamps by speed when producing the output-timeline SRT. This is
acceptable for Phase 3B. CTA timing correctness should be addressed in a dedicated audit.

**Classification**: **Not applicable for Phase 3B** — subtitle path concern, not text_layers.

---

### 3.6 Any drawtext added directly in render_engine.py

Title drawtext is the only drawtext generated directly in `render_engine.py` outside
`append_text_layer_filters()`. There is no other hardcoded drawtext in the codebase.

---

### 3.7 Text encoded into ASS subtitles

Market hook text is the only "text" applied directly to SRT/ASS content (replacing
subtitle text, not timestamps). This is handled by Phase 3A subtitle path and does
not require Phase 3B changes.

---

## 4. Overlay Migration Classification

| Overlay | Current timing | Overlay path timing | Conversion | Phase |
|---|---|---|---|---|
| ASS subtitle (`ass=`) | Source-clip ASS → Phase 3A output-timeline ASS | Output-timeline | Done — Phase 3A | 3A ✓ |
| Title drawtext `lt(t,3)` | Source-clip (pre-setpts) | Output-timeline (base_clip PTS) | **None needed** — same expression is correct | **3B** |
| Hook overlay `1.5×speed` | Source-clip (multiply for 1.5s output) | Output-timeline | **Remove `×speed`** — use `1.5` directly | **3B** |
| User text_layers | Source-clip (pre-setpts, creator intent is output) | Output-timeline | **None needed** — creator times are output-intended | **3B** |
| Market hook text | Subtitle SRT (not drawtext) | Handled by Phase 3A subtitle path | — | 3A ✓ |
| CTA text | Subtitle SRT (not drawtext) | Handled by Phase 3A subtitle path | — | 3A ✓ |
| `setpts=PTS/speed` | Speed filter | **Never moves** — baked in base_clip | — | D |
| `atempo=speed` | Audio speed filter | **Never moves** — baked in base_clip | — | D |
| scale/crop/reframe | Geometry | **Never moves** — baked in base_clip | — | D |
| color/effects/fade | Visual finish | **Never moves** — baked in base_clip | — | D |
| TTS narration mix | Post-render audio | Deferred | — | 3C |
| Remotion intro/outros | Post-render concat | Stays post-render | — | C |

---

## 5. Output-Timeline Text Layer Contract

### Design decision: plain dicts, no new dataclass

Text layers remain plain Python dicts, normalized by the existing `normalize_text_layers()`
and rendered by the existing `append_text_layer_filters()`. No new dataclass or module
is introduced. The contract is a semantic annotation:

> **In all paths through `composite_overlays_on_base_clip()`, the `start_time` and
> `end_time` values in every text layer dict are output-timeline seconds.**

This is enforced by construction (the pipeline builds them correctly) and verified by tests.

### Why not a dataclass

1. `normalize_text_layers()` already validates all fields — adding a dataclass would
   duplicate validation logic.
2. `append_text_layer_filters()` already renders dicts to drawtext expressions correctly.
3. The only change is the semantic meaning of `start_time`/`end_time`; the structure is identical.
4. A dataclass would require changes in `render_engine.py`, `text_overlay.py`, and every
   test — adding complexity without correctness benefit.

### Required fields (same as current text layer dict)

| Field | Type | Semantics in overlay path |
|---|---|---|
| `id` | str | Layer identifier (e.g. `hook_overlay_1`, `layer_1`) |
| `text` | str | Display text |
| `font_family` | str | Font family name |
| `font_size` | int | Font size in pixels |
| `color` | str | Hex color `#RRGGBB` |
| `position` | str | Named position (`top-center`, etc.) |
| `x_percent` | float | Horizontal position (0–100) |
| `y_percent` | float | Vertical position (0–100) |
| `alignment` | str | Text alignment |
| `bold` | bool | Bold text |
| `outline` | dict | Outline settings |
| `shadow` | dict | Shadow settings |
| `background` | dict | Box background settings |
| `start_time` | float | **Output-timeline seconds** — start of display window |
| `end_time` | float | **Output-timeline seconds** — end of display window (0 = no end) |
| `order` | int | Z-order for stacking |

### Module location

No new module. The timing contract lives in `render_pipeline.py` at the point where
`_part_text_layers_overlay` is constructed, and in `render_engine.py` in the
`composite_overlays_on_base_clip()` docstring.

---

## 6. Timing Conversion Strategy

### 6.1 Rule table

| Layer type | Legacy `_part_text_layers` timing | Overlay `_part_text_layers_overlay` timing | Action |
|---|---|---|---|
| Hook overlay | `end_time = 1.5 × speed` (source-clip s) | `end_time = 1.5` (output s) | Build separately — no `× speed` |
| User text_layers | `start_time`, `end_time` (source-clip s by accident) | `start_time`, `end_time` (output s by intent) | Use as-is |
| Title drawtext | `enable='lt(t,3)'` (source-clip PTS) | `enable='lt(t,3)'` (output PTS) | No change — same expression, different PTS context |

### 6.2 Implementation pattern

In `render_pipeline.py`, two parallel variables will exist in the overlay block:

```python
# Legacy: used only if _overlay_composite_succeeded is False
_part_text_layers          # existing — hook has end_time = 1.5 * speed (source-clip s)

# Overlay: used only in composite_overlays_on_base_clip()
_part_text_layers_overlay  # new — hook has end_time = 1.5 (output s), users as-is
```

Construction of `_part_text_layers_overlay` mirrors `_part_text_layers` construction
with exactly one change: the hook layer's `end_time` uses `1.5` not `1.5 * speed`.

### 6.3 No shared conversion function

A `source_text_layers_to_output_timeline(layers, timeline)` conversion function would
need to know which layers are source-time (hook) and which are output-time (user),
creating coupling between the converter and the layer construction logic.

Building two explicit lists in the pipeline is cleaner: the intent is visible at the
construction site, and each list is used in exactly one code path.

---

## 7. Hook Text Strategy

### Current (legacy path)

```python
_hook_spd = max(0.5, min(1.5, float(payload.playback_speed or 1.07)))
_hook_end_t = round(min(2.5, 1.5 * _hook_spd), 3)
# At speed=1.07: _hook_end_t = 1.605 source-clip seconds
# After setpts at 1.07×: hook shows until output t = 1.605 / 1.07 = 1.5 s ✓
```

### Phase 3B overlay path

```python
_hook_end_t_overlay = 1.5  # output-timeline seconds directly; no speed factor
# On base_clip.mp4 PTS is already output-timeline
# hook shows until output t = 1.5 s ✓
```

### Side-by-side hook layer comparison

```python
# Legacy layer (unchanged):
{"end_time": round(min(2.5, 1.5 * _hook_spd), 3), ...}

# Overlay layer (new):
{"end_time": 1.5, ...}  # always 1.5 output seconds, capped unchanged at 2.5 removed (not needed)
```

The `min(2.5, ...)` cap was protecting against `speed > 1.5` (which would give
`end_time > 2.5` source seconds); in overlay path the value is always `1.5` so the
cap is irrelevant and omitted for clarity.

### `resolve_hook_overlay_text()` unchanged

The function that resolves hook text content is timing-agnostic. It returns a string.
The timing difference is in how `end_time` is set, not in which text is used.

---

## 8. CTA Text Strategy

CTA is a subtitle path concern. It is appended to the SRT file as a subtitle block, not
as a drawtext overlay. Phase 3A handles CTA via `slice_srt_to_output_timeline()` which
divides CTA timestamps by speed.

**Phase 3B action**: None. CTA stays in the subtitle path.

**Known timing nuance**: `_append_cta_block_to_srt()` computes `cta_start` using a mix
of source-clip-time `_last_sub_end` and output-duration `_eff_dur`. This pre-existing
inconsistency is not addressed in Phase 3B. A dedicated CTA timing audit belongs in a
future hardening phase.

---

## 9. User `text_layers` Strategy

### Semantic decision

Creator-supplied `start_time`/`end_time` are treated as **output-timeline (perceived) seconds**
in the overlay path. This is the creator's intent: "show this overlay from second 2 to
second 5 of the clip" means 2–5 seconds of perceived video.

The legacy path treats them as source-clip seconds (pre-setpts), which is technically wrong
but is a pre-existing behavior that Phase 3B does NOT fix.

### Overlay path handling

User text_layers are passed to `composite_overlays_on_base_clip()` unchanged. On
`base_clip.mp4`, the frame PTS is already output-timeline, so `start_time`/`end_time`
are used correctly without any conversion.

### Validation

`normalize_text_layers()` runs on the user-supplied payload once per job (before any
per-segment work). The same normalized dicts are used for both the legacy and overlay paths.
No re-validation needed in `composite_overlays_on_base_clip()`.

---

## 10. `composite_overlays_on_base_clip()` Extension Plan

### New signature (Phase 3B)

```python
def composite_overlays_on_base_clip(
    base_clip_path: str,
    output_path: str,
    timeline: TimelineMap,
    subtitle_ass: str | None = None,       # Phase 3A: output-timeline ASS
    text_layers: list[dict] | None = None, # Phase 3B: output-timeline text layers
    title_text: str | None = None,         # Phase 3B: title drawtext text
    video_codec: str = "h264",
    video_crf: int = 18,
    video_preset: str = "slow",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    ffmpeg_threads: int | None = None,
) -> dict:
```

`audio_bitrate` remains in the signature for API completeness but is unused (audio is copied).
`timeline` remains unused in Phase 3B but stays for Phase 3C extensibility.

### vf_chain construction (Phase 3B)

```
vf_parts = []

# 1. Subtitle burn-in (Phase 3A)
if subtitle_ass:
    vf_parts.append(f"ass='{safe_ass}'")

# 2. Title drawtext (Phase 3B)
if title_text:
    vf_parts.append(f"drawtext=text='...' :enable='lt(t\\,3.000)'")

# 3. User text_layer drawtext filters (Phase 3B)
if text_layers:
    append_text_layer_filters(vf_parts, text_layers)

# 4. fps — always last (ensures CFR output)
vf_parts.append(f"fps={target_fps}")
```

`target_fps` is probed from `base_clip_path` using `probe_video_metadata()`. Since the
base clip was produced by `render_base_clip()` which always sets `fps=target_fps` as its
last filter, the probed FPS is always the correctly-targeted frame rate.

### Stream copy path (no overlays)

When `subtitle_ass is None` AND `text_layers` is empty/None AND `title_text` is empty/None:
use `-c:v copy -c:a copy` (Phase 3A behavior preserved). This is the zero-decode path
for when overlay composite is activated but no actual overlays exist.

### vf_chain trigger

Video re-encode (not stream copy) is triggered when ANY of: subtitle_ass, title_text,
or text_layers is non-empty. All three are optional; the stream copy path is only taken
when all three are absent.

### Forbidden filters (invariants asserted by tests)

The following must NEVER appear in the `composite_overlays_on_base_clip()` vf_chain,
under any configuration:

- `setpts=` — speed already applied in base_clip
- `atempo=` — audio speed already applied in base_clip
- `scale=` — geometry already applied in base_clip
- `crop=` — geometry already applied in base_clip
- `eq=` — color already applied in base_clip
- `hqdn3d` — denoise already applied in base_clip
- `-af` — audio must be copied, never reprocessed

### Audio rule (unchanged from Phase 3A)

Always `-c:a copy`. The base_clip.mp4 audio is already speed-adjusted, loudnorm-applied,
and BGM-mixed. No audio re-processing in the overlay composite.

### NVENC handling (unchanged from Phase 3A)

Same NVENC semaphore + CPU fallback pattern as Phase 3A implementation.

### Return value (unchanged from Phase 3A)

```python
{"path": output_path, "duration": ..., "fps": ..., "width": ..., "height": ..., "has_audio": ...}
```

---

## 11. Manifest Evolution Plan

### Phase 3B addition to `BaseClipManifest`

One new field:

```python
# Overlay composite tracking — set when FEATURE_OVERLAY_AFTER_BASE_CLIP=1
overlay_text_layers_applied: Optional[int] = field(default=None)
# Count of text layers (including hook) applied in the overlay composite.
# None if overlay was not used or composite had no text layers.
```

Added alongside the existing Phase 3A overlay fields.

### `to_dict()` addition

```python
"overlay_text_layers_applied": self.overlay_text_layers_applied,
```

### `from_dict()` addition

```python
overlay_text_layers_applied=d.get("overlay_text_layers_applied"),
```

### Naming

`overlay_text_layers_applied` follows the `overlay_*` prefix convention established by
Phase 3A. The `_applied` suffix indicates a count of actually-rendered layers (not
the payload spec), consistent with `overlay_srt_path` (actual produced artifact path).

### No overlay_text_layers_path field

The text layer definitions are not serialized to a separate file. They are derivable from
the original payload and the overlay path flag. Adding a serialized path would require
a separate JSON artifact, which adds I/O complexity without benefit for current use cases.

---

## 12. Feature Flag Strategy

### Recommendation: Single flag, no new flag for Phase 3B

**Decision**: Extend `FEATURE_OVERLAY_AFTER_BASE_CLIP` to cover subtitle + text layers.
No new flag for Phase 3B.

**Rationale**:

| Concern | Single flag | Separate text flag |
|---|---|---|
| Rollout granularity | Subtitle + text move together | Can enable text independently |
| State complexity | 2 flags × 2 states = 4 combinations | 3 flags × 2 states = 8 combinations |
| Test coverage | 4 combinations testable | 8 combinations; many untested in practice |
| Fallback safety | `render_part_smart()` covers all failures | Same fallback; extra flag doesn't add safety |
| Phase 3B prerequisite | Phase 3A already validated in production | Same prerequisite |

When Phase 3B is deployed, Phase 3A subtitle overlay is already proven. Enabling the
flag means the full overlay composite (subtitle + text). If text layers cause issues,
the fallback to `render_part_smart()` ensures job completion. The operator can disable
the feature entirely via `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`.

If future operators need to A/B test text layers vs subtitle-only, a separate flag can
be added at that time. Premature flag proliferation is harder to maintain than adding
a flag when the need is demonstrated.

### Existing flag behavior preserved

```python
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
```

Both remain default OFF. Decision matrix unchanged from Phase 3A:

| BASE_CLIP_FIRST | OVERLAY_AFTER_BASE_CLIP | Behavior |
|---|---|---|
| 0 | 0 | `render_part_smart()` — legacy path |
| 0 | 1 | `render_part_smart()` — overlay flag ignored, no base clip |
| 1 | 0 | `render_part_smart()` — base clip is parallel artifact only |
| 1 | 1 | `composite_overlays_on_base_clip()` with subtitle + text layers; `render_part_smart()` fallback |

---

## 13. Fallback Strategy

### Composite failure → `render_part_smart()`

Same as Phase 3A. If `composite_overlays_on_base_clip()` raises for any reason
(codec error, FFmpeg crash, missing font, drawtext syntax error), `_overlay_composite_succeeded`
remains False and `render_part_smart()` runs as authoritative fallback.

```python
try:
    # Build _part_text_layers_overlay (hook at 1.5 output s, user layers as-is)
    _oc_meta = composite_overlays_on_base_clip(
        ..., text_layers=_part_text_layers_overlay, title_text=..., ...
    )
    _overlay_composite_succeeded = True
except Exception as _oc_err:
    logger.warning("overlay_composite_failed ... %s — falling back to render_part_smart", _oc_err)

try:
    if not _overlay_composite_succeeded:
        render_part_smart(...)
finally:
    _encode_stop.set()
    _encode_timer.join(timeout=5.0)
```

### Text layer normalization failure → skip text, keep subtitle

If `normalize_text_layers()` raises when building `_part_text_layers_overlay` (edge case —
normalization already ran on payload at job start), log a warning and pass `text_layers=None`
to the composite. Subtitle overlay still proceeds. This is safer than falling back to
`render_part_smart()` because it preserves the validated subtitle overlay.

```python
try:
    _part_text_layers_overlay = _build_overlay_text_layers(...)
except Exception as _tl_err:
    logger.warning("overlay_text_layer_build_failed part=%d err=%s — subtitle-only composite", idx, _tl_err)
    _part_text_layers_overlay = None  # subtitle-only fallback
```

### Hook text resolution failure → no hook in overlay, continue

`resolve_hook_overlay_text()` returns `("", reason)` on failure. The overlay path handles
the empty case identically to the legacy path: no hook layer in `_part_text_layers_overlay`.

### Invariant

`render_part_smart()` MUST remain the final safety net. It is never removed from the code
path. It only becomes a no-op when `_overlay_composite_succeeded` is True.

---

## 14. QA Strategy

### Duration match (most critical)

Overlay composite output duration must be within ±1% of `base_clip.mp4` duration.
Any text layer drawtext expression that modifies frame counts would indicate a bug.
(Drawtext does not affect frame count, but the assertion prevents future regressions.)

### Resolution, FPS, codec match

Overlay output resolution and FPS must match `base_clip.mp4` exactly. The `fps=target_fps`
last filter guarantees FPS; the assertion catches any accidental filter insertion.

### Text layer presence check

For a clip with `hook_overlay_enabled=True` and expected hook text:
- Verify that `overlay_text_layers_applied > 0` in the manifest.
- Visual inspection: hook banner appears in the first 1.5 seconds of output.

### No double overlay

When `_overlay_composite_succeeded=True`, `render_part_smart()` must NOT run.
Log line `overlay_composite_succeeded part=N` must appear without
`render_part_smart` executing for the same part.

### Timing drift check (manual)

For a known source clip with hook overlay at 1.5s expected output time:
- Legacy path: hook visible ≈ 0–1.5 output seconds ✓
- Overlay path: hook visible 0–1.5 output seconds ✓ (not 0–(1.5/speed) = 0–1.3)

---

## 15. Test Strategy

### Extend `backend/tests/test_composite_overlays.py`

Extend the `_call_composite()` helper to accept `text_layers` and `title_text`:

```python
def _call_composite(subtitle_ass=..., text_layers=None, title_text=None, **overrides):
    ...
    kwargs = dict(..., text_layers=text_layers, title_text=title_text)
```

**New tests — drawtext presence:**

- `test_drawtext_present_when_text_layers_provided` — `drawtext` in cmd when layers non-empty
- `test_drawtext_absent_when_no_text_layers` — `drawtext` not in cmd when `text_layers=None`
- `test_title_drawtext_present_when_title_provided` — `drawtext=text=` in cmd
- `test_title_drawtext_absent_when_no_title` — no `drawtext=text=` when `title_text=None`

**New tests — title timing:**

- `test_title_enable_expression_is_lt_3` — `lt(t\\,3` in cmd string when title provided

**New tests — text layer timing:**

- `test_text_layer_enable_uses_layer_start_end_times` — `gte(t\\,1.500)` and `lt(t\\,5.000)` in cmd for a layer with `start_time=1.5, end_time=5.0`
- `test_text_layer_enable_absent_when_start_end_zero` — no `enable=` expression when start/end both 0

**New tests — invariants preserved with text layers:**

- `test_no_setpts_with_text_layers` — `setpts=` not in cmd even with layers present
- `test_no_atempo_with_text_layers` — `atempo=` not in cmd even with layers present
- `test_audio_copy_with_text_layers` — `("-c:a", "copy")` in cmd when layers present
- `test_no_scale_with_text_layers` — `scale=` not in cmd
- `test_no_crop_with_text_layers` — `crop=` not in cmd

**New tests — vf_chain order:**

- `test_fps_is_last_filter_with_text_layers` — last element of `-vf` value ends with `fps=`
- `test_ass_before_drawtext_in_vf_chain` — `ass=` appears before `drawtext=` in vf value

**New tests — stream copy with no overlays:**

Existing `test_stream_copy_when_no_subtitle` expands to `subtitle_ass=None, text_layers=None, title_text=None`.

### New file: `backend/tests/test_overlay_text_layer_timing.py`

**Hook timing tests:**

- `test_hook_legacy_end_time_is_1_5_times_speed` — confirms legacy `_hook_end_t = 1.5 × speed`
  for various speed values (sanity check that the legacy formula is not accidentally changed)
- `test_hook_overlay_end_time_is_1_5_output_seconds` — confirms overlay hook dict has
  `end_time == pytest.approx(1.5)` regardless of `effective_speed`
- `test_hook_overlay_end_time_not_speed_multiplied` — at speed=1.15, overlay end_time ≠ 1.5 × 1.15
- `test_hook_overlay_start_time_is_zero` — `start_time == 0.0` in overlay hook

**User layer passthrough tests:**

- `test_user_layer_times_unchanged_in_overlay_path` — user layer with `start_time=2.0, end_time=8.0`
  passes through to composite unchanged (same values in composite call)

**Timing isolation test:**

- `test_legacy_and_overlay_hook_times_differ_at_nonunit_speed` — at speed ≠ 1.0, legacy
  `_hook_end_t ≠ 1.5`, overlay `_hook_end_t == 1.5`

### Manifest field tests — extend `test_base_clip_manifest.py`

- `test_overlay_text_layers_applied_none_by_default`
- `test_overlay_text_layers_applied_in_to_dict`
- `test_overlay_text_layers_applied_round_trip`
- `test_from_dict_backward_compat_missing_overlay_text_layers_applied`

---

## 16. Clean Code / Naming Rules

| Rule | Detail |
|---|---|
| No phase-number variable names | `_part_text_layers_overlay` ✓ (not `_phase3b_layers`) |
| Comments explain timing contract | "output-timeline seconds, no speed factor" not "Phase 3B fix" |
| No `temp`, `new`, `final2` names | `_part_text_layers_overlay` exists for its duration, not as a temp |
| No duplicated speed formula | hook timing conversion is at ONE site in render_pipeline.py |
| `TimelineMap` remains timing authority | `timeline.effective_speed` used in Phase 3A; overlay path uses it for subtitle only in 3B |
| Legacy `_part_text_layers` unchanged | Phase 3B must not modify the variable that feeds `render_part_smart()` |
| Frontend/API/DB untouched | `payload.text_layers`, `payload.title_overlay_text`, all API fields unchanged |
| No runtime phase comments | comments say what the code does, not which sprint added it |

---

## 17. Required File Changes

### `backend/app/services/render_engine.py`

**Change**: Extend `composite_overlays_on_base_clip()` signature and vf_chain:
- Add params: `text_layers: list[dict] | None = None`, `title_text: str | None = None`
- Add title drawtext to vf_chain when `title_text` is provided
- Call `append_text_layer_filters(vf_parts, text_layers)` when `text_layers` is non-empty
- Trigger video re-encode (not stream copy) when any of subtitle_ass/title_text/text_layers is set
- Import: `from app.services.text_overlay import append_text_layer_filters` already imported

### `backend/app/orchestration/render_pipeline.py`

**Change 1**: Build `_part_text_layers_overlay` in the overlay block:
```python
_part_text_layers_overlay = list(normalized_text_layers)  # user layers as-is
if _hook_overlay_enabled and _hook_text:
    _part_text_layers_overlay = [
        {..., "end_time": 1.5}  # 1.5 output seconds, no speed factor
    ] + _part_text_layers_overlay
```

**Change 2**: Pass to composite call:
```python
_oc_meta = composite_overlays_on_base_clip(
    ...,
    text_layers=_part_text_layers_overlay if _part_text_layers_overlay else None,
    title_text=overlay_title if payload.add_title_overlay else None,
    ...
)
```

**Change 3**: Set manifest field:
```python
_part_manifest.overlay_text_layers_applied = len(_part_text_layers_overlay or [])
```

### `backend/app/domain/manifests.py`

**Change**: Add one field:
```python
overlay_text_layers_applied: Optional[int] = field(default=None)
```
Update `to_dict()` and `from_dict()` with None default for backward compat.

### `backend/tests/test_composite_overlays.py`

**Change**: Extend `_call_composite()` helper; add ~12 new tests.

### `backend/tests/test_overlay_text_layer_timing.py` (new file)

**New**: ~8 tests for hook timing and user layer passthrough.

### `backend/tests/test_base_clip_manifest.py`

**Change**: Add 4 tests for `overlay_text_layers_applied` field.

### `backend/app/services/text_overlay.py`

**No changes required.** `append_text_layer_filters()` already accepts the output-timeline
dict format. `normalize_text_layers()` is already called at job start.

### `backend/app/domain/timeline.py`

**No changes required.** `TimelineMap.source_to_output()` is available for any future
conversion needs but is not used in Phase 3B text layer construction.

### `backend/app/domain/overlays.py`

**Not created.** No new domain module required in Phase 3B.

---

## 18. Exact Implementation Order

**Step 1**: Extend `BaseClipManifest` with `overlay_text_layers_applied`.
- Update `manifests.py`: add field, update `to_dict()`, update `from_dict()`
- Add 4 manifest tests to `test_base_clip_manifest.py`
- Run: `python -m pytest tests/test_base_clip_manifest.py -v`

**Step 2**: Extend `composite_overlays_on_base_clip()` in `render_engine.py`.
- Add `text_layers` and `title_text` params
- Build vf_chain: subtitle → title drawtext → text_layer drawtext → fps
- Keep stream copy path when all three overlay sources are absent
- Run: `python -m pytest tests/test_composite_overlays.py -v`

**Step 3**: Add new timing tests in `test_overlay_text_layer_timing.py`.
- Write all ~8 timing tests
- Run: `python -m pytest tests/test_overlay_text_layer_timing.py -v`

**Step 4**: Extend `_call_composite()` in `test_composite_overlays.py`.
- Add 12 new overlay filter presence/absence tests
- Run: `python -m pytest tests/test_composite_overlays.py -v`

**Step 5**: Update `render_pipeline.py` overlay block.
- Add `_part_text_layers_overlay` construction (hook at 1.5 output s)
- Pass `text_layers` and `title_text` to composite call
- Set `_part_manifest.overlay_text_layers_applied`
- Note: `_part_text_layers` (legacy) must remain UNCHANGED

**Step 6**: Compile check and full test run.
- `python -m compileall app`
- `python -m pytest --tb=short -q`
- Must not add new failures beyond the existing 8.

**Step 7**: Commit and push.
- Commit message: `"feat(render): phase 3b text layer overlay after base clip"`

---

## 19. What Must NOT Change

The following are invariants for Phase 3B:

| Item | Why |
|---|---|
| `render_part_smart()` body | Legacy fallback must remain bit-for-bit identical |
| `render_base_clip()` body | Already correct; base clip generation is frozen |
| `_part_text_layers` variable | Used by `render_part_smart()` fallback; must keep `× speed` for hook |
| `normalize_text_layers()` | Validates payload; not timing-aware, correct as-is |
| `append_text_layer_filters()` | Renders dict to drawtext; timing-agnostic, correct as-is |
| `slice_srt_by_time()` | Core SRT slicer; not touched |
| `slice_srt_to_output_timeline()` | Phase 3A function; not modified |
| `composite_overlays_on_base_clip()` docstring invariant | "no setpts, no atempo, no crop, no scale, no color" |
| `backend/app/models/schemas.py` | No API schema change |
| `backend/app/routes/` | No route change |
| `backend/app/services/db.py` | No DB change |
| `backend/static/` | No frontend change |
| WebSocket payload fields | No change |
| Job status/stage names | No change |
| `FEATURE_OVERLAY_AFTER_BASE_CLIP` default | Remains OFF (`"0"`) |
| `FEATURE_BASE_CLIP_FIRST` default | Remains OFF (`"0"`) |

---

## 20. Phase 3C Handoff Notes

Phase 3C (TTS/BGM audio composite) is NOT part of Phase 3B scope. These notes
record what Phase 3C will need to know.

### Audio state after Phase 3B

After `composite_overlays_on_base_clip()` runs (Phase 3B):
- Video: subtitle + text overlays burned onto base_clip
- Audio: `-c:a copy` from `base_clip.mp4`
  - Speed-adjusted (atempo already applied)
  - Loudnorm applied (if enabled in base_clip render)
  - BGM mixed (if reup_bgm_enable, mixed in render_base_clip)
  - No narration mixed (narration is Phase 3C concern)

### Phase 3C integration point

TTS narration mix must run AFTER `composite_overlays_on_base_clip()` returns, on the
composite output file. `mix_narration_audio()` must be called with:
- `video_path = str(overlay_composite_output)`
- `playback_speed = _part_timeline.effective_speed` — narration is sped up to match video

The existing post-`render_part_smart()` narration mix block must be gated:
```python
if not _overlay_composite_succeeded:
    # Legacy narration mix path (render_part_smart output)
    mix_narration_audio(video_path=str(final_part), ...)
else:
    # Overlay composite narration mix path (Phase 3C)
    # NOT IMPLEMENTED until Phase 3C
    pass
```

Without this gate, narration would be double-mixed in the overlay path. Phase 3C must
add this gate before enabling TTS in the overlay path.

### No BGM re-mix in Phase 3C

BGM is already baked into `base_clip.mp4` audio. Do not re-mix BGM in Phase 3C.
Only narration needs to be mixed onto the composite output.

### `_part_manifest.narration_path` tracking

Phase 3C will need to add a manifest field for narration-on-composite tracking,
analogous to Phase 3A's `overlay_rendered_path`. Suggested name:
`overlay_narration_mixed_path` (the path of the composite output after narration mix).

---

## Summary

| Property | Value |
|---|---|
| New feature flag | None — extends existing `FEATURE_OVERLAY_AFTER_BASE_CLIP` |
| New functions | None — extends `composite_overlays_on_base_clip()` in place |
| New modules | None |
| Modified files | `render_engine.py`, `render_pipeline.py`, `manifests.py`, 3 test files |
| New test files | `test_overlay_text_layer_timing.py` |
| New manifest fields | `overlay_text_layers_applied` (Optional[int]) |
| Hook timing change | Legacy: `1.5 × speed` (unchanged); Overlay: `1.5` (output seconds) |
| User layer timing | Legacy: source-clip seconds (pre-existing); Overlay: output-timeline (correct) |
| Title drawtext timing | Same expression `lt(t,3)` — output-timeline in overlay context |
| CTA disposition | Subtitle path only — no Phase 3B action |
| Market hook text | Subtitle path only — no Phase 3B action |
| Fallback | `render_part_smart()` always available on any composite failure |
| Frontend/API/DB impact | Zero |
| Phase 3C precondition | Phase 3B stable; narration mix gate added |
