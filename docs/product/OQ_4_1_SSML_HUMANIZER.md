# OQ-4.1 — Edge-TTS SSML Humanizer
## Human Narration Pacing

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** NARRATION DELIVERY ONLY — no XTTS changes, no subtitle changes, no render changes

---

## 1. Audit Findings

### Current narration pipeline (pre-OQ-4.1)

**File:** `backend/app/services/tts_service.py`

**Text preprocessing chain:**
```
Input text
  → humanize_narration_text(text, pause_style)        # existing
      - splits on sentence boundaries
      - breaks long sentences at conjunctions (comma insert)
      - converts "Label: text" → "Label... text" (deliberate)
      - adds "!..." after short strong declarations
  → edge_tts.Communicate(humanized_text, voice_id, rate=rate)
```

**Problem:** Edge-TTS neural voices interpret `...` and `,` but ALL prosody control is implicit. No explicit pause durations, no emphasis signals, no hook breathing. Delivery feels flat/robotic because:
- All sentence gaps are the same length (engine default ~200ms)
- No dramatic pauses before hook questions
- No emphasis on key words
- No colon pauses ("Here's the problem: it's too slow")
- No breath-point between topic transitions

### SSML support in Edge-TTS

`edge_tts.Communicate(text, voice_id)` inserts `text` directly into the SSML body it sends to Azure TTS, WITHOUT HTML-escaping. SSML elements in the text are passed through to the Azure TTS API.

Supported elements (all Microsoft Neural voices):
- `<break time='Xms'/>` — explicit pause of X milliseconds
- `<emphasis level='strong|moderate|reduced'>word</emphasis>` — prosody emphasis
- `<prosody rate='X%' pitch='+Xst'>text</prosody>` — nested prosody override

This means: embedding `<break time='300ms'/>` in the text produces a 300ms pause in the generated audio.

### Vietnamese / non-English safety

All Microsoft Neural voices (including `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`) support `<break>` tags. `<emphasis>` and ALL-CAPS detection are English-only. Vietnamese and Japanese receive breaks-only (conservative subset).

---

## 2. Design

### Rule-based SSML humanizer (no API calls)

The "SSML humanizer" is a rule-based text processor. No Claude API calls — zero latency, zero cost, offline-safe. Rules produce professional-quality pacing equivalent to a human creator's natural delivery.

### Pause profiles (`_SSML_BREAK_MS`)

| Type | light | normal | deliberate |
|---|---|---|---|
| Colon pause (`:`) | 100ms | 250ms | 400ms |
| Ellipsis (`...`) | 200ms | 350ms | 500ms |
| Inter-sentence | 0ms | 150ms | 200ms |
| After `?` | 100ms | 200ms | 300ms |
| After `!` | 0ms | 150ms | 200ms |
| Hook lead-in | 0ms | 100ms | 150ms |

### Transformation rules (in order)

1. **Ellipsis** → `<break time='Xms'/>` (dramatic pause — must process before colon)
2. **Colon** → `:<break time='Xms'/> ` (introduces explanation / list)
3. **ALL CAPS emphasis** (English only) → `<emphasis level='strong'>WORD</emphasis>`
4. **Hook lead-in** (English, `i > 0`) → `<break time='Xms'/>` before sentence starting with hook words (but, wait, so, now, here, then, remember, think, imagine)
5. **Inter-sentence break** → `<break time='Xms'/>` after `?`, `!`, or period based on pause_style

### Content-type mapping (unchanged)

| Content type | Pause style |
|---|---|
| commentary, gaming, montage | light |
| vlog, story | normal |
| tutorial, interview | deliberate |

### Fallback chain

```
ssml_humanize_for_edge(text, pause_style, language)
  → SSML_HUMANIZER_ENABLED=0  → humanize_narration_text() (existing)
  → any exception             → humanize_narration_text() (existing)
  → empty result              → humanize_narration_text() (existing)
  → success                   → SSML fragment
```

The fallback is the existing `humanize_narration_text()` — no regression from baseline.

---

## 3. Implementation

