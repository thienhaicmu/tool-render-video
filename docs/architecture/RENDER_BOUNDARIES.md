# RENDER_BOUNDARIES.md

**Source of truth for render stage ownership and forbidden responsibilities.**
**Last updated**: 2026-05-22 (post Phase 3C)

---

## Ownership Table

| Render Stage | Function | File | Owns | Forbidden |
|---|---|---|---|---|
| Base clip | `render_base_clip()` | `render_engine.py` | Speed, crop, reframe, effect, color, audio atempo/loudnorm, BGM mix (reup_bgm_*) | ass=, drawtext=, text_layers, narration |
| Overlay composite | `composite_overlays_on_base_clip()` | `render_engine.py` | subtitle ASS, title drawtext, text_layer drawtext, fps=, -c:a copy | setpts, atempo, crop, scale, color, effect, BGM, loudnorm |
| Legacy all-in-one | `render_part_smart()` | `render_engine.py` | Everything (legacy path) | N/A — legacy path owns all |
| Post-assembly | `_maybe_prepend_*`, `_maybe_append_*`, `_maybe_apply_asset_logo()` | `render_pipeline.py` | Hook intro, asset intro/outro, logo watermark | Speed re-encoding of the main clip |
| Narration mix | `mix_narration_audio()` | `audio_mix_service.py` | TTS atempo on narration stream, narration/source blending | atempo on source audio, setpts, crop, video |

---

## render_base_clip() Invariants

```
MUST:
  - Apply setpts=PTS/{effective_speed}     ← output timeline PTS
  - Apply atempo={effective_speed}         ← audio speed match
  - Apply crop/reframe (motion-aware or standard)
  - Apply fps=target_fps as last vf filter
  - Use TimelineMap.effective_speed (not re-derive from payload)
  - Acquire NVENC semaphore (same as render_part_smart)
  - When reup_bgm_enable=True and path is valid: use filter_complex to bake BGM
    into base_clip.mp4 (atempo applied once to BGM stream alongside source audio)

MUST NOT:
  - Apply ass= subtitle filter
  - Apply drawtext= title or text_layers
  - Mix narration audio
  - Apply atempo to source audio more than once (atempo is already in the audio chain)
  - Read from or write to overlay manifest fields
```

---

## composite_overlays_on_base_clip() Invariants

```
MUST:
  - Treat base_clip as output-timeline PTS (never apply setpts again)
  - Use -c:a copy for audio (BGM and source audio stream-copied from base_clip)
  - Apply fps= as last vf filter (probed from base_clip)
  - Build vf_chain in order: ass → title → text_layers → fps

MUST NOT:
  - Apply setpts
  - Apply atempo
  - Apply crop, scale, colorbalance, eq, unsharp, fade
  - Apply any spatial transform
  - Apply any temporal transform
  - Mix narration or BGM
```

---

## render_part_smart() Invariants (Legacy Path)

```
MUST NOT be modified for overlay concerns:
  - Its filter chain (ass-before-setpts) is a hard invariant
  - Its signature must remain unchanged
  - It must always run as fallback when overlay composite fails
  - Never add FEATURE_OVERLAY_AFTER_BASE_CLIP logic inside it
```

---

## "Apply Exactly Once" List

These operations must be applied at most once per clip. The pipeline must guard against double application at phase boundaries.

| Operation | Applied in | Must NOT also appear in |
|---|---|---|
| `setpts=PTS/speed` (video speed) | `render_base_clip()` or `render_part_smart()` | `composite_overlays_on_base_clip()` |
| `atempo=speed` (audio speed) | `render_base_clip()` or `render_part_smart()` audio chain | `composite_overlays_on_base_clip()` |
| `loudnorm` | `render_base_clip()` or `render_part_smart()` | `composite_overlays_on_base_clip()` |
| `crop` (motion/standard) | `render_base_clip()` or `render_part_smart()` | `composite_overlays_on_base_clip()` |
| `eq=` / `unsharp=` / `colorbalance=` | `render_base_clip()` or `render_part_smart()` | `composite_overlays_on_base_clip()` |

---

## Anti-Patterns

### 1. Re-deriving speed from payload after TimelineMap creation

```python
# WRONG — re-derives speed from payload inline:
playback_speed = max(0.5, min(1.5, float(payload.playback_speed) + platform_delta))

# RIGHT — reads from the authoritative timeline record:
playback_speed = timeline.effective_speed
```

### 2. Applying overlay operations inside render_base_clip()

```python
# WRONG — base clip should be overlay-free:
vf_parts.append(f"ass='{ass_path}'")

# RIGHT — overlays belong in composite_overlays_on_base_clip():
# render_base_clip() builds vf_chain without ass=
```

### 3. Applying setpts inside overlay composite

```python
# WRONG — base_clip PTS is already output-timeline:
vf_parts.append(f"setpts=PTS/{speed}")

# RIGHT — no setpts in composite:
# composite accepts base_clip which already has output-timeline PTS
```

### 4. Using legacy ASS file in overlay composite

```python
# WRONG — part_N.ass has source-clip timestamps:
subtitle_ass = str(ass_part)  # source-time ASS

# RIGHT — overlay composite needs output-timeline ASS:
subtitle_ass = str(_overlay_ass_path)  # subtitle_output_timeline.ass
```

### 5. Multiplying hook end_time by speed in overlay path

```python
# WRONG — overlay path end_time is in output-seconds (no speed factor):
end_time = round(min(2.5, 1.5 * speed), 3)

# RIGHT — overlay hook:
end_time = 1.5   # constant output seconds
```

---

## Phase Boundary Checklist

When adding new overlay types to `composite_overlays_on_base_clip()`:

- [ ] Timing values are in output seconds (not source seconds)
- [ ] No setpts added to vf_chain
- [ ] No atempo added to audio chain
- [ ] No spatial transforms (crop, scale) added
- [ ] fps= remains last in vf_chain
- [ ] Fallback path still works (`render_part_smart()` runs correctly without the new overlay type)
- [ ] New manifest fields are Optional with None default (backward-compat)
- [ ] `from_dict()` uses `.get(key)` with None default for new fields

When adding new render layers to `render_base_clip()`:

- [ ] No ass=, drawtext=, text_layers filters added
- [ ] Speed still comes from `TimelineMap.effective_speed`
- [ ] NVENC semaphore still acquired
- [ ] Failure still propagates as exception (caller handles with warning + fallback)
