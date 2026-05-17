# PRODUCT STATE — QUALITY-UP8: Hook Intro Redesign

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): hook intro redesign`
**Status:** Shipped

---

## Summary

Four visually distinct intro personalities replace the single black-background
drawtext intro. Content-type auto-selects the right personality. AI hook text
drives the headline (not a hardcoded string). All rendering stays in FFmpeg —
no new frameworks, no Remotion, no performance cliff.

---

## Root Cause

The previous intro was:
- **Black background** (`color=c=black`) — looks like a prototype placeholder
- **Hardcoded `"STOP SCROLLING"`** — ignores AI hook text and source context
- **One style for all content types** — commentary, tutorial, and gaming all
  received the same visual treatment

These three factors combined to signal "unfinished tool" at the first frame.

---

## Part A — 4 Intro Personalities

**File:** `backend/app/services/remotion_adapter.py`

Each preset is a pure FFmpeg filter chain (drawbox + drawtext + fade).
No video templates. No external assets.

### `viral_pop` — TikTok/Reels-native

| Property | Value |
|----------|-------|
| Background | `#07080D` (near-black, deep blue tint) |
| Top accent | 3px cyan `#00E5FF`, 85% opacity |
| Bottom accent | 4px TikTok red `#FF2D55`, 82% opacity |
| Effect | White flash punch-in at t=0–0.08s; ghost oversized text at t=0–0.12s |
| Text size | `font_size × 1.12` (largest preset) |
| Text color | White, 6px black border, shadow |
| Fade in | 0.08s (fast punch) |
| Duration | 1.0s |

Target: commentary, reaction, hook-heavy clips.

---

### `clean_creator` — Minimal/premium

| Property | Value |
|----------|-------|
| Background | `#0A0E1A` (dark navy — slightly different from black) |
| Accent | Single thin 2px white divider line at 55% height, 22% opacity |
| Text size | `font_size × 0.88` (smallest, editorial) |
| Text position | Slightly above center |
| Fade in | 0.30s (slow, premium) |
| Duration | 1.2s |

Target: tutorial, education, podcast clips.

---

### `story_cinematic` — Cinematic/emotional

| Property | Value |
|----------|-------|
| Background | `#0D0A07` (dark warm — barely noticeable warmth) |
| Accent | 1px off-white `#EBEBEB`, 18% opacity — film-like, almost invisible |
| Text size | `font_size × 0.85` |
| Text color | Off-white `#EBEBEB`, 1px border (minimal) |
| Text position | Below center (cinematic safe-area placement) |
| Fade in | 0.25s |
| Duration | 1.5s (longest — gives emotional content room to breathe) |

Target: vlog, storytelling, emotional content.

---

### `gaming_energy` — High-energy/esports

| Property | Value |
|----------|-------|
| Background | `#070A0D` (dark cold blue-black) |
| Top bar | Full-width orange `#FF6600`, 90% opacity |
| Bottom bar | Same orange, symmetric |
| Effect | Electric blue flash at t=0–0.06s; offset ghost text at t=0–0.10s (micro-shake) |
| Text size | `font_size × 1.20` |
| Fade in | 0.06s (fastest punch) |
| Duration | 1.0s |

Target: gaming, sports, montage.

---

## Part B — Content-Type Auto Defaults

**File:** `backend/app/services/remotion_adapter.py`

`_CONTENT_TYPE_INTRO_DEFAULTS`:

| content_type | Auto preset |
|-------------|-------------|
| `commentary` | `viral_pop` |
| `vlog` | `story_cinematic` |
| `story` | `story_cinematic` |
| `tutorial` | `clean_creator` |
| `interview` | `clean_creator` |
| `montage` | `gaming_energy` |
| `gaming` | `gaming_energy` |

**Override safety:** `resolve_intro_preset(content_type, override=...)` —
if `payload.intro_preset` is non-empty, the creator's choice is used exactly.
Auto-default fires only when `intro_preset` is absent or empty.

---

## Part C — Typography Upgrade

**Hook text priority:** `_build_intro_headline(hook_text, headline_text, source_title, output_path, max_words)`

Fallback chain:
1. `hook_text` (AI-selected hook phrase from QUALITY-UP1A scoring)
2. `headline_text` (explicitly passed — kept for backward compat)
3. `source_title` (video source title)
4. Generic fallback from `_FALLBACK_HEADLINES`

**Word clamping per preset:**

| Preset | max_words | Effect |
|--------|----------|--------|
| `viral_pop` | 4 | Short punchy hook lines |
| `clean_creator` | 6 | Slightly more space for editorial clarity |
| `story_cinematic` | 5 | Medium — emotional, not truncated |
| `gaming_energy` | 4 | Same short burst as viral |

Text truncated to `max_words` gets `...` appended. All headline text is
uppercased for visual impact.

---

## Part D — Pipeline Integration

**File:** `backend/app/orchestration/render_pipeline.py`

`_maybe_prepend_remotion_hook_intro()` updated:
- Accepts `content_type`, `hook_text`, `source_title` instead of hardcoded `headline_text`
- Calls `resolve_intro_preset()` to select preset (creator override via `payload.intro_preset`)
- Uses per-preset duration (1.0s–1.5s) — returned to the part duration calculation
- Log: `hook_intro_requested part=N preset=viral_pop duration_sec=1.00`

