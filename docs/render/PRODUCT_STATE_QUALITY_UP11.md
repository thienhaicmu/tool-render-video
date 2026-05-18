# PRODUCT STATE — QUALITY-UP11: Visual Finish Layer

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): visual finish layer`
**Status:** Shipped

---

## Summary

Seven surgical improvements to the final render output quality.
No AI upscaling. No GPU dependency. No cinematic LUT. No render instability.
No new dependencies.

Each part targets a specific "tool-generated feel" that persisted after UP1A–UP10B.
All improvements are content-type-aware using `content_type_hint` already flowing
through the pipeline from UP10B.

---

## Part A — Smart Output Encode Ladder

**Files:** `backend/app/services/render_engine.py`, `backend/app/orchestration/render_pipeline.py`

### Problem

All content types received the same CRF regardless of what they contain.
Tutorial and interview content (sharp text, fine detail) needs tighter quantisation
than montage/gaming (motion-dominant, where AQ handles quality better than CRF).

### Fix

Content-type CRF delta applied per-part before the `render_part_smart()` call:

| Content type | CRF delta | Reason |
|---|---|---|
| `tutorial` | −2 | Screen text and UI sharpness benefit from tighter quantisation |
| `interview` | −2 | Face and fine hair detail benefit from tighter quantisation |
| `montage` | +1 | Fast motion quality governed more by AQ than marginal CRF |
| `commentary` / `vlog` | 0 | No change from profile default |

```python
def content_type_crf_delta(content_type: str) -> int:
    return {"tutorial": -2, "interview": -2, "montage": 1}.get(content_type or "", 0)
```

CRF is clamped `[11, 28]` to prevent quality or encode-time extremes.
Creator's explicit `video_crf` payload override still applies first (profile is the base).

---

## Part B — Anti-Muddy Clarity Pass

**File:** `backend/app/services/render_engine.py`

### Problem

The `_cinematic_sharpen_filter` applied the same luma-only `unsharp=5:5:0.4` to all
content types. For montage/gaming, this stacked with the effect filter's unsharp and
introduced mild halo artifacts on fast-moving edges. For tutorial/interview, slightly
more sharpening improves text and screen legibility.

### Fix: Content-type-aware luma sharpening

```python
def _cinematic_sharpen_filter(src_h, content_type="vlog"):
    if 0 < src_h < 480:
        return None
    if content_type in ("tutorial", "interview"):
        return "unsharp=5:5:0.5:5:5:0.0"   # +0.1 luma for text/screen clarity
    if content_type == "montage":
        return "unsharp=3:3:0.25:3:3:0.0"  # reduced — less halo on fast motion
    return "unsharp=5:5:0.4:5:5:0.0"       # standard (commentary/vlog)
```

Chroma sharpen remains 0.0 across all types (chroma sharpening introduces colour halos).
Low-res source guard (<480p) unchanged.

---

## Part C — Smart Denoise Lite

**File:** `backend/app/services/render_engine.py`

### Problem

`hqdn3d=1.5:1.5:6:6` fired only for `slower`/`veryslow` presets (quality mode).
Interview and tutorial content at `slow` preset (the default for `balanced` and `quality`
profiles) received no denoise benefit. Low-res or compressed sources showed amplified
noise after upscale.

### Fix: Content-type + source-quality gated denoise

```python
def _smart_denoise_filter(content_type, preset, src_h):
    if content_type == "montage":
        return None                          # motion smear risk
    if preset in ("slower", "veryslow"):
        return "hqdn3d=1.5:1.5:6:6"        # quality mode: full (unchanged)
    if preset == "slow" and content_type in ("interview", "tutorial"):
        return "hqdn3d=1.0:1.0:4:4"        # medium quality + static content: lite
    if 0 < src_h < 720:
        return "hqdn3d=0.8:0.8:3:3"        # low-res source: very lite
    return None
