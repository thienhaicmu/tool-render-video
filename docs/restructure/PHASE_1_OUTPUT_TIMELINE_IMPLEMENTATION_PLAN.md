# PHASE 1 — Output Timeline Architecture Foundation
## Implementation Plan

**Branch**: `restructure/output-timeline-architecture`
**Status**: Plan only — no code changes.
**Source of truth**: docs/review/BRUTAL_REVIEW_SUMMARY.md, BACKEND_REVIEW.md, VIDEO_PIPELINE_REVIEW.md, TECHNICAL_DEBT_REPORT.md, PROJECT_FLOW.md

---

## 1. Current Timing Flow

The pipeline operates on two implicit timelines that are never formally named or documented. This is the root cause of subtitle drift, TTS desync, and future maintenance hazards.

### Source Timeline
All timestamps are expressed in seconds from the beginning of the source video file.

```
source.mp4  0s ─────────────────────────────────────── 3600s
                 ↑ seg["start"]          ↑ seg["end"]
                 │                       │
                 ↑ _effective_start      │
                   (seg["start"] + _trim_offset from silence detection)
```

### Output Timeline
The rendered output is shorter because of speed adjustment and silence trimming.

```
output_part_n.mp4  0s ─────────────────── ~52s
                                           ↑
                   source_duration / effective_speed - micro_pacing_trim
```

### The Conversion Formula (implicit, spread across 7 call sites)
```
output_duration = (seg["end"] - _effective_start) / effective_speed - _micro_pacing_trim_sec
effective_speed = payload.playback_speed + _PLATFORM_PROFILES[target_platform]["speed_delta"]
```

### How Subtitle Alignment Currently Works (implicit contract)
The FFmpeg vf_chain in `render_engine.py` places filters in this exact order:
```
ass='{ass_path}'          ← subtitle rendered at SOURCE timeline timestamps
setpts=PTS/{speed:.4f}    ← re-clocks all frames to output timeline
fps={target_fps}
```
Because `ass` runs before `setpts`, the subtitle timestamps in the ASS file are in source-clip time (0s to ~clip_duration), and `setpts` shifts the frames so that a frame that was at t=10s in the source clip now appears at t=10s/1.15=8.7s in the output — but the subtitle is already drawn on the frame at that point. This implicit contract makes subtitle timing correct today, but is:
- Undocumented
- Fragile (any reordering of vf_chain breaks it)
- Not applicable to audio (narration, TTS) which doesn't go through the vf_chain
- Not applicable to any non-FFmpeg consumer of timing data (AI, thumbnails, reports)

---

## 2. Exact Places Where Source Timeline Is Used

### render_pipeline.py

| Line | Usage | Notes |
|------|-------|-------|
| 3591 | `detect_silence_trim_offset(str(source_path), seg["start"], seg["end"])` | Source timestamps passed directly |
| 3613 | `_effective_start = seg["start"] + _trim_offset` | Source timeline anchor point |
| 3621 | `detect_bad_first_frame(str(source_path), _effective_start, seg["end"])` | Source timestamps |
| 3630 | `_effective_start = seg["start"] + _trim_offset` (with visual trim) | Source timeline |
| 3654 | `cut_video(str(source_path), str(raw_part), _effective_start, seg["end"], ...)` | Source cut boundaries |
| 3690–3697 | `slice_srt_by_time(str(full_srt), str(srt_part), _effective_start, seg["end"], ..., apply_playback_speed=False)` | SRT sliced at source timestamps; timestamps rebased to 0 within source window |
| 3721–3725 | Logging block: `"part_start": seg["start"], "part_end": seg["end"], "effective_start": _effective_start` | Timing telemetry all in source time |
| 4030–4031 | `seg.get("variant_playback_speed") or getattr(payload, "playback_speed", 1.07)` | Per-variant speed (not platform-adjusted) used inline |
| 4309–4312 | Speed calculation at `render_part_smart()` call site: `seg.get("variant_playback_speed") or max(0.5, min(1.5, float(payload.playback_speed or 1.07) + _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0)))` | Speed computed inline, not from single source of truth |
| 4403 | `generate_narration_audio(...)` using subtitle text from source-sliced SRT | Audio generated from source-timeline text |
| 4495 | Second `generate_narration_audio(...)` call (translated subtitle path) | Same issue |
| 4565–4570 | `mix_narration_audio(..., playback_speed=_get_effective_playback_speed(payload, _target_platform))` | Phase 0 fix: atempo now applied but no manifest records this decision |
| 4697 | `_effective_duration = max(0.0, float(seg["end"]) - float(_effective_start))` | Output duration computed from source timestamps |
| 4716–4718 | `_expected_final_duration = (_effective_duration / _render_speed) - _micro_pacing_trim_sec + _remotion_intro_sec` | Output timeline math done inline, not from a manifest |

