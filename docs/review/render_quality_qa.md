# Render Quality QA Checklist

**Purpose:** Manual and automated QA coverage for render pipeline output quality.
**Scope:** scene_detection, subtitle timing, segment cutting, voice/audio sync, motion_crop, black frames, transitions.
**Debug mode:** Set `RENDER_DEBUG_LOG=1` to enable per-scene boundary logs, timeline JSON (`{slug}_timeline.json`), and per-part metadata JSON (`{slug}_part_NNN_meta.json`) in the job work directory.

---

## Root Cause Analysis

### QA-001 — Black Frames at Video Start

**Status:** Partially mitigated. Open risk on stream-copy path.

**Mechanism:**
1. `detect_bad_first_frame()` (render_engine.py:563) runs `blackdetect=d=0.0:pix_th=0.10` on the first 1.5 s of each clip.
2. If a dark region starting at ≤0.08 s is found, `_visual_trim` shifts `_effective_start` forward and sets `_force_accurate_cut=True`.
3. If no dark region is detected (pix_th=0.10 misses near-black frames), `force_accurate_cut=False` and the clip is cut with stream-copy.
4. Stream-copy (`-ss start -t dur -i input -c copy`) seeks to the nearest keyframe **at or before** `start`. The first output frame is the keyframe, not `start`. `-avoid_negative_ts make_zero` adjusts PTS but does not remove the extra frames before the intended start. Result: up to one keyframe interval (often 2–5 s at default GOP) of pre-cut content appears at the beginning.

**Affected files:**
- `backend/app/services/render_engine.py` — `detect_bad_first_frame()`, `cut_video()`
- `backend/app/orchestration/render_pipeline.py` — first-frame scan block (~line 3413)

**Reproducible test case:**
- Source: any video where scene segment starts mid-GOP (not at a keyframe)
- Expected: first frame of output = source frame at `_effective_start`
- Observed: first 1–5 frames are from before `_effective_start` when stream-copy is used

**Proposed fix (minimal):**
- Lower `black_pix_threshold` from 0.10 → 0.06 to catch more near-black frames
- When stream-copy produces a file with `duration > intended_duration + 0.1s`, automatically retry with `force_accurate_cut=True`
- `cut_video()` already logs `cut_mode=copy` with raw_duration; this data can drive the auto-retry

---

### QA-002 — Subtitles Not Matching Voice

**Status:** Two independent root causes identified.

**Root cause A — Stream-copy keyframe drift (primary):**
Same mechanism as QA-001. If stream-copy includes frames before `_effective_start`, the video content at time 0 in the rendered file is actually source content before the intended cut. Subtitle timestamps are rebased from `_effective_start` → 0, so they are shifted relative to what is actually playing. Magnitude: up to one GOP interval (1–5 s drift at worst case).

**Root cause B — Speed applied to video but not to subtitle pre-render rebase:**
`slice_srt_by_time()` is called with `apply_playback_speed=False` (render_pipeline.py:3495). This is intentional: the `setpts=PTS/{speed}` filter in FFmpeg is applied AFTER the `ass=` subtitle burn-in filter, so both video and burned subtitle are uniformly compressed in time together. Speed is NOT a source of drift when subtitles are burned in via `ass=`.

**Note:** If subtitles are played externally (SRT/ASS sidecar, not burned in), `apply_playback_speed=False` WOULD cause drift at any speed ≠ 1.0. Burn-in path is safe; sidecar path is not.

**Root cause C — SRT rebase from `_effective_start` vs. actual keyframe position:**
`slice_srt_by_time` uses `_effective_start` as the rebase origin. If stream-copy starts from an earlier keyframe, the SRT timestamps do not match the actual frame positions. Detected via `source_offset` field in `subtitle_file_chain` log.

**Affected files:**
- `backend/app/services/render_engine.py` — `cut_video()`, `render_part()` filter chain
- `backend/app/services/subtitle_engine.py` — `slice_srt_by_time()`
- `backend/app/orchestration/render_pipeline.py` — subtitle slice call (~line 3488)

**Reproducible test case:**
- Source: video with speech starting at a non-keyframe boundary
- Set `RENDER_DEBUG_LOG=1`, check `subtitle_file_chain` log `source_offset` value
- If `source_offset` ≠ 0 and stream-copy was used (`cut_mode=copy`), drift = `source_offset`

**Proposed fix (minimal):**
- Same as QA-001 fix: auto-retry stream-copy with `force_accurate_cut=True` when raw_duration > intended_duration + tolerance
- This eliminates both QA-001 and QA-002A simultaneously

---

### QA-003 — Rough Scene Transitions

**Status:** By design limitation. No cross-fade between clips.

