# OQ-1.4 — Motion Subtitle Engine
## CapCut-Inspired Subtitle Motion

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** MOTION ONLY — no intelligence, no styles, no fonts, no timing, no scoring

---

## 1. Current Motion Audit

### Bounce animation (pre-OQ-1.4)

```python
BOUNCE_FX = r"{\fscx122\fscy122\t(0,200,\fscx100\fscy100)}"
```

- Single constant. All 7 `bounce_fx=True` presets receive the **identical** animation.
- Scale: 122% → 100% (overshoot pop).
- Duration: 200ms (linear).
- Applied: `build_ass_style_line()` line 631, as `line_fx` prefix on each Dialogue Text field.
- Guard: fires only when `preset.bounce_fx=True AND highlight_per_word=True`.
  → Segment-level mode (`highlight_per_word=False`) has **zero animation** on all presets.

### Word-level timing path

- `_write_word_level_srt()` — one SRT block per word.
- `srt_to_ass_bounce()` processes each block as a separate Dialogue line.
- `line_fx` (= `BOUNCE_FX`) is prepended → each word pops individually.
- In word-level mode, each word is its own animation unit.

### Karaoke path

- `srt_to_ass_karaoke()` — groups words into `words_per_group=4` chunks.
- Uses `\k{dur_cs}` karaoke tags for highlight sweep.
- Has its own standalone ASS style line (does not use the preset system).
- Does NOT use `line_fx` or `BOUNCE_FX`.
- Falls back to `srt_to_ass_bounce()` if segment-level SRT is detected.
- **No pop-in animation in karaoke mode — only highlight sweep.**

### ASS animation capabilities (currently in use)

| Tag | Where used | What it does |
|---|---|---|
| `\fscx{N}\fscy{N}` | BOUNCE_FX, `_ass_highlight_tags()` | Scale X and Y |
| `\t(t1,t2,\tag)` | BOUNCE_FX | Timed linear animation |
| `\k{N}` | `srt_to_ass_karaoke()` | Karaoke highlight sweep |
| `\pos(x,y)` | Both ASS writers | Position override |
| `\b1\b0` | `_ass_highlight_tags()` | Bold toggle for emphasis |
| `\c&H...&` | `_ass_highlight_tags()` | Color override for emphasis |

**Not in use:** `\fad()`, `\move()`, `\blur`, `\an`, `\fade()`

### Presets and motion state (pre-OQ-1.4)

| Preset | bounce_fx | Animation (word-level) | Animation (segment) |
|---|---|---|---|
| viral | True | 122%→100% / 200ms | None |
| gaming | True | 122%→100% / 200ms | None |
| tiktok_bounce_v1 | True | 122%→100% / 200ms | None |
| viral_bold | True | 122%→100% / 200ms | None |
| bold_cap | True | 122%→100% / 200ms | None |
| story_clean_01 | True | 122%→100% / 200ms | None |
| clean_pro | True | 122%→100% / 200ms | None |
| boxed_caption | False | None | None |
| clean | False | None | None |
| story | False | None | None |

### Emphasis system (pre-OQ-1.4, unchanged in this phase)

- `subtitle_emphasis_pass()` runs on segment-level SRT only. Adds `_HL_OPEN/_HL_CLOSE` markers.
- `_ass_escape_text()` resolves markers via `_ass_highlight_tags()`.
- `_ass_highlight_tags()` returns: US market = `{\b1\fscx112\fscy112\c&H00FFFF&}` open / `{\b0\fscx100\fscy100\c&HFFFFFF&}` close.
- This static 112% scale IS the emphasis pulse — it holds the emphasized word at a higher scale than the 100% baseline of surrounding words.
- `\t()` tags CANNOT be safely added to inline mid-text emphasis tags: they are time-absolute (relative to event start), not position-relative. Adding `\t()` after the emphasis open tag would animate ALL text from that point forward, not just the word. → **Emphasis motion NOT changed in OQ-1.4.**
- Word-level SRT: `subtitle_emphasis_pass()` skips entirely (no per-word context for detection). Emphasis pulse in word-level mode comes from the per-preset bounce differentiation.

---

## 2. Problems Discovered

| # | Problem | Severity |
|---|---|---|
| P1 | Identical 122%/200ms for all 7 bounce presets — no visual identity differentiation | HIGH |
| P2 | 122% is too aggressive for editorial presets (story_clean_01, clean_pro) — overshoot feel | HIGH |
| P3 | 200ms is too slow for fast content (viral/gaming) — motion feels sluggish at word-speed | MEDIUM |
| P4 | Segment-level mode has zero animation — preset.bounce_fx is ignored without highlight_per_word | LOW |
| P5 | No motion at all in karaoke mode (separate path, no line_fx) | INFO (by design) |

---

## 3. Motion Architecture

### Change: Replace `BOUNCE_FX` with `_get_motion_fx(preset_id)`

`BOUNCE_FX` is a module-level constant — used in exactly one place (`build_ass_style_line()` line 631). Replace with:

1. `_PRESET_MOTION_FX: dict[str, str]` — per-preset ASS animation tag strings
2. `_MOTION_FX_DEFAULT: str` — fallback for any preset not in the dict
3. `_get_motion_fx(preset_id: str) -> str` — lookup with fallback

Update line 631:
```python
# Before
line_fx = BOUNCE_FX if (preset.bounce_fx and highlight_per_word) else ""
# After
line_fx = _get_motion_fx(preset.id) if (preset.bounce_fx and highlight_per_word) else ""
```

