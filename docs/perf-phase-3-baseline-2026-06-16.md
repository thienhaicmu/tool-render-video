# Phase 3 — Pre-edit Baseline (2026-06-16)

## Pytest state

| Suite | Tests | Result |
|---|---|---|
| Full pytest collect | **1396** | |
| Focused (7 suites) | **93** | **all pass** |

Focused set:
- `test_motion_crop.py`
- `test_motion_crop_quality_indicator.py`
- `test_stages_analyzing_scene_detection_emitted.py`
- `test_download_service.py`
- `test_pipeline_segment_selection.py`
- `test_phase_u1_platform_ownership.py`
- `test_pipeline_cache_atomic_write.py`

## Verified scope (after file-state triage)

| # | Item | File | Action |
|---|---|---|---|
| 1 | R10 instrument | `motion/cache.py` | Wrap `_motion_path_cache_get` with `@_instrument_cache("motion_path")` |
| 2 | R11 route | `pipeline/scene_detector.py:53`, `preview/ffmpeg_probers.py:19,36` | Replace subprocess ffprobe with `probe_video_metadata(path)` |
| 3 | D2 singleton | `download/engine/enrichment.py:136-151` | Module-level Whisper-tiny lazy singleton |
| 4 | D3 `/info` LRU | `download/engine/engine.py:81-130` | Module-level URL→(t, payload) dict with 300s TTL |
| 5 | D9 dedup | `download/engine/platform_detect.py:31` | `@functools.lru_cache(maxsize=1024)` |

## Rejected (false positives — verified in file)

- **D4 (cookie cache)** — `_apply_cookies` is ~400 µs (env + file stat). DPAPI lives inside yt-dlp when `cookiesfrombrowser` is set, not in our code.
- **D5 (timeout pool)** — Already per-download reuse at `downloader.py:633`, not per-attempt.

## Acceptance gate (compared in result doc)

- [ ] py_compile passes on all 5 files
- [ ] Focused pytest 93/93 (= baseline)
- [ ] Full pytest 1396 (= baseline)
- [ ] After smoke render: `render_cache_lookups_total{cache="motion_path"}` present
- [ ] `/info` repeat call benchmark: 2nd call returns < 50 ms
- [ ] `output_rank_score` unchanged