Call site updated:
- `content_type=seg.get("content_type_hint")` — segment's detected content type
- `hook_text=_hook_applied_text` — AI hook text from payload (already resolved earlier in the pipeline)
- `source_title=source.get("title")` — source video title for fallback

---

## Part E — Performance

All intro rendering uses the existing FFmpeg path:
- `lavfi color` source (trivially fast to generate solid-color frames)
- `drawbox` + `drawtext` filters (CPU-cheap on solid backgrounds)
- The flash and ghost-text effects use `enable='between(t,0,N)'` — these are
  evaluated per-frame but add no perceptible latency on short 1–1.5s clips

No `zoompan`, no `gblur`, no per-pixel compositing. Same performance
characteristics as the previous black-background intro.

---

## Part F — Failure Safety

`generate_hook_intro()` returns `None` on any exception or subprocess failure.
`_maybe_prepend_remotion_hook_intro()` returns `0.0` when `intro` is `None` —
the render continues with the original clip unmodified. No crash. No export failure.

The `prepend_intro_clip()` function also returns `None` on failure; same
safe-fallback chain applies.

---

## Parameter Comparison

| | Before | After |
|--|--------|-------|
| Background | `black` (uniform) | Preset-specific dark tones (07080D / 0A0E1A / 0D0A07 / 070A0D) |
| Accents | White line + red line | Preset-specific (cyan+pink / thin divider / bare / orange bars) |
| Text size multiplier | Fixed 1.08 / 1.0 | 0.85–1.20 per preset |
| Fade in | 0.2s (uniform) | 0.06–0.30s per preset |
| Duration | 1.0s (uniform) | 1.0–1.5s per preset |
| Headline source | Hardcoded `"STOP SCROLLING"` | AI hook → source title → fallback |
| Content-type auto | None | Full content_type_hint mapping |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| Animated text (slide-up, scale) | Requires `zoompan`/`geq`/complex filter expression — performance risk on high-res source |
| Background gradient | FFmpeg `lavfi color` is solid-only; gradient needs `geq` filter — higher CPU |
| Motion blur effects | Expensive per-frame computation |
| Custom font per preset | All use system/libass default sans-serif; font bundling is a QUALITY-UP9 scope item |
| Frontend preset picker | Backend-only change; UI to expose `intro_preset` field is a product decision |
| Logo/watermark overlay | Creator brand assets require upload flow — out of scope |
| Remotion/React integration | Brief explicitly excludes it |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/remotion_adapter.py` | 4 preset VF builders; `_CONTENT_TYPE_INTRO_DEFAULTS`; `_INTRO_PRESET_DURATIONS`; `_build_intro_headline`; `resolve_intro_preset`; `generate_hook_intro` updated with `preset_id`, `hook_text`, `source_title` params |
| `backend/app/orchestration/render_pipeline.py` | Import `resolve_intro_preset`; `_maybe_prepend_remotion_hook_intro` updated with `content_type`, `hook_text`, `source_title`; call site updated |
| `docs/render/PRODUCT_STATE_QUALITY_UP8.md` | This file |

---

## Manual QA Checklist

### Preset visual check (commentary → viral_pop)
- [ ] Log shows `hook_intro_requested preset=viral_pop`
- [ ] White flash visible in first 0.08s
- [ ] Cyan top + TikTok red bottom accent lines visible
- [ ] Text feels large and dominant
- [ ] Fade in is fast (punch, not slow dissolve)

### Preset visual check (tutorial → clean_creator)
- [ ] Log shows `hook_intro_requested preset=clean_creator`
- [ ] No flash effect
- [ ] Single thin white horizontal divider visible near center
- [ ] Text smaller, slightly above center — editorial feel
- [ ] Fade in is slow and premium (0.30s)
- [ ] Duration is 1.2s

### Preset visual check (vlog → story_cinematic)
- [ ] Log shows `hook_intro_requested preset=story_cinematic`
- [ ] Warm dark background (slightly different from black)
- [ ] Text is off-white (not pure white), positioned below center
- [ ] Very minimal accent (barely visible)
- [ ] Duration is 1.5s — feels like it breathes

### Preset visual check (montage/gaming → gaming_energy)
- [ ] Log shows `hook_intro_requested preset=gaming_energy`
- [ ] Electric blue flash at very start
- [ ] Full-width orange bars top + bottom
- [ ] Text is large and impactful
- [ ] Fade in is fastest (0.06s)

### Hook text priority
- [ ] Job with `hook_applied_text` set → first 4 words of hook appear in intro (not "STOP SCROLLING")
- [ ] Job without hook text → source title appears (truncated to max_words)
- [ ] Job without title → fallback headline used

### Creator override
- [ ] `payload.intro_preset = "gaming_energy"` on a tutorial job → gaming_energy is used
- [ ] Log shows `hook_intro_requested preset=gaming_energy` (not clean_creator)

### Timing regression
- [ ] `_expected_final_duration` accounts for 1.5s story intro correctly
- [ ] No subtitle drift after intro is prepended
- [ ] Export playback: intro + clip concat is seamless

### Failure safety
- [ ] `remotion_hook_intro=False` → no intro generated (same as before)
- [ ] Simulate FFmpeg failure → render continues with original clip
- [ ] No crash, no broken export

### Safety regression
- [ ] All content types render without errors
- [ ] Cancel still works
- [ ] No performance cliff vs previous intro render time
- [ ] No new backend errors
