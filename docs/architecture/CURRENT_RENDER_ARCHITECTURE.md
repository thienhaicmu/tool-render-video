# CURRENT_RENDER_ARCHITECTURE.md

**Source of truth for current render architecture.**
**Last updated**: 2026-05-22 (post Phase 4E.5)

---

## System Overview

```
Electron shell
  └── BrowserWindow → http://127.0.0.1:8000/
        └── FastAPI + Uvicorn (single process)
              ├── job_manager.py — ThreadPoolExecutor, priority heap, cancel events
              ├── render_pipeline.py — per-job orchestration (5,510 lines post Phase 4C)
              ├── orchestration/render_events.py — shared logging/event helpers (Phase 4B)
              ├── orchestration/asset_pipeline.py — post-assembly asset hooks (Phase 4B)
              ├── orchestration/qa_pipeline.py — output QA/validation helpers (Phase 4C)
              ├── orchestration/audio_pipeline.py — narration audio cleanup orchestration (Phase 4D)
              ├── render_engine.py — pure re-export shim (Phase 4E.5; all functions moved out)
              ├── services/render/ffmpeg_helpers.py — FFmpeg infrastructure + filter builders (Phase 4E.1)
              ├── services/render/clip_ops.py — cut_video, silence/bad-frame detect, apply_micro_pacing (Phase 4E.2)
              ├── services/render/base_clip_renderer.py — render_base_clip (Phase 4E.3)
              ├── services/render/overlay_compositor.py — composite_overlays_on_base_clip (Phase 4E.4)
              ├── services/render/legacy_renderer.py — render_part, render_part_smart (Phase 4E.5)
              └── SQLite — job/parts state, upload queue
```

No cloud dependency. FFmpeg and Python runtime ship bundled.

---

## Full Render Pipeline Flow

```
POST /api/render/process
  └── job_manager: queue → worker thread
        └── run_render_pipeline(job_id, payload)

1. SOURCE ACQUISITION
   ├── YouTube URL → yt-dlp download (socket_timeout=60, cancel_event propagated)
   └── Local file  → path validation

2. SCENE DETECTION
   └── PySceneDetect ContentDetector / TransNetV2 (optional)
       └── 72h cache keyed (path, mtime_ns, size)

3. SEGMENT BUILDING + SCORING
   ├── build_segments_from_scenes()
   ├── refine_segment_boundaries()
   ├── refine_cuts_for_naturalness()
   └── score_segments() → viral_score, hook_score, market_score

4. SEGMENT SELECTION
   ├── Standard: top-N by score
   └── Variant: 3 per segment (aggressive/balanced/story_first)

5. WHISPER TRANSCRIPTION
   └── Full-video transcription (72h cache, model lock)

6. PER-PART RENDER  [ThreadPoolExecutor, parallel parts]
   └── _render_part(seg, idx, ...)  — see §Per-Part Render Flow

7. RESULTS
   ├── AI visibility metadata
   ├── XLS report
   └── Job completed
```

---

## Per-Part Render Flow

Two modes depending on feature flags. See [FEATURE_FLAG_MATRIX.md](FEATURE_FLAG_MATRIX.md).

### Legacy Path (both flags OFF — default)

