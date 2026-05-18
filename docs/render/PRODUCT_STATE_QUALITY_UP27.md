# PRODUCT STATE — QUALITY-UP27: Creator Asset Intelligence

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): creator asset intelligence`
**Status:** Shipped

---

## Summary

Moves from "tool remembers preferences" to "tool remembers creator identity."

After UP21 (presets), UP26 (steering), and MAP-UI-V3 (workspace), the tool already remembers taste, DNA, preset, and steering decisions. UP27 adds the missing layer: **creator brand assets** — logo, intro sting, outro bumper, music profile, brand subtitle style.

**Creator goal:** "This finally looks like my channel."

---

## Philosophy

- **Local only.** No cloud. No backend storage. No upload. Files stay on creator's machine.
- **Always optional.** Missing asset = graceful skip. Never fails render.
- **Minimal UX.** Five rows in the Advanced panel. No media-library complexity.
- **Preset-linkable.** Asset pack is read at render time from `creator_assets_v1` localStorage. Any preset that fires will carry the active asset pack.

---

## Asset Pack

| Asset | Type | Applied As |
|---|---|---|
| Logo | PNG/JPEG/WebP | Watermark overlay, top-right, 8% of video width, 85% opacity |
| Intro sting | Video clip | Prepended before main clip (after remotion hook intro if active) |
| Outro / bumper | Video clip | Appended after main clip (after CTA if any) |
| Music profile | `clean` \| `soft` \| `energetic` | BGM gain multiplier (0.18 / 0.12 / 0.26) — only when BGM enabled |
| Brand subtitle | Style key | Stronger default subtitle style when `add_subtitle=True` |

---

## Application Order (per clip, post-encode)

1. Encode main clip (unchanged)
2. Prepend remotion hook intro (existing, if `remotion_hook_intro=True`)
3. **Prepend creator intro sting** (UP27, if `asset_intro_path` set)
4. **Append creator outro** (UP27, if `asset_outro_path` set)
5. **Apply logo watermark** (UP27, last — covers full assembled clip including intro/outro)

---

## Safe Fallback Rules

| Condition | Behavior |
|---|---|
| Asset path not set | Silent no-op |
| Asset path set, file missing | `asset_missing_skip` logged, render continues |
| FFmpeg concat fails | `asset_skipped` logged, original clip preserved |
| Logo overlay fails | `asset_skipped` logged, original clip preserved |
| Any Python exception | `asset_error` logged, render continues |

A render **never fails** due to an asset. The asset is always the optional layer.

---

## Files Changed

### `backend/app/services/remotion_adapter.py`
- `append_outro_clip(clip_path, outro_path, output_path)` — concat main clip + outro via FFmpeg
- `apply_logo_watermark(clip_path, logo_path, output_path, *, position, opacity, margin)` — overlay filter with `scale` + `colorchannelmixer` + `overlay`

### `backend/app/models/schemas.py`
- 5 new optional fields on `RenderRequest`:
  - `asset_logo_path: Optional[str]`
  - `asset_intro_path: Optional[str]`
  - `asset_outro_path: Optional[str]`
  - `asset_music_profile: Optional[str]`
  - `asset_brand_subtitle: Optional[str]`

### `backend/app/orchestration/render_pipeline.py`
- Imports `append_outro_clip`, `apply_logo_watermark` from remotion_adapter
- 3 new helper functions: `_maybe_prepend_asset_intro()`, `_maybe_append_asset_outro()`, `_maybe_apply_asset_logo()`
- All called after `_maybe_prepend_remotion_hook_intro()`, before timing calculations
- All emit `asset_applied` / `asset_missing` / `asset_skipped` events

### `backend/static/js/creator-assets.js` (NEW)
- `CreatorAssets` IIFE module
- Storage: `creator_assets_v1` localStorage key
- API: `init`, `setAsset`, `removeAsset`, `getAsset`, `getPayload`, `clear`
- File pickers: `pickLogo()`, `pickIntro()`, `pickOutro()` — use `<input type="file">`, read `file.path` (Electron) or `file.name` (browser fallback)
- `setMusicProfile(val)`, `setBrandSubtitle(val)` — dropdown handlers
- `_refresh()` — updates DOM labels + calls `v3RefreshSteeringPanel()`

### `backend/static/js/editor-view.js`
- `openEditorView` / `openEditorView_withSession`: `CreatorAssets.init()`
- `startRenderFromEditor()`: inject asset payload, apply music profile BGM gain adjustment, apply brand subtitle as stronger default
- `v3RefreshSteeringPanel()`: added 5 asset chip types (Logo, Intro, Outro, Music, Brand sub)

### `backend/static/js/batch-queue.js`
- `_buildPayload()`: spreads `CreatorAssets.getPayload()` into payload

### `backend/static/js/render-ui.js`
- Trust bar: adds 4 asset chips from job payload (Logo, Intro, Outro, Brand sub)

### `backend/static/index.html`
- Creator Assets panel added inside `qsAdvBody` (after Subtitle Size)
- 5 rows: Logo (Choose/Remove), Intro (Choose/Remove), Outro (Choose/Remove), Music dropdown, Brand Sub dropdown
- `<script src="/static/js/creator-assets.js"></script>` added after clip-steering.js

### `backend/static/css/app.css`
- `.v3AssetPanel`, `.v3AssetPanelTitle`, `.v3AssetRow`, `.v3AssetLabel`, `.v3AssetPath`, `.v3AssetSet`
- `.v3AssetBtn`, `.v3AssetRemoveBtn`
- `.v3ChipAsset` (steering panel), `.v3TrustAsset` (trust bar)

---

## Observability Events

| Event | When | Level |
|---|---|---|
| `asset_applied` | Asset successfully applied to part | INFO |
| `asset_missing` | Path set but file not found | WARNING |
| `asset_skipped` | File found but concat/overlay failed | WARNING |
| `asset_error` | Unexpected Python exception | WARNING |

---

## What Was Intentionally NOT Changed

| Not changed | Reason |
|---|---|
| `reup_bgm_path` path resolution | Music profile only adjusts gain, never sets a new file |
| `_maybe_prepend_remotion_hook_intro` | Creator intro sting is independent — both can coexist |
| Subtitle style selection logic | Brand subtitle is a stronger default; editor form value wins if manually changed |
| Any render engine encode path | Assets are all post-encode operations |
| Cancel / retry / batch queue lifecycle | Untouched |
| Any existing schema validators | Only new optional fields added |

---

## Preset ↔ Asset Pack Relationship

Presets (UP21) store: platform, subtitle style, CTA, render profile, etc.

Asset pack (UP27) stores: logo path, intro path, outro path, music profile, brand subtitle.

When a preset is applied, `CreatorAssets.init()` has already run and loaded the asset pack from localStorage. Both are included in the render payload independently. A preset does NOT own or copy an asset pack — they coexist and complement each other.

Creator workflow: set up asset pack once → apply any preset → render → asset pack applies automatically.

---

## Manual QA Checklist

### A — Logo watermark: file present
- [ ] Set a PNG logo via Creator Assets > Logo > Choose
- [ ] Render → output clip has logo watermark in top-right corner
- [ ] Watermark is subtle (85% opacity, 8% video width)
- [ ] Log: `asset_applied type=logo`

### B — Logo watermark: file missing
- [ ] Set logo path in localStorage manually to a non-existent path
- [ ] Render → completes successfully without watermark
- [ ] Log: `asset_missing_skip type=logo`
- [ ] No render failure, no error modal

### C — Intro sting prepend
- [ ] Set a short video clip as Intro sting
- [ ] Render → output clip has intro prepended before main content
- [ ] Log: `asset_applied type=intro`

### D — Outro append
- [ ] Set a short clip as Outro
- [ ] Render → output clip has outro appended after main content
- [ ] Log: `asset_applied type=outro`

### E — Music profile: energetic
- [ ] Enable BGM, set Music Profile = Energetic
- [ ] BGM audibly louder than default (gain 0.26 vs 0.18)

### F — Brand subtitle style
- [ ] Set Brand Sub = Viral
- [ ] Render with subtitles enabled → subtitle style is tiktok_bounce_v1
- [ ] Trust bar shows "Brand sub" chip

### G — Steering panel shows asset chips
- [ ] Set logo + intro → steering panel shows 🖼 Logo and ▶ Intro chips
- [ ] Remove logo → chip disappears immediately (no reload)

### H — Batch queue carries assets
- [ ] Add 3 files to batch queue, logo is set
- [ ] All 3 rendered clips have logo watermark

### I — Preset + asset coexist
- [ ] Apply "TikTok Fast" preset, set logo separately
- [ ] Render → TikTok Fast settings apply AND logo watermark appears
- [ ] Trust bar shows both preset and asset chips

### J — No render regression
- [ ] Normal render with no assets set → identical output to pre-UP27
- [ ] No asset chips in trust bar
- [ ] No asset log lines

### K — No crash on corrupt image
- [ ] Set logo path to a non-image file (e.g., .txt)
- [ ] Render → `asset_skipped` logged, render completes normally
