# Phase 3C — Audio Ownership for Overlay Path
## Implementation Plan

**Date**: 2026-05-22
**Branch**: restructure/output-timeline-architecture
**Status**: SHIPPED
**Predecessor**: Phase 3B (text/title overlay, commit 0a606ca), documentation consolidation (commit 407ec91)

---

> **HISTORICAL IMPLEMENTATION RECORD**
> This document is a planning record for Phase 3C.
> Current architecture source of truth lives in [docs/architecture/](../architecture/).
> For migration chronology see [MIGRATION_HISTORY.md](MIGRATION_HISTORY.md).

---

## Executive Summary

Phase 3C resolves the audio feature gap between the overlay path and the legacy path.

**Audit finding** (see §3): narration mixing is narrower than expected.
- TTS narration mixing **already operates on the overlay path**. `mix_narration_audio()` is called on `final_part` after the render/composite, regardless of which path produced it. No code change needed for narration.
- **BGM is the sole missing audio feature**. BGM (`reup_bgm_*`) is passed to `render_part_smart()` and baked into the render. `render_base_clip()` has no BGM parameters. When the overlay path is active, BGM is silently skipped.

**Recommended scope**: Phase 3C = add BGM support to `render_base_clip()`. Narration requires validation and tests, not new implementation.

---

## 1. Current Audio Behavior (Overlay Path, Post Phase 3B)

```
source.mp4 (source audio)
    │
    render_base_clip(...)
        FFmpeg audio chain:
            atempo={effective_speed}    ← ONE-TIME speed application
            loudnorm (optional)
        NO BGM mix
        → base_clip.mp4 (speed-adjusted audio, no BGM)
    │
    composite_overlays_on_base_clip(base_clip.mp4, ...)
        -c:a copy                       ← audio stream-copied unchanged
        → overlay_visual.mp4 (same audio as base_clip)
    │
    mix_narration_audio(                ← ALREADY CALLED on overlay output
        video_path=str(final_part),     ← final_part = overlay_visual.mp4
        narration_audio_path=...,
        playback_speed=effective_speed, ← atempo applied to NARRATION only
        ...
    )
    → final_part.mp4 (narration mixed in)

MISSING: BGM not applied anywhere on overlay path
```

---

## 2. Target Phase 3C Behavior

```
source.mp4 (source audio)
    │
    render_base_clip(..., reup_bgm_enable, reup_bgm_path, reup_bgm_gain)  ← NEW PARAMS
        FFmpeg audio chain:
            atempo={effective_speed}
            BGM mix (if enabled, same filter_complex as render_part_smart)
            loudnorm (optional)
        → base_clip.mp4 (speed-adjusted audio + BGM baked in)
    │
    composite_overlays_on_base_clip(base_clip.mp4, ...)
        -c:a copy                       ← unchanged — BGM is in base_clip
        → overlay_visual.mp4 (BGM included via stream copy)
    │
    mix_narration_audio(               ← unchanged — already works
        video_path=str(final_part),
        narration_audio_path=...,
        playback_speed=effective_speed,
        mix_mode=...,
    )
    → final_part.mp4 (BGM + narration)

BGM and narration both present on overlay path.
```

---

## 3. Audio Responsibility Audit

### 3.1 Narration: Already Working on Overlay Path

Audit of `render_pipeline.py` (lines 4432–4823):

```
[1] Overlay composite (line 4432–4506):
    composite_overlays_on_base_clip() → final_part (overlay output)
    _overlay_composite_succeeded = True

[2] Fallback render (line 4508–4545):
    if not _overlay_composite_succeeded:
        render_part_smart() → final_part (legacy render)

[3] Narration generation (line 4594+):
    if voice_enabled and voice_source == "subtitle":
        generate_narration_audio() → _part_subtitle_voice_path

[4] Narration mix (line 4775–4823):
    _final_voice_path = voice_audio_path or _part_subtitle_voice_path
    mix_narration_audio(
        video_path=str(final_part),   ← operates on WHICHEVER path ran
        playback_speed=_get_effective_playback_speed(...),
    )
    os.replace(mixed_part, final_part)
```