### subtitle_engine.py

| Line | Function | Usage |
|------|----------|-------|
| ~147–196 | `slice_srt_by_time()` | Receives source timestamps (`start_sec`, `end_sec`). When `apply_playback_speed=False`, output timestamps are in the rebased source window (0 to clip_duration). The ASS file produced from this is correct only because of the vf_chain filter order. |
| ~82–140 | `srt_to_ass_bounce()`, `srt_to_ass_karaoke()` | Consume the sliced SRT — timestamps assumed to be in source-clip time (0-based). No awareness of output timeline. |

### tts_service.py

| Function | Usage |
|----------|-------|
| `generate_narration_audio()` | Receives text extracted from the source-timeline SRT. The natural speaking rate of the generated audio corresponds to the source clip duration. The video is then played at `effective_speed` (e.g. 1.15x), so the audio runs short unless atempo is applied in `mix_narration_audio()`. Phase 0 fixed the mixing step but not the root recording: the TTS duration still encodes source-timeline assumptions. |

### render_engine.py

| Location | Usage |
|----------|-------|
| vf_chain build (~line 986–1013) | `ass` filter uses source-timeline ASS, `setpts=PTS/{speed}` converts frames to output timeline. The implicit contract that makes this work lives here. |
| `render_part_smart()` signature | `playback_speed: float = 1.07` parameter accepted but called with inline-computed value at line 4309–4312, not from a manifest |

### ai_director.py / AIEditPlan

The AI plan is created once (line 2969) and contains:
- `selected_segments` — source timeline timestamps
- `clip_cover_hints` — source-timeline thumbnail hints
- `beat_execution` — beat timestamps in source time
- `subtitle_execution_promotion`, `camera_execution_promotion` — advisory signals with no timeline reference

No output timeline timestamps exist anywhere in the AI plan. If the AI wants to say "this moment at output t=5.2s is important", it cannot — it can only say "source t=5.98s" and the conversion is implicit.

---

## 3. Exact Places Where playback_speed Changes the Output Timeline

### Speed Decision Chains (4 separate patterns — this is the fragmentation problem)

**Pattern A** — Single source of truth (correct):
```python
# render_pipeline.py:389
def _get_effective_playback_speed(payload, target_platform: str) -> float:
    platform_delta = _PLATFORM_PROFILES.get(target_platform, {}).get("speed_delta", 0.0)
    return max(0.5, min(1.5, float(payload.playback_speed or 1.0) + platform_delta))

# Used at:
# line 3688: _eff_speed = _get_effective_playback_speed(payload, _target_platform)  ← subtitle
# line 4570:  playback_speed=_get_effective_playback_speed(payload, _target_platform)  ← narration mix
# line 4698: _render_speed = _get_effective_playback_speed(payload, _target_platform)  ← validation
```

**Pattern B** — Inline re-computation (fragmented, at render call site):
```python
# render_pipeline.py:4309–4312  ← render_part_smart() call
playback_speed=float(
    seg.get("variant_playback_speed")
    or max(0.5, min(1.5, float(payload.playback_speed or 1.07)
           + _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0)))
),
```
This duplicates the formula from `_get_effective_playback_speed()` rather than calling it, and uses `1.07` as default instead of `1.0`.

