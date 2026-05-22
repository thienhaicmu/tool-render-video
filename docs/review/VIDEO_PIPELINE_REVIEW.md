# VIDEO_PIPELINE_REVIEW.md — Video Pipeline Review

## Current Pipeline Overview

```
Source video
  ↓ ffprobe: duration, fps, width, height, has_audio
  ↓ Scene detection (PySceneDetect ContentDetector OR TransNetV2)
  ↓ Segment building (silence-aware boundary refinement)
  ↓ Multi-signal scoring (viral + market + hook)
  ↓ [Optional] AI edit plan (transcript-driven)
  ↓ Segment selection (top-N or 3-variant)
  ↓ Full-video Whisper transcription (cached 72h)
  ↓ [Per segment parallel]
      ↓ SRT slicing + subtitle processing
      ↓ [Optional] Translation
      ↓ SRT → ASS conversion (bounce or karaoke)
      ↓ [Optional] TTS narration generation
      ↓ [Optional] Audio cleanup (DeepFilterNet)
      ↓ [Optional] BGM mix (sidechain ducking)
      ↓ Video cut (ffprobe-verified stream copy or encode)
      ↓ Render (motion crop + subtitle burn + speed + color + encode)
      ↓ [Optional] Hook intro / outro / logo watermark
      ↓ Output validation (duration + file size check)
      ↓ Thumbnail extraction
  ↓ AI visibility metadata attachment
  ↓ XLS report
  ↓ Job completed
```

---

## Pipeline Stage Analysis

### Stage 1: Source Acquisition

**What happens**: yt-dlp download (YouTube) or path validation (local).

**Risk**: Large YouTube videos (>1h) can take 5–15min to download synchronously. During this time the render job is in `downloading` state but the UI shows a static spinner with no byte-level progress. If the download hangs (network drop, yt-dlp cookie expiry), there is no timeout at the download stage. The job will hang indefinitely.

**ffprobe validation**: Called to get duration. No explicit codec validation before the render pass — unsupported codec discovered at encode time, not at input validation time.

---

### Stage 2: Scene Detection

**What happens**: PySceneDetect with `ContentDetector` (default) or `AdaptiveDetector` or `TransNetV2` (if installed).

**Strengths**:
- Frame-skip auto-tuning (`_auto_frame_skip`) based on source FPS — smart.
- TransNetV2 singleton with double-checked lock — correct.
- 72h cache keyed by (path, mtime, size) — correct invalidation.
- Deduplication merge gap for TransNetV2 cut points.

**Risks**:
- `detect_scenes()` runs on the full source video. For a 2-hour source, this is 2+ minutes of CPU. No progress reporting during scene detection — the job shows `scene_detection` stage but the progress bar doesn't move.
- If TransNetV2 is installed but returns garbage (corrupted model), the fallback is not automatic — it raises and the render fails at scene detection.
- Scene detection result has no FPS validation: if the source FPS is misidentified (e.g. VFR video), scene timestamps may be off by a proportional factor.

---

### Stage 3: Segment Building

**What happens**: `build_segments_from_scenes()` → raw candidate segments. `refine_segment_boundaries()` → boundary snap to scene cuts. `refine_cuts_for_naturalness()` → silence-aware alignment.

**Risks**:
- Silence detection in `refine_cuts_for_naturalness()` uses ffprobe `silencedetect` filter. For long videos this adds another subprocess call per segment candidate.
- No minimum segment pool size validation. If scene detection returns 1 scene (e.g. static talking head), all segments will be the same or overlapping. No error raised — the pipeline continues with a degenerate pool.

---

### Stage 4: Scoring

**What happens**: `score_scenes_clip()` → `score_segments()` → `_mv_score_part()`. Produces viral_score, hook_score, market_score, scene_quality_score, etc.

**Weaknesses**:
- `viral_scorer.py` is almost entirely heuristic. The ML path (sklearn Ridge regression) requires `_MIN_SAMPLES_TO_TRAIN = 30` feedback records and `train_model()` to be called manually. No user-facing UI to trigger training. In practice, all scoring is heuristic-only.
- Hook score is based on simple temporal position (early segments get a bonus) and scene density, not actual speech content analysis at this stage.
- `retention_score` is populated via `apply_retention_proxy()` which is a weighted alias for scene_quality_score — not real retention data.

---

### Stage 5: Transcription

**What happens**: Full-video Whisper transcription (base model default, medium optional).