### `_build_ssml_content(text, pause_style, language)` — private

- Splits text on sentence boundaries (`_SENTENCE_END_RE`)
- HTML-escapes each sentence's text content (`html.escape()`) so `&`, `<`, `>` in user text don't break SSML
- Applies 5 transformation rules in order
- Joins sentences with inter-sentence break tags

### `ssml_humanize_for_edge(text, pause_style, language)` — public

- `SSML_HUMANIZER_ENABLED=0` → returns `humanize_narration_text(text, pause_style)`
- Calls `_build_ssml_content()` wrapped in try/except
- Any failure → returns `humanize_narration_text(text, pause_style)`

### `generate_narration_mp3()` — modified call site

Before:
```python
_humanized = humanize_narration_text(clean_text, pause_style=_ct_profile["pause_style"])
```

After:
```python
_humanized = ssml_humanize_for_edge(
    clean_text,
    pause_style=_ct_profile["pause_style"],
    language=language,
)
```

XTTS path in `generate_narration_audio()` → **unchanged** — still calls `humanize_narration_text()` directly (XTTS doesn't use SSML).

---

## 4. Example Output

Input (tutorial):
```
Here's the problem: most creators quit too early. But why? Because results take time. And time feels like failure.
```

SSML output (deliberate):
```
Here's the problem:<break time='400ms'/> most creators quit too early. <break time='200ms'/> <break time='150ms'/> But why? <break time='300ms'/> Because results take time. <break time='200ms'/> <break time='150ms'/> And time feels like failure.
```

vs. plain text (existing):
```
Here's the problem... most creators quit too early. But why? Because results take time. And time feels like failure.
```

---

## 5. Compatibility Impact

| Component | Impact |
|---|---|
| `generate_narration_mp3()` — Edge-TTS path | `humanize_narration_text()` → `ssml_humanize_for_edge()` |
| `generate_narration_audio()` — XTTS path | **Unchanged** — still calls `humanize_narration_text()` |
| `humanize_narration_text()` | Preserved as fallback — unchanged |
| Edge-TTS voice profiles (all languages) | All Microsoft Neural voices support `<break>` |
| Vietnamese narration | `<break>` only — no emphasis/caps; safe |
| Japanese narration | `<break>` only — no emphasis/caps; safe |
| Render pipeline | Unchanged |
| Subtitle timing | Narration is free-running; no subtitle sync affected |
| `SSML_HUMANIZER_ENABLED=0` | Full fallback to pre-OQ-4.1 behavior |

---

## 6. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| SSML tags corrupt TTS output | None | Fallback wraps all exceptions; `humanize_narration_text()` as safety net |
| HTML-escaped `&amp;` read aloud | None | Azure TTS normalizes `&amp;` → silent in speech |
| Break tags add too much silence | Low | Conservative break times; `SSML_HUMANIZER_ENABLED=0` to disable |
| Vietnamese voice rejects SSML | None | Only `<break>` used; universally supported; fallback on exception |
| XTTS narration regresses | None | XTTS path uses `humanize_narration_text()` — no change |

---

## 7. Manual Verification Checklist

```
[ ] English tutorial: colon pauses heard, deliberate pacing
[ ] English vlog: natural inter-sentence breathing
[ ] English commentary: fast with minimal extra breaks
[ ] Hook sentences (But why? / Wait.) get lead-in beat
[ ] ALL CAPS words (AMAZING, WAIT) have emphasis
[ ] Vietnamese: no crash, natural pacing, no broken audio
[ ] SSML_HUMANIZER_ENABLED=0: reverts to plain-text humanization
[ ] XTTS path: unchanged, same humanize_narration_text behavior
[ ] Render stable: full pipeline completes without error
```

---

## 8. Files Modified

| File | Change |
|---|---|
| `backend/app/services/tts_service.py` | Add `_SSML_BREAK_MS`, `_build_ssml_content()`, `ssml_humanize_for_edge()`; update `generate_narration_mp3()` call |

---

## 9. Commit Hash

`[pending]`

---

## 10. Push Confirmation

`[pending]`