**Pattern C** — Variant speed from dict (multi-variant mode):
```python
# render_pipeline.py:429, 473, 479, 485
# _build_variant_segments() sets variant_playback_speed on each segment dict:
agg["variant_playback_speed"]  = round(min(1.15, base_speed + 0.05), 3)
bal["variant_playback_speed"]  = base_speed
story["variant_playback_speed"] = round(max(0.97, base_speed - 0.05), 3)
# This speed bypasses platform_delta — it's the base speed only
```

**Pattern D** — Hook intro speed (separate path):
```python
# render_pipeline.py:4173
_hook_spd = max(0.5, min(1.5, float(payload.playback_speed or 1.07)))
# No platform delta applied here
```

### Application Points in FFmpeg
- **Video speed**: `setpts=PTS/{speed:.4f}` in vf_chain (render_engine.py ~line 1010)
- **Audio speed**: `atempo={speed:.4f}` applied to audio stream (render_engine.py, same vf_chain build)
- **Narration speed**: `atempo={speed:.4f}` in `mix_narration_audio()` (audio_mix_service.py — Phase 0 fix)

---

## 4. Where TimelineMap Should Be Created

`TimelineMap` is a pure data object that formalizes the source→output coordinate transformation for one clip. It must be created **after** the silence trim detection and bad-first-frame scan, but **before** `slice_srt_by_time()`, `generate_narration_audio()`, and `render_part_smart()`.

**Exact creation point**: `render_pipeline.py`, after line 3649 (after `_effective_start` is finalized), before line 3654 (`cut_video()` call).

```
render_pipeline.py per-part loop
  ├── line 3591: detect_silence_trim_offset()  → _trim_offset
  ├── line 3613: _effective_start = seg["start"] + _trim_offset
  ├── line 3621: detect_bad_first_frame()       → _visual_trim
  ├── line 3630: _effective_start updated (if visual trim applied)
  │
  │   ← TIMELINE MAP CREATED HERE ←
  │   timeline = TimelineMap(
  │       source_start=_effective_start,
  │       source_end=seg["end"],
  │       effective_speed=_get_effective_playback_speed(payload, _target_platform),
  │       trim_offset=_trim_offset,
  │   )
  │
  ├── line 3654: cut_video()          uses timeline.source_start, timeline.source_end
  ├── line 3690: slice_srt_by_time()  uses timeline.source_start, timeline.source_end
  ├── line 4287: render_part_smart()  uses timeline.effective_speed
  └── line 4565: mix_narration_audio() uses timeline.effective_speed
```

For **multi-variant mode**, each variant has its own `variant_playback_speed` from `_build_variant_segments()`. The `TimelineMap` for a variant clip must use `seg.get("variant_playback_speed")` as the base speed (before platform delta), not `payload.playback_speed`.

---

## 5. Where BaseClipManifest Should Be Created

`BaseClipManifest` is a per-clip record written to disk as JSON. It captures all timing decisions made for that clip so that:
- Downstream stages (subtitle, TTS, audio mix) can read confirmed values instead of recomputing
- Debug logs have a single authoritative record
- Future phases (subtitle repositioning, output QA, AI feedback) can cross-reference

**Creation point**: Immediately after `TimelineMap` is constructed (same location, line ~3650).

**Write location**: `work_dir/part_{n}/manifest.json`

The manifest must be written before `cut_video()` runs so that even if the render crashes, the timing decisions are on disk.

---

## 6. Proposed New Files and Classes

### New file: `backend/app/models/timeline.py`

This file must contain only pure data classes — no FFmpeg knowledge, no subprocess calls, no I/O other than JSON serialization.

#### Class: `TimelineMap`

```
TimelineMap
  source_start: float       # effective start in source video seconds (after silence/frame trim)
  source_end: float         # end in source video seconds (= seg["end"])
  source_duration: float    # computed: source_end - source_start
  effective_speed: float    # clamped [0.5, 1.5] — exact value used for setpts and atempo
  trim_offset: float        # silence trim applied (seconds into the raw segment)
  output_duration: float    # computed: source_duration / effective_speed
  
  Methods:
    source_to_output(source_t: float) -> float
      # Convert a source-timeline timestamp (relative to source_start) to output timeline
      # (source_t - source_start) / effective_speed
    
    output_to_source(output_t: float) -> float  
      # Inverse: output_t * effective_speed + source_start
    
    to_dict() -> dict
      # JSON-serializable representation
    
    @classmethod
    from_dict(d: dict) -> TimelineMap
      # Deserialize from manifest
```