```
_render_part(seg, idx)
│
├── [TIMELINE]
│   └── TimelineMap(source_start, source_end, effective_speed, trim_offset)
│
├── [SUBTITLE PRE-PROCESSING]   ← source timeline
│   ├── detect_silence_trim_offset()  → _trim_offset
│   ├── detect_bad_first_frame()      → _visual_trim
│   ├── slice_srt_by_time()           → part.srt (source-clip seconds)
│   ├── apply_market_hook_text_to_srt()
│   ├── _apply_subtitle_edits_to_srt()
│   ├── srt_to_ass_bounce/karaoke()   → part.ass
│   └── translate() (optional)
│
├── [TTS / NARRATION]   ← source timeline text → audio
│   ├── generate_narration_audio()
│   ├── _maybe_cleanup_narration_audio() (DeepFilterNet, optional)
│   └── mix_narration_audio(playback_speed=effective_speed)  ← atempo applied
│
├── [VIDEO CUT]
│   └── cut_video(source_start, source_end)
│
├── [RENDER — single FFmpeg pass]    ← OUTPUT timeline created here
│   └── render_part_smart()
│       └── vf_chain order:
│           scale → crop → zoom → denoise →
│           effect (eq/unsharp) → color → sharpen →
│           format=yuv420p → fade →
│           ass=part.ass          ← ASS burned BEFORE setpts (source-time)
│           drawtext=title        ← title overlay BEFORE setpts
│           text_layers           ← user overlays BEFORE setpts
│           setpts=PTS/speed      ← speed re-clock: source→output timeline
│           fps=target_fps        ← always last
│       audio chain:
│           atempo=speed (if speed != 1.0)
│           loudnorm (optional)
│
├── [POST-RENDER ASSEMBLY]
│   ├── _maybe_prepend_remotion_hook_intro()
│   ├── _maybe_prepend_asset_intro()
│   ├── _maybe_append_asset_outro()
│   └── _maybe_apply_asset_logo()
│
├── [OUTPUT QA]
│   └── _validate_render_output()  ← duration ±20%, size > 0
│
└── [MANIFEST + DB]
    ├── write_manifest()
    └── upsert_job_part()
```

### Base-Clip-First + Overlay Path (both flags ON)

```
_render_part(seg, idx)
│
├── [TIMELINE] — same as legacy
│
├── [SUBTITLE PRE-PROCESSING — source timeline]
│   ├── slice_srt_by_time()           → part.srt (source-clip seconds)
│   ├── srt_to_ass_bounce/karaoke()   → part.ass
│   └── slice_srt_to_output_timeline() → subtitle_output_timeline.srt
│       └── srt_to_ass_bounce/karaoke() → subtitle_output_timeline.ass
│
├── [BASE CLIP RENDER]                ← OUTPUT TIMELINE BAKED HERE
│   └── render_base_clip()
│       vf_chain: scale → crop → effect → color → setpts → fps
│       audio: atempo + loudnorm
│       NO ass=, NO drawtext=, NO text_layers
│       → base_clip.mp4
│
├── [TEXT LAYER PREPARATION]
│   ├── _part_text_layers_overlay  (user layers + hook at 1.5 output-s)
│   └── overlay_title              (payload.title_overlay_text)
│
├── [OVERLAY COMPOSITE]              ← overlay-only, no re-encode of base
│   └── composite_overlays_on_base_clip(
│           base_clip_path,
│           subtitle_ass=subtitle_output_timeline.ass,
│           text_layers=_part_text_layers_overlay,
│           title_text=overlay_title,
│       )
│       vf_chain: ass= → drawtext=title → drawtext=layers → fps=
│       audio: -c:a copy
│       NO setpts, NO atempo, NO crop, NO scale, NO color
│       → final_part.mp4
│
├── [FALLBACK if composite raises]
│   └── render_part_smart()  → final_part.mp4  (legacy path)
│
├── [POST-RENDER ASSEMBLY] — same as legacy
├── [OUTPUT QA] — same as legacy
└── [MANIFEST + DB] — includes overlay_rendered_path, overlay_text_layers_applied
```

---

## Render Layer Responsibilities

| Layer | Function | Owns |
|---|---|---|
| `render_base_clip()` | Speed, crop, reframe, color, audio encoding | `services/render/base_clip_renderer.py` (re-exported from `render_engine.py`) |
| `composite_overlays_on_base_clip()` | Subtitle, title, text_layers overlay | `services/render/overlay_compositor.py` (re-exported from `render_engine.py`) |
| `render_part_smart()` | All-in-one legacy render (speed + overlays) | `services/render/legacy_renderer.py` (re-exported from `render_engine.py`) |
| Post-assembly | Hook intro, asset intro/outro, logo watermark | `render_pipeline.py` |
| Narration mix | TTS atempo compensation, BGM ducking | `audio_mix_service.py` |

