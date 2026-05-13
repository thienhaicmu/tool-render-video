# Subtitle and Translation System

## Subtitle System Role

**Stability marker: Stable contract**

Subtitles are part of the render intelligence layer, not just text burn-in. They affect creator-perceived quality, market fit, hook impact, accessibility, voice narration, and output ranking context.

Primary file:

- `backend/app/services/subtitle_engine.py`

Related files:

- `backend/app/services/translation_service.py`
- `backend/app/services/market_subtitle_policy.py`
- `backend/app/ai/subtitles/**`
- `backend/app/ai/creator_subtitle/**`
- `backend/app/orchestration/render_pipeline.py`

## Full Subtitle Workflow

**Stability marker: Stable contract**

```text
source video
  -> full Whisper transcription
  -> full SRT
  -> per-part SRT slice
  -> rebase timing to zero
  -> optional translation
  -> optional subtitle edits
  -> optional market hook/line-break policy
  -> optional keyword/emphasis markers
  -> ASS generation
  -> FFmpeg subtitle burn
```

## Full SRT Generation

**Stability marker: Semi-stable implementation**

The pipeline transcribes the full source once when subtitles are enabled and at least one selected part needs subtitles.

`transcribe_to_srt()` uses Whisper and writes a full-source SRT. The render profile can influence the model selection.

If the source has no audio stream, subtitle generation should be skipped safely.

## Per-Part SRT Slicing and Rebasing

**Stability marker: Stable contract**

Each selected segment gets a sliced SRT:

```text
full_srt + source start/end
  -> part_srt with timestamps rebased to 00:00:00,000
```

This is critical because FFmpeg burns subtitles onto each raw cut, whose local time starts at zero.

### What must not break: SRT timing

- Preserve `rebase_to_zero=True` behavior.
- Do not shift subtitles with source-time timestamps in per-part files.
- Do not re-transcribe each part unless explicitly changing architecture.
- Preserve playback-speed handling assumptions.

## Subtitle Translation Flow

**Stability marker: Semi-stable implementation**

If `subtitle_translate_enabled=true`, `translate_srt_file()` translates each part SRT to the target language.

Supported target language values are currently:

- `vi`
- `en`
- `ja`

Translation is block-based. If a block fails, original text is kept for that block. This is intentional; render should continue with partial translation rather than dropping subtitles.

Result summary in `jobs.result_json`:

- `not used`
- `applied`
- `partial`
- `failed`

## ASS Generation

**Stability marker: Stable contract**

ASS files are generated from translated SRT when available, otherwise from original sliced SRT.

Current ASS generation paths include:

- bounce-style subtitles
- karaoke-style subtitles

ASS generation must preserve browser/output readability, safe margins, style aliases, and fallback behavior.

## Bounce and Karaoke Styles

**Stability marker: Semi-stable implementation**

Known subtitle styles include modern presets such as:

- `pro_karaoke`
- `tiktok_bounce_v1`
- `bold_cap`
- `story_clean_01`
- `viral_bold`
- `clean_pro`
- `boxed_caption`

Karaoke depends on word-level timing. If the SRT is not suitable for karaoke, the engine can fall back to bounce-style rendering.

### What must not break: subtitle styles

- Preserve legacy aliases. Subtitle style aliases are backward compatibility contracts, not cleanup targets.
- Preserve karaoke fallback.
- Preserve ASS escaping and marker handling.
- Preserve readability across vertical formats.

## Market Subtitle Policy

**Stability marker: Semi-stable implementation**

`market_subtitle_policy.py` contains market-specific behavior for US/EU/JP style differences.

It can affect:

- line breaks
- keyword emphasis
- hook wording style
- reading density
- market fit metadata

Do not make market subtitle behavior global without preserving market-specific defaults.

## Hook Subtitle Formatting

**Stability marker: Semi-stable implementation**

Hook subtitle formatting can emphasize the first subtitle blocks for impact. It is connected to market viral behavior and hook application in the render pipeline.

This is creator-facing quality. It should improve perceived hook strength without corrupting text or timing.

## Keyword Highlighting and Emphasis

**Stability marker: Experimental / needs verification**

Keyword highlighting and emphasis markers are used to make important words stand out. AI subtitle execution can also produce metadata hints such as density, emotion style, emphasis strength, and keyword focus.

These hints should remain safe:

- no timing mutation unless explicitly implemented and tested
- no transcript rewrite as a side effect
- no unsafe ASS override injection

## Subtitle-Safe Regions

**Stability marker: Stable contract**

Subtitle placement interacts with:

- text overlays
- motion crop
- vertical aspect ratios
- safe bottom region
- creator readability

Do not treat subtitle placement as isolated. Changes can break overlays, crop framing, and perceived quality.

## Narration Interaction

**Stability marker: Stable contract**

Voice mode `translated_subtitle` depends on subtitle translation output.

Fallback chain:

```text
translated part SRT
  -> original part SRT
  -> temporary slice from full SRT
  -> skip narration for that part
```

Voice failures should not remove subtitles or fail otherwise valid video output.

## Known Limitations

**Stability marker: Semi-stable implementation**

- Translation quality depends on the translation service and source text.
- Mixed-language subtitles can occur when block-level fallback keeps original text.
- Karaoke quality depends on word-level timing.
- Premium subtitle feel requires more than valid ASS: typography, motion rhythm, contrast, and consistency matter.
- Subtitle AI metadata is richer than the currently visible UI.

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not claim translation is perfect.
- Do not document exact visual tuning values as permanent.
- Do not promise every AI subtitle hint changes final output.
- Do not remove historical warnings about fallback and partial translation.
