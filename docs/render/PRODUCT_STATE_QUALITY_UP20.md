# PRODUCT STATE — QUALITY-UP20: Creator Style DNA

**Branch:** `feature/ai-output-upgrade`
**Commits:** `feat(render): creator style dna` → `fix(render): harden creator dna` (UP20.1)
**Status:** Shipped + Hardened

---

## Summary

Moves from "tool remembers choices" to "tool gently adapts to creator editing identity."
Infers a lightweight editorial DNA from real behavior already tracked in UP12 and UP18.
No new raw signal collection. No ML. No embeddings. No cloud sync.

Nudges are gentle — they fire only after 10+ meaningful actions and only when explicit
creator settings and platform bias both leave room. Manual choice always wins.

---

## Part A — DNA Dimensions

Three dimensions derived from existing UP12 + UP18 preference signals.

### hook_forward (0.0 / 0.5 / 1.0)

| Signal | Source |
|---|---|
| `variantPreference === 'aggressive'` | UP18 variant download EMA |
| `platformPreference === 'tiktok'` | UP18 platform EMA |

Score: count of matching signals / 2. Fires backend nudge at ≥ 0.5 (one signal).

### clean_visual (0.0 / 0.33 / 0.67 / 1.0)

| Signal | Source |
|---|---|
| `variantPreference === 'story_first'` | UP18 variant download EMA |
| `platformPreference === 'instagram_reels'` | UP18 platform EMA |
| `subtitleStyle ∈ {story_clean_01, minimal_clean, clean_karaoke}` | UP12 subtitle EMA |

Score: count of matching signals / 3. Fires backend nudge at ≥ 0.67 (two of three signals).

### narrative_structure (0.0 / 1.0)

Single binary signal: `variantPreference === 'story_first'`. Exposed in DNA context
for future use; no separate backend nudge in UP20.

---

## Part B — Confidence Gate

```
DNA_MIN_ACTIONS = 10
action_count = taste.sessions (UP12) + feedback.sessions (UP18)
```

No DNA nudge fires until `action_count >= 10`. Below that threshold, `confident: false`
and zero nudges are applied. No guessing from sparse data.

---

## Part C — Backend Nudges (Gentle Only)

### Hook bonus in pool sort

When `hook_forward >= 0.5`:
```
_dna_hook_bonus = 3
```

Added to pool sort key alongside platform hook bonus:
```python
int(hook_score × (platform_hook_bonus + dna_hook_bonus) / 100)
```

Magnitude: max ~2.5 pts for a hook_score=84 creator. Platform TikTok gets 6 pts;
DNA adds at most 3 pts on top — or 3 pts alone on non-TikTok platforms.

### Subtitle gentle nudge

When `clean_visual >= 0.67` AND neither variant, creator explicit, nor platform
sub_bias have set a subtitle style:
```python
_dna_sub_bias = {"interview": "clean", "commentary": "story", "vlog": "story",
                 "tutorial": "clean", "montage": "gaming"}
```

Slots into hierarchy below platform sub_bias, above content-type default.

### Decision hierarchy (post-UP20)

```
1. Variant subtitle style (UP13 multi-variant explicit intent)
2. Creator explicit subtitle_style (payload)
3. Platform sub_bias — UP14
4. DNA sub_bias — UP20 (clean_visual ≥ 0.67 only)    ← NEW
5. Content-type default (_CONTENT_TYPE_SUB_DEFAULTS)
6. "tiktok_bounce_v1" fallback
```

---

## Part D — Storage

**`creator_dna_v1`** — localStorage key. Stores last computed snapshot only.
Not a raw signal store — derived from UP12 (`ct_taste_v1`) and UP18 (`cl_feedback_v1`).

```json
{
  "confident": true,
  "action_count": 14,
  "hook_forward": 0.5,
  "clean_visual": 0.67,
  "narrative_structure": 1.0,
  "ts": 1716000000000
}
```

DNA is always recomputed fresh at render submit time from live UP12/UP18 EMAs.
The snapshot is for explainability and audit only.

---

## Part E — Payload Field

`creator_dna: dict = Field(default_factory=dict)` added to `RenderRequest`.

Sent at render submit by `creator-dna.js`. Default empty — old payloads without this
field produce zero DNA effect (`_dna_confident = False`).

---

## Part F — Observability

### Backend log

When DNA fires (`confident AND at least one nudge active`):
```
dna_applied: action_count=14 hook_forward=0.50 hook_bonus=3 clean_visual=0.67 clean_visual_active=True
```

Grep: `dna_applied` in job log to audit DNA nudges.

### Output panel hint

When DNA fired, a subtle italic line appears below the platform banner:
```
Adapted to recent creator style
```

Color: `#64748b` (dim). Font-size: 10px. Only shown when at least one nudge was active.
Not per-clip — one note for the entire render session.

---

## Files Changed

| File | Change |
|---|---|
| `backend/static/js/creator-dna.js` | New module: DNA dimensions, confidence gate, `getDNAContext()`, `getAppliedHint()`, `init()`, `reset()` |
| `backend/app/models/schemas.py` | `creator_dna: dict = Field(default_factory=dict)` in `RenderRequest` |
| `backend/static/index.html` | `<script src="/static/js/creator-dna.js"></script>` after creator-feedback.js |
| `backend/static/js/editor-view.js` | `CreatorDNA.init()` in both `openEditorView` paths; `payload.creator_dna = CreatorDNA.getDNAContext()` at render submit |
| `backend/app/orchestration/render_pipeline.py` | DNA extraction after `_platform_hook_bonus`; sort key now uses `(_platform_hook_bonus + _dna_hook_bonus)`; DNA log block; `_dna_sub_bias_val` tier in subtitle selection |
| `backend/static/js/render-ui.js` | `_jobDNA`, `_dnaFired`, `_dnaHint` before clip list render; `_dnaHint` injected after platform banner |
| `backend/static/css/app.css` | `.clipsDnaHint` style (10px, `#64748b`, italic) |
| `docs/render/PRODUCT_STATE_QUALITY_UP20.md` | This file |

