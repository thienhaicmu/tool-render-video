# Render Pipeline

Entry point: `POST /api/render/process` → `routes/render.py` → `job_manager.py` → `run_render_pipeline()` in `features/render/engine/pipeline/render_pipeline.py`.

---

## Stage Overview

```
[1]  Source Prep         pipeline_source_prep.py
[2]  Manual Voice TTS    pipeline_narration.py
[3]  LLM Pre-Render      llm_pipeline.py           (Whisper + LLM Call 1)
[4]  RenderPlan Select   render_pipeline.py         (LLM Call 2 → RenderPlan)
[5]  Scored Override     render_pipeline.py         (_scored_from_render_plan)
[6]  DB Persist          db/jobs_repo.py            (save RenderPlan)
[7]  Subtitle Translate  render_pipeline.py         (if subtitle_translate_enabled)
[8]  Render Loop         pipeline_render_loop.py    (ThreadPoolExecutor)
     └─ Per-Part:
        [8.1] Cut         stages/part_cut.py
        [8.2] Setup       stages/part_render_setup.py
        [8.3] Encode      stages/part_render_encode.py   (FFmpeg)
        [8.4] Voice Mix   stages/part_voice_mix.py
        [8.5] Finalize    stages/part_done.py
[9]  Output Ranking      pipeline_ranking.py
[10] Finalize            pipeline_finalize.py        (result_json + DONE)
```

---

## Stage Detail

### [1] Source Prep — `pipeline_source_prep.py`

**Function:** `prepare_render_source()`

Reads `payload.edit_session_id` first. If non-empty → load editor session. Otherwise → validate local file.

**Editor session path:**
- Load session via `load_session_fn(edit_session_id)`
- Raises `RuntimeError` if session expired or video file missing
- Apply `edit_trim_in` / `edit_trim_out` via FFmpeg `-ss` / `-to`
- Apply `edit_volume` via FFmpeg `volume=` filter

**Local file path:**
- Validate `source_mode == "local"` — any other value raises `RuntimeError`
- Validate `source_video_path` exists on disk
- Compute `output_stem` via `_smart_output_stem()`

Returns `SourcePrepResult(source, source_path, detected_source_mode)`.

---

### [2] Manual Voice TTS — `pipeline_narration.py`

**Function:** `run_manual_voice_tts()`

Runs only when `payload.voice_enabled=True` and `payload.voice_source="manual"`.

Generates a single TTS audio file from `payload.voice_script`. Returns `(voice_audio_path, _voice_tts_failed)`. If TTS fails, `_voice_tts_failed=True` and render continues without voice.

---

### [3] LLM Pre-Render — `llm_pipeline.py`

**Function:** `run_llm_pre_render()`

Hard-fail semantics: raises `LLMPipelineError` if source has no audio stream or Whisper fails.

**Step 1 — Transcription (Whisper):**
- Model: `payload.whisper_model` (default `"auto"` → resolved by config, typically `"small"`)
- Checks `data/cache/transcription/` first — cache hit skips re-transcription
- Produces `full_srt` — full-video SRT file