#### Class: `BaseClipManifest`

```
BaseClipManifest
  job_id: str
  part_no: int
  
  # Source location
  source_path: str          # absolute path to source.mp4
  source_start: float       # = timeline.source_start
  source_end: float         # = timeline.source_end
  
  # Speed decisions
  payload_speed: float      # payload.playback_speed (creator setting)
  platform: str             # _target_platform
  platform_delta: float     # _PLATFORM_PROFILES[platform]["speed_delta"]
  effective_speed: float    # = timeline.effective_speed
  
  # Variant (multi-variant mode)
  variant_type: str | None  # "aggressive" | "balanced" | "story_first" | None
  variant_speed: float | None  # seg["variant_playback_speed"] if multi-variant
  
  # Trim decisions
  silence_trim_offset: float   # _trim_offset from detect_silence_trim_offset()
  visual_trim_offset: float    # _visual_trim from detect_bad_first_frame()
  
  # Derived
  timeline: TimelineMap
  
  # AI involvement
  ai_enabled: bool          # payload.ai_director_enabled
  ai_mode: str | None       # _ai_edit_plan.mode if plan exists
  ai_selected: bool         # whether AI selected this segment (vs scorer)
  ai_speed_hint: float | None  # if AI plan recommended a speed adjustment
  
  # File paths (filled in progressively)
  cut_path: str | None      # set after cut_video()
  srt_path: str | None      # set after slice_srt_by_time()
  ass_path: str | None      # set after srt_to_ass_*()
  narration_path: str | None  # set after generate_narration_audio()
  rendered_path: str | None   # set after render_part_smart()
  
  Methods:
    to_dict() -> dict
    
    @classmethod
    from_dict(d: dict) -> BaseClipManifest
    
    write(path: str) -> None
      # Atomic write: write to path + ".tmp", then os.replace()
    
    @classmethod
    read(path: str) -> BaseClipManifest
```

### New file: `backend/app/services/manifest_writer.py`

Single responsibility: write and read `BaseClipManifest` JSON files from the render work directory.

```
Functions:
  manifest_path(work_dir: Path, part_no: int) -> Path
    # Returns work_dir / f"part_{part_no}" / "manifest.json"
  
  write_manifest(work_dir: Path, manifest: BaseClipManifest) -> Path
    # Atomic write. Returns path written.
  
  read_manifest(work_dir: Path, part_no: int) -> BaseClipManifest | None
    # Returns None if file missing or corrupt (never raises).
  
  read_all_manifests(work_dir: Path) -> list[BaseClipManifest]
    # Reads all part_*/manifest.json files. Skips missing/corrupt.
```

No other files are created in Phase 1.

---

## 7. Exact Integration Points

### Integration Point 1: render_pipeline.py — TimelineMap creation

**Location**: Between line 3649 (end of trim/frame scan block) and line 3651 (`upsert_job_part` call for CUTTING stage).

**What changes**: Insert `TimelineMap` construction. No existing calls are changed yet.

```python
# AFTER: _effective_start finalized
# BEFORE: upsert_job_part(... JobPartStage.CUTTING ...)
timeline = TimelineMap(
    source_start=_effective_start,
    source_end=float(seg["end"]),
    effective_speed=_get_effective_playback_speed(payload, _target_platform),
    trim_offset=float(_trim_offset),
    visual_trim_offset=float(_visual_trim) if _visual_trim else 0.0,
    variant_speed=seg.get("variant_playback_speed"),
    platform=_target_platform,
    payload_speed=float(payload.playback_speed or 1.07),
)
```

### Integration Point 2: render_pipeline.py — BaseClipManifest creation and write

**Location**: Immediately after `TimelineMap` construction.

