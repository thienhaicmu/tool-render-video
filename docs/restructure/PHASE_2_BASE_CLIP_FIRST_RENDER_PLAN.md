# Phase 2 — Base Clip First Render: Implementation Plan

**Date**: 2026-05-22  
**Branch**: restructure/output-timeline-architecture  
**Status**: PLANNING ONLY — no code changes  
**Author**: Architecture review from Phase 1 + Phase 1.5 foundation

---

## 1. Current Per-Part Render Flow

Each segment runs `_render_part()` in a `ThreadPoolExecutor`. Inside that
function, the following happens sequentially:

```
_render_part(seg, idx, ...)
│
├─ [SUBTITLE PRE-PROCESSING]                        ← source timeline
│   ├─ slice_srt_by_time()                          ← subtracts seg start, no speed adjust
│   ├─ srt_to_ass_bounce() / srt_to_ass_karaoke()   ← .ass burn-in file
│   ├─ apply_market_hook_text_to_srt()              ← injects hook into first subtitle block
│   ├─ _apply_subtitle_edits_to_srt()               ← user edits
│   └─ translate() (optional)                       ← deep-translator
│
├─ [TTS / NARRATION PRE-PROCESSING]                 ← source timeline text → audio
│   ├─ generate_narration_audio()                   ← edge-tts / XTTS at natural rate
│   ├─ _maybe_cleanup_narration_audio()             ← optional DeepFilterNet
│   └─ mix_narration_audio(playback_speed=...)      ← Phase 0: atempo now applied
│
├─ [VIDEO CUT]
│   └─ cut_video()                                  ← ffprobe-verified stream-copy or re-encode
│
├─ [RENDER — single FFmpeg pass]                    ← OUTPUT timeline created here
│   └─ render_part_smart()
│       ├─ motion_crop.py: build_motion_path()      ← MediaPipe/ByteTrack on raw cut
│       └─ FFmpeg vf_chain (in order):
│           scale → crop → zoom → denoise →
│           effect (eq/unsharp) → color → sharpen →
│           format=yuv420p → fade →
│           ass=subtitle.ass              ← ASS burned BEFORE setpts
│           drawtext=title               ← title overlay
│           text_layers                  ← user text overlays
│           setpts=PTS/speed             ← speed adjustment
│           fps=target_fps               ← always last
│       audio chain:
│           atempo=speed (if speed != 1.0)
│           loudnorm (optional)
│       → encoded output: part_N_rendered.mp4
│
├─ [POST-RENDER ASSEMBLY]                           ← operates on rendered clip
│   ├─ _maybe_prepend_remotion_hook_intro()         ← animated title card
│   ├─ _maybe_prepend_asset_intro()                 ← creator asset
│   ├─ _maybe_append_asset_outro()                  ← creator asset
│   └─ _maybe_apply_asset_logo()                    ← watermark
│
├─ [OUTPUT QA]
│   └─ _validate_render_output()                    ← duration ±20%, size > 0
│
└─ [METADATA]
    ├─ extract_thumbnail_frame()
    ├─ write_manifest() (Phase 1)
    └─ upsert_job_part() → DB
```

---

## 2. Current Timing Dependency Graph

```
Source video seconds (absolute)
│
├── Segment boundaries [seg.start, seg.end]
│       └── _effective_start = seg.start + silence_trim + visual_trim
│
├── slice_srt_by_time(start=_effective_start, end=seg.end)
│       → subtitle timestamps: clip-relative source seconds
│       → NOT divided by playback_speed  ← known bug (C2 in TECHNICAL_DEBT_REPORT.md)
│
├── generate_narration_audio() from transcript text
│       → narration at natural speaking rate (source-derived)
│       → mix_narration_audio(playback_speed) applies atempo (Phase 0 fix)
│
├── cut_video(start=_effective_start, end=seg.end)
│       → raw cut in source time
│
└── render_part_smart()
        → applies setpts=PTS/speed AFTER ass= filter
        → output timeline = source_duration / effective_speed
        → subtitle timestamps NOT adjusted for speed  ← bug compounds here
        → audio atempo applies speed to video's embedded audio
```

### Critical timing coupling

The ASS burn-in happens **before** `setpts=PTS/speed`. This means:

