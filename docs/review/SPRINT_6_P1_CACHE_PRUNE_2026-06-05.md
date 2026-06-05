# Sprint 6 P1 — Render Cache Prune (CLAUDE.md Issue 3 closure)

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline at decision:** Pytest 2373 passed / 1 skipped / 0 failed @ `2f2c8ab` (Sprint 6 P1 Inline ASS DEFER + N.2 H3 fix)
**Closure tag:** `sprint-6-p1-cache-prune-done-2026-06-05`
**Final pytest:** 2376 passed / 1 skipped / 0 failed

## Purpose

Close out CLAUDE.md "Known Active Issues" Issue 3 (Cache Location, PARTIALLY RESOLVED). The audit found the bulk of the work had already shipped in Sprint 5.2 (commit history pointers at `pipeline_cache.py:147`, `maintenance.py:82-88`, audit `docs/review/AUDIT_2026-06-02.md` P2-D2) — CLAUDE.md documentation lagged behind. One genuine residual gap remained: `prune_render_cache` ran only at startup, not in the 30-minute periodic loop. Sprint 6 P1 closes that gap and updates the documentation.

## What Sprint 5.2 already shipped (pre-Sprint-6-P1 state)

| Asset | Location | Note |
|---|---|---|
| `prune_render_cache(cache_dir, max_age_hours=72)` | `services/maintenance.py:76-116` | Per-file mtime walk across all cache subdirs |
| Startup wire | `main.py:233` | `prune_render_cache(CACHE_DIR, max_age_hours=72)` |
| Test coverage | `tests/test_maintenance_cache_prune.py` (5 cases) | Missing-dir / removes-old / walks-unknown / ignores-stray / custom-TTL |
| `CACHE_DIR` constant | `core/config.py:46` | `APP_DATA_DIR / "cache"` |
| Lazy on-read eviction | `pipeline_cache.py:22-37, 59-77, 86-110` + `motion_crop/cache.py:31-50` | `_cache_get` unlinks stale before returning None |

The lazy eviction already deletes from disk when a stale entry is read. `prune_render_cache` complements it for entries whose source is never re-accessed.

## Residual gap closed by Sprint 6 P1

Before this sprint, `_run_periodic_cleanup` at `main.py:191-215` pruned `preview`, `render_temp`, `xtts`, and `text_overlay` directories every 30 minutes. **It did NOT call `prune_render_cache`.** Long-running server-style users (rare on a desktop app but possible) would see `APP_DATA_DIR/cache/` grow between restarts because the 72h TTL on never-re-accessed sources had no eviction trigger.

Three additive changes shipped in commit `d1162d8`:

### Change 1: `services/maintenance.py` — `freed_bytes` observability

```diff
- {"removed": int, "kept": int}
+ {"removed": int, "kept": int, "freed_bytes": int}
```

Size is captured before `unlink` (post-unlink `stat()` would fail). Log line extended:

```
maintenance: pruned %d stale render cache files (>%dh old, freed=%.1f MB) from %s
```

Honest metric: zero false positives. Test `test_freed_bytes_matches_removed_file_sizes` pins deterministic byte accounting (1000 + 4000 bytes removed → `freed_bytes == 5000`).

### Change 2: `app/main.py` — periodic wire

Inside `_run_periodic_cleanup`, after the existing 4 prune calls:

```python
result_cache = prune_render_cache(CACHE_DIR, max_age_hours=72)
```

Periodic log line extended with `cache_removed=%d cache_freed_mb=%.1f`. Cadence: same 30-minute `_CLEANUP_INTERVAL_SEC` env (default 1800 s). 72-h TTL matches `_RENDER_CACHE_TTL_SEC` in `pipeline_cache.py` so prune and lazy-eviction semantics are identical.

### Change 3: `tests/test_maintenance_cache_prune.py` — 3 new cases

- `test_freed_bytes_matches_removed_file_sizes` — deterministic byte accounting
- `test_freed_bytes_zero_when_nothing_stale` — no false-positive metric on idle prune
- `test_periodic_cleanup_source_pins_render_cache_call` — source-pin against future drift on `_run_periodic_cleanup` that drops the call or the `cache_freed_mb` log field

Plus three existing assertions updated to expect the new `freed_bytes` key in the return dict.

## Cache subdir inventory (subdir-agnostic walk)

The Sprint 5.2 walk is `cache_dir.iterdir()` → `subdir.iterdir()` → file. Any subdir added under `APP_DATA_DIR/cache/X/` is auto-pruned without code change. Current subdirs:

