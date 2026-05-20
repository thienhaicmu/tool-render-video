# OQ-1.3 — Premium Subtitle Style System
## CapCut-Inspired Visual Overhaul

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** VISUAL ONLY — no timing, no intelligence, no scoring changes

---

## 1. Current Style Audit

### Font situation (pre-OQ-1.3)

All 10 presets use `Bungee` as `font_default`. No visual differentiation by content type. Only `Bungee-Regular.ttf` existed in `backend/fonts/`.

### Letter-spacing (pre-OQ-1.3)

`ASSPreset` has no `spacing` field. `build_ass_style_line()` hardcodes `Spacing=0` in all rendered ASS style lines at:
```python
f"100,{scale_y},0,0,"
```
ASS field order: ScaleX, ScaleY, **Spacing**, Angle. The third zero is letter-spacing — always zero for all presets.

### Outline / shadow weight (pre-OQ-1.3)

| Preset | Outline | Shadow | Notes |
|---|---|---|---|
| viral | 7 | 1 | Heaviest — good for short punchy text |
| gaming | 14 (box) | 0 | Box padding |
| tiktok_bounce_v1 | 5 | 3 | Heavy shadow creates depth |
| bold_cap | 5 | 3 | Same as bounce |
| viral_bold | 5 | 3 | Same |
| clean_pro | 4 | 2 | Slightly lighter |
| story_clean_01 | 4 | 1 | |
| clean | 3 | 1 | Lightest |
| story | 2 | 1 | Lightest — cinematic |
| boxed_caption | 12 (box) | 0 | Box padding |

---

## 2. Problems Discovered

| # | Problem | Severity |
|---|---|---|
| P1 | All presets identical font — no visual identity per content type | HIGH |
| P2 | Spacing=0 on all presets — text appears cramped at larger sizes | MEDIUM |
| P3 | `viral` outline=7 is heavier than Anton's visual weight warrants | LOW |
| P4 | `gaming` box padding=14 slightly oversized vs CapCut reference | LOW |
| P5 | `Montserrat-Regular.ttf` referenced but not in fonts dir | HIGH |
| P6 | `Inter` not in font map at all | HIGH |

---

## 3. Architecture

### Change 1: `spacing` field on `ASSPreset`

```python
spacing: float = 0.0   # ASS Spacing field — letter-spacing in pixels
```

Added after `margin_v_ratio`. Default `0.0` preserves all existing renders.

### Change 2: `build_ass_style_line()` uses `preset.spacing`

```python
# Before
f"100,{scale_y},0,0,"

# After
f"100,{scale_y},{preset.spacing:.1f},0,"
```

ASS Spacing field accepts float; `.1f` keeps formatting clean.

### Change 3: Four content-native font families

| Preset | Font | File | Rationale |
|---|---|---|---|
| `viral`, `gaming` | Anton | Anton-Regular.ttf | High x-height, condensed, maximum impact at large sizes |
| `clean`, `clean_pro` | Inter | Inter-Variable.ttf | Neutral grotesque — maximum legibility for educational content |
| `story`, `story_clean_01` | Montserrat | Montserrat-Variable.ttf | Geometric warmth for narrative/vlog content |
| `tiktok_bounce_v1`, `bold_cap`, `viral_bold`, `boxed_caption` | Bungee | Bungee-Regular.ttf | Legacy — retains original visual identity |

---

## 4. Font Strategy

### Why Anton for viral/gaming?
Anton is a poster-display condensed sans — every stroke is thick and uniform. At 44-50px it reads instantly at thumb-scroll speed, which is the primary TikTok/Reels use case. It pairs naturally with bold outlines and box backgrounds.

### Why Inter for clean/clean_pro?
Inter is designed for on-screen reading at small sizes, with an open aperture and tight spacing. For education/podcast/tutorial content where the viewer is reading actual information (not just an emotional hook), Inter reduces eye strain and improves comprehension.

### Why Montserrat for story/story_clean_01?
Montserrat's geometric roundness creates warmth without sacrificing legibility. Story/vlog content relies on emotional tone — a slightly warmer typeface reinforces the cinematic quality without requiring animation.

### Variable fonts
Montserrat and Inter are variable fonts (`.ttf` with weight axis). libass resolves fonts by internal family name metadata, which variable fonts include. The weight axis is available but not explicitly set — libass uses the default weight (400).

---

## 5. Visual Tuning

### Letter-spacing by preset type

| Preset type | Spacing | Rationale |
|---|---|---|
| Anton large/viral | 0.5 | Condensed letterforms benefit from slight opening |
| Inter clean | 1.0 | Grotesque at larger sizes needs more air |
| Montserrat story | 1.0 | Geometric warmth increased by more tracking |
| Bungee bounce | 0.3–0.4 | Minimal — Bungee is designed tight |
| Box-backed | 0.3–0.4 | Tight spacing reads better with box background |