- Subtitle timestamps are source-time seconds
- FFmpeg burns subtitles at source-time frame positions
- `setpts` then re-clocks all frames to output time
- Result: at 1.15x, a subtitle at source t=10.0s appears at output t=8.7s
- **The subtitle IS correctly synchronized with the frame it was associated with**
- But the viewer reads subtitles based on audio (speech), not video frames
- Audio is separately sped by `atempo=1.15` in the audio filter chain
- Speech at t=10.0s in audio is heard at output t=8.7s
- Subtitle at source t=10.0s appears at frame output t=8.7s
- **This means subtitles ARE in sync with the sped-up audio/video at the moment**
- The "drift" issue is more subtle: subtitle timing matches the frame clock
  but text duration is not compressed — subtitles intended for a 3s window
  appear for 3/1.15 = 2.6s due to setpts compression but the text and audio
  are in sync

**Revised understanding (Phase 1.5)**: The `ass-before-setpts` order means
the subtitle timestamps in source-clip seconds are re-clocked by setpts, so
they remain correctly sync'd with the video. The historical bug report was
about *text reading duration compression* and *end-of-clip accumulation*.
The vf_chain order MUST NOT change.

---

## 3. Target Base-Clip-First Flow (Phase 2)

> **IMPORTANT**: In Phase 2 the base clip is a **parallel validation artifact**.
> It is NOT used as input to the final render. The final output still comes
> exclusively from the unmodified `render_part_smart()` path. See §3a below.

```
_render_part(seg, idx, ...)
│
├─ [PRE-PROCESSING — unchanged, source timeline]
│   ├─ slice_srt_by_time()
│   ├─ ASS conversion
│   ├─ narration generation + mix
│   └─ cut_video()
│
├─ [BASE CLIP RENDER — PARALLEL ARTIFACT, only when FEATURE_BASE_CLIP_FIRST=1]
│   └─ render_base_clip()
│       ├─ speed from TimelineMap.effective_speed  ← authoritative timing record
│       ├─ crop/reframe (motion_aware or standard)
│       ├─ fps normalization
│       ├─ target resolution/aspect
│       ├─ color grading + effect
│       ├─ audio normalization (inseparable from video encode)
│       ├─ NO ass= subtitle filter
│       ├─ NO drawtext title overlay
│       ├─ NO text_layers
│       ├─ NO TTS narration mix at encode time
│       → base_clip.mp4  ← ARTIFACT ONLY; NOT used as final output input
│
├─ [MANIFEST UPDATE — base clip fields only]
│   └─ write base_clip_path, base_clip_duration, base_clip_fps, etc.
│
├─ [FINAL RENDER — ALWAYS runs, UNCHANGED legacy path]
│   └─ render_part_smart()           ← UNMODIFIED; produces the final output
│       ├─ ALL overlays (ass=, drawtext=, text_layers)
│       ├─ speed from payload (same computation as before Phase 2)
│       └─ → part_N_rendered.mp4    ← the user-facing output clip
│
├─ [POST-RENDER ASSEMBLY — unchanged]
│   └─ hook intro, asset intro/outro, logo
│
├─ [OUTPUT QA — unchanged]
└─ [METADATA — unchanged + manifest update]
```

### §3a. Phase 2 Does NOT Change Final Output Path

The final output clip (`part_N_rendered.mp4`) is produced by `render_part_smart()`
**in both `FEATURE_BASE_CLIP_FIRST=0` and `FEATURE_BASE_CLIP_FIRST=1` modes**.

When the flag is ON, `render_base_clip()` runs first as a **side-channel** and
produces `base_clip.mp4` — a separate file used for validation, manifest
population, and future Phase 3+ planning. After `render_base_clip()` completes
(or fails silently), `render_part_smart()` runs unconditionally as before.

**No user-visible output changes in Phase 2.**

| Flag state | base_clip.mp4 produced? | Final output producer | User sees change? |
|---|---|---|---|
| `FEATURE_BASE_CLIP_FIRST=0` (default) | No | `render_part_smart()` | No |
| `FEATURE_BASE_CLIP_FIRST=1` (dev/test) | Yes | `render_part_smart()` (unchanged) | No |

When the flag is ON, two encode passes run per part (base clip + final). This
is intentional — the base clip is a validation artifact. The motion path cache
is shared between both passes to limit the additional CPU cost.

---

## 4. Phase Roadmap: From Parallel Artifact to Overlay Composite

Phase 2 lays the foundation without changing visible output. The full progression:

