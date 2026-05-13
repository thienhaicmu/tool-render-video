# Voice Narration

## Voice System Role

**Stability marker: Semi-stable implementation**

Voice narration is an optional creator-facing layer added after a clip has been rendered. It can turn source subtitles, translated subtitles, or manual text into narration audio and mix that audio into each output part.

Primary files:

- `backend/app/services/tts_service.py`
- `backend/app/services/audio_mix_service.py`
- `backend/app/services/voice_profiles.py`
- `backend/app/orchestration/render_pipeline.py`

Voice improves creator productivity, but it is not yet a full audio mastering system.

## Narration Modes

**Stability marker: Stable contract**

Voice is controlled by `voice_enabled` in `RenderRequest`.

Supported `voice_source` values:

- `manual`
- `subtitle`
- `translated_subtitle`

Supported `voice_mix_mode` values:

- `replace_original`
- `keep_original_low`

## Manual Voice Text

**Stability marker: Stable contract**

`voice_source="manual"` uses `voice_text` from the editor.

Behavior:

- `voice_text` is required when manual voice is enabled.
- TTS can be generated before per-part rendering.
- The same narration source can be mixed into outputs.
- If TTS fails, render should continue without narration when possible.

## Subtitle Source Mode

**Stability marker: Stable contract**

`voice_source="subtitle"` extracts narration text from the per-part SRT generated from Whisper.

Behavior:

- TTS runs per part.
- Empty or missing subtitle text skips narration for that part.
- Other parts continue even if one part has no usable subtitle text.

## Translated Subtitle Source Mode

**Stability marker: Stable contract**

`voice_source="translated_subtitle"` prefers translated per-part SRT text.

Fallback chain:

```text
translated part SRT
  -> original part SRT
  -> temporary slice from full SRT
  -> skip narration for that part
```

This mode is intended for workflows such as original-language video plus translated subtitle plus target-language narration.

The pipeline can warn on mismatch between `subtitle_target_language` and `voice_language`.

## TTS Engine

**Stability marker: Semi-stable implementation**

The current TTS engine uses `edge-tts`.

Output files are written under the job temp voice directory.

Voice profiles are defined in `backend/app/services/voice_profiles.py`. Current language families include:

- `vi-VN`
- `ja-JP`
- `en-US`
- `en-GB`

The user can pass a direct `voice_id` or rely on language/gender defaults.

## Audio Mix Modes

**Stability marker: Stable contract**

`replace_original`:

- keeps video stream
- discards original audio
- uses narration as the only audio track

`keep_original_low`:

- keeps original audio at reduced volume
- mixes narration above it
- falls back to narration-only behavior when the video has no original audio stream

Mixing is performed by FFmpeg. A failed mix should preserve the already rendered video.

## Failure and Timeout Behavior

**Stability marker: Stable contract**

Voice is optional. Voice failures should not destroy valid rendered clips.

Expected behavior:

- TTS failure logs `voice_failed`.
- Voice errors use `error_code: VOICE001`.
- Per-part TTS failure skips narration for that part.
- Mix failure removes temporary mixed output and preserves the original final part.
- Render result JSON still records voice summary.

### What must not break: voice

- Do not make optional voice failure fatal for the whole render unless explicitly required by product policy.
- Do not remove `VOICE001` diagnostics.
- Do not change mix-mode semantics silently.
- Do not break translated-subtitle fallback.
- Do not overwrite video output with a failed audio mix.

## Result Summary Fields

**Stability marker: Stable contract**

The render pipeline writes `voice_summary` into `jobs.result_json`.

Expected values include:

- `not used`
- `applied`
- `failed`
- `partial`

The exact summary depends on which parts attempted voice and whether generation/mix succeeded.

## Audio Polish Limitations

**Stability marker: Experimental / needs verification**

Technical audio correctness is not the same as creator-perceived premium audio.

Current voice/audio flow can produce valid narration, but premium audio may still require:

- loudness normalization across all outputs
- smoother ducking
- EQ/compression
- better pause/breath handling
- transition polish
- consistent voice identity per creator/channel

Do not document current TTS as studio-grade mastering.

## Voice API

**Stability marker: Stable contract**

Routes:

- `GET /api/voice/profiles`
- `GET /api/voice/list`

These return available voices, labels, gender, language, and recommended-use metadata for the frontend.

## Validation Rules

**Stability marker: Stable contract**

Validation is in `RenderRequest`.

Important constraints:

- `voice_source`: `manual`, `subtitle`, `translated_subtitle`
- `voice_language`: `vi-VN`, `ja-JP`, `en-US`, `en-GB`
- `voice_gender`: `female`, `male`
- `voice_mix_mode`: `replace_original`, `keep_original_low`
- `voice_text` is required for manual mode
- `subtitle_target_language`: `vi`, `en`, `ja`

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not promise a specific third-party TTS provider forever.
- Do not document exact timeout values as stable unless exposed by config/tests.
- Do not claim professional mastering.
- Do not expose provider credentials or private environment assumptions.