**Step 2 — Segment Selection (LLM Call 1):**
- Calls `select_segments()` via `features/render/ai/llm/__init__.py`
- Provider selected by `payload.ai_provider` (default `"gemini"`)
- Input: SRT content (truncated to `GEMINI_MAX_SRT_CHARS`), `output_count`, `min_sec`, `max_sec`
- Returns `list[LLMSegment]` or `None` (Sacred Contract #3)
- Result converted to `scored[]` list by `llm_stage.py:_to_scored_dict()`

Returns `LLMPreRenderResult(full_srt, full_srt_available, scored, total_parts)`.

---

### [4] RenderPlan Selection — `render_pipeline.py`

**Function:** `_llm_select_render_plan()` at line ~533

Runs when `LLM_EMIT_RENDER_PLAN=1` (default ON since Sprint 7.6a).

Calls `select_render_plan()` — LLM Call 2 using same provider and SRT. Returns full `RenderPlan` dataclass or `None` on any failure (Sacred Contract #3 — never raises).

**RenderPlan schema** → see [AI_INTEGRATION.md](AI_INTEGRATION.md).

---

### [5] Scored Override — `render_pipeline.py`

**Function:** `_scored_from_render_plan()` at line ~244

If `RenderPlan` is not None and has clips:
- Convert `RenderPlan.clips` (list of `ClipPlan`) into `scored[]` dict list
- This **overwrites** the Call 1 result from step [3]
- Maps: `start`, `end`, `viral_score`, `hook_score`, `retention_score`, `rank`, `subtitle_style`, `content_type`, `cover_offset_ratio`, `speech_density`, `duration_fit`

If RenderPlan is None or has no clips → use `scored[]` from Call 1 unchanged.

---

### [6] DB Persist — `db/jobs_repo.py`

`update_render_plan(job_id, render_plan)` — serializes `RenderPlan` to JSON, saves to `jobs.render_plan_json` column.

---

### [7] Subtitle Translation — `render_pipeline.py`

Runs only when `payload.subtitle_translate_enabled=True`.

Translates the full SRT to `payload.subtitle_translate_target_lang` before part dispatch. Partial failures tracked in `_sub_translate_partial` list. Render continues even if translation partially fails.

---

### [8] Render Loop — `pipeline_render_loop.py`

**Function:** `run_render_loop()`

Dispatches each segment in `scored[]` to a worker thread in `ThreadPoolExecutor(max_workers=MAX_RENDER_JOBS)`.

Each worker calls `process_one_part(ctx, part_no, seg)` in `stages/part_renderer.py`.

---

### [8.1] Cut — `stages/part_cut.py`

**Function:** `cut_video(ctx, part_no, seg)`

**Standard path:**
```
ffmpeg -ss {start} -i {source} -t {duration} -c:v copy -c:a copy {raw_part.mp4}
```

**FEATURE_RAW_PART_SKIP optimization** (default OFF):
- Skips writing `raw_part.mp4`
- Uses input-side `-ss`/`-t` seek in the encode step instead
- Only applies when `motion_aware_crop=False`
- Returns `None` to signal "no intermediate file"

---

### [8.2] Setup — `stages/part_render_setup.py`

**Function:** `setup_part_render(ctx, part_no, seg)`

Resolves final encoding parameters. Priority for each: `RenderPlan` field → `payload` field → `tuned` profile default.

**Codec resolution:**
```python
final_codec = (render_plan.output_config.codec or "") or payload.video_codec
```

**CRF resolution:**
```python
final_crf = (render_plan.output_config.crf or 0) or payload.video_crf or tuned["video_crf"]
```

**Subtitle SRT generation:**
- Extracts SRT lines for `[seg.start, seg.end]` from `full_srt`
- Applies `payload.subtitle_edits` if present
- Writes to `work_dir/srt/part_NNN.srt`

**Text layer placement:**
- For each `payload.text_layers` entry overlapping the segment time range
- Adjusts timing relative to part start
- Builds FFmpeg `drawtext` filter strings

---

### [8.3] Encode — `stages/part_render_encode.py`

**Function:** `render_part_smart(ctx, part_no, seg, setup_result)`

Main FFmpeg call. Builds command from setup_result parameters.

**FFmpeg command structure:**
```bash
ffmpeg -y \
  [-ss {trim_in}] -i {input} [-t {duration}] \
  -vf "scale={w}:{h}[,subtitles={srt}][,{overlay_filters}]" \
  -c:v {codec} -preset {preset} -crf {crf} \
  -c:a aac -b:a 192k \
  {output}
```

**NVENC hardware encoding:**
- Acquires `NVENC_SEMAPHORE` (max 3 sessions) defined in `encoder/ffmpeg_helpers.py:27-28`
- Codec: `h264_nvenc` or `hevc_nvenc`
- Falls back to software encoding if NVENC unavailable or semaphore times out

**Progress monitoring:**
- Background timer thread emits `render.progress` events every 3 seconds
- Calculates `progress_percent` from elapsed / expected duration

**Feature flags:**
- `FEATURE_BASE_CLIP_FIRST` — render base clip without overlays first
- `FEATURE_OVERLAY_AFTER_BASE_CLIP` — composite subtitles/overlays onto base clip afterward

---

### [8.4] Voice Mix — `stages/part_voice_mix.py`

**Function:** `maybe_mix_voice(ctx, part_no, seg, encoded_path)`

Runs only when `payload.voice_enabled=True`.

**Voice source:**
- `voice_source="manual"` → use `ctx.voice_audio_path` from step [2]
- `voice_source="model"` → generate TTS per-segment from segment transcript

**Provider selection:**
```python
voice_provider = (render_plan.audio_plan.voice_provider or "") or payload.tts_engine
# Options: "edge" (default, free), "xtts" (local neural TTS)
```

**Mix command:**
```bash
ffmpeg -y -i {part_video} -i {tts_audio} \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=first[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac {output_with_voice}
```

---

### [8.5] Finalize Per-Part — `stages/part_done.py`

**Function:** `run_part_done(ctx, idx, seg, ...)`

1. **Quality intelligence:** calls `_assess_render_quality_intelligence()` in `qa_pipeline.py` (no-op on failure, Sacred Contract #3)
2. **Cover frame selection:**
   - `_select_cover_frame_time()` with `cover_hint_ratio` from seg (AI-suggested thumbnail offset)
   - Optional `select_best_thumbnail()` if `S4_THUMBNAIL_QUALITY_ENABLED=1`
   - `extract_thumbnail_frame()` as fallback
   - Writes `{output_stem}_cover.jpg`
3. **DB upsert:** `upsert_job_part(DONE, 100, ...)` — terminal transition
4. **Temp cleanup:** delete `raw_part.mp4`, `srt_part`, `ass_part` if `payload.cleanup_temp_files=True`
5. Returns `{"idx", "output", "row", "skipped": False}`

---

### [9] Output Ranking — `pipeline_ranking.py`

**Function:** `_compute_output_ranking_entry()` + `_resolve_rank_from_plan()`

**Score formula:**
```
output_rank_score = (
    viral_score    * 0.35 +
    hook_score     * 0.20 +
    retention_score * 0.20 +
    speech_density  * 0.10 +
    market_score    * 0.10 +
    duration_fit    * 0.05
)
```

**Rank resolution:**
- If `LLM_EMIT_RENDER_PLAN=1` AND `RenderPlan.clips[i].rank` is valid → use AI ranks
- Else → sort by descending `output_rank_score`

**Sacred Contract #1 — these three keys always present in every ranking entry:**
- `output_rank_score`
- `is_best_output`
- `is_best_clip`

---

### [10] Finalize — `pipeline_finalize.py`

**Function:** `run_render_finalize()`

1. Auto-best-export: copy top-N outputs to `output_dir/best/`
2. Determine `_final_status`: `"completed"` or `"completed_with_errors"`
3. Assemble `result_json` — see [DATABASE.md](DATABASE.md) for full schema
4. `upsert_job(JobStage.DONE, result_json)` — terminal job transition
5. Trigger DB backup if `DB_BACKUP_EVERY_N_JOBS` threshold reached

---

## PartRenderContext

Dataclass (`stages/part_render_context.py`) capturing all closure state passed to each worker:

```python
@dataclass
class PartRenderContext:
    job_id: str
    effective_channel: str
    total_parts: int
    work_dir: Path
    output_dir: Path
    output_stem: str
    source_path: Path
    source: dict                          # {title, slug, duration, filepath}
    payload: RenderRequest
    tuned: dict                           # resolved preset profile
    ffmpeg_threads: int
    full_srt: Path
    full_srt_available: bool
    subtitle_enabled_by_idx: dict         # {part_idx: bool}
    voice_audio_path: Optional[Path]
    mv_cfg: dict                          # market-viral config
    hook_apply_enabled: bool
    hook_applied_text: str
    ai_edit_plan: Optional[Any]           # unused in current pipeline
    render_plan: Optional[RenderPlan]     # Sprint 2.3: RenderPlan passed to workers
    target_platform: str
    # Mutable shared lists (passed by reference to workers)
    voice_part_tts_attempts: list
    voice_mix_ok: list
    failed_parts: list
    retry_count: int
```

---

## Error Handling

| Failure Mode | Behavior |
|-------------|----------|
| Source file missing | HTTP 400 before job starts |
| Session expired | HTTP 400 before job starts |
| No audio stream | `LLMPipelineError` raised — job FAILED immediately |
| Whisper fails | `LLMPipelineError` raised — job FAILED immediately |
| LLM Call 1 fails | Returns `None` → empty scored[] → job FAILED (no segments) |
| LLM Call 2 fails | Returns `None` → falls back to Call 1 result (Sacred Contract #3) |
| RenderPlan parse error | Returns `None` → falls back (Sacred Contract #3) |
| FFmpeg subprocess error | Part marked FAILED, added to `failed_parts` list |
| All parts fail | Job status `"failed"` in result_json |
| Some parts fail | Job status `"completed_with_errors"`, `is_partial_success=True` |
| Voice TTS fails | `_voice_tts_failed=True`, render continues without voice |
| Cover frame fails | Warning logged, part marked DONE without cover |
| Subtitle translation partial | Continues with untranslated subtitles for failed parts |

---

## Job Stage Transitions

`JobStage` enum (`core/stage.py`):

```
QUEUED → STARTING → RUNNING → ANALYZING → TRANSCRIBING_FULL →
SCENE_DETECTION → SEGMENT_BUILDING → RENDERING → RENDERING_PARALLEL →
WRITING_REPORT → DONE
(terminal: FAILED, CANCELLED)
```

`DOWNLOADING` is retained in the enum for backward compat but not emitted by the render pipeline.

## Part Stage Transitions

`JobPartStage` enum (`core/stage.py`):

```
QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
(terminal: FAILED, SKIPPED)
```

These names are **frozen** — changing them breaks WebSocket consumers and frontend state machines. See [API_CONTRACT.md](API_CONTRACT.md).
