# FEATURE_FLAG_MATRIX.md

**Source of truth for render feature flags.**
**Last updated**: 2026-05-22 (post Phase 3B)

---

## Active Flags

Both flags are environment variables. Both default **OFF** (value `"0"`).

```python
# render_pipeline.py (top-level constants)
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
```

No API, no DB, no frontend change needed to toggle either flag.

---

## Decision Matrix

```
BASE_CLIP_FIRST=0, OVERLAY=0  (default production)
  → render_part_smart()        → final_part.mp4
  base_clip.mp4: NOT produced
  overlay composite: NOT run
  manifest overlay fields: None

BASE_CLIP_FIRST=1, OVERLAY=0
  → render_base_clip()         → base_clip.mp4  [parallel artifact]
  → render_part_smart()        → final_part.mp4 [unchanged final output]
  base_clip.mp4: produced (validation artifact only)
  overlay composite: NOT run
  manifest: base_clip_* fields populated

BASE_CLIP_FIRST=0, OVERLAY=1  (warning: misconfiguration)
  → render_part_smart()        → final_part.mp4
  overlay flag is IGNORED (no base_clip.mp4 available)
  WARNING logged: "FEATURE_OVERLAY_AFTER_BASE_CLIP requires FEATURE_BASE_CLIP_FIRST"

BASE_CLIP_FIRST=1, OVERLAY=1  (full overlay path)
  → render_base_clip()         → base_clip.mp4
  → composite_overlays_on_base_clip(base_clip.mp4)  → final_part.mp4
  fallback on composite failure:
  → render_part_smart()        → final_part.mp4
  manifest: all fields populated when composite succeeds
```

---

## Per-Flag Reference

### FEATURE_BASE_CLIP_FIRST

| Setting | Value | Effect |
|---|---|---|
| Default (OFF) | `"0"` | Legacy path only: `render_part_smart()` is the sole output producer |
| Dev/test (ON) | `"1"` | `render_base_clip()` runs first → `base_clip.mp4` (artifact); `render_part_smart()` still runs for final output |

**Activation milestone**: Phase 2 shipped this flag. It is safe to enable in dev/test. Production default remains OFF until Phase 3 validates the overlay composite output quality.

---

### FEATURE_OVERLAY_AFTER_BASE_CLIP

| Setting | Value | Effect |
|---|---|---|
| Default (OFF) | `"0"` | `render_part_smart()` is the sole output producer |
| Dev/test (ON) | `"1"` | Overlay composite is attempted; `render_part_smart()` runs as fallback only |

**Dependency**: Requires `FEATURE_BASE_CLIP_FIRST=1`. Without base_clip.mp4, the overlay composite has no input — the flag is ignored with a logged warning.

---

## Code Path Flow

```
if _FEATURE_BASE_CLIP_FIRST:
    try:
        render_base_clip(...) → base_clip.mp4
        manifest.base_clip_* = ...
    except Exception:
        logger.warning("base_clip_render_failed ...")
        base_clip.mp4 = None

    if _FEATURE_OVERLAY_AFTER_BASE_CLIP and base_clip.mp4:
        try:
            composite_overlays_on_base_clip(base_clip.mp4, ...)
            _overlay_composite_succeeded = True
            manifest.overlay_rendered_path = ...
            manifest.overlay_text_layers_applied = ...
        except Exception:
            logger.warning("overlay_composite_failed ...")
            _overlay_composite_succeeded = False
        finally:
            # timer stopped here always

if not _overlay_composite_succeeded:
    render_part_smart(...)   # always runs when overlay not active or failed
    manifest.rendered_path = ...
```

---

## Manifest State by Flag Combination

| Flag state | `base_clip_path` | `overlay_rendered_path` | `rendered_path` | Final output |
|---|---|---|---|---|
| Both OFF | None | None | Part N path | `render_part_smart()` |
| BASE=1, OVERLAY=0 | base_clip.mp4 | None | Part N path | `render_part_smart()` |
| Both ON (success) | base_clip.mp4 | final_part.mp4 | final_part.mp4 | `composite_overlays_on_base_clip()` |
| Both ON (composite fails) | base_clip.mp4 | None | Part N path | `render_part_smart()` (fallback) |

---

## Debug Expectations

### When BASE=0, OVERLAY=0

- No `base_clip.mp4` in `work_dir/part_N/`
- No `subtitle_output_timeline.*` files
- Manifest: `base_clip_path=null`, `overlay_rendered_path=null`

### When BASE=1, OVERLAY=0

- `base_clip.mp4` exists in `work_dir/part_N/`
- Manifest: `base_clip_path` populated, `base_clip_duration` populated
- Final output still from `render_part_smart()`

### When BASE=1, OVERLAY=1 (composite success)

- `base_clip.mp4` exists
- `subtitle_output_timeline.srt` and `subtitle_output_timeline.ass` exist
- `final_part_NNN.mp4` exists (overlay composite output)
- Manifest: `overlay_rendered_path` and `rendered_path` both point to `final_part_NNN.mp4`
- Manifest: `overlay_text_layers_applied` ≥ 0

### When BASE=1, OVERLAY=1 (composite fails)

- `base_clip.mp4` exists
- Warning log: `overlay_composite_failed part=N: <error>`
- Fallback produces `part_N_rendered.mp4` via `render_part_smart()`
- Manifest: `overlay_rendered_path=null`, `rendered_path` = fallback output

---

## Rollback Procedure

If overlay composite causes regressions in production:

1. Set `FEATURE_OVERLAY_AFTER_BASE_CLIP=0` — no restart required if loaded at startup
2. Set `FEATURE_BASE_CLIP_FIRST=0` — disables base clip render too (reduces compute)
3. `render_part_smart()` is never removed — it is the permanent fallback

No DB migration, no API change, no frontend change needed.
