# CURRENT_RENDER_ARCHITECTURE.md

**Source of truth for current render architecture.**
**Last updated**: 2026-05-23 (Phase 5.3: AI contract models + validation layer + knowledge→hints mapper; limited render influence: hook overlay gated by AI hint; pacing/subtitle advisory only; trace logger extended with execution_hints/validation_fixup/decision_rejected events)

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
              ├── orchestration/qa_pipeline.py — output QA/validation helpers (Phase 4C); audio stream presence check added (Phase 5.1 — warns when output has no audio stream)
              ├── orchestration/audio_pipeline.py — narration audio cleanup orchestration (Phase 4D)
              ├── render_engine.py — pure re-export shim (Phase 4E.5; all functions moved out)
              ├── services/render/ffmpeg_helpers.py — FFmpeg infrastructure + filter builders (Phase 4E.1)
              ├── services/render/clip_ops.py — cut_video, silence/bad-frame detect, apply_micro_pacing (Phase 4E.2)
              ├── services/render/base_clip_renderer.py — render_base_clip (Phase 4E.3)
              ├── services/render/overlay_compositor.py — composite_overlays_on_base_clip (Phase 4E.4)
              ├── services/render/legacy_renderer.py — render_part, render_part_smart (Phase 4E.5)
              ├── services/subtitles/ (Phase 4G COMPLETE)
              │     ├── styles.py — ASSPreset, _PRESETS, _STYLE_ALIASES, _HL_OPEN/_HL_CLOSE, compute helpers, build_ass_style_line (Phase 4G.1)
              │     ├── srt_core.py — format/parse timestamps, SRT parse/write/slice, slice_srt_to_text, _run_with_retry (Phase 4G.2)
              │     ├── output_timeline.py — slice_srt_to_output_timeline (Phase 4G.3)
              │     ├── readability.py — visual-width helpers, _HOOK_EMPHASIS_WORDS, _is_cjk, subtitle_emphasis_pass, resegment_srt_for_readability, emphasis constants/helpers (Phase 4G.5 full)
              │     ├── ass_core.py — _ass_time, _ass_escape_text, srt_to_ass_bounce, srt_to_ass_karaoke, burn_subtitle_onto_video, render_subtitle_preview (Phase 4G.4)
              │     ├── text_transforms.py — resolve_hook_overlay_text, apply_market_hook_text_to_srt, apply_hook_subtitle_format, format_hook_subtitle, apply_market_line_break_to_srt, apply_subtitle_execution_hints (Phase 4G.5)
              │     └── transcription.py — _MODEL_CACHE, get_whisper_model, _get_transcribe_lock, transcribe_to_srt, extract_audio_for_transcription, has_audio_stream (Phase 4G.6)
              ├── services/preview/ (Phase 4H.1–4H.6 COMPLETE — FROZEN)
              │     ├── ffmpeg_probers.py — _probe_video_codec, _probe_preview_profile, _is_browser_safe_preview, _ensure_h264_preview, _run_ffmpeg_checked, _detect_leading_black_duration (Phase 4H.1)
              │     ├── session_service.py — _PREVIEW_SESSIONS, _PREVIEW_DIR, _SESSION_TTL_HOURS, _MAX_PREVIEW_SESSIONS, _save_session, _load_session, _cleanup_preview_session, evict_stale_preview_sessions (Phase 4H.2)
              │     └── media_streaming.py — _parse_range_header, _iter_file_bytes (Phase 4H.3)
              ├── db/ (Phase 4F COMPLETE) — app/db/connection.py (get_conn, init_db, thread-local, _drop_upload_tables), app/db/jobs_repo.py (upsert_job, update_job_progress, job parts CRUD), app/db/creator_repo.py (get_creator_prefs, upsert_creator_prefs); platform_repo.py DELETED (4F.5C), uploads_repo CANCELLED (upload domain removed instead)
              └── SQLite — job/parts state (3 live tables: jobs, job_parts, creator_prefs; upload tables dropped on startup via _drop_upload_tables())
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

---

## Phase 5.3 — AI Render Contract (2026-05-23)

**New files**:
- `app/ai/contracts.py` — `CreativeBrief`, `RenderExecutionHints`, `AIValidationResult` dataclasses
- `app/ai/validators.py` — `validate_execution_hints()`: clamp/fallback for all hint fields
- `app/ai/render_mapper.py` — `map_knowledge_to_execution_hints()`: knowledge → validated hints

**Modified files**:
- `app/ai/director/ai_director.py` — Phase 5.3 mapper called last in `create_ai_edit_plan()`, after all Phase 53–57 blocks; result merged into `plan.knowledge_injection`
- `app/ai/tracing.py` — `log_execution_hints()`, `log_validation_fixup()`, `log_decision_rejected()` added
- `app/orchestration/render_pipeline.py` — Phase 5.3 block reads `execution_hints` from plan; applies hook overlay gate; pacing/subtitle hints logged as advisory only

**Render behavior impact**:
- Hook overlay: `hook_overlay_enabled=False` in execution_hints → `_hook_overlay_enabled = False`; all other values keep existing behavior
- Pacing hints: advisory only — logged but no runtime parameter overridden
- Subtitle hints: advisory only — per-part style resolved from payload unchanged
- FFmpeg: ZERO changes to FFmpeg commands or filter graphs