See [RENDER_BOUNDARIES.md](RENDER_BOUNDARIES.md) for ownership invariants.

---

## Key Domain Models

### TimelineMap (`backend/app/domain/timeline.py`)

Pure dataclass. Formalizes source→output time conversion for one clip.

```
fields:
  source_start: float      # effective start in source.mp4 seconds
  source_end: float        # end in source.mp4 seconds
  effective_speed: float   # clamped [0.5, 1.5]
  trim_offset: float       # silence trim applied
  source_duration: float   # computed: source_end - source_start
  output_duration: float   # computed: source_duration / effective_speed

methods:
  source_to_output(t) → (t - source_start) / effective_speed
  output_to_source(t) → t * effective_speed + source_start
```

### BaseClipManifest (`backend/app/domain/manifests.py`)

Per-part JSON record written to `work_dir/part_N/manifest.json`.

Key field groups:
- Job metadata: `job_id`, `part_no`, `platform`, `effective_speed`
- Speed decisions: `payload_speed`, `platform_delta`, `effective_speed`, `variant_type`
- Trim decisions: `silence_trim_offset`, `visual_trim_offset`
- Embedded `timeline: TimelineMap`
- Progressive paths: `cut_path`, `srt_path`, `ass_path`, `narration_path`, `rendered_path`
- Base clip artifacts: `base_clip_path`, `base_clip_duration`, `base_clip_fps`, `base_clip_width`, `base_clip_height`, `base_clip_has_audio`, `base_clip_created_at`
- Overlay artifacts: `overlay_srt_path`, `overlay_ass_path`, `overlay_rendered_path`, `overlay_text_layers_applied`

### manifest_writer (`backend/app/services/manifest_writer.py`)

Atomic write (`path.tmp` → `os.replace()`). Never raises — logs warning on failure.

---

## Feature Flag Summary

Both flags default **OFF**.

| `FEATURE_BASE_CLIP_FIRST` | `FEATURE_OVERLAY_AFTER_BASE_CLIP` | Final output |
|---|---|---|
| 0 | 0 | `render_part_smart()` |
| 0 | 1 | `render_part_smart()` (overlay flag ignored) |
| 1 | 0 | `render_part_smart()` (base clip is parallel artifact) |
| 1 | 1 | `composite_overlays_on_base_clip()`, fallback to `render_part_smart()` |

See [FEATURE_FLAG_MATRIX.md](FEATURE_FLAG_MATRIX.md) for full matrix.

---

## Timeline Semantics Summary

- **Source timeline**: timestamps in `source.mp4` seconds
- **Output timeline**: timestamps in rendered clip seconds = source_t / effective_speed
- **Legacy vf_chain**: `ass-before-setpts` keeps subtitle PTS correct at source-clock
- **Overlay path**: `base_clip.mp4` PTS is already output-timeline; all overlay timing in output seconds

See [TIMELINE_SEMANTICS.md](TIMELINE_SEMANTICS.md) for full timing contract.

---

## Speed Clamp

`effective_speed` is always clamped `[0.5, 1.5]` at every entry point:
- `_get_effective_playback_speed()` in `render_pipeline.py`
- `_sanitize_speed()` in `render_engine.py`
- `TimelineMap.__post_init__()` in `timeline.py`

`audio_mix_service.py` uses `[0.5, 2.0]` — this is the FFmpeg atempo filter range, a separate concern.

---

## Completed Phases

**Phase 3C** (shipped): BGM support added to `render_base_clip()`.

`render_base_clip()` now accepts `reup_bgm_enable`, `reup_bgm_path`, `reup_bgm_gain`. When BGM is enabled and valid, `filter_complex` is used to mix BGM into `base_clip.mp4`, which then flows through the composite via `-c:a copy`. `base_clip_bgm_applied: Optional[bool]` added to `BaseClipManifest`.

See [PHASE_3C_AUDIO_OWNERSHIP_PLAN.md](../restructure/PHASE_3C_AUDIO_OWNERSHIP_PLAN.md) and [MIGRATION_HISTORY.md](../restructure/MIGRATION_HISTORY.md).
