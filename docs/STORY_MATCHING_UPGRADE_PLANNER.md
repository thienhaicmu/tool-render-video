# Planner — Story Mode AI-plan Matching Upgrade + Workflow + UI

> Status: **PROPOSED — awaiting approval.** No code changed by this doc.
> Author pass: 2026-07-11. Scope: make the AI plan drive asset matching across ALL of
> Story Mode, fix the dead per-beat emotion path, tidy the offline-art workflow, and
> surface/override it in the UI. Grounded in a code read of the v2 planning chain
> (prompt → parser → domain → director → pipeline) + the FE story-studio.

Related: [[project-svg-asset-system]] · `docs/AI_INTEGRATION.md` ·
`docs/SVG_ASSET_SYSTEM_PLAN.md` · `STORY_ROADMAP.md` (SVG row).

---

## 0. Why (the gap)

Story Mode now has **569 offline assets** + a strong fuzzy matcher (`best_asset`,
description-scored, scope-widening) + a reproducible generator. But the **AI plan does
not actually drive matching** in the default configuration:

1. **Per-beat `emotion` is dead.** The domain parses `beat.emotion`
   ([story_plan_v2.py:608](../backend/app/domain/story_plan_v2.py#L608)), `build_cues`
   carries it into the cue ([:396](../backend/app/domain/story_plan_v2.py#L396)), and the
   N4 overlay render consumes it — but the **super-prompt schema has no `emotion`
   field** ([story_prompts_v2.py:90-107](../backend/app/features/render/ai/llm/story_prompts_v2.py#L90-L107)),
   only `pose` (added in s7). So every beat renders the neutral face.
2. **Controlled vocab under-taught.** The schema gives ~6 example tokens each for
   `archetype` / `scene_kind`. The code now knows **56 archetypes**
   (`svg_presets._ARCH`) and **~30 canonical scene kinds** (`svg_scene._SCENES`). The AI
   emits free tokens that often don't align with slug tokens → fuzzy match misses.
3. **Library-pick is OFF by default.** `STORY_LIBRARY_PICK=0`
   ([story_pipeline_v2.py:129](../backend/app/features/render/engine/pipeline/story_pipeline_v2.py#L129))
   → the catalog is never injected → the AI never emits `asset` slugs → the single
   strongest matching signal is unused. This is exactly the original intent ("AI plan
   quyết định dùng hình từ kho") sitting behind a default-off flag.

Everything else in the planning chain is sound (INV1-8 enforcement, repair pass,
long-chapter split, canon injection, deterministic cue sheet). This plan does **not**
touch those.

---

## 1. Sacred-contract pre-clearance

| Contract | Impact | Verdict |
|---|---|---|
| #2 RenderRequest defaults | `story_image_provider` default STAYS `gpt_image`. All new behaviour is gated by ENV (`STORY_LIBRARY_PICK` etc.), not a RenderRequest field. Stored-job replay is bit-identical. | ✅ unaffected |
| #3 AI returns None / never raises | prompt/parser/matching stay defensive; no new raise paths. | ✅ |
| #4/#5 stage/part names | untouched. | ✅ |
| #6 `_emit_render_event` | untouched. | ✅ |
| #8 qa_pipeline | untouched. | ✅ |
| Frozen wire (`/api/render/process`) | `emotion` already exists on the internal `Beat`; no wire field added (StoryPlan travels in `render_plan_json`, not the RenderRequest wire surface). | ✅ |

Prompt-version bump: `SUPER_PROMPT_VERSION` s7 → **s8** (pins `test_super_prompt_v2.py`
+ `test_story_bgm.py` version asserts — update in the same commit).

---

## 2. Phase P1 — Prompt: emotion + controlled vocab  **(HIGH tier)**

**Goal:** fix the dead `emotion` path and teach the matching vocabulary, so the AI plan
aligns with the library + procedural presets even before library-pick is on.

**Files**
- `backend/app/features/render/ai/llm/story_prompts_v2.py` (HIGH — prompt templates)
- `backend/app/domain/story_plan_v2.py` (LOW — add `EMOTION` tuple + `_norm` the field)
- Tests: `test_super_prompt_v2.py`, `test_story_plan_v2.py`, `test_story_bgm.py`
  (version asserts).

**Changes**
1. **Schema** — add to each timeline beat object (after `motion`, mirroring `pose`):
   ```
   "emotion": "normal|happy|angry|sad|surprised",
   ```
2. **Rule 10** (currently pose) — extend: `emotion = the speaker's feeling THIS beat …
   use normal unless the beat's tone clearly calls for one`. Keep pose text as-is.
3. **Vocab hints** — inside the schema comments for `archetype` / `scene_kind`, replace
   the ~6 ad-hoc examples with the **canonical token list, derived from code** (a new
   `_VOCAB` helper in prompts that imports the keys, so it never drifts):
   - archetype ∈ `svg_presets._ARCH` keys (56) — rendered as a compact `pick the
     closest, else ""` line.
   - scene_kind ∈ a **canonical subset** of `svg_scene._SCENES` (drop pure aliases:
     keep e.g. `cafe, classroom, forest, mountain, throne_room, bedroom, living_room,
     kitchen, garden, park, street, castle, temple, shrine, inn, market, library,
     battlefield, cave, beach, snow, desert, rooftop, office, hospital, graveyard,
     ruins, waterfall, courtyard`).
   - Keep the "leave '' when unsure (never invent)" guard (Rule 12).
   > **Source-of-truth rule:** the vocab strings are IMPORTED from `svg_presets` /
   > `svg_scene` at prompt-build time (not hand-copied), so adding an archetype/scene in
   > code auto-updates the prompt. A unit test asserts the prompt contains a sample of
   > each vocab so drift is caught.
4. **Domain** — add `EMOTION = ("normal","happy","angry","sad","surprised")` and change
   `_beat_from` / cue parse to `_norm(x.get("emotion"), EMOTION, "normal")` (fixes A4;
   still back-compat — unknown → "normal"). `svg_char.emotion_expr` already maps these.

**Risk / blast radius:** HIGH (prompt is consumed by every plan). But additive: a beat
with no `emotion` → "normal" (today's behaviour). Format-safety unchanged (vocab is a
controlled constant, concatenated not `.format`'d).

**Tests**
- `test_super_prompt_v2.py`: assert `"emotion"` in schema; assert a sample archetype
  (`swordsman`) + scene (`temple`) + emotion vocab present; bump version to `s8`.
- `test_story_plan_v2.py`: a beat with `emotion:"angry"` round-trips; unknown → normal.
- Full pytest before/after (baseline 3021).

**Rollback:** revert the single prompt commit; parser `EMOTION` norm is inert without
the schema field.

**Acceptance:** a real idea render (svg + `STORY_CHAR_OVERLAY=1`) shows the speaker's
face changing emotion per beat driven by the AI (not just pose).

---

## 3. Phase P2 — Workflow: library-pick default + catalog cache + flag unification  **(MED tier)**

**Goal:** turn matching ON coherently for the offline-art path; cut per-plan DB cost;
reduce the 4-flag footgun.

**Files**
- `backend/app/features/render/engine/pipeline/story_pipeline_v2.py` (MED)
- `backend/app/db/story_asset_repo.py` (MED — cache)
- `backend/app/core/config.py` (LOW — default/env)
- Tests: `test_story_library_catalog.py`, `test_story_generate_images_v2.py`,
  `test_run_story_v2_e2e.py`.

**Changes**
1. **B3 — library-pick default on.** Flip the gate so the catalog is injected when the
   render will use offline art. Two options (pick in review):
   - (a) **Provider-driven (recommended):** build the catalog when
     `story_image_provider == "svg"` OR `STORY_LIBRARY_PICK=1`. Keeps gpt-image renders
     byte-identical; turns matching on exactly for the FE default (svg).
   - (b) **Env default flip:** `STORY_LIBRARY_PICK` default `"1"`. Simpler but changes
     gpt-image planning too (bigger prompt) — less surgical.
2. **C1 — catalog cache.** `build_library_catalog()` currently scans `list_assets` (DB)
   every call. Add a process cache keyed by `(region, genre, asset_count)` (cheap
   `SELECT COUNT(*)`), invalidated when the count changes (scan adds assets). Bounds a
   long batch to one catalog build.
3. **Catalog size guard.** With 569 assets the character catalog is ~150 base families.
   Add a `cap` (already a param) default sized to keep the block ≲ ~120 lines; when
   `region`/`genre` are known upstream (FE genre pick) pass them to scope the catalog.
4. **C2 — flag unification (docs + thin shim).** Introduce ONE `STORY_OFFLINE_ART`
   umbrella (or document the coherent set) that implies `LIBRARY_PICK` + `SVG_GEN`
   sensible defaults; keep the individual flags as overrides. No behaviour removed.
5. **C3 — svg draft preview.** In `PlanReview`, when `imageProvider==='svg'`, draft via
   the svg compositor instead of pollinations (offline, matches final). FE-only + a
   `previewVisual` provider branch already exists — extend it.

**Risk:** MED. `story_pipeline_v2.py` is MED-tier; changes are gated + additive. E2E
test must confirm a real plan now carries `asset` slugs when provider=svg.

**Tests**
- catalog cache: same output, one DB build across N calls (spy/count).
- provider-driven gate: `svg` → catalog non-empty passed to director; `gpt_image` →
  empty (byte-identical) unless `STORY_LIBRARY_PICK=1`.
- full pytest.

**Rollback:** the gate + cache are independent commits; revert either.

---

## 4. Phase P3 — UI: emotion/pose editors + AI-pick visibility  **(FE, LOW/MED)**

**Files** (all `frontend/src/features/story-studio/…`)
- `PlanReview/TimelineEditor.tsx` — add `emotion` + `pose` `<Sel>` per beat.
- `PlanReview/CharactersPanel.tsx` / `VisualsPanel.tsx` — show the AI-chosen `asset`
  slug + a thumbnail; allow override (extend the existing `AssetPicker`).
- `types.ts` / `api/story.ts` — ensure `Beat.emotion`/`pose` + `CharacterDef.asset` /
  `SettingDef.asset` are in the FE types (add if missing).
- After changes: `npm run build` → `backend/static-v2` (per the render-flow rule).

**Changes**
- **D1** — TimelineEditor: two new selects (`emotion` ∈ normal/happy/angry/sad/surprised,
  `pose` ∈ stand/wave/cheer/point/hip) wired via the existing `onChangeBeat`. Makes the
  AI's per-beat choice visible + overridable.
- **D2** — Characters/Visuals panels: a small "📚 from library: `<slug>`" chip with
  thumbnail when `asset` is set; "✎ change" opens AssetPicker; empty → "procedural".
- **D3** — a compact "matching" summary on the review bar: `N/M characters · K/L scenes
  from library` (needs a tiny backend count or FE-derived from `asset` fields).
- **D4** (optional) — an "Nâng cao" toggle to reveal bgm_mood/char_anchor/char_scale.

**Risk:** FE-only, LOW. No API/contract change (fields already exist on the plan).

**Tests:** `tsc -b` green; manual smoke in Review; port to `static-v2` via build.

---

## 5. Phase P4 — Per-beat overlay default for svg  **(CRITICAL — separate approval)**

**Goal:** make the AI's per-beat emotion/pose actually VISIBLE in the default svg render
(today `STORY_CHAR_OVERLAY=0` → chars are baked static into the key-visual; emotion/pose
only show when overlay is on).

**Files:** `stages/story/beat_render.py` (**CRITICAL** — owns cue render), `visuals_stage.py`,
`story_pipeline_v2.py`. **Full Render Edit Protocol** applies (docs read, planner list,
explicit approval, full pytest baseline before/after, minimal Edit-tool diffs).

**Why separate:** `beat_render.py` is a CRITICAL-tier state-machine-adjacent file; a
change affects every Story render. Only attempt after P1-P3 land and a real render
confirms the emotion masters are correct. Decision to make in review: default overlay ON
for svg, or keep opt-in with a clear FE toggle.

---

## 6. Recommended order & gates

```
P1 (HIGH, prompt)  → approval → implement → full pytest → real render verify
P2 (MED, workflow) → approval → implement → full pytest + e2e
P3 (FE)            → implement → tsc + build static-v2
P4 (CRITICAL)      → separate explicit approval + Render Edit Protocol
```

P1 alone delivers the biggest correctness win (emotion) + stronger matching (vocab).
P2 turns the library-pick signal on. P3 makes it visible/overridable. P4 is the optional
"per-beat expressiveness in the default path" and is gated behind its own approval.

---

## 7. Open questions — DECIDED (2026-07-11)

1. **P2 gate → (b) env-default flip.** `STORY_LIBRARY_PICK` default `0 → 1` (unconditional;
   gpt-image plans also get the catalog and may emit picks it ignores — acceptable; set
   `=0` to opt out). ✅ done in `feat/story-library-pick-default`.
2. **Catalog scope → scope by the FE-picked genre.** Implemented as a genre GROUP, not a
   single exact key: the library genre folders (wuxia/codai/hiendai/fantasy/horror/
   ngontinh) are art-style buckets and one story spans several (a wuxia tale has codai
   emperors/scholars), so an exact filter would hide valid picks. FE genre → a small set
   of related genre_keys (e.g. kiem-hiep → {wuxia, codai}). **Region stays broad** — the
   FE has no region picker (only language); noted, not scoped, to avoid over-narrowing.
3. **P4 → default overlay ON for svg.** `STORY_CHAR_OVERLAY` effectively on for the svg
   path (opt-out `=0`). CRITICAL — `beat_render.py`; own commit under the Render Edit
   Protocol (full pytest baseline before/after).
4. **Vocab → list all 56 archetypes** in the prompt (derived from `svg_presets._ARCH`),
   plus the canonical scene_kind set (from `svg_scene._SCENES`).

### Execution status
- P2 flip + genre-group scope: IN PROGRESS (this branch).
- P1 prompt (emotion + full vocab, s8) + domain EMOTION: next.
- P3 UI (emotion/pose editors + AI-pick visibility): after P1/P2.
- P4 overlay-default (CRITICAL): separate Render-Edit-Protocol commit.