**Mechanism:**
- Each rendered part has an opening `fade=t=in:st=0:d={max(0.03, min(0.08, transition_sec))}` (render_engine.py:932).
- Cap: 0.03–0.08 s (0.9–2.4 frames at 30fps). This is visually imperceptible and does not soften cuts.
- In the motion crop path, cap is wider: `max(0.05, min(0.8, transition_sec))` (motion_crop.py:1996), allowing up to 0.8 s dissolves.
- No xfade or cross-dissolve between consecutive output parts — each is a standalone file.
- Segment boundaries are selected algorithmically (high viral_score / hook_score), not at natural pause or edit points.

**Affected files:**
- `backend/app/services/render_engine.py` — `render_part()` fade filter (~line 929)
- `backend/app/services/motion_crop.py` — `render_motion_aware_crop()` fade filter (~line 1995)
- `backend/app/services/segment_builder.py` — segment boundary selection

**Reproducible test case:**
- Any multi-part export
- Play parts consecutively and observe abrupt cuts at segment boundaries

**Proposed fix (minimal, requires product decision):**
- Increase `transition_sec` cap in `render_part()` from 0.08 → 0.25 s for non-montage content
- Add `starts_at_scene_cut` awareness in segment selection: prefer cuts that align with detected scene boundaries (reduces mid-motion cuts)
- These are behavior changes requiring product approval

---

### QA-004 — Motion Crop Jumping

**Status:** Velocity limiter in place but three jump sources identified.

**Mechanism:**
1. Subject tracking runs every `subject_detect_interval` frames (default 16 frames = 0.53 s at 30fps). Between detections, OpenCV KCF/CSRT/MOSSE tracker extrapolates. When the next detection fires at a significantly different position, the velocity limiter (`_apply_velocity_limiter`) caps jump speed to `max_pan_speed_ratio=0.010` frame-widths/frame and acceleration `max_pan_accel_ratio=0.0045`.
2. At scene cuts: `_detect_scene_ranges_in_clip()` resets tracker (motion_crop.py:1945). The new clip starts subject detection from scratch, and the initial crop center jumps to the new detected position. The velocity limiter smooths this, but if the subject is in a very different position, 5–15 frames of visible pan can still occur.
3. If MediaPipe face detection fails for many consecutive frames, the tracker may lock onto background motion. When face re-acquired, the crop snaps back.

**Affected files:**
- `backend/app/services/motion_crop.py` — `build_motion_path()`, `_apply_velocity_limiter()`, `_subject_to_crop_center()`

**Reproducible test case:**
- Source: interview video with camera cuts or subject leaving frame
- Enable `motion_aware_crop=True`
- Set `RENDER_DEBUG_LOG=1`, check `motion_crop_path` log: large differences between `first_xy`, `mid_xy`, `last_xy` indicate jump

**Proposed fix (minimal):**
- Reduce `subject_detect_interval` from 16 → 8 for interview/commentary content to improve tracking continuity
- This is a tuning change, not a behavior change, and is safe to apply

---

## QA Checklist

### 1. Scene Detection

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Scene count reasonable | `RENDER_DEBUG_LOG=1` logs | 1–50 scenes per 5-min source | `Scene detection done: N scenes` |
| No duplicate scene boundaries | `scene_boundary` debug logs | Each `start` < `end`, monotonic | `scene_boundary idx=N start=... end=...` |
| Transition scores in range | debug logs | 0.1–1.0 | `transition_score=...` |
| Frame skip not too aggressive | log fps | `frame_skip` ≤ 7 (≤ 8 fps analysis rate) | `_auto_frame_skip` internal |

### 2. Segment Cutting

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Cut mode logged | render log | `cut_mode=copy` or `cut_mode=accurate` | `cut_video: cut_mode=...` |
| Duration matches intent | render log | `raw_duration` within tolerance | `intended_duration=X raw_duration=Y` |
| Silence trim applied correctly | render log | `trim_offset_sec` ≤ 1.5 | `silence_trim_applied` event |
| Black frame detection triggered | render log | `first_frame_shift_applied` event logged when dark | `first_frame_shift_applied` |
| Accurate cut forced after visual trim | render log | `force_accurate_cut=True` after any shift > 0 | `accurate_cut_forced` event |

### 3. Subtitle Timing

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Subtitle count > 0 for speech | render log | `count > 0` for clips with speech | `subtitle_part_sync count=N` |
| First subtitle timestamp near 0 | debug log | `first_ts` ≈ 0.0–2.0 s (rebased) | `subtitle_file_chain first_ts=...` |
| Source offset = 0 | debug log | `source_offset=0.0` (no rebase drift) | `subtitle_file_chain source_offset=...` |
| SRT file non-empty | debug log | `srt_size > 0` | `subtitle_file_chain srt_size=...` |
| ASS file non-empty | debug log | `ass_size > 0` | `subtitle_file_chain ass_size=...` |
| Speed not applied in rebase | render log | `apply_playback_speed=False` (burn-in path) | `subtitle_part_sync apply_playback_speed=False` |