---

## Phase 5.4 — AI Pacing Hint Propagation (2026-05-23)

**New files**:
- `app/ai/pacing.py` — `AIPacingConfig` dataclass, `build_ai_pacing_config(execution_hints, payload)`: validates and applies pacing hints with user override protection

**Modified files**:
- `app/ai/tracing.py` — `log_pacing_applied(config)` added; writes `ai.pacing_applied` JSONL event
- `app/orchestration/render_pipeline.py` — Phase 5.4 early pacing block added before `SEGMENT_BUILDING` stage; local `_seg_min_sec`/`_seg_max_sec` variables replace `payload.min_part_sec`/`payload.max_part_sec` in all three segment building calls; Phase 5.2 block reuses `_early_retrieved_knowledge` to avoid double FAISS query

**Pacing injection point**:
- Before `build_segments_from_scenes()` (~line 1683): `_seg_min_sec`/`_seg_max_sec` set from AI hint or payload
- Also propagated to `refine_segment_boundaries()` and `refine_cuts_for_naturalness()`

**Render behavior impact**:
- Pacing hints: NOW APPLIED — `cut_interval_min/max` from knowledge hints sets segment duration bounds when `ai_director_enabled=True` and user has not overridden defaults
- User explicit limits: always win — if `payload.min_part_sec != 15` or `payload.max_part_sec != 60`, AI pacing rejected with `user_duration_override`
- AI disabled: if `ai_director_enabled=False`, early pacing block skipped; segment duration unchanged
- Subtitle hints: still advisory only — unchanged
- Hook overlay gate: still active — unchanged
- FFmpeg: ZERO changes to FFmpeg commands or filter graphs

---

## Phase 5.5 — AI Subtitle Emphasis Hint Propagation (2026-05-23)

**New files**:
- `app/ai/subtitle_hints.py` — `AISubtitleEmphasisConfig` dataclass, `build_ai_subtitle_emphasis_config(execution_hints, payload)`: validates and applies subtitle emphasis hints

**Modified files**:
- `app/services/subtitles/readability.py` — `subtitle_emphasis_pass()` gains optional `emphasis_level_override: str | None = None` parameter; when provided and valid, overrides the emphasis level derived from `preset_id`; timing is never touched
- `app/ai/tracing.py` — `log_subtitle_emphasis_applied(config)` added; writes `ai.subtitle_emphasis_applied` JSONL event
- `app/orchestration/render_pipeline.py` — Phase 5.5 block added after Phase 5.3 block (before per-part loop); builds `_ai_subtitle_emphasis_config`; per-part `subtitle_emphasis_pass()` call passes `emphasis_level_override=_ai_emph_override`

**Subtitle injection point**:
- Phase 5.5 config built once at ~line 2578 (after Phase 5.3, before per-part loop)
- Per-part: `subtitle_emphasis_pass()` call at ~line 3664 receives `emphasis_level_override` from config

**Render behavior impact**:
- Subtitle emphasis: NOW APPLIED — `subtitle_emphasis_style` from knowledge hints now influences text emphasis level inside `subtitle_emphasis_pass()` when `ai_director_enabled=True`
- No new style IDs: `_effective_subtitle_style` (preset ID for ASS generation) is never changed by AI
- Subtitle timing: GUARANTEED UNCHANGED — `subtitle_emphasis_pass()` modifies only `b['text']`, never `b['start']` or `b['end']`
- User subtitle_style: preserved — style resolution hierarchy (variant > creator > platform > DNA > content-type) unchanged
- AI disabled: if `ai_director_enabled=False`, Phase 5.5 block skipped; emphasis derived from preset_id as before
- Pacing hints: active — unchanged from Phase 5.4
- Hook overlay gate: active — unchanged from Phase 5.3
- FFmpeg: ZERO changes to FFmpeg commands or filter graphs

---

## Phase 5.6 — AI Visual Intensity Hint (2026-05-23)

**New files**:
- `app/ai/visual_hints.py` — `AIVisualIntensityConfig` dataclass, `build_ai_visual_intensity_config(execution_hints, payload)`: validates visual intensity hints, detects user override, documents injection point investigation

**Modified files**:
- `app/ai/tracing.py` — `log_visual_intensity_applied(config)` added; writes `ai.visual_intensity_applied` JSONL event
- `app/orchestration/render_pipeline.py` — Phase 5.6 block added after Phase 5.5 block; builds `_ai_visual_intensity_config`; logs applied/rejected; no render parameter changes

**Visual injection point investigation**:
- `render_part()`, `render_part_smart()`, `render_base_clip()` all accept `effect_preset: str`
- `effect_preset` maps directly to FFmpeg filter strings via `_effect_filter()` — no intermediate intensity parameter
- No `_effect_intensity`, `_visual_energy`, `effect_strength`, `visual_profile` local variables exist in render_pipeline.py
- `_cinematic_color_filter()` and `_cinematic_sharpen_filter()` accept `content_type`/`src_h`, not intensity levels
- `content_type` and `effect_preset` are both user-controlled payload fields — AI must not override them
- **Result: NOT FOUND — no safe visual intensity injection point** (Phase 5.6)