```
Phase 2 (this plan):
  render_base_clip() → base_clip.mp4  [PARALLEL ARTIFACT, not used for final]
  render_part_smart() → final output  [UNCHANGED LEGACY PATH, always runs]
  Goal: establish base clip contract, manifest fields, feature flag infrastructure

Phase 3 (future — NOT in Phase 2):
  render_base_clip() → base_clip.mp4  [no subtitles, no text overlays]
  render_overlays(base_clip, ass, title, text_layers) → final_clip.mp4
  base_clip becomes the input to the final composite
  TimelineMap.output_duration is authoritative for overlay timing
  render_part_smart() is RETIRED from production path

Phase 4 (future — NOT in Phase 2 or 3):
  Subtitle timestamps converted from source-time to output-time using TimelineMap
  Subtitle display duration expanded to compensate for speed compression
  TTS narration aligned to base_clip output timeline
```

### §4a. Phase 3 Will Activate Overlay Composite

Phase 3 is the step that actually wires `base_clip.mp4` into the final output.
Phase 2 intentionally does NOT do this because:

1. **Double-encoding risk**: Using base_clip as input to a second encode pass
   introduces quality loss. Phase 3 must evaluate whether this is acceptable
   or whether lossless intermediate formats / single-pass composite are needed.

2. **Audio sync risk**: The base clip encodes audio with atempo. A second encode
   pass applying audio filters on top risks double atempo application.

3. **Test coverage gap**: Phase 2's parallel-artifact approach means the final
   output is still validated against the known-good legacy path. Phase 3 cannot
   activate without its own full smoke-test suite.

Phase 2 must NOT activate Phase 3/4 behavior. It creates the naming and manifest
infrastructure without coupling `base_clip.mp4` to the production output path.

---

## 5. Option Analysis: A / B / C

### OPTION A — Add flags to `render_part_smart()` to disable overlays

Add boolean params: `include_subtitles=True`, `include_title=True`,
`include_text_layers=True` that default to current behavior.
The "base clip" is produced by calling `render_part_smart()` with all set to False.

**Pros**:
- Minimal diff to existing code
- No new files
- `render_part_smart()` call site unchanged if defaults match
- All existing tests still pass trivially

**Cons**:
- `render_part_smart()` already has 30+ parameters — adds more
- "Base clip" concept is implicit, not a named contract
- Callers bear responsibility for remembering to set all three flags
- No explicit separation of "base" from "overlay" phase
- Future changes to base clip definition require finding the right flags
- Encourages gradual parameter creep

**Migration risk**: LOW — defaults preserve existing behavior  
**Code duplication risk**: NONE  
**Regression risk**: LOW — no render path changed if flags not passed  
**Testing complexity**: LOW — test that flags propagate, no re-encode test  
**Rollout complexity**: LOW — single call site change  

---

### OPTION B — New `render_base_clip()` that internally reuses helpers

Create a new top-level function `render_base_clip(...)` in `render_engine.py`
that calls the same internal helpers (`_sanitize_speed`, `_resolve_fps`,
`_resolve_codec`, `append_text_layer_filters` disabled, etc.) but constructs
its own vf_chain without the overlay filters.

**Pros**:
- Named concept: `render_base_clip` is explicit and searchable
- Base clip contract lives in one function body
- `render_part_smart()` completely unchanged
- Clean separation: base clip and overlay render are distinct call sites
- `BaseClipManifest.base_clip_path` has an obvious owner

**Cons**:
- Some filter-chain construction duplicated from `render_part()`
- Two code paths for the same underlying FFmpeg call type
- `render_motion_aware_crop()` signature duplication (motion crop path)
- Must keep in sync when `render_part()` FFmpeg flags change

**Migration risk**: LOW — legacy path untouched  
**Code duplication risk**: MEDIUM — ~80 lines of filter-chain construction shared  
**Regression risk**: VERY LOW — legacy path never called  
**Testing complexity**: MEDIUM — can test base clip has no ass filter in cmd  
**Rollout complexity**: LOW — add function, add call site in pipeline  

---

### OPTION C — Small wrapper around FFmpeg utilities, leaving render_part_smart untouched

Compose a thin base-render wrapper that directly builds an FFmpeg command
using the same utilities (`get_ffmpeg_bin`, `_resolve_codec`, etc.)
but is entirely separate from the `render_part` family.

**Pros**:
- Truly zero coupling to `render_part_smart`
- Cleanest architectural separation
- Easiest to unit test in isolation

**Cons**:
- Highest duplication: audio filter chain, BGM logic, codec flags,
  NVENC semaphore handling all duplicated
