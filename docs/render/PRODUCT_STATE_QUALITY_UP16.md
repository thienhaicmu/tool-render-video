# PRODUCT STATE — QUALITY-UP16: CTA / Series Intelligence

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): tasteful CTA intelligence`
**Status:** Shipped

---

## Summary

Adds an optional subtitle end card — a single neutral line appended to the last
subtitle block after the main content ends. Default OFF. Creator must explicitly
check "Add ending CTA" in the editor. No silent injection. No cringe. No emojis.

No LLM. No templates that override creator intent. The text is deterministic,
content-type-aware, and platform-aware. Creator is always in control.

---

## Part A — CTA Text Library

`_CTA_TEXTS` is a module-level dict keyed by `content_type_hint` → CTA type → list
of options. Six content types × three CTA types.

### CTA Types

| Type | Description |
|---|---|
| `comment` | Invites viewer response ("Thoughts?", "Agree or disagree?") |
| `part_2` | Series continuation hint ("Want part 2? Let me know.") |
| `follow` | Soft follow ask ("Follow for more.", "More tips coming.") |
| `auto` | Picks the best type by content — resolved at render time |

### Auto-type mapping

| Content type | Auto CTA type | Rationale |
|---|---|---|
| tutorial | part_2 | Tutorial creators often have follow-up content |
| commentary | comment | Commentary invites debate and reaction |
| vlog | comment | Vlog viewers engage through comments |
| interview | comment | Interview viewers want to add their take |
| montage | follow | Montage = highlight reel, follow for more |
| gaming | follow | Gaming clips — follow for next session |

### Variant-aware auto-type *(HARDENING1)*

When `cta_type=auto` and multi-variant is active, variant intent overrides the
content-type mapping above. Creator's explicit `cta_type` choice always wins.

| Variant | Auto CTA type override | Rationale |
|---|---|---|
| `aggressive` | `comment` (always) | Hook-forward → drive engagement; content-type auto is ignored |
| `story_first` | `follow` (always) | Payoff ending → soft natural close; content-type auto is ignored |
| `balanced` | Content-type auto mapping | No override — uses table above |

### Platform and variant text selection

TikTok or aggressive variant: shorter option (index 1) when available.
All other platform/variant combinations: index 0.

---

## Part B — `_select_cta_text()` Pure Function

Zero I/O. Zero randomness. Deterministic for same inputs.

```
_select_cta_text(content_type, target_platform, cta_type) → str
```

Resolves `auto` cta_type → actual type using `_CTA_AUTO_TYPE`.
Falls back to `follow` for unknown types. Falls back to `_CTA_TEXTS["vlog"]`
for unknown content types.

---

## Part C — `_append_cta_block_to_srt()` SRT Injection

Reads the existing SRT, appends one block at the end, writes it back.
Uses `parse_srt_blocks()` / `write_srt_blocks()` — same round-trip functions
used by the emphasis pass.

### Timing logic

```
cta_start = max(last_sub_end + 0.3s,  clip_end - 3.0s)
cta_end   = min(cta_start + 2.5s,     clip_end - 0.1s)
```

- Never starts less than 0.3s after the last subtitle
- Fits within the last 3 seconds of the clip
- Duration capped at 2.5 seconds
- Returns False (no-op) if timing math would create an invalid block

The caller uses `_eff_dur = seg["duration"] / playback_speed - 0.5s` as the
effective clip end — accounts for speed without overrunning.

---

## Part D — Injection Point in `_process_one_part()`

CTA is appended **after the emphasis pass** and **before ASS conversion**.

```
... subtitle_emphasis_pass ...
except Exception:                          ← end of emphasis except block
    _job_log(... "emphasis pass skipped" ...)

# ← UP16 CTA block goes here

if needs_ass:                              ← ASS conversion trigger
    srt_to_ass_bounce / srt_to_ass_karaoke(...)