**What changes**: Construct manifest and write to disk. No existing calls changed.

```python
_manifest = BaseClipManifest(
    job_id=job_id,
    part_no=idx,
    source_path=str(source_path),
    timeline=timeline,
    variant_type=seg.get("variant_type"),
    variant_speed=seg.get("variant_playback_speed"),
    ai_enabled=bool(getattr(payload, "ai_director_enabled", False)),
    ai_mode=getattr(_ai_edit_plan, "mode", None) if _ai_edit_plan else None,
    ai_selected=_ai_edit_plan is not None and idx in getattr(_ai_edit_plan, "selected_segment_indices", set()),
    ai_speed_hint=None,   # Phase 2 will populate from AI plan
    cut_path=None,        # filled after cut_video()
    srt_path=None,        # filled after slice_srt_by_time()
    ass_path=None,
    narration_path=None,
    rendered_path=None,
)
write_manifest(work_dir, _manifest)
```

### Integration Point 3: render_pipeline.py — manifest path fields updated as files are created

**Location A** (after `cut_video()`, ~line 3654):
```python
_manifest.cut_path = str(raw_part)
write_manifest(work_dir, _manifest)   # atomic overwrite
```

**Location B** (after `slice_srt_by_time()`, ~line 3690):
```python
_manifest.srt_path = str(srt_part)
write_manifest(work_dir, _manifest)
```

**Location C** (after `srt_to_ass_*()`, ASS conversion):
```python
_manifest.ass_path = str(ass_part)
write_manifest(work_dir, _manifest)
```

**Location D** (after `generate_narration_audio()`, ~line 4403/4495):
```python
_manifest.narration_path = str(_part_subtitle_voice_path)
write_manifest(work_dir, _manifest)
```

**Location E** (after `render_part_smart()`, ~line 4320):
```python
_manifest.rendered_path = str(final_part)
write_manifest(work_dir, _manifest)
```

### Integration Point 4: Debug log enrichment

**Location**: The `playback_speed_resolution` log at line 4721–4729.

**What changes**: Add `manifest_path` to the log so operators can cross-reference the JSON file.

```python
_job_log(
    effective_channel, job_id,
    f"playback_speed_resolution part={idx} "
    f"payload_speed={float(payload.playback_speed or 1.0):.4f} "
    f"platform_delta={...:.4f} "
    f"effective_speed={_render_speed:.4f} "
    f"source_duration={timeline.source_duration:.3f}s "    # NEW
    f"output_duration={timeline.output_duration:.3f}s "    # NEW
    f"manifest={str(manifest_path(work_dir, idx))}",       # NEW
    kind="debug",
)
```

---

## 8. What Must NOT Be Changed in Phase 1

These constraints are hard. Violating any of them requires a separate phase plan.

| Area | What must not change | Why |
|------|---------------------|-----|
| `render_engine.py` vf_chain | Filter order `ass → setpts → fps` must remain unchanged | The implicit source-timeline contract that makes subtitles correct depends on this order. Phase 2 will make this explicit. |
| `slice_srt_by_time()` signature | `apply_playback_speed=False` call in render_pipeline.py must remain | Same filter-order dependency. |
| `render_part_smart()` signature | No new parameters | API contract for the renderer must not change in Phase 1. |
| `mix_narration_audio()` signature | Already correct after Phase 0 fix | Do not change again. |
| Any existing API endpoint | `/api/render/process`, `/api/jobs/*`, etc. | Frontend depends on these. |
| `schemas.py:RenderRequest` | No new fields | Do not change the request schema. |
| DB schema | `jobs`, `job_parts` tables | No new columns in Phase 1. |
| `_get_effective_playback_speed()` | Do not rename or move yet | Other call sites depend on it. Phase 2 will consolidate. |
| `_build_variant_segments()` | Speed logic inside must not change | Variant speed behavior unchanged in Phase 1. |
| `ai_director.py` / `AIEditPlan` | No changes to AI plan structure | AI changes are Phase 3+. |
| Existing test files | No modifications to any test_*.py file outside of new test additions | Must not break passing tests. |
| `downloader.py` | No changes | Phase 0 fix is complete. |
| Cleanup/temp file logic | `_safe_unlink()`, `prune_render_temp_dirs()` | Manifest files must be excluded from cleanup rules in Phase 2. In Phase 1, manifests are not cleaned up (they live and die with work_dir). |