**Result**: `mix_narration_audio()` already operates on the overlay composite output when overlay succeeds. No implementation gap for narration.

### 3.2 atempo Safety: No Double-Atempo

`mix_narration_audio()` internal FFmpeg commands:
```python
# replace_original mode:
"-filter_complex", f"[1:a]atempo={speed:.4f}[narr]",   # [1:a] = narration input
"-map", "0:v:0",    # video from overlay output
"-map", "[narr]",   # narration only
"-c:v", "copy",

# keep_original_low mode:
"-filter_complex",
f"[0:a]volume=0.25[a0];[1:a]atempo={speed:.4f},volume=1.0[a1];..."
# [0:a] = overlay audio (speed already baked) — only volume applied
# [1:a] = narration — atempo applied (narration is at natural speed)
```

`atempo` is applied only to `[1:a]` (the narration input). The video audio `[0:a]` from the overlay path (which has speed already baked by `render_base_clip()`) gets only `volume=0.25`. No double-atempo.

**Invariant confirmed**: atempo applied exactly once per audio stream.

### 3.3 BGM: Missing from Overlay Path

`render_part_smart()` (line 1024–1110 in `render_engine.py`):
```python
bgm_path = str(reup_bgm_path or "").strip()
bgm_ok = reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
# ... BGM mixed via filter_complex inside the FFmpeg encode command
```

`render_base_clip()`: does NOT accept `reup_bgm_enable`, `reup_bgm_path`, `reup_bgm_gain`. BGM is not applied to base_clip.mp4. BGM is skipped silently on the overlay path.

### 3.4 Loudnorm: Already in `render_base_clip()`

`render_base_clip()` accepts `loudnorm_enabled: bool` and applies it to the audio chain. No gap. Loudnorm is NOT applied in `composite_overlays_on_base_clip()`.

### 3.5 Narration Speed: Uses Pipeline Speed

`mix_narration_audio()` is called with `playback_speed=_get_effective_playback_speed(payload, _target_platform)`. This is the same effective speed used by `TimelineMap` and `render_base_clip()`. The narration is speed-compensated to match the output duration. Correct.

---

## 4. Audio Ownership Table (Target Post Phase 3C)

| Operation | Owner (overlay path) | Owner (legacy path) |
|---|---|---|
| Source audio speed (atempo) | `render_base_clip()` — once, in base clip | `render_part_smart()` — once, in encode |
| Loudnorm | `render_base_clip()` | `render_part_smart()` |
| BGM mix | `render_base_clip()` ← Phase 3C | `render_part_smart()` |
| BGM stream copy | `composite_overlays_on_base_clip()` (`-c:a copy`) | N/A |
| Narration generation | `render_pipeline.py` (after render) | same |
| Narration cleanup (DeepFilterNet) | `_maybe_cleanup_narration_audio()` | same |
| Narration speed compensation | `mix_narration_audio(playback_speed=...)` | same |
| Narration mix | `mix_narration_audio()` on overlay output | `mix_narration_audio()` on smart render |
| Audio QA | `_validate_render_output()` on `final_part` | same |

---

## 5. Recommended Phase 3C Scope

**Primary implementation**: Add BGM parameters to `render_base_clip()` and its call site in `render_pipeline.py`.

**Validation**: Add tests confirming narration behavior on overlay path and no double-atempo.

**Out of scope for Phase 3C**:
- Changing `composite_overlays_on_base_clip()` audio behavior (stays `-c:a copy`)
- Changing `mix_narration_audio()` interface
- Adding separate post-composite audio pipeline
- Phase 4+ concerns (subtitle timestamp rescaling, output-timeline TTS alignment)