- Must track changes to `render_part` manually (risk of divergence)
- More code to write and maintain

**Migration risk**: LOW  
**Code duplication risk**: HIGH  
**Regression risk**: VERY LOW  
**Testing complexity**: MEDIUM  
**Rollout complexity**: MEDIUM  

---

### Recommendation: **OPTION B**

Option B is the safest minimal option. It:
- Names the concept explicitly (`render_base_clip`)
- Leaves `render_part_smart()` and `render_part()` completely untouched
- Creates a clean boundary for Phase 3 overlay separation
- Allows `BaseClipManifest.base_clip_path` to be written at a clearly
  owned call site
- Has moderate duplication (vf_chain construction) but no conceptual
  coupling back to the overlay path

The duplication is bounded and reviewable: it is ~80 lines of vf_chain
construction, not the full render_part() body. A comment in both places
noting that they share heritage is sufficient to prevent silent divergence.

---

## 6. Recommended Implementation Strategy

### Phase 2 implementation boundary

**IN scope for Phase 2**:
- Add `render_base_clip()` to `render_engine.py`
  - Same vf_chain as `render_part()` minus: `ass=`, `drawtext=`, `text_layers`
  - Speed from `TimelineMap.effective_speed`
  - Motion crop path preserved
  - Audio chain: atempo + loudnorm (inseparable from video encode)
  - NVENC semaphore handling preserved
  - Behind `FEATURE_BASE_CLIP_FIRST=0` env flag (default OFF)
- Add `base_clip_path`, `base_clip_duration`, `base_clip_fps`,
  `base_clip_width`, `base_clip_height`, `base_clip_has_audio`,
  `base_clip_created_at` to `BaseClipManifest`
- Write base clip manifest fields when base clip is produced
- Update `_render_part()` in render_pipeline.py to call `render_base_clip()`
  behind the feature flag
- New tests: base clip vf_chain has no `ass=` filter, no `drawtext=`,
  uses timeline.effective_speed, output file created

**OUT of scope for Phase 2**:
- Overlay-after-render workflow (Phase 3)
- Subtitle timestamp rescaling (Phase 3+)
- TTS alignment to output timeline (Phase 3+)
- Any API contract changes
- Any frontend changes
- Any DB schema changes
- Splitting `render_part_smart()` further
- Removing `render_part_smart()`

### Dual-path compatibility

Phase 2 is a **parallel-artifact** model, not a replacement model:

- `FEATURE_BASE_CLIP_FIRST=0` (default):
  Only `render_part_smart()` runs. Output unchanged. No base_clip.mp4.

- `FEATURE_BASE_CLIP_FIRST=1` (dev/validation):
  `render_base_clip()` runs first → produces `base_clip.mp4` (validation artifact).
  Then `render_part_smart()` runs unconditionally → produces the final output (unchanged).
  `base_clip.mp4` is NOT passed as input to `render_part_smart()`.
  The final output clip is identical to the `FEATURE_BASE_CLIP_FIRST=0` output.

**`render_part_smart()` always runs in Phase 2. It is never skipped.**

The feature flag controls whether a *second*, overlay-free encode pass happens
before the primary render. This is intentional: Phase 2 validates the base clip
contract without risking the production output path.

---

## 7. Required File Changes

| File | Change | Risk |
|---|---|---|
| `backend/app/services/render_engine.py` | Add `render_base_clip()` | LOW — additive |
| `backend/app/domain/manifests.py` | Add base_clip_* fields | LOW — additive |
| `backend/app/orchestration/render_pipeline.py` | Add feature-flagged call to `render_base_clip()` | LOW — behind flag |
| `backend/tests/test_render_base_clip.py` | New test file | LOW |
| `backend/tests/test_base_clip_manifest.py` | Add new field tests | LOW |

**No changes to**:
- `render_part_smart()`, `render_part()`, `render_motion_aware_crop()`
- `motion_crop.py` build_motion_path()
- `subtitle_engine.py`
- `audio_mix_service.py`
- `tts_service.py`
- Any route file
- Any model/schema file
- Any frontend file
- `db.py`

---

## 8. Manifest Evolution Plan

### New fields on `BaseClipManifest`

