# Render Pipeline

File: `backend/app/orchestration/render_pipeline.py`  
Entry point: `run_render_pipeline(job_id, payload, resume_mode, load_session_fn, cleanup_session_fn)`

## Pipeline Identity

**Stability marker: Stable contract**

The render pipeline is the execution spine of the AI rendering intelligence platform. It coordinates validation, source preparation, AI metadata, subtitles, voice, motion crop, FFmpeg execution, output validation, ranking, and result JSON.

FFmpeg is the execution backend. It is not the product identity.

The pipeline must remain conservative:

- Existing render payloads must keep working.
- Optional systems must fail soft where possible.
- Partial clip failures should not fail the whole job when other outputs are usable.
- Result JSON, job stages, part rows, and output aliases are compatibility contracts.

## End-to-End Flow

**Stability marker: Stable contract**

```text
Input payload
  -> request/source validation
  -> source load or download
  -> preview/editor session resolution
  -> optional editor trim/volume
  -> optional source archive
  -> scene detection
  -> segment generation
  -> viral/hook/motion scoring
  -> optional full subtitle transcription
  -> optional AI Director planning
  -> optional bounded AI render influence
  -> per-part cut
  -> per-part subtitle slice/translate/style
  -> per-part motion crop/reframe/FFmpeg render
  -> per-part voice/TTS/audio mix
  -> output validation and quality checks
  -> output ranking and best clip selection
  -> report and result_json
```

## Stage Model

**Stability marker: Stable contract**

Stages are represented by `JobStage` and stored in the `jobs.stage` column.

Typical sequence:

```text
queued
-> starting
-> downloading
-> scene_detection
-> segment_building
-> transcribing_full
-> rendering or rendering_parallel
-> writing_report
-> done or failed
```

Part-level stages are stored in `job_parts` and include queued/waiting/cutting/transcribing/rendering/done/failed.

UI-visible terminal job statuses include `completed`, `completed_with_errors`, `failed`, and `interrupted`. Preserve `completed_with_errors` for partial-success jobs because the UI/history layer can use it to distinguish successful outputs with failed parts from clean completion.

### What must not break: render stages

- Keep stage strings compatible with `/api/jobs/*` and frontend monitor rendering.
- Preserve structured render events used by logs and UI.
- Preserve startup recovery behavior: unfinished jobs become `interrupted`, not silently resumed.

## Source Preparation and Preview Sessions

**Stability marker: Stable contract**

Source resolution has three paths:

| Source path | Behavior |
|---|---|
| Editor session | `edit_session_id` resolves to a saved preview session created by `/api/render/prepare-source`. |
| Local file | `source_video_path` is validated and used from disk. |
| YouTube | `download_youtube()` downloads into the job work directory or preview session. |

Preview sessions live under `TEMP_DIR/preview/{session_id}` and store `session.json`, source path, preview path, export dir, duration, and optional preview transcript cache.

Browser-safe preview may be generated through `_ensure_h264_preview()`, but the render pipeline should use the original source path where possible.

## Validation Rules

**Stability marker: Stable contract**

Validation happens before queueing and again after rendering.

Pre-render validation protects:

- source mode
- output directory
- local file existence
- YouTube URL presence
- editor session presence
- channel/manual output compatibility
- schema constraints from `RenderRequest`

Post-render validation protects:

- final file exists
- file is not trivially small
- ffprobe can read the output
- output has a video stream
- duration is plausible
- audio presence is checked when expected

Validation failures must produce useful messages without corrupting job state.

## Scene Detection and Segment Generation

**Stability marker: Semi-stable implementation**

Scene detection is handled by `backend/app/services/scene_detector.py`. Segment building is handled by `backend/app/services/segment_builder.py`.

The pipeline uses scenes plus source duration to create candidate segments within `min_part_sec` and `max_part_sec`. Segments are then scored and ordered before rendering.

Preserve these behaviors:

