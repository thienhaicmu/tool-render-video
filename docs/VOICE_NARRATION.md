# Voice Narration

AI-generated narration is added to each rendered part using Microsoft Edge TTS.  
Voice is optional and controlled by `voice_enabled` in `RenderRequest`.

---

## Voice sources

Three mutually exclusive modes for the narration text:

### 1. `manual`

The user provides text directly in the editor:

```json
{
  "voice_enabled": true,
  "voice_source": "manual",
  "voice_text": "Welcome to today's video. Here are the top highlights..."
}
```

- TTS is run once before the render loop starts
- The same audio file is mixed into every part
- Requires `voice_text` to be non-empty

### 2. `subtitle`

Narration text is extracted from the Whisper-generated SRT for each part:

```python
# Per part, inside _process_one_part():
_part_narration_text = extract_text_from_srt(str(srt_part))
_part_subtitle_voice_path = generate_narration_mp3(text=_part_narration_text, ...)
```

- TTS runs separately for each part
- Each part gets narration from its own subtitle segment
- If SRT is empty or missing, narration is skipped for that part (logged as `VOICE_SUBTITLE_EMPTY` or `VOICE_SUBTITLE_MISSING`)

### 3. `translated_subtitle`

Narration text comes from the translated SRT (after `translate_srt_file()` runs):

```python
_voice_srt = translated_srt_part   # e.g. part_001.vi.srt
# fallback chain: translated → original → full_srt slice
```

- Intended use: video in language A → subtitle translated to language B → TTS in language B
- Falls back to original SRT if translation is unavailable
- Warns on language mismatch (`VOICE_LANGUAGE_TARGET_MISMATCH`)

---

## TTS engine

File: `backend/app/services/tts_service.py`  
Library: `edge-tts` (Microsoft Edge browser TTS, no API key required)

```python
communicate = edge_tts.Communicate(text, voice_id, rate=rate)
await communicate.save(mp3_path)
```

Output: `.mp3` file in `TEMP_DIR/{job_id}/voice/`

---

## Voice profiles

File: `backend/app/services/voice_profiles.py`

| Language | Gender | Voice ID |
|---|---|---|
| `vi-VN` | female | `vi-VN-HoaiMyNeural` |
| `vi-VN` | male | `vi-VN-NamMinhNeural` |
| `ja-JP` | female | `ja-JP-NanamiNeural` |
| `ja-JP` | male | `ja-JP-KeitaNeural` |
| `en-US` | female | `en-US-JennyNeural`, `en-US-AriaNeural` |
| `en-US` | male | `en-US-GuyNeural`, `en-US-DavisNeural` |
| `en-GB` | female | `en-GB-SoniaNeural`, `en-GB-LibbyNeural` |
| `en-GB` | male | `en-GB-RyanNeural`, `en-GB-OliverNeural` |

`voice_id` can be passed directly to override the gender-based default. The `resolve_voice_profile()` function validates the ID against the flat `_ALL_VOICES` dict.

**Rate parameter:** `voice_rate` is a string like `"+0%"`, `"+10%"`, `"-5%"` — passed directly to Edge TTS for speed adjustment.

---

## Audio mixing

File: `backend/app/services/audio_mix_service.py`  
Function: `mix_narration_audio(video_path, narration_audio_path, mix_mode, output_path)`

Two mix modes:

### `replace_original`

```
ffmpeg -i video.mp4 -i narration.mp3
  -map 0:v:0 -map 1:a:0
  -c:v copy -c:a aac -shortest
  output.mp4
```

Original audio is discarded. Narration becomes the only audio track.

### `keep_original_low`

```
ffmpeg -i video.mp4 -i narration.mp3
  -filter_complex "[0:a]volume=0.25[a0];[1:a]volume=1.0[a1];[a0][a1]amix=..."
  -map 0:v:0 -map [aout]
  -c:v copy -c:a aac -shortest
  output.mp4
```

Original audio ducked to 25%, narration at 100%, mixed together. If the video has no audio stream, narration is used directly (no filter_complex needed).

After mixing, the output replaces the final part atomically:

```python
os.replace(mixed_part, final_part)
```

---

## Narration pipeline (per-part)

```
render_part_smart() → final_part.mp4
        ↓
generate_narration_mp3(text, ...) → part_NNN.mp3
        ↓
mix_narration_audio(final_part, part_NNN.mp3, mix_mode, .voice_tmp.mp4)
        ↓
os.replace(.voice_tmp.mp4, final_part.mp4)
```

The `.voice_tmp.mp4` intermediate is cleaned up automatically by `os.replace()`.

---

## Failure handling

- TTS failure for `manual` source: `voice_tts_failed = True`, render continues without narration
- TTS failure for `subtitle` / `translated_subtitle` source: part-level failure logged, other parts continue
- Mix failure: `_safe_unlink(mixed_part)`, original `final_part.mp4` is preserved
- All voice failures are logged as `voice_failed` events with `error_code: VOICE001`

---

## Voice API

Route: `GET /api/voice/profiles`  
Route: `GET /api/voice/list`

Returns available languages, voice IDs, gender labels, and recommended use descriptions.

---

## Validation rules (from RenderRequest schema)

```python
voice_source: "manual" | "subtitle" | "translated_subtitle"
voice_language: "vi-VN" | "ja-JP" | "en-US" | "en-GB"
voice_gender: "female" | "male"
voice_mix_mode: "replace_original" | "keep_original_low"
voice_text: required when voice_source == "manual"
subtitle_target_language: "vi" | "en" | "ja"
```

All validated in `RenderRequest.validate_voice_settings()` before the job is submitted.