```python
# Added in Phase 2:
base_clip_path: Optional[str] = None          # absolute path to base_clip.mp4
base_clip_duration: Optional[float] = None    # ffprobe-verified output duration (s)
base_clip_fps: Optional[int] = None           # actual target fps used in render
base_clip_width: Optional[int] = None         # output width in pixels
base_clip_height: Optional[int] = None        # output height in pixels
base_clip_has_audio: Optional[bool] = None    # whether base clip has audio stream
base_clip_created_at: Optional[float] = None  # Unix timestamp (time.time())
```

### Population lifecycle

| Field | Written when | Writer |
|---|---|---|
| `base_clip_path` | After `render_base_clip()` succeeds | `_render_part()` in pipeline |
| `base_clip_duration` | After `probe_video_metadata(base_clip)` | same |
| `base_clip_fps` | Same probe call | same |
| `base_clip_width` | Same probe call | same |
| `base_clip_height` | Same probe call | same |
| `base_clip_has_audio` | Same probe call | same |
| `base_clip_created_at` | After render completes | same |

All fields are `Optional[X] = None`. If the feature flag is OFF or base clip
rendering fails (never raises), they remain None. Manifest read-back is not
in Phase 2 — pipeline decisions still use payload fields.

### Cleanup lifecycle

`base_clip.mp4` lives in `work_dir/part_N/base_clip.mp4`. It is cleaned up
by the existing `prune_render_temp_dirs()` background thread (age-based
cleanup). No additional cleanup logic needed in Phase 2.

### Serialization

All new fields follow the existing `to_dict()` / `from_dict()` pattern.
`None` serializes as `None`. `from_dict()` uses `.get()` with None default,
so existing manifests without these fields round-trip correctly.

---

## 9. Compatibility Strategy

### Dual-path via environment flag

```python
# render_pipeline.py (Phase 2 addition)
_FEATURE_BASE_CLIP_FIRST = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
```

**Flag location**: Top of `render_pipeline.py` (with other config constants).  
**Flag default**: `"0"` (feature off, legacy path).  
**Flag type**: Environment variable — no DB, no API, no frontend touch required.

### Fallback strategy

If `FEATURE_BASE_CLIP_FIRST=1` and `render_base_clip()` raises:
1. Log warning with job_id and part_no
2. `_p1_manifest.base_clip_path` remains None (correct)
3. Continue to `render_part_smart()` unconditionally — no clip is lost
4. The base clip failure has zero impact on the final output

```python
# Pseudocode — Phase 2 execution model:
if _FEATURE_BASE_CLIP_FIRST:
    try:
        _base_clip_path = render_base_clip(...)
        _p1_manifest.base_clip_path = str(_base_clip_path)
        # ... probe + update manifest fields ...
    except Exception as _bc_exc:
        logger.warning("base_clip_render_failed part=%d: %s; skipping artifact", idx, _bc_exc)
        _base_clip_path = None

# render_part_smart() ALWAYS runs — it is the source of the final output:
render_part_smart(...)  # unchanged, unconditional
```

There is no "fall back to legacy path" language because `render_part_smart()`
IS the only path to the final output in Phase 2. It is never replaced.

### Rollback strategy

1. Set `FEATURE_BASE_CLIP_FIRST=0` (no restart required if loaded at startup)
2. Or: cherry-revert the pipeline call site (2 lines)
3. `render_base_clip()` function can remain dormant in render_engine.py
4. Manifest fields remain None — no manifest schema migration needed

### Migration gating

Phase 2 internal testing: `FEATURE_BASE_CLIP_FIRST=1` in dev environment.  
Phase 2 production: flag stays at `0` until Phase 3 is ready.  
Phase 3 activation: switches flag to `1` by default after overlay separation.

---

## 10. Migration Strategy

### Step-by-step implementation order

1. **Add base_clip_* fields to `BaseClipManifest`** and update `to_dict()` /
   `from_dict()` / tests. This is purely additive — zero behavior change.

2. **Write `render_base_clip()` in `render_engine.py`**. At this point it is
   dead code — nothing calls it. All tests still pass.

3. **Add `FEATURE_BASE_CLIP_FIRST` flag to `render_pipeline.py`** and wire it
   to call `render_base_clip()` with fallback to legacy path.

4. **Write tests for `render_base_clip()`**: verify no `ass=` in vf_chain,
   no `drawtext=` in vf_chain, speed is from timeline, output path created
   (mocked FFmpeg).

5. **Manual smoke test**: Enable flag, run a real render, verify:
   - `base_clip.mp4` appears in `work_dir/part_N/`
   - Manifest fields populated
   - Final rendered output unchanged from legacy path
   - No regressions

