# Render Pipeline

File: `backend/app/orchestration/render_pipeline.py`  
Entry point: `run_render_pipeline(job_id, payload, resume_mode, load_session_fn, cleanup_session_fn)`

---

## Stage sequence

```
QUEUED → STARTING → DOWNLOADING → SCENE_DETECTION → SEGMENT_BUILDING
       → TRANSCRIBING_FULL → RENDERING (or RENDERING_PARALLEL) → WRITING_REPORT → DONE
```

Each stage maps to a `JobStage` enum value stored in the `jobs.stage` column and emitted as a structured log event via `_emit_render_event()`.

---

## Stage 1 — Source preparation (`DOWNLOADING`, 5%)

Three possible paths depending on payload:

### A. Editor session (from prepare-source)

```python
edit_session_id = payload.edit_session_id
sess = load_session_fn(edit_session_id)
source_path = Path(sess["video_path"])   # original path, no re-download
```

`sess["video_path"]` is the original local path or the YouTube download path from the editor session. No copy is made here.

### B. Local file (source_mode = "local")

```python
source_path = Path(payload.source_video_path).expanduser().resolve()
```

File is used directly from its original location. No copy is created at this stage.

### C. YouTube download (source_mode = "youtube")

```python
source = download_youtube(yt_url, work_dir)
source_path = Path(source["filepath"])   # TEMP_DIR/{job_id}/source.mp4
```

`download_youtube()` uses a 10-attempt multi-client retry strategy. See [DOWNLOAD_SYSTEM.md](DOWNLOAD_SYSTEM.md).

---

## Editor edits (trim / volume)

Immediately after source resolution, if the user applied trim or volume in the editor:

```python
if needs_trim or needs_volume:
    edited_path = work_dir / f"edited_{source_path.stem}.mp4"
    # ffmpeg -ss {trim_in} -i source -t {duration} [-af volume=X] -c:v copy edited_path
    source_path = edited_path
```

This creates one additional intermediate file in `TEMP_DIR/{job_id}/`. The original source is not modified.

---

## Source archive (`keep_source_copy`)

When `payload.keep_source_copy = True` (frontend default):

```python
keep_source_dir = output_dir.parent / "source"   # e.g. channels/T1/upload/source/
keep_path = _reserve_source_path_in_dir(keep_source_dir, slug, ext)

is_temp_source = str(source_path).startswith(str(TEMP_DIR))

if is_temp_source:
    shutil.move(source_path, keep_path)       # YouTube / edited: zero-copy move
else:
    try:
        os.link(source_path, keep_path)       # local: hardlink (O(1), same volume)
    except OSError:
        shutil.copy2(source_path, keep_path)  # fallback: full copy (cross-volume)
```

After this block, `source_path = keep_path`. All downstream steps (scene detection, whisper, cut) read from `keep_path`.

**Performance note:** The hardlink optimization (`os.link`) makes archiving a local source effectively free when source and destination are on the same NTFS volume.

---

## Stage 2 — Scene detection (`SCENE_DETECTION`, 15%)

```python
scenes = detect_scenes(str(source_path))   # when auto_detect_scene=True
```

Uses `PySceneDetect` `ContentDetector(threshold=28.0)` with auto frame-skip:
- Target: analyze ~8 fps regardless of source FPS
- 30fps → skip 3 frames (analyze every 4th)
- 60fps → skip 7 frames (analyze every 8th)
- Returns `[{"start": float, "end": float, "transition_score": float}]`

---

## Stage 3 — Segment building (`SEGMENT_BUILDING`, 25%)

```python
segments = build_segments_from_scenes(scenes, source["duration"], min_part_sec, max_part_sec)
scored = score_segments(segments, scenes)
```

Segments respect `min_part_sec` and `max_part_sec` boundaries. Each segment is scored for:
- `viral_score` — combined metric
- `motion_score` — optical flow / scene activity
- `hook_score` — opening hook likelihood

**High-motion filter:** If ≥3 segments have `motion_score ≥ 60`, only those are kept.

**Part ordering:**
- `part_order = "viral"` (default) — top-scored segments first
- `part_order = "timeline"` — chronological order

**Max export cap:** `max_export_parts` truncates the list after scoring and ordering.

---

## Stage 4 — Full transcription (`TRANSCRIBING_FULL`, 28%)

Run once for the entire source video, only when subtitles are enabled:

```python
transcribe_to_srt(str(source_path), str(full_srt), model_name=tuned["whisper_model"])
```

Whisper model is selected by render profile:
- `fast` → `tiny`
- `balanced` → `base`
- `quality` → `small`
- `best` → `small`
- `whisper_model = "auto"` → profile default

The full SRT is then sliced per-part using `slice_srt_by_time()`. This avoids re-transcribing each segment individually.