### Outline refinements

| Preset | Before | After | Rationale |
|---|---|---|---|
| viral | 7 | 5 | Anton's uniform strokes need less outline than Bungee |
| gaming | 14 | 12 | Box padding slightly tighter, still readable |
| tiktok_bounce_v1 | 5 | 4 | Lighter, crisper |
| bold_cap | 5 | 4 | Same |
| viral_bold | 5 | 4 | Same |
| clean_pro | 4 | 3 | Inter is more readable with thinner outline |
| story_clean_01 | 4 | 3 | Montserrat reads lighter |
| boxed_caption | 12 | 10 | Box padding tighter |
| clean | 3 | 2 | Inter barely needs outline |
| story | 2 | 2 | No change |

### Shadow refinements

| Preset | Before | After | Rationale |
|---|---|---|---|
| viral | 1 | 2 | Anton at large size benefits from slightly more depth |
| tiktok_bounce_v1 | 3 | 2 | Less depth, crisper bounce |
| bold_cap | 3 | 2 | Same |
| viral_bold | 3 | 2 | Same |
| clean_pro | 2 | 1 | Inter looks cleaner with minimal shadow |

---

## 6. Preset Strategy

### Each preset's visual identity

| Preset | Font | Character |
|---|---|---|
| `viral` | Anton | Condensed impact — punchy, scroll-stopping |
| `gaming` | Anton | Heavy box caption — max readability on fast video |
| `clean` | Inter | Minimal, professional, editorial |
| `clean_pro` | Inter | Same as clean but slightly bolder |
| `story` | Montserrat | Warm, cinematic, narrative |
| `story_clean_01` | Montserrat | Softer story with subtle bounce |
| `tiktok_bounce_v1` | Bungee | Classic TikTok bounce identity |
| `bold_cap` | Bungee | All-caps Bungee energy |
| `viral_bold` | Bungee | Heavier Bungee variant |
| `boxed_caption` | Bungee | Box-style captions, Bungee character |

---

## 7. Compatibility Impact

| Component | Impact |
|---|---|
| ASS format | None — `spacing` field was already in the ASS spec, just set to 0 before |
| Subtitle presets | Visual change only — no timing, no split logic |
| Existing renders (cached SRT) | Will re-render with new font/spacing when next requested |
| Bungee-only presets | Unchanged font — only minor outline/shadow and spacing change |
| OQ-1.2 intelligence | None — operates before style layer |
| Transcript cache | None — not touched |
| Render queue | None — stateless style resolution |
| S1 AI orchestrator | None |
| Scoring | None |

---

## 8. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Inter/Montserrat not found by libass | Low | libass falls back to system sans if font file missing; Anton still serves viral/gaming |
| Variable font weight axis ignored | Low | Default weight (400) renders — visual is acceptable |
| Spacing=0.0 default preserves all preset backward compat | None | Only explicitly set presets get non-zero spacing |
| Outline reduction causes hard-to-read subtitle | Low | All reductions are 1-2px; min outline for Anton presets is 5px |
| ASS Spacing field rejected by old libass | Low | Spacing is in ASS v4+ spec; all modern FFmpeg/libass builds support it |

---

## 9. Manual Verification Checklist

```
[ ] viral preset renders Anton font (not Bungee)
[ ] clean preset renders Inter font (not Bungee)
[ ] story preset renders Montserrat font (not Bungee)
[ ] gaming preset renders Anton font (not Bungee)
[ ] tiktok_bounce_v1 still renders Bungee (unchanged)
[ ] Letter-spacing visible difference between Inter (1.0) and Bungee (0.3) presets
[ ] Outline weight visually lighter on viral (5 vs 7 before)
[ ] No font fallback warnings in FFmpeg stderr for Anton/Inter/Montserrat
[ ] All 10 presets produce valid ASS output (no parse errors)
[ ] OQ-1.2 intelligence still fires before style layer
[ ] Bounce animation (tiktok_bounce_v1, bold_cap) unaffected
[ ] Box caption (gaming, boxed_caption) outline box still renders correctly
[ ] Multi-render stable — stateless style resolution
[ ] ASS Spacing field appears correctly in rendered .ass file header
```

---

## 10. Files Modified

| File | Change |
|---|---|
| `backend/app/services/subtitle_engine.py` | Add `spacing: float = 0.0` to `ASSPreset`. Update `build_ass_style_line()` Spacing field. Update 10 preset definitions. |
| `backend/app/services/text_overlay.py` | Add `Inter: Inter-Variable.ttf` to `regular_map`. Fix `Montserrat` to `Montserrat-Variable.ttf`. |
| `backend/fonts/` | Anton-Regular.ttf, Montserrat-Variable.ttf, Inter-Variable.ttf (downloaded in STEP 1) |

---

## 11. Commit Hash

`[pending]`

---

## 12. Push Confirmation

`[pending]`