6. **Commit behind flag at OFF**.

---

## 11. Test Strategy

### Unit tests — no FFmpeg required

```
test_render_base_clip.py:
  ✓ render_base_clip() FFmpeg command contains NO 'ass=' filter
  ✓ render_base_clip() FFmpeg command contains NO 'drawtext=' filter
  ✓ render_base_clip() FFmpeg command contains NO text_layer references
  ✓ render_base_clip() uses timeline.effective_speed for setpts
  ✓ render_base_clip() uses timeline.effective_speed for atempo
  ✓ render_base_clip() still applies crop/reframe filters
  ✓ render_base_clip() still applies fps= filter as last vf filter
  ✓ render_base_clip() still applies effect (eq/unsharp)
  ✓ render_base_clip() handles motion_aware_crop=True path
  ✓ render_base_clip() handles motion_aware_crop=False path
  ✓ render_base_clip() fallback: raises → returns None gracefully

test_base_clip_manifest.py (additions):
  ✓ base_clip_path None by default
  ✓ base_clip_duration None by default
  ✓ base_clip_* fields serialize/deserialize correctly
  ✓ to_dict() JSON-serializable with new fields
  ✓ from_dict() handles missing base_clip_* fields (backward compat)
```

### Integration-light tests (mock FFmpeg command)

```
  ✓ FEATURE_BASE_CLIP_FIRST=1: render_base_clip() called with correct args
  ✓ FEATURE_BASE_CLIP_FIRST=0: legacy render_part_smart() called unchanged
  ✓ base_clip_path written to manifest on success
  ✓ base_clip_path remains None if render_base_clip() raises
  ✓ fallback to legacy path on render_base_clip() exception
  ✓ TimelineMap.effective_speed matches render_part_smart playback_speed arg
```

### Smoke validation (real render, FEATURE_BASE_CLIP_FIRST=1)

```
  ✓ base_clip.mp4 exists in work_dir/part_N/  (parallel artifact)
  ✓ base_clip duration ≈ source_duration / effective_speed (within 5%)
  ✓ base_clip has video stream
  ✓ base_clip has audio stream (if source has audio)
  ✓ base_clip fps matches target_fps
  ✓ no subtitle text visible in base_clip.mp4  (visual check)
  ✓ part_N_rendered.mp4 (final output) produced by render_part_smart()
  ✓ final output is byte-comparable to flag=OFF reference render
  ✓ render_part_smart() was called — not skipped — even with flag=1
```

### Exclusions

- No real YouTube download in tests
- No slow FFmpeg encode in unit tests (mock the command)
- No flaky timing assertions (use `pytest.approx` with generous rel tolerance)
- No tests that require optional dependencies (MediaPipe, DeepFilterNet)

---

## 12. Risk Checklist

| Risk | Severity | Mitigation |
|---|---|---|
| Two encode passes when flag=1 (base clip + final) | MEDIUM | Both encodes are independent; base clip is discardable if render time is too high; flag is OFF by default |
| Double-encoding quality loss in final output | NONE in Phase 2 | Final output is always produced by `render_part_smart()` from the raw cut, not from base_clip.mp4; no quality chain |
| Double encode in Phase 3 (future risk) | HIGH — Phase 3 concern | Document now: Phase 3 must decide whether base_clip → overlay composite introduces a lossy second pass |
| Render time increase when flag=1 | MEDIUM | Two encode passes per part; motion path cache shared; flag is OFF by default in production |
| Audio sync drift in base clip | LOW | Base clip audio uses same atempo path; mismatch only if encode differs from render_part — must not happen |
| Audio double-atempo risk (Phase 3) | HIGH — Phase 3 concern | If Phase 3 re-encodes base_clip with audio filters, atempo may be applied twice; document for Phase 3 review |
| Subtitle filter order dependency | HIGH | `ass-before-setpts` order preserved in all paths; `render_base_clip()` has NO ass= filter; `render_part_smart()` unchanged |
| Duplicated crop/reframe | LOW | `render_base_clip()` calls same motion_crop helper; motion path cache prevents double MediaPipe scan |
| Artifact cleanup lifecycle | LOW | `base_clip.mp4` covered by existing `prune_render_temp_dirs()`; no new cleanup logic needed |
| Output duration mismatch | MEDIUM | Probe base_clip duration after render; write to manifest; compare to TimelineMap.output_duration; log discrepancy |
| Hidden playback_speed recomputation in base clip | HIGH | `render_base_clip()` must use `TimelineMap.effective_speed`; must NOT re-derive speed from payload |
| AI timing assumptions | LOW | AI plan uses source timeline; Phase 2 does not change AI plan behavior |
| Feature flag not defaulting OFF | HIGH | Code review gate: default MUST be "0" before merge |
| `render_base_clip()` signature drift from `render_part()` | MEDIUM | Explicit comment in both functions; test both use same vf primitives |
| NVENC semaphore not acquired in base clip path | HIGH | `render_base_clip()` must replicate NVENC semaphore handling from `render_part()` |
| Windows path escaping in vf_chain | HIGH | Use same `_safe_filter_path()` helper; test on Windows (the target platform) |
| Motion crop cache miss on base clip | MEDIUM | Use same `_motion_cache_key` derivation as `render_part_smart()` call site |