**Risks**:
- **Blocking**: Whisper runs synchronously on the render thread. For a 1-hour video with Whisper medium, this can take 10–20min on CPU. The job is stuck at `transcribing_full` with no sub-progress.
- **Thread contention**: `_get_transcribe_lock(model_name)` ensures only one thread transcribes with a given model at once. With `MAX_CONCURRENT_JOBS=2` (CPU//2 default on 4-core), the second render job waits while the first transcribes. Silent wait.
- **Model loading**: `get_whisper_model()` holds `_MODEL_CACHE_LOCK` during model load (potentially 30–60s). All concurrent callers block. The lock is released immediately after load, but the first cold start is a hard stall.
- **Cache miss cost**: The 72h transcription cache is by (path, mtime, size). If the source file is re-downloaded (new yt-dlp session, different work_dir), the cache misses even for the same URL.

---

### Stage 6: Per-Part Render (FFmpeg)

**What happens**: `cut_video()` → extract segment. `render_part_smart()` → full render.

#### Subtitle Sync Risks

**`slice_srt_by_time()`** adjusts timestamps by subtracting `start_sec`. The math is straightforward but:
- If Whisper produces word-level segments with very short durations (<0.1s), the ASS conversion may produce zero-duration events that FFmpeg either drops or renders as flashes.
- `WORD_MIN_DURATION_SEC = 0.12` and `WORD_MERGE_SHORTER_THAN_SEC = 0.11` guard against this in the ASS converter, but the SRT slice step has no equivalent guard.

**Subtitle Timing at Non-1.0 Speed**: The ASS filter runs **before** `setpts=PTS/speed` in the vf_chain (see vf_chain order above). This means subtitle timestamps are expressed in source-clip seconds, and `setpts` re-clocks the frames so the subtitle appears at `source_t / speed` in the output — correctly synchronized with the sped-up video and audio.

The real impact is subtitle *display duration compression*: a subtitle meant to display for 3.0s at natural speed is shown for 3.0/1.15 ≈ 2.6s at 1.15x. At high speeds this may make text harder to read. The accumulated effect over a 60s clip is that the final subtitles appear and disappear more quickly than at 1.0x. This is a legibility concern, not a synchronization desync.

**Current State (2026-05-22)**: The `ass-before-setpts` ordering is confirmed correct and intentional. The vf_chain order MUST NOT be changed. Phase 2+ will address subtitle display duration compression as a separate concern.

- Historical note: earlier reviews described this as "drift" or "desync." That description was imprecise. The subtitles are in sync with the corresponding video frames and audio; the issue is compressed reading time per subtitle block.

#### FPS Handling

**`_probe_video_metadata()`** prefers `avg_frame_rate` then falls back to `r_frame_rate`. For VFR (variable frame rate) video (common in screen recordings), both fields may be unreliable. The pipeline uses the detected FPS to compute output FPS. If misdetected (e.g. 24000/1001 ≈ 23.976 read as 24), the encoded output has a slightly different FPS from the source — harmless but pedantically wrong.

FFmpeg filter chains do not explicitly set `-r` output framerate, so FFmpeg infers from the input — usually correct but can produce VFR output for VFR inputs, which some platforms dislike.

#### Aspect Ratio Handling

The crop-to-aspect pipeline uses `render_motion_aware_crop()` which applies scale + crop filters. The target resolutions are hardcoded:
- `9:16` → PlayResY=1920
- `1:1` → PlayResY=1080
- `3:4` → PlayResY=1440
- `16:9` → PlayResY=1080

**Risk**: If the source video is already 9:16 (e.g. a vertical TikTok re-exported) and the user selects 9:16, the crop filter runs unnecessarily with no detection of "already correct aspect ratio" — wastes encode time and marginally degrades quality via double encode.

#### Black Frame Risk

`detect_bad_first_frame()` exists in `render_engine.py` and is called by `render_part_smart()`. It checks if the first frame of the rendered clip is black. If detected, it tries a 0.1s seek offset retry. This is a good guard, but:
- The check runs after the full render, not before — a black first frame is discovered after a multi-minute encode.
- The retry does not change the segment selection — it re-renders the same segment with a tiny offset. If the segment genuinely opens on black (title card, fade-in), the retry just produces another black frame.

#### Audio-Video Sync

Multiple audio manipulations are applied in sequence: speed (atempo), loudnorm, narration mix. The order matters for sync:
- `atempo` changes playback speed → audio duration changes
- The narration is generated from the SRT text at source speed, then the video is sped up
- `mix_narration_audio()` mixes based on original narration duration

If `playback_speed != 1.0` AND `tts_enabled=True`, the TTS narration will be out of sync because the narration was generated for the original-speed clip but is burned into the sped-up video. There is no atempo compensation applied to the narration track.

---

### Stage 7: Output QA

**`_validate_render_output()`** checks:
- Output file exists and size > 0
- Duration within expected range (±20% of expected)

**Weakness**: 20% tolerance is very wide. A 60s clip can pass QA at 48s–72s. A subtitles-only rendering error that produces a 90% correct clip with silent audio passes QA.

No check for:
- Audio stream presence (output may be video-only if audio mix failed silently)
- Subtitle presence in output (subtitle burn-in failure is silent — FFmpeg may skip bad ASS events)
- Keyframe placement (for streaming compatibility)
- Codec compliance (H.264 baseline for TikTok compatibility)

---

## Render Speed Bottlenecks

| Stage | Time Cost | Notes |
|-------|-----------|-------|
| YouTube download | 30s–15min | No timeout, no progress |
| Scene detection | 1–5min | CPU-bound, no sub-progress |
| Whisper transcription | 2–20min | CPU-bound, blocks all concurrent renders |
| Motion crop (MediaPipe) | Adds 30–60% to encode time | GPU not used for MediaPipe |
| NVENC encode | 3–10x faster than libx264 | Only if GPU present and NVENC enabled |
| DeepFilterNet audio | 5–30s per clip | Optional but slow on CPU |

**Repeated FFmpeg work**: For variant rendering (3 variants), scene detection runs once (cached), scoring runs once, but transcription runs once and SRT processing runs 3x, and the full render runs 3x. There is no sharing of intermediate cut files between variants.

---

## Output Quality Risks

1. **Subtitle drift at non-1.0 speeds** — timestamps not adjusted for playback speed delta.
2. **TTS desync at non-1.0 speeds** — narration not speed-adjusted to match video.
3. **No codec compliance validation** — output may use B-frames (not TikTok-safe).
4. **Black frame risk on scene transitions** — first frame detection is post-render only.
5. **Variable FPS output** — no `-r` forcing may produce VFR output.
6. **Wide QA tolerance** (±20%) — real quality regressions pass validation.
7. **Zero audio check** — muted output passes QA if file has size > 0 and duration is in range.
