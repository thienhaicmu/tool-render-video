# PRODUCT STATE — QUALITY-UP6: Creator Subtitle System

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): creator subtitle system`
**Status:** Shipped

---

## Summary

Four new subtitle personality presets (`viral`, `clean`, `story`, `gaming`) with
content-type-aware auto-defaults driven by the `content_type_hint` from QUALITY-UP2.
Each preset has a distinct visual identity tuned for its target content type.
Creator's explicit style choice always overrides the auto-default.

---

## Root Cause

QUALITY-AUDIT1 identified subtitles as one of the strongest remaining "generic AI
editor" signals. Every video produced the same visual personality regardless of
whether the content was a commentary reaction, a tutorial, a vlog, or a gaming
montage. The existing 6 presets were all Bungee/heavy-outline variations that
felt interchangeable.

---

## Part A — Subtitle Personality Presets

**File:** `backend/app/services/subtitle_engine.py`

Four new canonical entries added to `_PRESETS`:

### `viral` — TikTok/Reels-native
Target content: commentary, reaction, hook-heavy shorts.

| Property | Value | Rationale |
|----------|-------|-----------|
| Font | Bungee bold | Energy, authority |
| Font size | 50 (heavy formula) | Dominant, fills frame |
| Outline | 7 px | Maximum bg separation |
| Shadow | 1 px | Depth only, clean |
| Back color | transparent | Pure outline — modern, no box |
| Wrap em | 13.0 | Short punchy 2-3 word bursts |
| Bounce FX | yes | Word-by-word pop-in |
| Margin V ratio | 0.22 | Clears TikTok/Reels bottom chrome |
| Emphasis level | strong | Numbers, contrast, urgency, hook words |

### `clean` — Minimal/premium
Target content: education, tutorial, podcast clips.

| Property | Value | Rationale |
|----------|-------|-----------|
| Font | Bungee normal weight | Readable, not aggressive |
| Font size | 34 (standard formula) | Clear without dominating |
| Outline | 3 px | Thin: editorial, premium |
| Shadow | 1 px | Barely there |
| Back | `&H40000000` very subtle | Near-invisible depth |
| Margins | 60 px each side | Narrower text block = premium feel |
| Wrap em | 18.0 | Full sentence pacing |
| Bounce FX | no | Professional, no distraction |
| Emphasis level | subtle | Numbers only |

### `story` — Cinematic/soft
Target content: vlog, storytelling, emotional content.

| Property | Value | Rationale |
|----------|-------|-----------|
| Font | Bungee normal | Soft weight |
| Font size | 33 | Understated |
| Primary color | `&H00EBEBEB` (off-white) | Warmer/softer than pure white |
| Outline | 2 px | Barely present: like movie subtitles |
| Shadow | 1 px | Minimal depth |
| Back | `&H20000000` near-transparent | Almost invisible |
| Wrap em | 19.0 | Natural speech, no rushing |
| Bounce FX | no | Serene, no pop |
| Emphasis level | medium | Numbers + emotional/contrast words |

### `gaming` — Caption-box for fast motion
Target content: gaming, sports, montage clips.

| Property | Value | Rationale |
|----------|-------|-----------|
| Font | Bungee bold | High energy |
| Font size | 44 (heavy formula) | Large, visible at speed |
| Border style | 3 (opaque box) | Caption box: clear on any bg |
| Outline (padding) | 14 px | Wide box padding |
| Back color | `&HB0000000` | Semi-opaque dark box fill |
| Shadow | 0 | Box provides separation, no shadow |
| Wrap em | 13.0 | Short bursts |
| Bounce FX | yes | Energetic pop |
| Margin V ratio | 0.20 | High position |
| Emphasis level | strong | Full keyword emphasis |

---

## Part B — Content-Type Auto Defaults

**File:** `backend/app/orchestration/render_pipeline.py`

When `payload.subtitle_style` is empty/None (no explicit creator choice), the pipeline
now selects a personality preset based on `seg["content_type_hint"]`:

| content_type_hint | Auto-default preset |
|-------------------|---------------------|
| `commentary`      | `viral` |
| `vlog`            | `story` |
| `tutorial`        | `clean` |
| `interview`       | `clean` |
| `montage`         | `gaming` |

**Override safety:** `_raw_sub_style = (payload.subtitle_style or "").strip()`. If
this is non-empty, `_effective_subtitle_style = _raw_sub_style` — the creator's
choice is used exactly. The auto-default is only the fallback.

`_effective_subtitle_style` replaces `payload.subtitle_style` in:
- `subtitle_emphasis_pass(preset_id=...)`
- `srt_to_ass_bounce(subtitle_style=...)`
- `if ... == "pro_karaoke":` check
- Log and event context (includes `subtitle_style_source: "auto"/"explicit"` for observability)

---

## Part C — Readability Improvements

New `wrap_max_em` values drive readability:

| Preset | `wrap_max_em` | Effect |
|--------|-------------|--------|
| `viral` | 13.0 | Short 2-3 word bursts — punchy, platform-native |
| `gaming` | 13.0 | Same short-burst pacing |
| `clean` | 18.0 | Full sentences fit — educational clarity |
| `story` | 19.0 | Wide lines — natural speech, no forced breaks |

The existing `_break_by_visual_width` midpoint-split logic already handles
semantic splitting. The `wrap_max_em` tuning ensures each personality breaks
at the right density for its content type.

---

## Part D — Font Safety

All four new presets use `font_default="Bungee"` — the font bundled at
`backend/fonts/Bungee-Regular.ttf`. This is always resolvable via the
`fontsdir` parameter passed to FFmpeg's `ass` filter.

If a creator overrides `sub_font` with a custom font name:
1. libass searches `fontsdir` (bundled fonts) + system fonts
2. If not found: libass substitutes a system sans-serif
3. No render crash, no subtitle disappearance — libass never fails on a missing
   font, it degrades to a substitute

The bundled Bungee fallback is the safety net. Custom fonts are best-effort.

---

## Part E — Platform Feel

| Preset | Platform feel target |
|--------|---------------------|
| `viral` | TikTok commentary. Thick outline, no box, short bursts. Clears bottom chrome. |
| `clean` | YouTube education. Thin, narrow text block. No bounce distraction. |
| `story` | Instagram/YouTube vlog. Off-white, soft, cinematic. |
| `gaming` | Twitch/YouTube gaming. Caption box, always-readable under motion. |

The `gaming` preset uses `border_style=3` (opaque box) — the only non-outline
preset in the new group. This is a strong visual differentiator from `viral`
(which uses pure outline) even though both target high-energy content.

---

## Parameter Comparison — New vs Closest Existing

| | `viral_bold` | `viral` (new) | `clean_pro` | `clean` (new) |
|--|-------------|--------------|------------|--------------|
| Bold | yes | yes | yes | no |
| Font size | 46 (heavy auto) | 50 (heavy auto) | 38 | 34 (std auto) |
| Outline px | 5 | 7 | 4 | 3 |
| Wrap em | 16.0 | **13.0** | 16.0 | **18.0** |
| Bounce | yes | yes | yes | **no** |
| Margin V | 0.20 | **0.22** | 0.0 | 0.0 |

| | `story_clean_01` | `story` (new) | `bold_cap` | `gaming` (new) |
|--|----------------|--------------|-----------|---------------|
| Primary color | `&H00F6F6F6` | `&H00EBEBEB` | white | white |
| Outline px | 4 | **2** | 5 | **14 (box padding)** |
| Border style | 1 | 1 | 1 | **3 (box)** |
| Wrap em | 16.0 | **19.0** | 16.0 | **13.0** |
| Bounce | yes | **no** | yes | yes |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| Color accent stroke (colored outline_color) | ASS outline is single-color; per-word colored outline requires per-word override tags |
| Animated reveal effects (fade-in, slide-up) | Requires per-dialogue ASS timing tags; scope is QUALITY-UP7 |
| Font family variety (Impact, Montserrat, etc.) | Bundled Bungee is the safe default; font selection is a creator config option |
| Frontend preset picker UI | Backend-only change; UI to expose new IDs is a product decision |
| `"auto"` sentinel value in payload | Requires frontend/API change; currently auto-default fires on empty style only |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/subtitle_engine.py` | 4 new presets in `_PRESETS` (`viral`, `clean`, `story`, `gaming`); 4 new entries in `_emphasis_level()` |
| `backend/app/orchestration/render_pipeline.py` | `_CONTENT_TYPE_SUB_DEFAULTS` table; `_effective_subtitle_style` computation; all 3 subtitle call sites updated |
| `docs/render/PRODUCT_STATE_QUALITY_UP6.md` | This file |