---

## What Was Intentionally Excluded

| Excluded | Reason |
|---|---|
| Independent raw signal tracking in creator-dna.js | DNA derives from UP12+UP18 — no duplicate storage |
| Speed nudges from DNA | Platform handles pacing; DNA adding a second speed delta would compound unpredictably |
| Hook bonus for combined_scoring path | ~~Excluded~~ — **Fixed in UP20.1**: `_provisional_combined()` now applies DNA hook bonus |
| DNA-based max_export_parts override | Creator controls clip count explicitly |
| DNA-driven variant selection weights | Variant formula is purposeful by design; DNA doesn't override it |
| "Reset DNA" UI button | `reset()` exists for programmatic use; UI reset is part of a broader preference panel |
| Per-clip DNA chip | One dim panel note is sufficient — per-clip would be noise |
| LLM-inferred identity | Deterministic derivation only |

---

## Manual QA Checklist

### Default-off guarantee

- [ ] Fresh creator (< 10 actions): `creator_dna_v1` key absent or `confident=false`; no `dna_applied` in log
- [ ] `creator_dna` absent from old payloads: no DNA effect (`_dna_confident=False` branch taken)

### Confidence gate

- [ ] After 10 total renders (UP12 sessions + UP18 sessions): `creator_dna_v1` shows `confident=true`
- [ ] Below 10: `confident=false`, no `dna_applied` log line, no hint in output panel

### Hook-forward creator

- [ ] Simulate: repeatedly download aggressive variant → UP18 `variants.aggressive` grows
- [ ] Set TikTok platform repeatedly → UP18 `platforms.tiktok` grows
- [ ] After confidence gate: log shows `dna_applied … hook_bonus=3`
- [ ] Output pool sort slightly biased toward hook-strong clips (confirm via log segment order)

### Clean-visual creator

- [ ] Simulate: story_first downloads + Instagram + clean subtitle style
- [ ] After 2/3 clean signals + confidence: log shows `clean_visual_active=True`
- [ ] Subtitle style on next render uses "clean"/"story" when platform bias absent

### DNA hint

- [ ] Output panel shows "Adapted to recent creator style" when DNA fired
- [ ] No hint when DNA not confident or no nudge fired
- [ ] Hint appears below platform banner (not above)

### Hierarchy correctness (manual always wins)

- [ ] Creator sets explicit subtitle style → platform and DNA sub_bias both skipped
- [ ] Variant sets subtitle → creator and DNA sub_bias both skipped
- [ ] Platform sub_bias present → DNA sub_bias skipped even if clean_visual active

### Safety

- [ ] No crash when `creator_dna` is `{}` or `null` in payload (default_factory guards)
- [ ] Zero regression: cancel / resume / retry / queue / render speed
- [ ] UP15 cover unaffected by DNA
- [ ] UP16 CTA unaffected by DNA
- [ ] UP13 variant selection formula unaffected by DNA

---

## UP20.1 — Hardening Changes

### Part A — Combined Scoring Alignment (gap closed)

`_provisional_combined()` in the combined scoring path now includes the DNA hook bonus:
```python
return vs * 0.80 + hs * (0.20 + _dna_hook_bonus / 100)
```
`_dna_hook_bonus` is captured via closure. The formula is additive and bounded: for
hook_score=84, dna_hook_bonus=3 → adds 2.52 to the 0-100 combined score (~2.5% nudge).

### Part B — Observability

DNA logging is now always emitted per render, not just when a nudge fires:

| Log event | When emitted | Contents |
|---|---|---|
| `dna_confidence` | Every render | `confident`, `action_count`, all three dimension scores, `suppressed_signals` |
| `dna_applied` | When ≥1 nudge fires | Which nudges: `hook_bonus=3`, `subtitle_clean_bias=active` |
| `dna_suppressed` | Confident but no nudge fires | Dimension values, threshold reason |
| `dna_sub_suppressed` | Per-part when clean_visual suppressed by higher layer | `reason=variant|creator|platform` (debug level) |

### Part C — Overfit Protection

`hook_forward` now has a stricter session gate: `DNA_MIN_HOOK_SESS = 15` (separate from
`DNA_MIN_ACTIONS = 10`). A burst of 2-3 aggressive downloads won't fire the hook bonus
until the creator has 15 total sessions of history. The `clean_visual` dimension requires
2/3 signals simultaneously — already a sufficient multi-signal stability gate at 10 actions.

When `hook_forward` is suppressed by the session gate, `suppressed_signals: ['hook_forward_needs_more_sessions']`
is emitted in the DNA context and logged in `dna_confidence`.

### Part D — Conflict Guard

No structural changes — hierarchy was already correct. Added `dna_sub_suppressed` debug
log per part when `clean_visual` DNA is active but suppressed by a higher subtitle layer.

### Part E — Trust Hint

Hint text changed from "Adapted to recent creator style" → **"Using recent creator style"**.
Applied in both `creator-dna.js` `getAppliedHint()` and `render-ui.js` clip output panel.

---

## Audit Notes

### DNA dimensions are binary-to-sparse

With two signals, `hook_forward` can only be 0.0, 0.5, or 1.0. No continuous EMA of its
own. This is intentional — the DNA does not independently track signals; it reads the
already-decayed UP12/UP18 EMAs. The coarser resolution is acceptable for a "gentle nudge."