---

## 9. Test Plan

### New test file: `backend/tests/test_timeline_map.py`

#### Group A: TimelineMap math

| Test | What it verifies |
|------|-----------------|
| `test_output_duration_at_1x_speed` | `source_duration=30.0, speed=1.0 → output_duration=30.0` |
| `test_output_duration_at_115x_speed` | `source_duration=30.0, speed=1.15 → output_duration≈26.09s` |
| `test_output_duration_at_107_plus_008_tiktok` | `speed=1.15 (1.07+0.08 TikTok) → matches _get_effective_playback_speed output` |
| `test_source_to_output_at_midpoint` | `source_t=15.0 in a 30s clip at 1.15x → output_t≈13.04s` |
| `test_output_to_source_inverse` | `output_to_source(source_to_output(t)) == t` for any t in [0, source_duration] |
| `test_speed_clamped_min` | `effective_speed=0.1 → clamped to 0.5` |
| `test_speed_clamped_max` | `effective_speed=3.0 → clamped to 1.5` |
| `test_trim_offset_reduces_source_duration` | `source_start=10.0+trim=2.0, source_end=40.0 → source_duration=28.0` |
| `test_zero_trim_offset` | `trim_offset=0.0 → source_start == seg_start` |
| `test_platform_tiktok_speed_delta` | `payload_speed=1.07, platform=tiktok (delta=0.08) → effective_speed=1.15` |
| `test_platform_youtube_shorts_no_delta` | `payload_speed=1.07, platform=youtube_shorts (delta=0.0) → effective_speed=1.07` |
| `test_variant_aggressive_speed` | Aggressive variant speed formula matches `_build_variant_segments()` output |
| `test_to_dict_round_trip` | `TimelineMap.from_dict(tl.to_dict()) == tl` |

#### Group B: BaseClipManifest serialization

| Test | What it verifies |
|------|-----------------|
| `test_manifest_to_dict_contains_required_keys` | All required fields present in `to_dict()` output |
| `test_manifest_from_dict_round_trip` | `BaseClipManifest.from_dict(m.to_dict())` produces identical values |
| `test_manifest_timeline_embedded` | `manifest.to_dict()["timeline"]` contains all TimelineMap fields |
| `test_manifest_null_paths_serialize_as_none` | Optional path fields serialize to `null` when not set |
| `test_manifest_path_fields_set_progressively` | Setting `cut_path` after construction serializes correctly |

#### Group C: manifest_writer.py I/O

| Test | What it verifies |
|------|-----------------|
| `test_write_manifest_creates_file` | `write_manifest(work_dir, m)` creates `part_1/manifest.json` |
| `test_manifest_path_convention` | `manifest_path(work_dir, 1)` == `work_dir/part_1/manifest.json` |
| `test_write_is_atomic` | Verifies temp-then-replace pattern (file either exists complete or not at all) |
| `test_read_manifest_returns_none_on_missing` | `read_manifest(work_dir, 99)` returns `None`, does not raise |
| `test_read_manifest_returns_none_on_corrupt` | Corrupt JSON file returns `None`, does not raise |
| `test_read_all_manifests_finds_all_parts` | `read_all_manifests()` finds all `part_*/manifest.json` files |
| `test_read_all_manifests_skips_corrupt` | Corrupt file in middle of set is skipped, others returned |
| `test_write_then_read_round_trip` | Write + read produces identical manifest |

#### Group D: Integration invariants (source-inspection tests, no file I/O)

| Test | What it verifies |
|------|-----------------|
| `test_pipeline_creates_timeline_before_cut_video` | `inspect.getsource(render_pipeline)` shows `TimelineMap(` appears before `cut_video(` in the per-part loop |
| `test_pipeline_creates_manifest_before_cut_video` | `BaseClipManifest(` appears before `cut_video(` |
| `test_pipeline_writes_manifest_after_construction` | `write_manifest(` appears after `BaseClipManifest(` |
| `test_render_part_smart_speed_not_inline_recomputed` | The Pattern B inline speed re-computation is replaced by `timeline.effective_speed` |