```

This ordering is critical:
- AFTER emphasis: CTA text is not reformatted or annotated by the emphasis pass
- BEFORE ASS conversion: CTA block is included in the final encoded subtitle track

When CTA is appended, `needs_ass = True` is set to force ASS regeneration.

---

## Part E — Safety and Default-Off Guarantee

- `cta_enabled` defaults to `False` in `RenderRequest` — no CTA without explicit opt-in
- CTA block is wrapped in `try/except Exception` — failure logs a warning; render continues
- `_append_cta_block_to_srt()` returns False silently for short clips or timing edge cases
- `cta_appended` event NOT emitted on failure
- Zero regression on: cancel / resume / retry / render speed / existing subtitle flow

---

## Part F — Output Signals

### Render event

```
event: cta_appended
context: {
  part_no: 1,
  cta_text: "Want part 2? Let me know.",
  cta_type: "part_2",
  content_type: "tutorial",
  target_platform: "youtube_shorts",
  last_sub_end: 28.4
}
```

### Segment dict and ranking entry

`seg["cta_applied"] = True` and `seg["cta_text"] = "..."` are set on success.
These propagate to `_rank_entry["cta_applied"]` and `_rank_entry["cta_text"]`
in the ranking loop.

### Clip card chip

When `rk.ctaApplied` is true, a small `clipCardCtaChip` chip appears in the
clip card body below the variant badge. Hover shows the exact CTA text.
Color: purple-tinted to distinguish from score/variant indicators.

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/orchestration/render_pipeline.py` | `_CTA_TEXTS`, `_CTA_AUTO_TYPE`, `_select_cta_text()`, `_append_cta_block_to_srt()` (module level); CTA injection block in `_process_one_part()`; `cta_applied`/`cta_text` in ranking loop |
| `backend/app/models/schemas.py` | `cta_enabled: bool = False` and `cta_type: str = "auto"` in `RenderRequest` |
| `backend/static/index.html` | "Add ending CTA" checkbox + CTA type dropdown (hidden until checkbox enabled) |
| `backend/static/js/editor-view.js` | `payload.cta_enabled` and `payload.cta_type` at render submit |
| `backend/static/js/render-ui.js` | `ctaApplied`/`ctaText` in `_rankMap`; `clipCardCtaChip` chip in clip card body |
| `backend/static/css/app.css` | `.clipCardCtaChip` style (10px, purple-tinted) |
| `docs/render/PRODUCT_STATE_QUALITY_UP16.md` | This file |

---

## What Was Intentionally Excluded

| Excluded | Reason |
|---|---|
| CTA for re-up mode | Re-up clips have different semantics — deferred |
| Multiple CTA lines / CTA overlay | One line only — anything more is spam |
| Emoji in CTA text | Explicitly excluded — neutral text only |
| LLM-generated CTA | No LLM anywhere in this pipeline |
| Forced CTA (always-on) | Default OFF is a product guarantee, not a toggle |
| Creator-editable CTA text | Custom text = separate UX feature; library covers all practical cases |
| CTA for non-subtitle renders | CTA requires an SRT file to exist — guard is `_ass_srt_source.exists()` |

---

## Manual QA Checklist

### Default-off guarantee

- [ ] Fresh render with no changes: no CTA block in subtitle, no chip in clip card
- [ ] `cta_enabled` absent from old requests: no CTA injected (schema default=False)

### CTA enabled flow

- [ ] Check "Add ending CTA" checkbox: `evCtaTypeWrap` shows below
- [ ] Type dropdown: Auto / Comment prompt / Series Part 2 / Follow
- [ ] After render: log shows `cta_appended` event with `cta_text`, `content_type`, `platform`
- [ ] Clip card shows purple CTA chip with text (`CTA · Want part 2? Let me know.`)
- [ ] Hover chip: tooltip shows the exact CTA text

### Content-type auto selection

- [ ] Tutorial + auto → part_2 text
- [ ] Commentary + auto → comment text  
- [ ] Vlog + auto → comment text
- [ ] Gaming + auto → follow text

### Platform text selection

- [ ] TikTok + auto + tutorial → shorter option from list
- [ ] YouTube Shorts → first option from list

### Timing

- [ ] CTA subtitle block appears in last ~3s of the clip (open SRT to verify)
- [ ] Very short clip (< 5s): CTA skipped silently, render completes, no chip

### Safety

- [ ] CTA failure (corrupted SRT, filesystem error): warning logged, render succeeds
- [ ] `cta_appended` NOT emitted when append returned False
- [ ] Zero regression: cancel / resume / retry / queue / render speed / cover extraction
- [ ] UP15 cover file unaffected by CTA
- [ ] UP18 variant/platform preference unaffected by CTA