`BOUNCE_FX` is retained as a backward-compatible module-level export (unchanged value). Nothing external references it, but keeping it avoids import errors.

### Why NOT change the segment-level guard?

The `highlight_per_word` guard on `line_fx` is load-bearing: in segment mode, `line_fx=""` is used intentionally to keep static segment captions. Animating multi-word blocks produces a less polished feel than word-by-word pop-in. Keeping the guard unchanged is the safe path.

### Emphasis pulse implementation

The emphasis pulse is already implemented via `_ass_highlight_tags()` (US: static 112%, JP: 104%). This provides the required "slightly stronger motion" for important words without the ASS `\t()` mid-text timing risks. **No change to emphasis system in OQ-1.4.**

---

## 4. Preset Motion Strategy

### Motion profiles

| Preset | Scale | Duration | Character |
|---|---|---|---|
| viral | 115% → 100% | 140ms | Energetic snap — Anton at large size reads best with faster settle |
| gaming | 115% → 100% | 140ms | Same class — fast-motion content needs instant pop |
| tiktok_bounce_v1 | 112% → 100% | 150ms | Classic TikTok — softer than pre-OQ-1.4 122%, still punchy |
| viral_bold | 112% → 100% | 150ms | Same class as bounce_v1 |
| bold_cap | 112% → 100% | 150ms | Same class |
| story_clean_01 | 108% → 100% | 160ms | Soft micro-pop — Montserrat warmth with gentle entry |
| clean_pro | 106% → 100% | 160ms | Barely-there entry — Inter editorial feel, almost static |
| boxed_caption | — (bounce_fx=False) | — | No motion — box style is static by design |
| clean | — (bounce_fx=False) | — | No motion — editorial, bounce would conflict with tone |
| story | — (bounce_fx=False) | — | No motion — cinematic static feel |

### Comparison with pre-OQ-1.4

| Dimension | Before | After |
|---|---|---|
| Scale range | 122% (all) | 106%–115% (per preset) |
| Duration | 200ms (all) | 140ms–160ms (per preset) |
| Presets differentiated | 0 | 7 |
| Karaoke | Unchanged | Unchanged |
| Segment mode | Unchanged (no animation) | Unchanged |

---

## 5. Compatibility Impact

| Component | Impact |
|---|---|
| OQ-1.2 intelligence (resegment) | None — fires before ASS generation |
| OQ-1.3 font/spacing system | None — styling fields untouched |
| Karaoke path (`srt_to_ass_karaoke`) | None — entirely separate code path |
| Segment-level SRT mode | None — `highlight_per_word=False` guard unchanged |
| `boxed_caption`, `clean`, `story` | None — `bounce_fx=False`, never reached |
| Emphasis pass (`subtitle_emphasis_pass`) | None — fires before ASS, text-level only |
| `BOUNCE_FX` constant | Preserved (unchanged value) — backward-compatible |
| ASS file format | None — same `\fscx\fscy\t()` tags, just different scale/duration values |
| Render pipeline | None — `srt_to_ass_bounce()` signature unchanged |
| Multi-render | None — stateless per-clip transform |
| Scoring | None |

---

## 6. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| New scale/duration values cause libass render error | None | `\fscx\fscy\t()` are proven ASS v4+ tags already in use |
| `_get_motion_fx()` returns empty string | None | `_MOTION_FX_DEFAULT` covers any missing preset_id; `bounce_fx=False` guard prevents reach |
| Karaoke broken by motion change | None | Karaoke path uses no `line_fx` — code path is separate |
| Segment-level mode affected | None | `highlight_per_word=False` guard unchanged |
| Motion too strong (115% viral) | Very Low | 115% is softer than the pre-OQ-1.4 122% — this is a reduction |
| Motion too subtle (106% clean_pro) | Very Low | User-perceptible but deliberate — editorial feel |
| `BOUNCE_FX` external import broken | None | Constant value preserved |

---

## 7. Manual Verification Checklist

```
[ ] viral preset: pop-in more energetic (faster settle at 140ms)
[ ] gaming preset: same snap-pop feel as viral
[ ] tiktok_bounce_v1: classic TikTok pop, slightly softer than before
[ ] viral_bold: same class as bounce_v1
[ ] bold_cap: same class as bounce_v1
[ ] story_clean_01: soft micro-pop visible but gentle (108%)
[ ] clean_pro: barely-perceptible entry (106%), Inter editorial feel
[ ] boxed_caption: no animation (bounce_fx=False — unchanged)
[ ] clean preset: no animation (bounce_fx=False — unchanged)
[ ] story preset: no animation (bounce_fx=False — unchanged)
[ ] Karaoke mode: unaffected — highlight sweep only, no pop animation
[ ] Word-level mode stable: each word pops independently
[ ] Segment mode stable: no animation (highlight_per_word=False guard)
[ ] ASS file valid: open in text editor — \fscx\t() tags formatted correctly
[ ] Multi-render stable: stateless per-clip transform
[ ] No subtitle flicker: timing unchanged, only animation profile changed
[ ] Emphasis words (segment mode): still get 112% static scale from _ass_highlight_tags()
[ ] Log entries unchanged: subtitle_style_resolved still fires correctly
```

---

## 8. Files Modified

| File | Change |
|---|---|
| `backend/app/services/subtitle_engine.py` | Add `_PRESET_MOTION_FX` dict, `_MOTION_FX_DEFAULT`, `_get_motion_fx()`. Update `build_ass_style_line()` line 631. |

---

## 9. Commit Hash

`[pending]`

---

## 10. Push Confirmation

`[pending]`