| Subdir | Resolver | TTL | Lazy eviction on read |
|---|---|---|---|
| `scene_detect/` | `pipeline_cache.py:29` | 72h | YES (unlink) |
| `transcription/` | `pipeline_cache.py:59` | 72h | YES |
| `segment_scores/` | `pipeline_cache.py:86` | 72h | YES |
| `motion_path/` | `motion_crop/cache.py:31` | 72h | YES |

Test `test_walks_unknown_subdirs` (existing, Sprint 5.2) pins the subdir-agnostic contract.

Caches outside `APP_DATA_DIR/cache/` deliberately not in scope:

| Path | Why excluded |
|---|---|
| `TEMP_DIR/xtts_cache/` | Different TTL (30d) + different file shape; already handled by `prune_xtts_cache` |
| `data/temp/text_overlays/` | 7d TTL; already handled by `prune_text_overlay_dir` |
| `APP_DATA_DIR/whisper_cache/`, `huggingface/`, `torch/`, `ollama/` | Model storage — redownload cost is high; deliberately unpruned |

## Sacred Contract walk

- **#7 `data/app.db` sole authority** — `CACHE_DIR = APP_DATA_DIR/cache` and `DATABASE_PATH = APP_DATA_DIR/data/app.db` resolve to different subtrees. The walk requires `is_file()` and only iterates one level deep into subdirs (`for subdir in cache_dir.iterdir(): for f in subdir.iterdir()`). No crossover possible.
- **#8 `qa_pipeline`** — n/a (no output mp4 touched).
- **#1, #2, #4, #5, #6** — n/a (no API/event/schema/state-machine changes).

## ROI verification

Per-source cache footprint (sum of all 4 subdirs):

| Subdir | Typical entry size |
|---|---|
| `scene_detect/{md5}.json` | 1–5 KB |
| `transcription/{md5}.srt` | 5–50 KB |
| `segment_scores/{md5}.json` | 2–10 KB |
| `motion_path/{md5}.json` | 10–500 KB (largest — per-frame x,y data) |

Total per unique source ≈ **20 KB – 600 KB**. Realistic user (1-3 jobs/day × 6 months, with re-renders sharing a cache entry) ≈ 200-500 unique sources → **< 300 MB cumulative**. Audit row S-11 quoted "100 MB+" which matches.

This is real but modest. The Sprint 5.2 lazy-eviction already deletes any cache entry whose source is re-touched. Only never-revisited-source entries reach this prune. Urgency: low. Correctness of the patch: high.

## What this sprint does NOT do

- Does NOT modify `pipeline_cache.py` or `motion_crop/cache.py` (lazy-eviction unchanged).
- Does NOT add a per-subdir TTL (single 72h applies — matches `_RENDER_CACHE_TTL_SEC`).
- Does NOT track or prune model caches (`whisper_cache/`, `huggingface/`, etc.).
- Does NOT add an HTTP endpoint to expose `freed_bytes` — it only flows to logs.

## Closure declarations

- **CLAUDE.md Issue 3** → flipped to `RESOLVED 2026-06-05 via Sprint 6 P1`. Doc body updated to reflect the two scheduler entry points (startup + periodic), the `freed_bytes` metric, and the source-pin test that guards the wire.
- **`docs/review/TEMP_FILE_AUDIT_2026-06-04.md`** row S-11 (cache TTL) — fully closed.

## Cross-references

- `CLAUDE.md` Known Active Issues §"Issue 3 — Cache Location" — updated this commit
- `docs/review/AUDIT_2026-06-02.md` P2-D2 — original Sprint 5.2 audit row that scoped the now-existing `prune_render_cache` function
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` S-11 — audit row that ranked cache prune for future closure
- `backend/app/services/maintenance.py:76-122` — `prune_render_cache` after this sprint's `freed_bytes` extension
- `backend/app/main.py:191-220` — `_run_periodic_cleanup` after this sprint's wire
- `backend/app/main.py:241` — startup call (unchanged since Sprint 5.2)
- `backend/tests/test_maintenance_cache_prune.py` — 8 cases total post Sprint 6 P1 (5 existing + 3 new)
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` — Sprint 6 P0 HIGH sibling success
- `docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md`, `docs/review/SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` — sibling P1 defers in this same audit cycle (different reasons: Whisper had a viable swap but PIN was load-bearing; Inline ASS had no FFmpeg mechanism at all)