All tests: no FFmpeg, no subprocess, no real video files, no network. `tmp_path` fixture for file I/O tests.

---

## 10. Risk Checklist

### Implementation risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `TimelineMap` construction adds latency to the per-part loop | Very low — it's pure Python arithmetic | Profile if a concern; expected < 0.1ms |
| Manifest write fails (disk full, permissions) | Low | `write_manifest()` must catch and log, not raise — rendering must continue if manifest write fails |
| `manifest.json` conflicts with existing temp files | None — name is new | Verify `_safe_unlink()` list does not include `manifest.json` |
| Corrupt manifest from partial write on crash | Possible on power loss | Atomic write (temp file + `os.replace()`) eliminates this risk on all supported platforms |
| Multi-variant loop creates manifests for all 3 variants | Works correctly — each variant has its own `idx` and `part_n` directory | No special handling needed |
| Resume path: manifest already exists for a completed part | Harmless — manifest is overwritten at start of part loop, before the skip check | Verify resume logic still skips correctly |
| `_ai_edit_plan.selected_segment_indices` may not exist | High — this field is not in the current `AIEditPlan` schema | Use `ai_selected=False` in Phase 1; Phase 3 will populate correctly |

### Architecture risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Phase 1 manifest is written but never read by anything | Intentional — Phase 1 is write-only. Phase 2 will add readers. | Document clearly in manifest_writer.py: "Phase 1: write only. Phase 2 adds consumers." |
| Pattern B speed re-computation at `render_part_smart()` call site (line 4309–4312) is not consolidated in Phase 1 | Intentional — Phase 1 does not change render call sites | Phase 2 will replace Pattern B with `timeline.effective_speed`. Risk: Pattern B drift. Acceptance: low risk since Pattern B and Pattern A agree (same formula). |
| `_get_effective_playback_speed()` and `TimelineMap` both compute effective speed independently | Intentional — Phase 1 does not remove `_get_effective_playback_speed()`. `TimelineMap` calls it internally. | Phase 2 will consolidate to `TimelineMap` as the single source. |
| 290KB render_pipeline.py gets another block of code | Real, but unavoidable — Phase 1 adds ~30 lines to the per-part loop | This plan adds minimum viable lines. Extraction of the per-part loop into its own module is Phase 5. |

---

## 11. Step-by-Step Implementation Order

Each step is independently verifiable before proceeding to the next.

### Step 1: Create `backend/app/models/timeline.py`

Create the file. Implement `TimelineMap` and `BaseClipManifest` as pure data classes.

**Verify**: `python -c "from app.models.timeline import TimelineMap, BaseClipManifest; print('OK')"` exits 0.

**Tests to write first**: All of Group A and Group B from the test plan above. Run them — they should fail because the file doesn't exist yet, then pass after implementation.

### Step 2: Create `backend/app/services/manifest_writer.py`

Implement `manifest_path()`, `write_manifest()`, `read_manifest()`, `read_all_manifests()`.

**Verify**: `python -c "from app.services.manifest_writer import write_manifest; print('OK')"` exits 0.

**Tests to write**: All of Group C from the test plan. They should pass after implementation.

### Step 3: Add imports to `render_pipeline.py`

Add two imports at the top of `render_pipeline.py`:
```python
from app.models.timeline import TimelineMap, BaseClipManifest
from app.services.manifest_writer import write_manifest, manifest_path
```

**Verify**: `python -c "from app.orchestration import render_pipeline; print('OK')"` exits 0 (imports valid, no circular dependency).

### Step 4: Insert `TimelineMap` construction in `render_pipeline.py`

Insert after line 3649 (after `_effective_start` is finalized for the last time). No other lines change.

**Verify**: Group D `test_pipeline_creates_timeline_before_cut_video` passes.

### Step 5: Insert `BaseClipManifest` construction and initial write