---

## Stage 5 — Per-part render (`RENDERING` / `RENDERING_PARALLEL`, 30–90%)

Each part goes through this sequence inside `_process_one_part()`:

```
QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
```

### 5a. Cut raw part

```python
cut_video(str(source_path), str(raw_part), seg["start"], seg["end"])
# ffmpeg -ss start -to end -i source -c copy raw_part.mp4
```

### 5b. Subtitle (if enabled)

```python
slice_srt_by_time(full_srt, srt_part, seg["start"], seg["end"], rebase_to_zero=True)
translate_srt_file(srt_part, translated_srt_part, target_language)  # optional
srt_to_ass_karaoke(...)   # or srt_to_ass_bounce(...)
```

Subtitle styles: `pro_karaoke` or `bounce`. Karaoke has per-word highlight animation.

Subtitle viral gate: if `subtitle_only_viral_high=True`, only segments with `viral_score >= subtitle_viral_min_score` get subtitles. A safety fallback enables all parts if no segments pass the gate.

### 5c. Render final part

```python
render_part_smart(
    raw_part, final_part, ass_file,
    aspect_ratio,         # "9:16" for vertical, "3:4" etc.
    frame_scale_x/y,      # crop scale
    motion_aware_crop,    # optical-flow subject tracking
    reframe_mode,         # "subject" or "center"
    effect_preset,        # visual effect
    video_codec,          # h264 / h265 / vp9
    video_crf, video_preset,
    text_layers,          # custom text overlays
    ...
)
```

A background progress timer thread writes interpolated 70–99% estimates to the DB every 3 seconds while FFmpeg runs.

### 5d. Voice narration mix (if enabled)

```python
generate_narration_mp3(text, language, gender, rate, job_id)
mix_narration_audio(video_path, narration_audio_path, mix_mode, output_path)
os.replace(mixed_part, final_part)
```

See [VOICE_NARRATION.md](VOICE_NARRATION.md) for voice sources and mix modes.

---

## Parallelism

The number of parallel workers is computed from hardware and payload flags:

```python
if gpu_ready:
    base = max(2, cpu_total // 3)
    hard_ceiling = 6
    heavy_penalty = sum([motion_aware_crop, reup_mode])  # CPU pre-pass ops
else:
    base = max(1, cpu_total // 4)
    hard_ceiling = 4
    heavy_penalty = sum([motion_aware_crop, add_subtitle, reup_mode, text_layers])

hw_cap = max(1, min(base - heavy_penalty, hard_ceiling))
max_workers = max(1, min(user_req or hw_cap, hw_cap))
```

`max_parallel_parts = 0` means adaptive (backend decides). Any value ≥ 1 caps workers at that number but still respects `hw_cap`.

---

## Stage 6 — Report (`WRITING_REPORT`, 95%)

```python
append_rows(report_path, headers, rows)
# Writes/appends to channels/T1/upload/video_output/render_report.xlsx
```

Each row: `job_id, channel_code, video_title, part_no, start, end, duration, viral_score, priority_rank, output_file`

---

## Resume mode

When `resume_from_last=True`:

- Per-part: if `final_part.exists()` and size > 0 → skip (mark `done`)
- Cut step: if `raw_part.exists()` and size > 0 → skip re-cut
- Transcription: if `full_srt.exists()` and size > 0 → reuse existing

The full payload is stored in `payload_json` in SQLite, enabling full replay of the exact same settings.

---

## Error handling

Three error log destinations:
- Type 1 (request/validation): `data/logs/request.log` — never enters pipeline
- Type 2 (pipeline failure): `data/logs/error.log` + `channels/<code>/logs/{job_id}.log`
- Type 3 (system/unexpected): uvicorn default handler → `desktop-backend.log`

On pipeline failure, the job is marked `failed` in SQLite with `failed_step = current_stage`. Part failures are isolated — other parts continue rendering.

---

## Cleanup

```python
finally:
    if payload.cleanup_temp_files:
        shutil.rmtree(work_dir, ignore_errors=True)   # TEMP_DIR/{job_id}/ only
    if edit_session_id:
        cleanup_session_fn(edit_session_id)            # TEMP_DIR/preview/{id}/
```

The user's original local file and the `keep_path` archive are never deleted by cleanup.

---

## Render profiles

| Profile | Preset | CRF | Whisper | Transition |
|---|---|---|---|---|
| `fast` | veryfast | 23 | tiny | 0.12s |
| `balanced` | medium | 18 | base | 0.25s |
| `quality` | slow | 15 | small | 0.35s |
| `best` | slower | 13 | small | 0.40s |

Individual fields in `RenderRequest` (`video_preset`, `video_crf`, `whisper_model`) override profile defaults.