**Why this scope:**
- Narration is already working — no implementation needed
- BGM is the only missing feature — one bounded change to `render_base_clip()`
- `-c:a copy` in composite stays correct — BGM will be in the stream-copied audio
- No new pipeline stages needed

---

## 6. Overlay Audio Flow (Post Phase 3C)

```
render_base_clip(
    ...,
    reup_bgm_enable=payload.reup_bgm_enable,    ← NEW (from call site)
    reup_bgm_path=payload.reup_bgm_path,        ← NEW
    reup_bgm_gain=payload.reup_bgm_gain,        ← NEW
)
→ base_clip.mp4
    audio: source_audio [atempo=speed] [BGM mix] [loudnorm]
    PTS: output-timeline

composite_overlays_on_base_clip(base_clip.mp4, ...)
→ overlay_visual.mp4
    audio: -c:a copy (base_clip audio, incl. BGM)

[if voice_enabled and _final_voice_path]:
mix_narration_audio(
    video_path=overlay_visual.mp4,
    narration_audio_path=...,
    mix_mode=payload.voice_mix_mode,
    output_path=mixed_part,
    playback_speed=timeline.effective_speed,
)
→ os.replace(mixed_part, final_part)

final_part.mp4
    audio: BGM + narration (atempo-compensated) OR source + BGM + narration
    video: overlays applied on output-timeline PTS
```

---

## 7. Artifact Naming Plan

No new intermediate artifacts are created. BGM is baked into `base_clip.mp4` (existing artifact). The stream copy in the composite carries BGM through to `overlay_visual_path` (the `final_part` before narration mix).

Temp artifact for narration mix (already exists): `{final_part.stem}.voice_tmp.mp4`
- Kept in place as is. No rename needed.

---

## 8. Manifest Evolution Plan

One new field on `BaseClipManifest`:

```python
# Base clip artifact — populated when FEATURE_BASE_CLIP_FIRST=1
base_clip_bgm_applied: Optional[bool] = field(default=None)
```

**Purpose**: Records whether BGM was baked into `base_clip.mp4`. Allows downstream stages and debugging to know if base_clip audio includes BGM.

**Naming justification**: `base_clip_bgm_applied` follows existing `base_clip_*` field convention. Describes the artifact state (what was applied to base_clip), not the feature flag.

**Population**:
- Set to `True` after `render_base_clip()` when `reup_bgm_enable=True` and `bgm_ok` (BGM file exists)
- Set to `False` when `reup_bgm_enable=False` (or BGM file missing)
- Remains `None` when `FEATURE_BASE_CLIP_FIRST=0`

**Serialization** (follows existing pattern):
```python
# to_dict():
"base_clip_bgm_applied": self.base_clip_bgm_applied,

# from_dict():
base_clip_bgm_applied=bool(d["base_clip_bgm_applied"]) if d.get("base_clip_bgm_applied") is not None else None,
```

**Backward compat**: `from_dict()` uses `.get()` → None default for old manifests without this field.

---

## 9. Fallback Strategy

| Scenario | Audio outcome | Correct? |
|---|---|---|
| Overlay succeeds + BGM enabled + narration requested | BGM in base_clip → stream-copied → narration mixed on top | ✓ |
| Overlay succeeds + BGM disabled + narration requested | No BGM → stream-copied → narration mixed | ✓ |
| Overlay succeeds + BGM enabled + no narration | BGM in base_clip → stream-copied → final_part has BGM | ✓ |
| Overlay succeeds + nothing enabled | Source audio in base_clip → stream-copied | ✓ |
| Overlay fails → render_part_smart() fallback | render_part_smart() runs with full BGM + narration (unchanged legacy) | ✓ |
| render_base_clip() fails → skip base_clip + skip overlay → render_part_smart() | Legacy path, full audio | ✓ |

**Key invariant**: If overlay composite fails for any reason, `render_part_smart()` runs with its own BGM and narration parameters, as today. No audio state from the failed overlay attempt leaks into the fallback.