Insert immediately after Step 4. Write manifest before `cut_video()`.

**Verify**: Group D `test_pipeline_creates_manifest_before_cut_video` passes.

### Step 6: Add manifest update calls after each file-producing step

Add `_manifest.cut_path = ...` + `write_manifest()` after `cut_video()`.
Add `_manifest.srt_path = ...` + `write_manifest()` after `slice_srt_by_time()`.
Add `_manifest.ass_path = ...` + `write_manifest()` after ASS conversion.
Add `_manifest.narration_path = ...` + `write_manifest()` after `generate_narration_audio()`.
Add `_manifest.rendered_path = ...` + `write_manifest()` after `render_part_smart()`.

**Verify**: A full render job produces `work_dir/part_n/manifest.json` for each part, with all path fields populated and non-null.

### Step 7: Enrich the `playback_speed_resolution` debug log

Add `source_duration`, `output_duration`, and `manifest` path to the existing log at line 4721.

**Verify**: Log output contains the new fields. Existing log parsers are not broken (additive only).

### Step 8: Write Group D integration tests

Write `test_timeline_map.py::TestPipelineInvariants` (Group D). These tests inspect source code to guard against future regressions.

**Verify**: All 4 Group D tests pass.

### Step 9: Run the full test suite

```
cd backend && python -m pytest tests/ -v --tb=short
```

**Acceptance**: No previously passing test fails. All new tests in `test_timeline_map.py` pass.

### Step 10: Manual smoke test

Run one real render job (YouTube URL, TikTok platform, default settings). Verify:
- `manifest.json` exists in each `part_n/` directory
- JSON is valid and contains expected values
- Rendered output is visually identical to a pre-Phase-1 render (no behavioral change)
- Log contains `playback_speed_resolution` entries with `source_duration` and `output_duration`

---

## Appendix: File Map After Phase 1

```
backend/
  app/
    models/
      schemas.py                  ← unchanged
      timeline.py                 ← NEW: TimelineMap, BaseClipManifest
    services/
      manifest_writer.py          ← NEW: write_manifest, read_manifest, manifest_path
      render_engine.py            ← unchanged
      subtitle_engine.py          ← unchanged
      audio_mix_service.py        ← unchanged (Phase 0 complete)
      tts_service.py              ← unchanged
      downloader.py               ← unchanged (Phase 0 complete)
    orchestration/
      render_pipeline.py          ← +2 imports, +~30 lines in per-part loop only
    ai/
      director/
        ai_director.py            ← unchanged
  tests/
    test_timeline_map.py          ← NEW: Groups A, B, C, D (target: ~35 tests)
    test_phase0_hotfixes.py       ← unchanged (Phase 0 tests remain passing)
    test_render_audit_p0_fixes.py ← unchanged
    [all existing tests]          ← unchanged, all must still pass

docs/
  restructure/
    PHASE_1_OUTPUT_TIMELINE_IMPLEMENTATION_PLAN.md  ← this document
```

## Appendix: What Phase 2 Will Build on This Foundation

Phase 2 is out of scope for this plan but is documented here so Phase 1 decisions are made with full context:

- **Consolidate Pattern B**: Replace the inline speed re-computation at `render_part_smart()` call site (line 4309–4312) with `timeline.effective_speed`. This is the first consumer of the manifest.
- **Explicit filter contract**: Document the `ass→setpts` order in `render_engine.py` with a comment that cites the `TimelineMap` contract. This makes the implicit explicit.
- **AI timeline awareness**: Extend `AIEditPlan` to optionally store `output_timeline_hints` (timestamps in output time). AI plan consumers in `render_pipeline.py` will read the manifest to resolve hints to output timestamps.
- **Output QA**: `_validate_render_output()` reads the manifest to compare `manifest.timeline.output_duration` against actual FFprobe duration — tighter than the current ±20% heuristic.
- **Manifest cleanup**: Add `manifest.json` to the list of files excluded from the per-part temp cleanup but included in `prune_render_temp_dirs()` (so they survive the render but are swept with the work dir after 24h).
