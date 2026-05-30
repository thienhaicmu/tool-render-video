# Subtitle Overhaul + Groq AI Clip Selection Fix

**Date:** 2026-05-30  
**Branch:** `restructure/output-timeline-architecture`  
**Risk tier:** MEDIUM (frontend + subtitle styles) + LOW (type alignment)  
**Build baseline:** 7549 passed, 0 TS errors (held through all changes)

---

## What Was Done

### 1 — Feature router L0–L9 pipeline shim files

Created `backend/app/features/renderer/pipeline/` shim layer (L0–L9):

| File | Layer | Role |
|------|-------|------|
| `source.py` | L0 | Local-only source validation docs |
| `scene_analysis.py` | L1 | Re-exports from `pipeline_pre_render` |
| `ai_analysis.py` | L2 | Imports `AIDirector` from `ai_director` |
| `transcription.py` | L3 | Whisper layer docs |
| `ai_refinement.py` | L4 | Re-exports from `pipeline_ai_phases` |
| `render_loop.py` | L5 | Re-exports from `pipeline_render_loop` |
| `part_renderer.py` | L6 | Re-exports from `stages.part_renderer` |
| `qa.py` | L7 | Re-exports from `qa_pipeline` |
| `ranking.py` | L8 | Re-exports from `pipeline_ranking` |
| `finalizer.py` | L9 | result_json + cleanup docs |

All shims are thin re-exports or documentation stubs. None alter runtime behaviour.

`backend/app/main.py` updated: import source changed from `routes.platform_downloader` → `features.downloader.router`.

---

### 2 — TypeScript type alignment with backend contracts

**`frontend/src/types/api.ts`:**
- `source_mode: 'youtube' | 'local'` → `'local'` only (YouTube removed from this build)
- Removed `youtube_urls?: string[]`
- `JobPartStatus` corrected: removed `'downloading'`, `'cancelled'`; added `'queued'`, `'skipped'`

**Downstream fixes:** `SourceHero.tsx`, `StudioScreen.tsx`, `PlanStep.tsx` all narrowed to `'local'`.  
`OutputClipGallery.tsx`: `status === 'cancelled'` → `status === 'skipped'`.

---

### 3 — Subtitle font-size bug fix (`styles.py`)

**Bug:** `_compute_subtitle_scale` used `min(play_res_x, play_res_y)` as the base dimension.  
For a 9:16 (1080×1920) video this produced `base = 1080`, yielding ~54px font — visually tiny.

**Fix:** Changed to `max(1, int(play_res_y))` so the base tracks the longer dimension.  
Result: `play_res_y = 1920` → ~96px font (5% of frame height, matching TikTok convention).

Same fix applied to `build_ass_style_line` `heavy_scale` path.  
Font size cap raised from 120 → 200 to accommodate large-display presets.

---

### 4 — Six new CapCut-style subtitle presets

Added to `backend/app/services/subtitles/styles.py` and exposed in `StepConfigure.tsx`:

| Preset key | Style |
|------------|-------|
| `neon_glow` | White + cyan outline + purple shadow, Bungee, pop-in bounce |
| `fire_bold` | Yellow + orange-red outline, Anton, snap-fast motion |
| `color_pop` | Yellow + thick black outline, Bungee, energetic scale |
| `dark_card` | White on opaque dark box (BorderStyle=3), Montserrat |
| `slay_soft` | White + hot-pink outline + shadow, Bungee, editorial ease |
| `bold_stroke` | White + 8px black outline, Anton, no shadow |

Aliases added: `pro_karaoke` → `tiktok_bounce_v1`, `slay_soft_01` → `slay_soft`, `boxed` → `dark_card`.

`auto_scale=True` enabled for `tiktok_bounce_v1` and `story_clean_01`.

---

### 5 — Real FFmpeg/libass subtitle preview in StepConfigure

`SubStyleCard` component rewired to call `GET /api/render/subtitle-preview?style=&aspect_ratio=9:16&font_size=0&text=AI+Clip`.  
Returns a server-rendered PNG (libass, cached 1 h). Falls back to CSS approximation on error.

Font size slider: `min=0` (0 = Auto from backend formula), `max=200`, `step=8`.  
Default font size changed from 72 → 0 (auto) in `RenderWorkflow.tsx`.

---

### 6 — Groq AI clip selection auto-enable (root-cause fix)

**Root cause:** Phase 44 in `pipeline_ai_phases.py` is gated on `ai_content_driven_selection=True`.  
This field defaulted to `False` in `RenderRequest` (correct by Contract 2).  
Frontend `aiContentDriven` also defaulted to `false` and required explicit user toggle.  
Result: Groq was called for enrichment (+15 soft bonus) but never performed actual clip override.

**Fix — `RenderWorkflow.tsx` payload:**
```typescript
// Before
ai_content_driven_selection: cfg.aiEnabled && cfg.aiContentDriven || undefined,

// After — auto-enables when cloud provider is configured with a key
ai_content_driven_selection: cfg.aiEnabled && (
  cfg.aiContentDriven ||
  (cfg.aiAnalysisMode !== 'local' && !!cfg.aiCloudApiKey)
) || undefined,
```

**Fix — `StepConfigure.tsx` UX triggers:**
- Switching analyzer mode to `cloud` or `hybrid` while a key exists → auto-checks "AI selects clips" toggle
- Typing an API key → auto-checks toggle immediately

**Effect:** With Groq selected and `gsk_...` key present, Phase 44 now runs; Groq overrides heuristic clip ranking with semantic LLM selection.

---

## Contracts Preserved

- `result_json` backward-compat aliases: not touched
- `RenderRequest` new fields: no new fields added; existing `ai_content_driven_selection` default `False` unchanged
- WebSocket event shape: not touched
- Stage/part transition names: not touched
- `qa_pipeline.py`: not touched
- `data/app.db`: not touched

## Known Issue (not fixed here)

Groq API enrichment adds `+15` soft points to heuristic scorer even when `ai_content_driven_selection=False`.  
This is acceptable — enrichment improves ranking signal without overriding clip boundaries.  
The complete Phase 44 override path is now correctly activated by the fix in item 6 above.
