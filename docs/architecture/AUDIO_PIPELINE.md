# AUDIO_PIPELINE.md

**Source of truth for audio flow through the render pipeline.**
**Last updated**: 2026-05-22 (post Phase 3B)

---

## Audio Responsibility Map

| Stage | Audio operation | Owner | Applied when |
|---|---|---|---|
| `render_base_clip()` | atempo={speed}, loudnorm, BGM mix (Phase 3C planned) | `render_engine.py` | Overlay path, base clip |
| `render_part_smart()` | atempo={speed}, loudnorm, TTS mix, BGM mix | `render_engine.py` + `audio_mix_service.py` | Legacy path, fallback |
| `composite_overlays_on_base_clip()` | -c:a copy (stream copy) | `render_engine.py` | Overlay path, final step |
| `mix_narration_audio()` | atempo={speed} on narration, source/narration blend | `audio_mix_service.py` | Both paths (post-render step on final_part) |

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

**TTS narration IS mixed into the overlay output** — `mix_narration_audio()` is called on `final_part` after the composite, regardless of which path produced it. No implementation gap for narration.

**BGM is NOT applied on the overlay path** (Phase 3A/3B) — `render_base_clip()` has no BGM parameters. Phase 3C will add BGM to `render_base_clip()`. See [PHASE_3C_AUDIO_OWNERSHIP_PLAN.md](../restructure/PHASE_3C_AUDIO_OWNERSHIP_PLAN.md).

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

## TTS Narration (Both Paths)

`generate_narration_audio()` → edge-tts or XTTS at natural speaking rate.

The narration runs at source speaking pace. The render is at `effective_speed`. Without compensation, narration would end too early.

**Phase 0 fix** (resolved): `mix_narration_audio()` accepts `playback_speed: float` and applies `atempo={speed}` to the narration track before mixing. This compensates for the video speed difference.

**Overlay path**: `mix_narration_audio()` is called on `final_part` (the composite output) at the same pipeline step where legacy narration is mixed. The narration atempo applies to `[1:a]` (narration input) only. The composite output audio `[0:a]` (already speed-adjusted from base_clip) gets only `volume` adjustment, not atempo. No double-atempo.

Regression tests: `TestMixNarrationAudioAtempo` in `test_phase0_hotfixes.py`.

---

## BGM

BGM (`reup_bgm_*` params) is mixed via `filter_complex` inside `render_part_smart()`, using `_bgm_duck_filter()` (sidechaincompress when `BGM_DUCKING_ENABLED=1`).

**Legacy path**: BGM baked into final encode inside `render_part_smart()`. Active.  
**Overlay path (Phase 3A/3B)**: `render_base_clip()` has no BGM parameters — BGM silently skipped.  
**Overlay path (Phase 3C, planned)**: BGM params added to `render_base_clip()`, baked into `base_clip.mp4`, carried through composite via `-c:a copy`.

---

## Phase 3C Scope (PLANNED — not yet implemented)

**Audit finding**: TTS narration mixing **already operates on the overlay path**. `mix_narration_audio()` is called on `final_part` after the render, regardless of which path (overlay or legacy) produced it. Narration requires validation and tests, not new implementation.

**BGM is the sole missing feature** on the overlay path. `render_base_clip()` does not accept `reup_bgm_*` parameters. BGM is silently skipped when the overlay path is active.

**Phase 3C implementation plan**: See [PHASE_3C_AUDIO_OWNERSHIP_PLAN.md](../restructure/PHASE_3C_AUDIO_OWNERSHIP_PLAN.md).

**Phase 3C scope (planned)**:
1. Add `reup_bgm_enable`, `reup_bgm_path`, `reup_bgm_gain` parameters to `render_base_clip()`. Reuse `_bgm_duck_filter()` helper.
2. Pass BGM params from `render_pipeline.py` call site to `render_base_clip()`.
3. Add `base_clip_bgm_applied: Optional[bool]` to `BaseClipManifest`.
4. Add `test_overlay_narration.py` verifying narration already works on overlay output.
5. Add tests asserting no atempo and no BGM in `composite_overlays_on_base_clip()` command.

`composite_overlays_on_base_clip()` continues to use `-c:a copy`. BGM is baked into `base_clip.mp4`; stream copy carries it through to the composite output. `mix_narration_audio()` operates on the composite output unchanged.

---

## Audio Overlap Hazard Analysis

| Scenario | Audio state | Risk |
|---|---|---|
| Legacy path, narration disabled | Source audio + atempo | Correct |
| Legacy path, narration enabled | Narration mixed + atempo | Correct (Phase 0 fix) |
| Overlay path (Phase 3A/3B) | Base clip audio (-c:a copy) | Correct — atempo once |
| Overlay path + narration enabled | Base clip audio (-c:a copy) → narration mixed post-composite | Correct — narration atempo on [1:a] only, source [0:a] gets volume only |
| Overlay path + BGM enabled (before Phase 3C) | BGM silently skipped | Gap — Phase 3C fixes this |
| Overlay path + BGM enabled (after Phase 3C) | BGM baked into base_clip, stream-copied through composite | Correct — atempo on BGM once in render_base_clip |
| Overlay path + composite audio filter | DANGER | Double-atempo if composite ever adds atempo — FORBIDDEN |
| Fallback to render_part_smart() | Reverts to legacy, all audio rules apply | Correct |