---

## 13. Exact Implementation Order

```
Step 1 — BaseClipManifest fields [~30 min]
  File: backend/app/domain/manifests.py
  - Add 7 Optional fields with None defaults
  - Update to_dict() / from_dict()

Step 2 — Manifest tests [~20 min]
  File: backend/tests/test_base_clip_manifest.py
  - Add round-trip tests for new fields
  - Add backward-compat test (from_dict with old dict missing fields)

Step 3 — render_base_clip() [~90 min]
  File: backend/app/services/render_engine.py
  - New function after render_part_smart()
  - Signature: same as render_part_smart() minus subtitle_ass, title_text,
    text_layers; add timeline: TimelineMap parameter
  - vf_chain: omit ass=, drawtext=, text_layer filters
  - speed = timeline.effective_speed (not raw playback_speed)
  - motion crop path: calls render_motion_aware_crop() without subtitle_file
    and without title_text
  - NVENC semaphore handling: identical to render_part_smart()
  - Return: output_path (str) on success, raise on failure

Step 4 — render_base_clip() unit tests [~60 min]
  File: backend/tests/test_render_base_clip.py
  - Mock _run_ffmpeg_with_retry and render_motion_aware_crop
  - Assert vf_chain contents (no ass=, no drawtext=)
  - Assert speed comes from timeline.effective_speed
  - Assert fps= is last filter

Step 5 — Feature flag + pipeline integration [~45 min]
  File: backend/app/orchestration/render_pipeline.py
  - Add _FEATURE_BASE_CLIP_FIRST constant (default "0")
  - BEFORE render_part_smart() call site: add try/except block for render_base_clip()
  - On success: write base_clip_* fields to manifest
  - On failure: log warning, base_clip_path=None, continue
  - render_part_smart() call is UNCHANGED and ALWAYS runs after the base clip block
  - Probe base_clip output duration + write to manifest on success only

Step 6 — Integration tests [~30 min]
  File: backend/tests/test_render_base_clip.py (additions)
  - Test feature flag behavior
  - Test fallback on exception

Step 7 — Full test suite [~5 min]
  python -m pytest tests/ --tb=short -q
  Expect: same 8 pre-existing failures, 0 new failures

Step 8 — Manual smoke test [~20 min]
  Set FEATURE_BASE_CLIP_FIRST=1 and run a real render.
  Verify:
  - work_dir/part_N/base_clip.mp4 exists
  - manifest.json contains base_clip_path, base_clip_duration, base_clip_fps
  - part_N_rendered.mp4 (final output) is produced by render_part_smart()
  - final output is identical to a reference render with flag OFF
  - no subtitle text visible in base_clip.mp4 (visual check)
  - base_clip duration ≈ source_duration / effective_speed (within 5%)

Step 9 — Commit [feature flag OFF]
  git commit -m "phase 2 base clip first render"
```

---

## 14. Rollback Strategy

### If Phase 2 causes regressions after merge:

1. **Immediate**: set `FEATURE_BASE_CLIP_FIRST=0` (env var, no deploy needed)
2. **Short-term**: revert pipeline call site (~10 lines) — safe, legacy path
   is not removed
3. **Last resort**: revert Step 5 commit — `render_base_clip()` stays in
   render_engine.py as dead code, zero impact on production

### What cannot regress in Phase 2:

- `render_part_smart()` is **not modified**
- `render_part()` is **not modified**
- `render_motion_aware_crop()` is **not modified**
- `motion_crop.py` is **not modified**
- `subtitle_engine.py` is **not modified**
- `audio_mix_service.py` is **not modified**
- All API routes are **not modified**
- DB schema is **not modified**
- Frontend is **not modified**
- Feature flag OFF = identical behavior to Phase 1