### 4. Voice/Audio Sync

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Audio filter applied at speed ≠ 1.0 | debug log | `atempo=X.XXXX` in audio_filter when speed ≠ 1.0 | `render_part audio_filter=...` |
| setpts matches atempo | vf_chain log | `setpts=PTS/X` value matches `atempo=X` | `render_part vf_chain=...` |
| Audio stream present | render log | `input_has_audio=True` | `render_part:` info line |
| No BGM amplitude clipping | listening test | Volume ≤ -1 dBFS | `alimiter=limit=0.95` in filter |

### 5. Motion Crop

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Motion path computed | render log | `motion_cache_miss` or `motion_cache_hit` with `centers > 0` | `motion_cache_miss centers=N` |
| Crop dimensions valid | debug log | `crop_src=WxH` fits within source resolution | `motion_crop_path crop_src=...` |
| No large position jumps | debug log | `first_xy`, `mid_xy`, `last_xy` within ≤30% of frame width difference | `motion_crop_path first_xy=... mid_xy=... last_xy=...` |
| Subtitle-safe ceiling enforced | code review | `subtitle_safe_bottom_ratio > 0` in MotionCropConfig | `motion_crop.py:820` |

### 6. Black Frames

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Black frame scanner runs | render log | `first_frame_scan_ms` logged per part | `first_frame_scan_ms=...` |
| Shift applied when dark | render log | `shift > 0.0` → `first_frame_shift_applied` event | `first_frame_shift_applied` |
| Accurate cut used after shift | render log | `accurate_cut_forced` event follows shift | `accurate_cut_forced` event |
| Stream-copy duration mismatch caught | render log | `duration_mismatch` triggers re-encode | `cut_video: cut_mode=accurate fallback_reason=duration_mismatch` |

### 7. Transitions

| Check | Method | Expected | Log Key |
|---|---|---|---|
| Fade-in applied per part | vf_chain log | `fade=t=in:st=0:d=...` in chain | `render_part vf_chain=...` |
| Transition duration logged | render log | `transition_sec` value visible in render call | `render_part_smart` call context |
| Motion crop path uses wider fade cap | code review | 0.05–0.8 s cap in motion_crop.py vs. 0.03–0.08 s in render_engine.py | `motion_crop.py:1996` vs `render_engine.py:932` |

---

## Debug Artifacts (RENDER_DEBUG_LOG=1)

Set env var before starting the backend:
```
RENDER_DEBUG_LOG=1
```

Artifacts written to `{work_dir}`:
| File | Contents |
|---|---|
| `{slug}_timeline.json` | All selected segments with scores and timecodes |
| `{slug}_part_NNN_meta.json` | Per-part metadata: timecodes, scores, file paths |
| `{slug}_part_NNN.srt` | Per-part SRT (rebased to 0) — always present |
| `{slug}_part_NNN.ass` | Per-part ASS (generated from SRT) — always present |
| `{slug}_part_NNN_raw.mp4` | Raw cut segment before render — always present |

Additional debug log lines (visible in `RENDER_DEBUG_LOG=1` mode):
- `scene_boundary idx=N start=... end=... transition_score=...` — per detected scene
- `selected_segment part=N start=... end=... viral=... motion=... hook=...` — per selected segment (INFO, always)
- `render_part vf_chain=...` — full FFmpeg video filter chain per part
- `render_part audio_filter=...` — audio filter chain per part
- `render_part ffmpeg_cmd=...` — full FFmpeg command per part
- `motion_crop_path centers=N first_xy=... mid_xy=... last_xy=...` — crop path sample positions

---

## Fix Plan by Priority

| ID | Issue | Fix | Files | Risk |
|---|---|---|---|---|
| QA-FIX-01 | Black frames / subtitle drift from stream-copy keyframe alignment | Auto-retry `cut_video` with `force_accurate_cut=True` when `raw_duration > intended + 0.1 s` | `render_engine.py:cut_video()` | Low — additive fallback, no behavior change on clean cuts |
| QA-FIX-02 | Near-black frames not detected (pix_th too high) | Lower `black_pix_threshold` from 0.10 → 0.06 | `render_engine.py:detect_bad_first_frame()` | Low — may detect slightly more false positives |
| QA-FIX-03 | Motion crop jumping on scene cuts | Reduce `subject_detect_interval` 16 → 8 for interview/commentary | `motion_crop.py:build_motion_path()` | Low — slower, but only for interview/commentary |
| QA-FIX-04 | Rough transitions (short fade cap) | Increase fade cap in `render_part()` 0.08 → 0.20 s for non-montage | `render_engine.py:render_part()` | Medium — changes visual output, needs A/B test |
| QA-FIX-05 | Subtitle sidecar drift at speed ≠ 1.0 | Document that sidecar path requires `apply_playback_speed=True` | `subtitle_engine.py`, API docs | None — documentation only |