- Segment start/end must remain source-time based until SRT slicing rebases per part.
- `max_export_parts` limits selected outputs after scoring/order logic.
- `part_order` controls output order. Current known values include viral/combined-style ordering and timeline ordering.

## Viral, Hook, Retention, and Market Scoring

**Stability marker: Semi-stable implementation**

Scoring is part of the intelligence layer:

- `viral_scorer.py` scores candidate segments using timing, scene density, motion, and hook position.
- `viral_scoring.py` scores market fit for US/EU/JP using hook patterns, keywords, duration, tone, and readability.
- The pipeline may combine viral, hook, market, motion, retention, and quality penalty signals into output ranking.

Market-aware rendering is not just decoration. It affects subtitle policies, hook handling, market scoring, and ranking metadata.

## AI Director Integration

**Stability marker: Experimental / needs verification**

AI Director is called when `ai_director_enabled=true`.

Primary file:

- `backend/app/ai/director/ai_director.py`

The AI Director creates an `AIEditPlan` from transcript, scene, duration, source, market, memory, pacing, subtitle, camera, creator, and quality signals.

Important safety contract:

- If AI Director fails, render continues.
- AI plan metadata is optional.
- AI phases must not assume internet/cloud/GPU.
- Most AI phases are advisory or metadata-only.

## Advisory Metadata vs Bounded Render Influence

**Stability marker: Experimental / needs verification**

The pipeline distinguishes:

- **Advisory AI:** plans, reasons, scores, recommends, explains.
- **Bounded AI execution:** opt-in, narrow payload influence under safety gates.

`ai_render_influence_enabled` allows `backend/app/ai/director/render_influence.py` to apply small safe changes. Current examples include limited subtitle/camera influence. It must not rewrite playback speed, segment timing, FFmpeg commands, output validation, or executor behavior.

### What must not break: AI influence

- Defaults must keep AI off.
- Render must work when AI modules return fallback metadata.
- Bounded influence must remain traceable in `ai_render_influence`.
- Advisory-only phases must not silently become execution phases.

## Subtitle Pipeline

**Stability marker: Stable contract**

Subtitle work is centralized in `backend/app/services/subtitle_engine.py`.

Flow:

```text
full source audio
  -> Whisper full SRT
  -> per-part SRT slice
  -> rebase timing to zero
  -> optional translation
  -> optional market hook/line-break/emphasis logic
  -> ASS generation
  -> FFmpeg burn-in
```

The full SRT is generated once for the source, then sliced per selected segment. This avoids per-part transcription and keeps timing consistent.

### What must not break: subtitle

- Preserve SRT slicing with `rebase_to_zero=True`.
- Preserve fallback to original subtitles when translation fails.
- Preserve ASS style aliases and karaoke fallback behavior.
- Preserve subtitle-safe region assumptions used by overlays and motion crop.
- Preserve `subtitle_translate_summary` values.

## Motion Crop and Reframe Pipeline

**Stability marker: Semi-stable implementation**

Motion-aware crop lives in `backend/app/services/motion_crop.py`. Standard FFmpeg rendering lives in `backend/app/services/render_engine.py`.

`render_part_smart()` chooses motion-aware rendering when enabled and falls back to standard rendering when safe to do so.

Motion crop may use subject, face, motion, or fallback tracking depending on input and configuration.

### What must not break: motion crop

- Fallback to standard render must remain available.
- Subtitle-safe framing must not be ignored.
- Reframe mode values must stay backward compatible.
- Motion crop must not corrupt the final video when tracking fails.

## Voice and TTS Pipeline

**Stability marker: Semi-stable implementation**

Voice narration uses:

- `backend/app/services/tts_service.py`
- `backend/app/services/audio_mix_service.py`
- `backend/app/services/voice_profiles.py`

Supported voice sources:

- `manual`
- `subtitle`
- `translated_subtitle`

Supported mix modes:

- `replace_original`
- `keep_original_low`