---

## 15. What MUST NOT Change in Phase 2

| Constraint | Reason |
|---|---|
| `ass-before-setpts` filter order | Subtitle sync invariant — must remain unchanged in all render paths |
| `render_part_smart()` signature | Many call sites; any change breaks all |
| `render_part()` filter chain | Legacy path must be preserved exactly |
| `_sanitize_speed()` clamp [0.5, 1.5] | Must match TimelineMap._SPEED_MAX; already fixed in Phase 1.5 |
| API contracts | No schema changes, no route changes |
| Frontend | No JS/HTML/CSS changes |
| DB schema | No new columns; manifests are filesystem-only |
| AI plan structure | AIEditPlan untouched |
| Subtitle timing | No timestamp rescaling in Phase 2 |
| TTS generation | No changes to narration generation |
| Audio mix | No changes to audio_mix_service.py |
| FFmpeg command structure (legacy) | Must be identical to current production |
| Feature flag default | MUST default to "0" (OFF) before any merge |

---

## 16. Review Doc Synchronization

**Updated as of 2026-05-22 (Phase 2.0 sync)**:

| Doc | Section | Status |
|---|---|---|
| VIDEO_PIPELINE_REVIEW.md | Subtitle Sync Risks | Updated — `ass-before-setpts` confirmed correct; display duration compression documented |
| VIDEO_PIPELINE_REVIEW.md | Audio-Video Sync | Updated — Phase 0 atempo fix confirmed; marked resolved |
| VIDEO_PIPELINE_REVIEW.md | Stage 1 (Source Acquisition) | Updated — Phase 0 socket_timeout=60 noted |
| VIDEO_PIPELINE_REVIEW.md | Output Quality Risks | Updated — items 1 and 2 reflect corrected status |
| TECHNICAL_DEBT_REPORT.md | C2 (Subtitle timestamps) | Updated — Partially Resolved; display duration compression documented |
| TECHNICAL_DEBT_REPORT.md | C3 (TTS desync) | Updated — Resolved (Phase 0) |
| TECHNICAL_DEBT_REPORT.md | H6 (YouTube timeout) | Updated — Partially Resolved (Phase 0) |
| BRUTAL_REVIEW_SUMMARY.md | What Is Dangerous | Updated — subtitle/TTS/download status corrected |
| BRUTAL_REVIEW_SUMMARY.md | What Will Break First | Updated |
| BRUTAL_REVIEW_SUMMARY.md | Final Verdict priorities | Updated — Phase 0 items removed/marked done |

---

## Summary

**Recommended option**: B — New `render_base_clip()` function that leaves
the entire legacy render path fully intact and untouched.

**Phase 2 core contract**:
- `base_clip.mp4` is a **parallel validation artifact**, never a final output input.
- `render_part_smart()` runs **unconditionally** in Phase 2; it is never replaced.
- Feature flag `FEATURE_BASE_CLIP_FIRST` defaults to `"0"` (OFF).
- No user-visible output change in Phase 2.

**Main architectural risks**:
1. NVENC semaphore must be replicated in `render_base_clip()` (HIGH)
2. Feature flag must default OFF — mandatory code review gate (HIGH)
3. Two encode passes when flag=1 increases render time — document clearly (MEDIUM)
4. Phase 3 double-encode quality and audio-sync risk — document now, solve in Phase 3 (HIGH — future)
5. Windows path escaping in vf_chain needs explicit test (HIGH on target platform)
6. `render_base_clip()` must use `TimelineMap.effective_speed`, not re-derive from payload (HIGH)

**Compatibility strategy**: Parallel-artifact model behind `FEATURE_BASE_CLIP_FIRST` env var.
Default OFF. `render_part_smart()` call site completely unchanged.

**Testing strategy**: Unit tests with mocked FFmpeg command inspection (assert no `ass=`,
no `drawtext=`, speed from timeline). Integration-light tests for feature flag behavior.
Smoke test: flag=1 produces base_clip.mp4 AND final output identical to flag=0 reference.
No real YouTube, no heavy FFmpeg in CI.

**Phase 3 entry condition**: `base_clip.mp4` has been validated as timing-accurate
(duration within 2% of `TimelineMap.output_duration`) across multiple real renders.
Only then should Phase 3 attempt to wire `base_clip.mp4` into the final output path.
