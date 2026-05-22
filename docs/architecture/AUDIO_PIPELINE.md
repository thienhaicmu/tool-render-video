# AUDIO_PIPELINE.md

**Source of truth for audio flow through the render pipeline.**
**Last updated**: 2026-05-22 (post Phase 3B)

---

## Audio Responsibility Map

| Stage | Audio operation | Owner | Applied when |
|---|---|---|---|
| `render_base_clip()` | atempo={speed}, loudnorm | `render_engine.py` | Overlay path, base clip |
| `render_part_smart()` | atempo={speed}, loudnorm, TTS mix, BGM mix | `render_engine.py` + `audio_mix_service.py` | Legacy path, fallback |
| `composite_overlays_on_base_clip()` | -c:a copy (stream copy) | `render_engine.py` | Overlay path, final step |
| `mix_narration_audio()` | atempo={speed}, BGM ducking | `audio_mix_service.py` | Legacy path only (Phase 3C pending) |

---

## Current Audio Flow: Legacy Path

```
source.mp4 (source audio, unmodified)
    │
    ├── generate_narration_audio()  → narration.mp3 (natural speaking rate)
    ├── _maybe_cleanup_narration_audio() → DeepFilterNet (optional)
    └── mix_narration_audio(playback_speed=effective_speed)
            atempo={speed} applied to narration track
            BGM sidechain ducking (optional)
        → mixed_narration.mp3

render_part_smart():
    FFmpeg audio chain:
        source audio + mixed_narration
        atempo={speed}      ← video source audio speed compensation
        loudnorm (optional) ← normalization
    → final_part.mp4 (speed-adjusted audio baked in)
```

---

## Current Audio Flow: Overlay Path

```
source.mp4 (source audio)
    │
    render_base_clip():
        FFmpeg audio chain:
            atempo={effective_speed}    ← ONE-TIME speed application
            loudnorm (optional)
        → base_clip.mp4 (speed-adjusted audio)
    │
    composite_overlays_on_base_clip():
        -c:a copy                        ← audio stream copied unchanged
    → final_part.mp4 (same audio as base_clip)
```

TTS narration and BGM are NOT applied in the overlay path. Phase 3C will add them.

---

## Speed Clamp Separation

Two distinct speed clamps exist in the audio subsystem:

| Location | Clamp | Reason |
|---|---|---|
| `render_pipeline._get_effective_playback_speed()` | [0.5, 1.5] | Pipeline render speed |
| `render_engine._sanitize_speed()` | [0.5, 1.5] | FFmpeg encode |
| `TimelineMap.__post_init__()` | [0.5, 1.5] | Domain model |
| `audio_mix_service.py` (narration atempo) | [0.5, 2.0] | FFmpeg atempo filter hardware range |

The `[0.5, 2.0]` is **correct and intentional** for `audio_mix_service.py`. The FFmpeg `atempo` filter accepts values in [0.5, 2.0] by spec. This is a hardware/filter constraint, not a pipeline policy. Do not change it to [0.5, 1.5].

---

## Double-Atempo Risk

**Critical invariant**: atempo must be applied exactly ONCE per audio stream.

Current safe design:
- Legacy: atempo applied inside `render_part_smart()` FFmpeg audio chain
- Overlay: atempo applied inside `render_base_clip()` FFmpeg audio chain; composite does `-c:a copy`

**Risk**: If Phase 3C adds audio operations to the composite step, it MUST NOT apply atempo again. The base clip audio already has speed applied. Only loudnorm, narration mix, or BGM can be added — not atempo.

---

## TTS Narration (Legacy Path Only)

`generate_narration_audio()` → edge-tts or XTTS at natural speaking rate.

The narration runs at source speaking pace. The render is at `effective_speed`. Without compensation, narration would end too early.

**Phase 0 fix** (resolved): `mix_narration_audio()` accepts `playback_speed: float` and applies `atempo={speed}` to the narration before mixing. This compensates for the video speed difference.

Regression tests: `TestMixNarrationAudioAtempo` in `test_phase0_hotfixes.py`.

---

## BGM (Legacy Path Only)

BGM sidechain ducking is applied inside `mix_narration_audio()` in `audio_mix_service.py`. Not active in overlay path.

---

## Phase 3C Scope (Not Yet Implemented)

Phase 3C will migrate TTS narration and BGM to the overlay composite path. It must:
- Generate mixed audio (narration + BGM, with atempo compensation) separately
- Pass the mixed audio file to `composite_overlays_on_base_clip()`
- Replace `-c:a copy` with the mixed audio input in the composite FFmpeg command
- NOT apply atempo again (base_clip audio already speed-adjusted)
- Handle the case where no narration/BGM is requested (keep `-c:a copy`)

Phase 3C is out of scope until explicitly planned.

---

## Audio Overlap Hazard Analysis

| Scenario | Audio state | Risk |
|---|---|---|
| Legacy path, narration disabled | Source audio + atempo | Correct |
| Legacy path, narration enabled | Narration mixed + atempo | Correct (Phase 0 fix) |
| Overlay path (Phase 3A/3B) | Base clip audio (-c:a copy) | Correct — atempo once |
| Overlay path + composite audio filter | DANGER | Double-atempo if not guarded |
| Fallback to render_part_smart() | Reverts to legacy, all audio rules apply | Correct |