---

## Manual QA Checklist

### Commentary / Reaction
- [ ] Auto-default selects `viral` when `subtitle_style` is unset
- [ ] Subtitles feel platform-native TikTok — short burst lines, word pop
- [ ] Log shows `style=viral subtitle_style_source=auto content_type=commentary`

### Tutorial / Education
- [ ] Auto-default selects `clean`
- [ ] Subtitles feel clean and minimal — thin outline, no bounce
- [ ] Wider text block visible (60px margins)

### Vlog / Storytelling
- [ ] Auto-default selects `story`
- [ ] Off-white color visible (slightly softer than clean/viral)
- [ ] No bounce, natural pacing

### Gaming / Montage
- [ ] Auto-default selects `gaming`
- [ ] Caption box visible behind text (not just outline)
- [ ] Stays readable under fast background motion

### Auto-default vs manual override
- [ ] Job with `subtitle_style="viral_bold"` → uses `viral_bold` (not overridden)
- [ ] Job with `subtitle_style="tiktok_bounce_v1"` → uses `tiktok_bounce_v1`
- [ ] Job with `subtitle_style=""` (empty) → uses content-type default
- [ ] Log `subtitle_style_source=explicit` vs `auto` matches expectation

### Font fallback safety
- [ ] Custom `sub_font="SomeMissingFont"` → render completes, subtitles show (libass substitutes)
- [ ] No crash on unknown font name

### Timing regression
- [ ] Subtitle timing unchanged across all presets
- [ ] No subtitle drift after render
- [ ] No render errors or backend crashes