```

| Condition | Before | After |
|---|---|---|
| slower/veryslow, any | hqdn3d=1.5:1.5:6:6 | Same (no regression) |
| slow + interview/tutorial | none | hqdn3d=1.0:1.0:4:4 |
| fast/medium, any | none | Same |
| <720p source, non-montage | none | hqdn3d=0.8:0.8:3:3 |
| montage, any | preset-gated | always skipped |

---

## Part D — Perceptual Color Polish

**File:** `backend/app/services/render_engine.py`

### Problem

`_cinematic_color_filter` applied `eq=contrast=1.02:saturation=1.03` to all content.
For tutorial/interview (screen recordings, face-to-camera), this extra saturation on
top of the effect filter's saturation made content feel slightly over-processed.
Montage/gaming energy content benefits from a richer boost.

### Fix: Content-type-aware color lift

```python
def _cinematic_color_filter(src_h, content_type="vlog"):
    if 0 < src_h < 480:
        return None
    if content_type in ("tutorial", "interview"):
        return "eq=contrast=1.01:saturation=1.01"   # near-neutral: preserve authenticity
    if content_type == "montage":
        return "eq=contrast=1.03:saturation=1.06"   # richer for energy
    return "eq=contrast=1.02:saturation=1.03"        # commentary/vlog (unchanged)
```

Low-res source guard (<480p) unchanged.

---

## Part E — Export Bitrate Safety

**Files:** `backend/app/services/encoder_helpers.py`, `backend/app/services/render_engine.py`

### Problem

`-maxrate 20M -bufsize 40M` was fixed for all content types. Montage/gaming content
at high motion could hit the ceiling and collapse quality in dense action sequences.
Interview/tutorial uses far less bitrate budget — 20M was wasteful without benefit.

### Fix: Content-type bitrate profile in `codec_extra_flags`

`codec_extra_flags()` now accepts `maxrate_m: int = 20, bufsize_m: int = 40` params.
`render_part()` computes the right profile from `content_type` before calling:

| Content type | maxrate | bufsize |
|---|---|---|
| `montage` | 25M | 50M |
| `interview` | 15M | 30M |
| `tutorial` | 15M | 30M |
| `commentary` / `vlog` | 20M | 40M (unchanged) |

Applies to both CPU (libx264/libx265) and NVENC paths.
`motion_crop.py`'s `_codec_flags()` is independent and unaffected (NVENC uses
unconstrained VBR for pipe latency reasons, CPU delegates and picks up defaults).

---

## Part F — Subtitle Visual Safety

**File:** `backend/app/orchestration/render_pipeline.py`

### Problem

`sub_margin_v = 180` was a fixed default with no awareness of face position.
When `motion_aware_crop=True`, the crop system already enforces `subtitle_safe_bottom_ratio=0.12`,
keeping the tracked subject clear of the subtitle zone. When disabled, interview
and commentary faces can occupy the lower third of the frame and collide with subtitles.

### Fix: Light margin bump for face-forward content without crop

```python
# Applied before srt_to_ass_bounce() call
if not payload.motion_aware_crop and seg.get("content_type_hint") in ("interview", "commentary"):
    _margin_v += 40
```

- Only fires when `motion_aware_crop=False` (when enabled, crop system handles this)
- +40px vertical clearance (180 → 220 from bottom)
- No tracking, no subtitle rewrite, no animation
- Creator's explicit `sub_margin_v` override still applies as the base

---

## Part G — Visual Finish Observability

**File:** `backend/app/orchestration/render_pipeline.py`

A `visual_finish_applied` event is emitted per part after render completes:

```
event: visual_finish_applied
context: {
  part_no, content_type, visual_finish_score,
  clarity_level, compression_risk, subtitle_visibility,
  crf_applied, crf_delta, bitrate_profile
}
```

`visual_finish_score` is a 0–100 index derived from CRF headroom
(tighter CRF = higher perceived quality budget expended = higher score).

Also logged to `logger.info` as `visual_finish_applied` for easy grep during QA.

---

## Parameter Comparison

| Scenario | Before UP11 | After UP11 |
|---|---|---|
| Tutorial `slow` preset | CRF 18, maxrate 20M, hqdn3d off, unsharp 0.4 luma | CRF 16, maxrate 15M, hqdn3d 1.0 lite, unsharp 0.5 luma, neutral color |
| Interview `slow` preset | CRF 18, maxrate 20M, hqdn3d off | CRF 16, maxrate 15M, hqdn3d 1.0 lite, neutral color |
| Montage `slow` preset | CRF 18, maxrate 20M, unsharp 0.4, saturation +3% | CRF 19, maxrate 25M, unsharp 0.25 (reduced), saturation +6% |
| Commentary/vlog | All values at default | No change |
| Interview, no motion crop | `sub_margin_v = 180` | `sub_margin_v = 220` |
| Commentary, no motion crop | `sub_margin_v = 180` | `sub_margin_v = 220` |
| `slower`/`veryslow` preset, any type | hqdn3d=1.5:1.5:6:6 | Same (no regression) |
| Low-res source (<720p) non-montage | hqdn3d off unless quality preset | hqdn3d=0.8:0.8:3:3 |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| Two-pass encode for bitrate accuracy | Doubles encode time; CRF + AQ already handles quality well |
| Scene-adaptive sharpening (frame-by-frame) | Requires OpenCV per-frame analysis; too slow for production |
| Face-position-based dynamic margin_v | Requires running MediaPipe outside the crop system and before subtitle generation; pipeline reorder prohibited |
| Chroma sharpening | Introduces colour halos on all content types at social recompression bitrates |
| Per-clip CRF adjustment based on scene_quality_score | scene_quality_score not yet propagated to render call site; deferred to UP12 |
| Low-bitrate source detection via ffprobe stream bitrate | Would require additional probe; visual signals (`src_h`) are sufficient proxy |

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/services/encoder_helpers.py` | `codec_extra_flags` accepts `maxrate_m`, `bufsize_m` params |
| `backend/app/services/render_engine.py` | `_cinematic_color_filter`, `_cinematic_sharpen_filter` content-type-aware; new `_smart_denoise_filter`, `content_type_crf_delta`; `render_part()` `content_type` param; bitrate profile |
| `backend/app/orchestration/render_pipeline.py` | Import `content_type_crf_delta`; `_part_video_crf` delta; Part F margin bump; Part G observability event |
| `docs/render/PRODUCT_STATE_QUALITY_UP11.md` | This file |

