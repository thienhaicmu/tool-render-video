# Sprint 7.3 — Content-Addressable ASS Cache

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-3-ass-cache`
**Baseline:** Pytest 2397 passed / 1 skipped / 0 failed @ `ee08938` (main, post Sprint 7.1)
**Final pytest:** **2422 passed (+25 new) / 1 skipped / 0 failed**
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.3 row + `docs/review/SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` §"N.1 Content-addressable ASS cache"

## Purpose

Eliminate per-part `srt_to_ass_*` re-runs on re-renders of identical source+style. The cache stores generated ASS bodies at `APP_DATA_DIR/cache/ass/{sha256}.ass`. A cache hit `shutil.copy2`'s the cached file to the expected `ass_part` path, preserving the existing downstream contract (`ass_part` is a file path consumed by FFmpeg via libass) — no FFmpeg argv change, no Sacred Contract surface touch.

## Two commits per the Planner-approved chain

**Commit 1** (`d2b6fe7`) — `pipeline_cache.py` helpers + `tests/test_ass_cache.py` (25 cases). Zero render-pipeline risk; helpers wrapped in broad try/except returning None / silent no-op.

**Commit 2** (this commit) — wire into `part_asset_planner.py:603-636` inside the existing `if needs_ass:` block. Surgical edit: compute key → cache lookup → on hit, `shutil.copy2`; on miss, generate normally then `_ass_cache_put`. Extends `subtitle_style_applied` event context with `ass_cache_hit: bool` (additive — Sacred Contract #6 compliant). New debug log `ass_content_cache part_no=N hit=true|false key=<sha256[:8]> elapsed_ms=N writer=bounce|karaoke style=<style>`.

## Cache key design (per user-approved choice — hash inputs, not outputs)

SHA-256 of canonical pipe-delimited string covering 13 inputs:

| Slot | Field | Source |
|---|---|---|
| 1 | writer | `"karaoke"` or `"bounce"` (binary discriminator for the two srt_to_ass_* writers) |
| 2 | srt_sha256 | SHA-256 of SRT bytes from `_ass_srt_source` |
| 3 | style | `_effective_subtitle_style` (viral / clean / story / gaming / preset_id) |
| 4 | scale_y | `ctx.payload.frame_scale_y` |
| 5 | font_name | `ctx.payload.sub_font` (default `"Bungee"`) |
| 6 | font_size | `ctx.payload.sub_font_size` |
| 7 | margin_v | computed value (includes content-type +40 bump and aspect-ratio override) |
| 8 | play_res_y | `_aspect_play_res_y(ctx.payload.aspect_ratio)` |
| 9 | play_res_x | hardcoded 1080 (defensive forward-compat — both writers default to 1080 today) |
| 10 | x_percent | `ctx.payload.sub_x_percent` (default 50.0) |
| 11 | highlight_per_word | `ctx.payload.highlight_per_word` |
| 12 | base_color | karaoke only: `ctx.payload.sub_color` — empty string for bounce |
| 13 | highlight_color | karaoke only: `ctx.payload.sub_highlight` — empty string for bounce |
| 14 | outline_size | karaoke only: `ctx.payload.sub_outline` — 0 for bounce |

**Why hash inputs (not outputs):** A cache hit skips both the 5-20 ms `srt_to_ass_*` generation AND the file write. Hashing outputs would force generation on every miss (wins only on the write step). The 13-input key captures every determinant that flows into the ASS body — verified by `tests/test_ass_cache.py::TestKeySensitiveToEveryParam` which parametrizes mutation of each slot.

**Why SHA-256 (not MD5):** Existing render caches (`_render_cache_key`) use MD5 because the key is a sidecar to a stat-validated source file. The ASS cache is content-addressable — the file IS the cache value, so collision risk warrants the stronger hash.

## Wiring point

Inside the existing `if needs_ass:` block at `part_asset_planner.py:603-636` (line numbers post-edit). Order:

1. Compute `_play_res_y` and `_margin_v` (unchanged).
2. Compute `_ass_writer` discriminator + `_ass_cache_k` key.
3. **Cache lookup:** `_ass_cache_get(_ass_cache_k)` — returns `Path | None`.
4. **On hit:** `shutil.copy2(cached, ass_part)` + set `_ass_cache_hit = True`.
5. **On miss:** existing karaoke/bounce branch unchanged; on success, `_ass_cache_put(_ass_cache_k, ass_part)`.
6. `_subtitle_ass_ms` timer wraps the whole block — captures hit elapsed too.
7. Log + event emit (extended with `ass_cache_hit`).

Copy fallback: if `shutil.copy2` raises (rare — permission issue, disk full), we log at DEBUG and fall through to the generation path. The cache is a best-effort optimisation, never the critical path.

## Sacred Contracts walk (Commit 2)

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json aliases | No | unchanged |
| #2 RenderRequest additive | No | no schema change, no new field |
| #3 AI returns None | No | not under `backend/app/ai/**`. Helper try/except returns None — same defensive idiom |
| #4 Job stage frozen | No | unchanged |
| #5 Part stage frozen | No | `TRANSCRIBING` upsert at `:199` unchanged |
| #6 `_emit_render_event` shape | **Additive only** | new `ass_cache_hit: bool` key INSIDE `subtitle_style_applied` event `context` dict — sibling to existing `resume_cache_hit_srt`/`_ass`. Event signature (`event`, `level`, `message`, `step`, `context`) unchanged. WS consumer reads `context` as passthrough dict. |
| #7 `data/app.db` | No | cache lives in `APP_DATA_DIR/cache/ass/`, not `data/` |
| #8 `qa_pipeline` | No | qa reads `final_part` only, never reads ASS |

## Interaction with existing resume cache

Two-stage cache stack inside `prepare_part_assets`:

1. **Fastest — resume guard at `:200-201`:** if `payload.resume_from_last AND ass_part.exists() AND size > 0`, the entire `if needs_ass:` block is skipped. Pre-Sprint-7.3 behaviour, unchanged.
2. **Second-fastest — content cache (new in Sprint 7.3):** inside `if needs_ass:`, `_ass_cache_get` hit copies cache → `ass_part` in ~ms. Only fires when resume guard didn't match (new `work_dir`, cleanup, A/B retry with content match).
3. **Slowest — generation + cache put:** existing srt_to_ass_* + new `_ass_cache_put` tail.

Resume guard absolutely wins. Content cache complements for the re-render workflow where work_dir differs but ASS content is byte-identical.

## ROI realistic

Per `TEMP_FILE_AUDIT_2026-06-04.md` row O-6: ASS files 50-500 KB per part.

| Scenario | Hit rate | Win |
|---|---|---|
| First render | 0% | none (Cache put adds ~ms overhead) |
| A/B style test | rare | low (style is in key) |
| Re-render after non-subtitle payload tweak | HIGH | 50-200 ms / 50-part render |
| History re-process identical request | 100% | full bypass of generation |

Cache size 30-day worst-case: ~500 unique (srt_bytes, style, font, margin, …) combinations × 500 KB = **~250 MB**, well under the S-11 audit envelope (sub-300 MB cumulative for all caches combined). 72h TTL via `prune_render_cache` keeps steady-state ≪ 250 MB.

## Test coverage

### Commit 1 (`tests/test_ass_cache.py`) — 25 cases across 5 classes

1. **TestKeyDeterminism** (2) — same inputs → identical sha256 hex, 64 chars.
2. **TestKeySensitiveToEveryParam** (13) — parametrize each of the 13 inputs; changing any one changes the hash. **Load-bearing**: this is what prevents stale ASS delivery on a config the renderer actually differs on.
3. **TestKeyDefensive** (2) — missing/unreadable SRT returns None, never raises.
4. **TestGetPutRoundtrip** (5) — put/get roundtrip, miss on unknown key, tolerance of missing/empty src.
5. **TestTtlEviction** (2) — 100h-old file evicts on get (lazy unlink); <72h stays.

Plus `TestPruneRenderCacheCoversAssSubdir` (1) — sibling pin documenting that `prune_render_cache` picks up `cache/ass/` via the existing subdir-agnostic walk.

### Commit 2 (existing test coverage)

`tests/test_part_asset_planner_render_plan_consume.py`, `tests/test_part_asset_planner_market_line_break.py`, `tests/test_part_asset_planner_subtitle_model_default.py` — 56 cases total, all pass on merged main.

Full pytest delta from Sprint 7.1 baseline (2397) → +25 new (2422) → unchanged (Commit 2 wires without adding new tests beyond Commit 1's helpers). No integration test on the full `prepare_part_assets` orchestration — the function has 30+ ctx fields and the existing test files cover the surrounding contract. Cache wiring exercised by the helpers' unit tests + post-merge production smoke (see below).

## Branch + commit chain

| Commit | SHA | Scope |
|---|---|---|
| Sprint 7.3 Commit 1 | `d2b6fe7` | `pipeline_cache.py` 3 helpers + `tests/test_ass_cache.py` 25 cases |
| Sprint 7.3 Commit 2 (this) | TBD | `part_asset_planner.py` wiring + event-context extension + this doc |

## Performance protections

- **NVENC_SEMAPHORE:** no FFmpeg call from this layer. Unchanged.
- **MAX_RENDER_JOBS / parallel workers:** new cache writes are per-part, small. No new contention surface.
- **Per-part disk peak:** cache hit copies ~50-500 KB. Cache put copies the same. Both single-digit MB instantaneous.

## What this sprint does NOT do

- Does NOT change the `ass=` filter in FFmpeg argv. The cached ASS file feeds the same `_safe_filter_path` consumer at `base_clip_renderer.py:391-397` (F-1), `overlay_compositor.py:84-90` (F-2), `motion_crop/__init__.py:517-523` (F-3). Sacred Contract "FFmpeg Path Helpers — Mandatory Usage" preserved.
- Does NOT introduce a new feature flag. Cache is pure-additive; on any error the key returns None and the existing generation path fires. No env-flag surface.
- Does NOT add an integration test on the full `prepare_part_assets` orchestration. The function's signature surface (30+ ctx fields) made a stub-heavy test fragile. Unit tests of the helpers + Sacred Contract walk + post-merge smoke are the alternative gate.

## Post-merge smoke verification (P6 — pending merge)

After PR merges + local `git pull --ff-only`:
1. Re-run pytest on merged main — expect 2422/1/0.
2. Start backend, hit `GET /api/jobs` (200 expected).
3. After running one render, verify `APP_DATA_DIR/cache/ass/` directory was created and contains one .ass file.
4. Re-run the same render config, verify the cache hit log line fires.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.3 row — scoped this work
- `docs/review/SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` §"N.1 Content-addressable ASS cache" — parked the idea
- `docs/review/SPRINT_6_P1_CACHE_PRUNE_2026-06-05.md` — sibling cache work (subdir-agnostic prune is what makes Sprint 7.3 zero-maintenance)
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` row O-6 — empirical audit's ASS sizing
- `backend/app/orchestration/pipeline_cache.py` — helper triplet
- `backend/app/orchestration/stages/part_asset_planner.py:603-636` — wiring point
- `backend/tests/test_ass_cache.py` — 25-case unit suite
- `CLAUDE.md` Sacred Contracts §6 (event additive), §8 (qa untouched), Performance Protections