**Narration not mixed twice**: `mix_narration_audio()` is guarded by `if _final_voice_path:` (line 4776). If overlay succeeds and narration mixes, `final_part` is replaced by `os.replace(mixed_part, final_part)`. If overlay then also fails (impossible — they're sequential), fallback runs on the original `raw_part` anyway. No double-mix risk.

---

## 10. Double-Atempo Prevention

**Current invariant (confirmed safe, no change needed):**

| Audio stream | atempo applied by | Applied where | Applied times |
|---|---|---|---|
| Source audio (overlay path) | `render_base_clip()` | Inside FFmpeg encode | Once |
| Source audio (legacy path) | `render_part_smart()` | Inside FFmpeg encode | Once |
| BGM audio (legacy path) | `render_part_smart()` | Inside FFmpeg encode | Once |
| BGM audio (overlay path, Phase 3C) | `render_base_clip()` | Inside FFmpeg encode | Once |
| Narration audio | `mix_narration_audio()` | Post-render FFmpeg cmd | Once |
| Composite audio | `composite_overlays_on_base_clip()` | `-c:a copy` | Zero (stream copy) |

**Phase 3C change does NOT introduce double-atempo**: BGM is added to `render_base_clip()`. The composite still does `-c:a copy`. `mix_narration_audio()` still applies `atempo` only to `[1:a]` (narration). Source audio `[0:a]` in the composite output gets only `volume=0.25` (not atempo).

**Enforcement rule**: `composite_overlays_on_base_clip()` MUST NEVER add atempo. This is an existing invariant. Phase 3C does not relax it.

---

## 11. Double-Mix Prevention

**Narration**: `mix_narration_audio()` is called once, guarded by `if _final_voice_path:`. The result replaces `final_part` via `os.replace()`. There is no second call path.

**BGM (Phase 3C)**: BGM is baked into `base_clip.mp4` inside `render_base_clip()`. It flows through the composite via `-c:a copy`. There is no separate BGM mix step after composite. No double-mix possible.

**Legacy fallback**: When overlay fails and `render_part_smart()` runs, it produces its own `final_part` from `raw_part` (the video cut), not from `base_clip.mp4`. The base_clip BGM baking is irrelevant to the fallback. No cross-contamination.

---

## 12. BGM Strategy

### Current BGM behavior (legacy path)

BGM is applied inside `render_part_smart()` → `_render_part()` in `render_engine.py`:
```python
bgm_ok = reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
if bgm_ok:
    cmd += ["-stream_loop", "-1", "-i", bgm_path]
    # ... mixed via filter_complex with sidechain ducking or static amix
```

The BGM ducking logic lives in `_bgm_duck_filter()` (line 362 of `render_engine.py`). This uses `sidechaincompress` when `BGM_DUCKING_ENABLED=1`.

### Phase 3C BGM plan

Add the same BGM parameters to `render_base_clip()`:
```python
def render_base_clip(
    ...,
    reup_bgm_enable: bool = False,      # NEW
    reup_bgm_path: str | None = None,   # NEW
    reup_bgm_gain: float = 0.18,        # NEW
) -> dict:
```

Internally, `render_base_clip()` reuses the same `_bgm_duck_filter()` helper already used in `_render_part()`. No new BGM filter logic is written.

Call site in `render_pipeline.py`:
```python
render_base_clip(
    ...,
    reup_bgm_enable=payload.reup_bgm_enable,
    reup_bgm_path=payload.reup_bgm_path,
    reup_bgm_gain=payload.reup_bgm_gain,
)
```

`manifest.base_clip_bgm_applied` is set based on whether `bgm_ok` was True inside `render_base_clip()`.

### BGM + narration interaction (keep_original_low mode)

When BGM is baked into base_clip and narration is mixed in `keep_original_low` mode:
- `[0:a]` = overlay audio (source + BGM, speed-baked) → `volume=0.25`
- `[1:a]` = narration → `atempo=speed, volume=1.0`
- `[aout]` = amix of both

Result: BGM is audible at 25% during narration. This matches the intent of `keep_original_low` and is equivalent to the legacy behavior (BGM is present in source audio at 25% volume alongside narration at 100%).

### BGM + replace_original mode

When narration `mix_mode == "replace_original"`:
- Source video audio (incl. BGM) is discarded
- Only narration remains

This is a pre-existing behavior in the legacy path too. BGM is not preserved in `replace_original` mode regardless of path. **No regression from Phase 3C.**

---

## 13. Loudnorm Strategy

Loudnorm is already owned by `render_base_clip()` (parameter: `loudnorm_enabled`). It is applied to the base audio before BGM mix (or BGM is normalized together with source audio).

**Phase 3C does NOT change loudnorm behavior.** `composite_overlays_on_base_clip()` must NOT add loudnorm — base_clip audio is already normalized.

---

## 14. Audio QA Strategy

Existing `_validate_render_output()` checks:
- File size > 0
- Duration within expected range (±20%)
- Audio stream present when `voice_enabled=True` or `reup_bgm_enable=True`

**Phase 3C additions needed (test coverage, not production QA):**
- Assert that when overlay path is active and BGM enabled, `base_clip.mp4` has audio stream
- Assert that when overlay path is active and narration enabled, `final_part.mp4` has audio stream
- Assert `final_part` audio duration ≈ video duration (narration mix uses `-shortest`)

No changes to `_validate_render_output()` required — existing checks cover final output QA.

---

## 15. Test Strategy

### Unit tests (no real FFmpeg, mocked subprocess)

```
test_render_base_clip.py (additions):
  ✓ render_base_clip() with reup_bgm_enable=True → FFmpeg cmd contains bgm_path input
  ✓ render_base_clip() with reup_bgm_enable=False → FFmpeg cmd does NOT contain bgm_path
  ✓ render_base_clip() with BGM enabled → audio filter_complex includes BGM ducking
  ✓ render_base_clip() with BGM enabled → NO atempo applied to BGM stream separately
    (BGM is mixed together with source audio, one atempo on the combined output)

test_composite_overlays.py (additions):
  ✓ composite command does NOT contain atempo
  ✓ composite command audio is -c:a copy regardless of BGM state
  ✓ composite command does NOT contain BGM file path as input

test_overlay_narration.py (NEW FILE):
  ✓ When overlay succeeds + voice enabled: mix_narration_audio called with video_path=final_part
  ✓ When overlay succeeds + voice enabled: render_part_smart NOT called
  ✓ When overlay fails + voice enabled: mix_narration_audio called on fallback output
  ✓ When overlay fails + voice enabled: narration NOT mixed twice
  ✓ narration playback_speed = timeline.effective_speed
  ✓ narration atempo applies to [1:a] only (narration stream)
  ✓ source audio [0:a] in overlay output is NOT sped by mix_narration_audio
  ✓ mix_narration_audio called at most once per part

test_base_clip_manifest.py (additions):
  ✓ base_clip_bgm_applied None by default
  ✓ base_clip_bgm_applied in to_dict()
  ✓ base_clip_bgm_applied True round-trip
  ✓ base_clip_bgm_applied False round-trip
  ✓ from_dict backward compat: missing base_clip_bgm_applied → None
```

### Integration-light tests (pipeline behavior)

```
test_render_pipeline_overlay.py or additions to test_render_base_clip.py:
  ✓ FEATURE_BASE_CLIP_FIRST=1, BGM enabled → base_clip produced with BGM
  ✓ FEATURE_BASE_CLIP_FIRST=1, OVERLAY=1, BGM enabled → composite -c:a copy (BGM in stream)
  ✓ FEATURE_OVERLAY=1, overlay fails → render_part_smart receives BGM params
  ✓ manifest.base_clip_bgm_applied = True when BGM enabled and bgm_ok
  ✓ manifest.base_clip_bgm_applied = False when BGM disabled
```

---

## 16. Clean Code / Naming Rules

| Rule | Rationale |
|---|---|
| No phase-number names in manifest fields | `base_clip_bgm_applied` not `phase_3c_bgm_flag` |
| Temp file for narration mix: `{stem}.voice_tmp.mp4` | Already established, keep unchanged |
| No `final2`, `temp_audio`, `new_audio` temp files | Use existing naming patterns |
| BGM params follow `reup_bgm_*` naming already in codebase | Consistent with payload fields |
| `render_base_clip()` defaults match `render_part_smart()` defaults | `reup_bgm_enable=False, reup_bgm_gain=0.18` |

---

## 17. Required File Changes

| File | Change | Risk |
|---|---|---|
| `backend/app/services/render_engine.py` | Add `reup_bgm_enable`, `reup_bgm_path`, `reup_bgm_gain` params to `render_base_clip()`. Reuse existing `_bgm_duck_filter()` | LOW — additive params with defaults |
| `backend/app/orchestration/render_pipeline.py` | Pass BGM params to `render_base_clip()` call site. Set `manifest.base_clip_bgm_applied`. | LOW — additive at existing call site |
| `backend/app/domain/manifests.py` | Add `base_clip_bgm_applied: Optional[bool]` field, `to_dict()`, `from_dict()` | LOW — additive, backward compat |
| `backend/tests/test_render_base_clip.py` | Add BGM parameter tests | LOW |
| `backend/tests/test_overlay_narration.py` | NEW — narration + overlay integration tests | LOW — no FFmpeg, mocked |
| `backend/tests/test_base_clip_manifest.py` | Add `base_clip_bgm_applied` field tests | LOW |
| `backend/tests/test_composite_overlays.py` | Assert no atempo in composite, no BGM in composite cmd | LOW — additive assertions |

**No changes to**:
- `composite_overlays_on_base_clip()` audio behavior (stays `-c:a copy`)
- `mix_narration_audio()` (already works correctly)
- `render_part_smart()` (legacy path unchanged)
- Any API route, schema, frontend, DB

---

## 18. Exact Implementation Order

```
Step 1 — manifest field [~15 min]
  Add base_clip_bgm_applied to BaseClipManifest + to_dict + from_dict
  Add manifest field tests (backward compat + round-trip)

Step 2 — render_base_clip() BGM params [~45 min]
  Add reup_bgm_enable, reup_bgm_path, reup_bgm_gain to render_base_clip()
  Reuse _bgm_duck_filter() / existing BGM filter_complex logic from _render_part()
  Add unit tests: BGM in cmd when enabled, not in cmd when disabled

Step 3 — render_pipeline.py call site [~20 min]
  Pass BGM params to render_base_clip() call
  Set manifest.base_clip_bgm_applied based on bgm_ok

Step 4 — test_overlay_narration.py [~45 min]
  New test file verifying narration+overlay behavior
  Mock render_base_clip, composite_overlays_on_base_clip, mix_narration_audio
  Verify call order: base_clip → composite → mix_narration (on composite output)
  Verify no double-atempo, no double-mix

Step 5 — composite overlap assertions [~20 min]
  Add to test_composite_overlays.py: no atempo in composite cmd
  Add: no BGM file in composite cmd inputs

Step 6 — full test suite [~5 min]
  python -m pytest tests/ --tb=short -q
  Expect: same 8 pre-existing failures, 0 new failures

Step 7 — smoke test (manual, optional)
  FEATURE_BASE_CLIP_FIRST=1, FEATURE_OVERLAY_AFTER_BASE_CLIP=1, BGM enabled
  Verify: base_clip.mp4 has BGM, final_part.mp4 has BGM + narration
  Verify: manifest.base_clip_bgm_applied = True
```

---

## 19. What MUST NOT Change

| Constraint | Reason |
|---|---|
| `composite_overlays_on_base_clip()` audio: stays `-c:a copy` | Base clip owns audio; composite is overlay-only |
| `mix_narration_audio()` interface unchanged | Already works on overlay path; no new params needed |
| `render_part_smart()` unchanged | Legacy path must be identical to today |
| BGM NOT applied in composite | Composite is overlay-only; BGM belongs in base audio |
| atempo NOT applied in composite | Base clip already speed-adjusted; double-atempo forbidden |
| Feature flags default OFF | No production behavior change without explicit flag |
| Narration mixing happens once (post-render) | `os.replace()` pattern already guards this |
| API contracts | No schema, route, or frontend changes |

---

## 20. Phase 3C.5 Validation Plan

Phase 3C.5 validates the implementation before declaring Phase 3 complete.

### Automated checks

```
python -m pytest tests/test_render_base_clip.py -v        ← BGM param tests
python -m pytest tests/test_overlay_narration.py -v       ← narration+overlay tests
python -m pytest tests/test_composite_overlays.py -v      ← no-atempo assertions
python -m pytest tests/test_base_clip_manifest.py -v      ← BGM manifest field
python -m pytest tests/ --tb=short -q                     ← full suite
```

Acceptance: 0 new failures, all new tests pass.

### Manual smoke test (real render)

Enable flags, enable BGM, enable narration, run one real render:
```
FEATURE_BASE_CLIP_FIRST=1
FEATURE_OVERLAY_AFTER_BASE_CLIP=1
reup_bgm_enable=True
voice_enabled=True
voice_source=subtitle
```

Verify:
- `base_clip.mp4`: has audio stream, BGM audible, speed-adjusted
- `overlay_visual.mp4` (if temp artifact visible): has same audio as base_clip
- `final_part.mp4`: has BGM + narration mixed correctly
- `manifest.json`: `base_clip_bgm_applied=true`, `narration_path` set, `overlay_rendered_path` set
- No warning log for double-atempo or double-mix
- Final output quality visually and audibly acceptable

### Regression checks

- Render with both flags OFF: output identical to pre-Phase-3C (legacy path, no BGM in base_clip since base_clip not rendered)
- Render with BGM disabled (both flags ON): base_clip audio is source+atempo only, final_part correct
- Overlay composite failure: fallback `render_part_smart()` runs with its own BGM, no contamination from failed base_clip BGM

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| BGM filter_complex in render_base_clip diverges from render_part_smart | MEDIUM | Reuse `_bgm_duck_filter()` helper shared between both; add tests asserting filter string matches |
| BGM file path not validated before passing to render_base_clip | LOW | Existing `bgm_ok` guard (checks `Path(bgm_path).is_file()`) used in both functions |
| Narration mix speed mismatch: _get_effective_playback_speed vs timeline.effective_speed | LOW | Both compute the same value; ideally Phase 3C migrates to `timeline.effective_speed` at the call site |
| replace_original mode loses BGM | LOW — pre-existing in legacy path | Document as known; not a Phase 3C regression |
| BGM ducking with sidechain uses compressed narration as key signal — narration comes from [0:a] of overlay | MEDIUM | Verify sidechain input mapping is correct; narration is [1:a] and BGM [2:a] when BGM is an extra input |
| base_clip_bgm_applied not set if render_base_clip raises | LOW | Manifest field stays None; semantics are correct (BGM not applied if render failed) |

---

## Docs Updated by This Plan

- `docs/restructure/MIGRATION_HISTORY.md` — Phase 3C section added (planned)
- `docs/architecture/AUDIO_PIPELINE.md` — Phase 3C scope section updated with findings
- `docs/architecture/RENDER_BOUNDARIES.md` — BGM ownership updated to include Phase 3C
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` — Phase 3C pending section updated
- Review docs: no stale claims introduced by this plan
