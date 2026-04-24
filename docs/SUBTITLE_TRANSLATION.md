# Subtitle Translation

## Scope
This document explains how subtitle translation works in the Render Studio render pipeline:
- Whisper transcription
- SRT slicing per clip
- Translation with `deep-translator` (`GoogleTranslator`)
- Translation result states (`applied` / `partial` / `failed` / `not used`)
- `translated_subtitle` narration mode

## End-to-End Flow

### 1. Full transcription (once per source)
When subtitles are enabled, the pipeline transcribes the full source video one time:
- Function: `transcribe_to_srt(...)`
- Output: `*_full.srt`
- Whisper model comes from render profile tuning (`auto` resolves by profile)

### 2. Per-part SRT slicing
For each selected segment:
- Function: `slice_srt_by_time(full_srt, part_srt, start, end, rebase_to_zero=True)`
- Output: `*_part_XXX.srt`

This avoids re-transcribing each part.

### 3. Translation (optional)
If `subtitle_translate_enabled=true`:
- Function: `translate_srt_file(input_srt, output_srt, target_language)`
- Output file pattern: `*_part_XXX.<lang>.srt` (example: `part_001.vi.srt`)
- Supported target languages in schema: `vi`, `en`, `ja`

Implementation details:
- Service uses `deep_translator.GoogleTranslator`
- Long text is chunked at ~4500 chars
- Translation is block-based (SRT block by block)
- If a block fails, original text is kept for that block (not dropped)

### 4. ASS generation and burn-in
ASS is generated from:
- translated SRT when available
- otherwise original sliced SRT

Then FFmpeg burns ASS into each part.

## Translation State Model

At job end, pipeline writes `subtitle_translate_summary` into `jobs.result_json`:

- `not used`
- `applied`
- `partial`
- `failed`

Decision logic:
- `not used`: translation toggle off, or no part attempted translation
- `applied`: all attempted parts translated cleanly (no failed blocks/parts)
- `failed`: all attempted parts failed translation
- `partial`: mixed result (some clean, some failed blocks, or some failed parts)

Internal tracking lists in pipeline:
- `_sub_translate_attempts`
- `_sub_translate_clean`
- `_sub_translate_partial`
- `_sub_translate_failed_parts`

## Event and Log Signals

Per part translation emits events/logs such as:
- `subtitle_translate_started`
- `subtitle_translate_completed`
- `subtitle_translate_block_failed` (warning per failed block)
- `subtitle_translate_failed`

These appear in:
- channel job log (`channels/<channel>/logs/<job_id>.log`)
- structured app logs (`data/logs/app.log`)

## Narration Interaction: `translated_subtitle`

When voice is enabled and `voice_source="translated_subtitle"`:

1. Pipeline prefers translated SRT for narration text.
2. Fallback chain is:
   - translated part SRT
   - original part SRT
   - temporary slice from full SRT
3. If no usable SRT text exists, narration for that part is skipped.

Important behavior:
- Render still continues when part-level TTS fails.
- Voice failures are logged with `voice_failed` (`error_code: VOICE001`).

## Request Fields (Editor -> Render)

Relevant payload fields:

```json
{
  "add_subtitle": true,
  "subtitle_translate_enabled": true,
  "subtitle_target_language": "en",
  "voice_enabled": true,
  "voice_source": "translated_subtitle",
  "voice_language": "en-US"
}
```

## Practical Outcomes

### Case A: Translation off
- Subtitle is generated from original SRT
- `subtitle_translate_summary = "not used"`

### Case B: Translation on, all good
- Part subtitles use translated SRT
- `subtitle_translate_summary = "applied"`

### Case C: Some blocks fail in some parts
- Failed blocks keep original text
- Render still completes
- `subtitle_translate_summary = "partial"`

### Case D: All part translations fail
- ASS falls back to original part SRT
- Render may still complete successfully
- `subtitle_translate_summary = "failed"`

## Troubleshooting Quick List

- Translation not happening:
  - Check `subtitle_translate_enabled`
  - Check `subtitle_target_language` (`vi`/`en`/`ja`)
- Narration from translated subtitles missing:
  - Check `voice_source=translated_subtitle`
  - Ensure translated SRT exists per part
  - Check fallback logs (`VOICE_TRANSLATED_SUBTITLE_MISSING`)
- Mixed language lines in subtitle output:
  - Expected when block-level fallback keeps original text on translation errors