---

## Manual QA Checklist

### Part A — Encode ladder

- [ ] Tutorial render log shows `crf_delta=-2 crf_applied=16` (for balanced profile CRF 18)
- [ ] Interview render log shows `crf_delta=-2`
- [ ] Montage render log shows `crf_delta=+1`
- [ ] Commentary/vlog render log shows `crf_delta=0`
- [ ] Explicit `video_crf=25` payload: tutorial renders at CRF 23 (25 - 2), not 25

### Part B — Clarity

- [ ] Tutorial subtitle: visually sharper than commentary at same resolution
- [ ] Montage: no halo artifacts on fast cuts at full playback speed
- [ ] Low-res source (<480p): no sharpen applied (log `cinematic_pass_reduced_for_low_quality_source`)

### Part C — Denoise

- [ ] Interview at `slow` preset: log shows `hqdn3d=1.0:1.0:4:4` in filter chain
- [ ] Montage at any preset: no `hqdn3d` in filter chain
- [ ] Slower/veryslow preset: log still shows `hqdn3d=1.5:1.5:6:6` (no regression)
- [ ] Low-res source (<720p) commentary: `hqdn3d=0.8:0.8:3:3` in filter chain

### Part D — Color

- [ ] Tutorial render: saturation noticeably less boosted than commentary (authentic screen look)
- [ ] Montage render: slightly richer color than vlog
- [ ] Low-res source: no color pass applied (low_quality_source guard)

### Part E — Bitrate

- [ ] Montage render log shows `maxrate=25M bufsize=50M`
- [ ] Interview render log shows `maxrate=15M bufsize=30M`
- [ ] Commentary render log shows `maxrate=20M bufsize=40M` (unchanged)
- [ ] Montage dark scene: no visible quality collapse in motion-heavy sequences

### Part F — Subtitle safety

- [ ] Interview with `motion_aware_crop=False`: log shows `sub_margin_v=220`
- [ ] Interview with `motion_aware_crop=True`: log shows `sub_margin_v=180` (crop handles it)
- [ ] Montage: margin_v unchanged regardless of motion_aware_crop setting
- [ ] Creator explicit `sub_margin_v=150`: subtitle at 190 when bump applies (150 + 40)

### Part G — Observability

- [ ] Each rendered part emits `visual_finish_applied` event in job log
- [ ] Event context includes `content_type`, `crf_delta`, `bitrate_profile`, `clarity_level`
- [ ] `visual_finish_score` present and between 0–100

### Safety

- [ ] Cancel still works during render phase
- [ ] Resume still works for interrupted renders
- [ ] No regression on commentary, vlog, montage renders
- [ ] No backend errors in queue or concurrent renders
- [ ] `render_part_smart` motion-aware-crop fallback path still receives `content_type`