### What must not break: voice

- TTS failures should not fail the whole render when the video output is otherwise valid.
- Mix failure must preserve the original rendered clip.
- `VOICE001` error events must remain useful.
- Translated subtitle narration must keep fallback behavior.
- Voice summaries must remain in result JSON.

## FFmpeg Execution Backend

**Stability marker: Semi-stable implementation**

FFmpeg and ffprobe are used for:

- source probing
- editor trim/volume
- raw part cuts
- subtitle burn-in
- crop/scale/render
- text overlays
- audio mixing
- output validation

`render_engine.py` handles codec selection, NVENC fallback, CPU fallback, FFmpeg retries, and render filters.

Do not document every FFmpeg argument as a stable contract. The stable contract is behavior: valid output, fallback, validation, and compatible metadata.

## Output Validation and Quality Intelligence

**Stability marker: Semi-stable implementation**

The pipeline performs hard validation first, then non-blocking quality checks.

Hard validation determines whether an output can count as successful. Quality checks can add warnings and score penalties without necessarily failing the output.

AI quality evaluation under `backend/app/ai/quality/**` is evaluation-only. It should not mutate files, delete outputs, or fail jobs.

### Creator-perceived quality gap

Technical quality can pass while creator-perceived quality still feels less premium. Premium perception depends on hook visuals, typography, motion rhythm, audio polish, intro/outro treatment, branding, and visual consistency. These are product-quality concerns, not only FFmpeg correctness.

## Output Ranking and Best Clip

**Stability marker: Stable contract**

The pipeline writes ranking metadata after outputs are known.

Important surfaces:

- `output_ranking`
- `best_clip`
- `best_exports`
- ranking components
- ranking reasons
- `output_rank_score`
- `is_best_clip`
- `is_best_output`

Ranking may use viral score, hook score, retention score, motion score, market score, and quality penalty.

Auto best export copies selected top outputs to a `best` directory when enabled.

## Partial Success and Failed Parts

**Stability marker: Stable contract**

Part failures are isolated. If at least one output succeeds, the job can complete with partial success.

Result JSON includes:

- `failed_parts`
- `failed_parts_detail`
- `successful_outputs_count`
- `failed_outputs_count`
- `is_partial_success`

Final status may be `completed_with_errors` when some parts fail.

### What must not break: partial success

- A failed part must not erase successful outputs.
- Failed parts must remain visible to UI/history.
- All-parts-failed should still fail the job clearly.
- Partial success warning must remain in output ranking metadata.

## result_json Contract

**Stability marker: Stable contract**

`jobs.result_json` is consumed by UI, history, output gallery, AI panels, and future agents.

Do not remove or rename existing keys without tests and migration notes.

Important keys:

```text
outputs
segments
market_viral_parts
output_ranking
output_ranking_warning
best_clip
best_exports
voice_summary
subtitle_translate_summary
failed_parts
failed_parts_detail
selected_parts_count
successful_outputs_count
failed_outputs_count
is_partial_success
ai_director
ai_render_influence
ai_beat_execution
ai_output_ranking
ai_render_quality_evaluation
ai_ux
```

## Timeout and Fallback Behavior

**Stability marker: Semi-stable implementation**

Important fallback patterns:

- Download tries multiple yt-dlp clients and dynamic format fallback.
- Whisper transcription has heartbeat logging during long work.
- FFmpeg can retry or fall back from NVENC to CPU encoders.
- Motion crop falls back to standard render where possible.
- Translation failures keep original text.
- TTS/mix failures preserve the rendered video when possible.
- AI modules return fallback metadata rather than raising.

Exact timeout values are implementation details unless exposed in config or tests.

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not mirror every implementation branch.
- Do not list every FFmpeg flag as a public contract.
- Do not promise experimental AI phases affect output unless currently wired.
- Do not document private/internal future plugin plans.
- Do not document forbidden `docs/review/**` or `docs/archive/**` as editable workflow.