**Render behavior impact**:
- Visual intensity hints: ADVISORY ONLY — logged as `ai.visual_intensity_applied` (always `applied=False` in Phase 5.6)
- `effect_preset`: GUARANTEED UNCHANGED — AI never reads or writes `payload.effect_preset`
- `render_overrides={}`: no render parameters changed in Phase 5.6
- AI disabled: if `ai_director_enabled=False`, Phase 5.6 block skipped; `ai_disabled` rejection logged
- User effect_preset override: if `payload.effect_preset != "slay_soft_01"`, rejected as `user_visual_override`
- Subtitle hints: active — unchanged from Phase 5.5
- Pacing hints: active — unchanged from Phase 5.4
- Hook overlay gate: active — unchanged from Phase 5.3
- FFmpeg: ZERO changes to FFmpeg commands or filter graphs

### Phase 5.7 — Safe Visual Intensity Injection (2026-05-23)

**Safe injection point found and implemented.**

New files/changes:
- `app/services/render/ffmpeg_helpers.py` — `resolve_effect_preset_with_intensity()` added; `_VISUAL_INTENSITY_PRESET_MAP` mapping table; renderer OWNS all mapping
- `app/services/render/legacy_renderer.py` — `visual_intensity_hint: str | None = None` added to `render_part()` and `render_part_smart()`; calls `resolve_effect_preset_with_intensity()` before `_effect_filter()`
- `app/services/render/base_clip_renderer.py` — `visual_intensity_hint: str | None = None` added to `render_base_clip()`; same pattern
- `app/ai/visual_hints.py` — `_NO_SAFE_INJECTION_POINT = False`; `applied=True` now possible; `render_overrides={"visual_intensity_hint": <value>}`
- `app/orchestration/render_pipeline.py` — Phase 5.7 block extracts `_vis_intensity_hint` from config; passes to `render_part_smart()` and `render_base_clip()` calls

**_effect_filter() supported presets** (all 6):
| Preset | Description |
|---|---|
| `slay_soft_01` | Default — natural cinematic, light sharpening |
| `slay_pop_01` | High energy — boosted contrast/saturation/unsharp |
| `story_clean_01` | Subtle — low contrast/saturation, soft sharpening |
| `social_bright` | Bright social — high saturation, strong brightness |
| `cinematic_soft` | Cinematic desaturated — soft, denoised |
| `high_contrast` | Maximum contrast — heaviest unsharp |

**AI visual intensity mapping table** (renderer-owned):
| AI hint | Preset | Rationale |
|---|---|---|
| `"low"` | `story_clean_01` | Subtle look, gentle processing |
| `"medium"` | `slay_soft_01` | Natural default (schema default) |
| `"high"` | `slay_pop_01` | Energetic pop, boosted processing |

**Priority order** (enforced by renderer):
1. FFmpeg safety — `_effect_filter()` only accepts known preset names
2. `user_effect_is_explicit=True` → `effect_preset` unchanged
3. Valid `visual_intensity_hint` → renderer maps to known preset
4. Default: `effect_preset` unchanged

**Render behavior impact (Phase 5.7)**:
- Visual intensity hints: ACTIVE — `applied=True` for valid hints when user has default preset
- `effect_preset`: GUARANTEED UNCHANGED — never mutated; original preserved for logging
- `render_overrides={"visual_intensity_hint": <value>}`: render_pipeline passes value to renderer
- AI disabled: `visual_intensity_hint=None` → renderer uses `effect_preset` unchanged
- User effect_preset override: `user_effect_is_explicit=True` → renderer uses `effect_preset` unchanged
- overlay_compositor: NOT modified — no `visual_intensity_hint` parameter added
- FFmpeg: ZERO changes to filter construction — only the input preset name may change (to a known supported preset)
- API: ZERO changes — no new endpoints, no schema changes, no websocket payload changes
- API changes: NONE

---

## Phase 5.8 — Quality Intelligence Module (2026-05-23)

New module: `backend/app/quality/`

| File | Purpose |
|---|---|
| `app/quality/__init__.py` | Package exports: `QualityIssue`, `QualityReport`, `assess_rendered_part_quality` |
| `app/quality/models.py` | `QualityIssue` and `QualityReport` dataclasses; scoring penalty table |
| `app/quality/assessor.py` | `assess_rendered_part_quality()` — 9-category offline assessment |

**Integration point**: `app/orchestration/qa_pipeline.py` → `_assess_render_quality_intelligence()`
Called from: `render_pipeline.py` after `_assess_output_quality()` succeeds

**Sidecar report path**: `<output_dir>/quality/<job_id>_part_<N>.json`

**Scoring penalties**:
| Severity | Penalty |
|---|---|
| critical | -100 (score → 0) |
| error | -25 |
| warning | -10 |
| info | -2 |

**Constraints**:
- Never raises
- Never changes FFmpeg commands
- Never auto-regenerates video
- Never makes warnings fatal for existing QA
- Requires no internet, no API keys
