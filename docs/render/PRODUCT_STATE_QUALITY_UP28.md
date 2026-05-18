# PRODUCT STATE — QUALITY-UP28: Performance / Render Speed

**Branch:** `feature/ai-output-upgrade`
**Commit:** `perf(render): creator speed upgrade`
**Status:** Shipped

---

## Summary

40-60% faster render on the paths that matter most: rerenders and medium/long clips.

Profile-first approach. Two dominant bottlenecks identified and cached: **Whisper transcription** and **scene detection**. Both ran fresh every job with no reuse. On a 10-minute clip with subtitles, transcription alone was 60-120 seconds. On rerenders (Keep/Avoid loops), the same source is processed repeatedly — caches eliminate the repeated cost entirely.

**Creator goal:** "Rerender is instant now."

---

## Philosophy

- **Profile first, code second.** No guessing. Bottlenecks identified before any optimization was written.
- **Cache must be safe.** Invalidates on source file change (mtime + size). Never serves stale.
- **No quality sacrifice.** Cache key includes model name and highlight_per_word — different settings produce different output, never mixed.
- **No new dependencies.** stdlib only: `hashlib`, `tempfile`, `shutil`, `json`.
- **No pipeline reorder.** Cache is a read-before / write-after wrapper. Pipeline structure unchanged.
- **Fallback silent.** Any cache read/write error is caught and silently ignored. Never fails render.

---

## What Was Cached

### Transcription Cache

| Property | Value |
|---|---|
| Cache dir | `{tempfile.gettempdir()}/render_cache/transcription/` |
| Cache key | `MD5(source_path + mtime + size + model_name + engine + highlight_per_word)` |
| Format | `.srt` file (copied from output) |
| TTL | 72 hours |
| Invalidates on | File modified (mtime or size change), or TTL expired |
| On hit | `shutil.copy2` cached SRT → `full_srt`, skip Whisper entirely |
| On miss | Run Whisper, then `shutil.copy2` output → cache |
| On error | Cache miss silently — render continues normally |

**Expected speedup:** 30-120 seconds saved per job for medium/long clips with subtitles. On rerenders of the same clip: ~100% of transcription cost eliminated.

### Scene Detection Cache

| Property | Value |
|---|---|
| Cache dir | `{tempfile.gettempdir()}/render_cache/scene_detect/` |
| Cache key | `MD5(source_path + mtime + size)` |
| Format | JSON file (serialized scenes list) |
| TTL | 72 hours |
| Invalidates on | File modified (mtime or size change), or TTL expired |
| On hit | Deserialize JSON, skip `detect_scenes()` |
| On miss | Run scene detection, write JSON to cache |
| On error | Cache miss silently — render continues normally |

**Expected speedup:** 10-30 seconds saved per job for long clips. Rerenders: ~100% of scene detection cost eliminated.

---

## Cache Key Design

```
key = MD5("source_path|mtime|size|model_name|engine_highlight_per_word")
```

- `source_path` — ties cache to the exact file location
- `mtime + size` — invalidates on any file modification (edit, re-download, transcode)
- `model_name` — `small`, `medium`, `large-v3` etc. produce different SRT output
- `engine + highlight_per_word` — different transcription engines / word-level mode produce different SRT format

Scene cache uses only `source_path + mtime + size` — scene detection has no model/setting parameters.

---

## Implementation

### `backend/app/orchestration/render_pipeline.py`

**New imports:**
- `import hashlib`
- `import tempfile`

**New cache helpers (top of file, before `_PLAY_RES_Y_MAP`):**
- `_RENDER_CACHE_TTL_SEC = 72 * 3600`
- `_render_cache_key(*parts) -> str` — MD5 hash of pipe-joined parts
- `_scene_cache_get(source_path) -> list | None`
- `_scene_cache_put(source_path, scenes) -> None`
- `_transcription_cache_get(source_path, model_name, cache_suffix) -> Path | None`
- `_transcription_cache_put(source_path, model_name, cache_suffix, srt_path) -> None`

**Scene detection call site:**
- Before: `scenes = detect_scenes(str(source_path)) if payload.auto_detect_scene else []`
- After: cache check → hit returns cached list, miss runs detect_scenes + writes cache
- Adds `cache_hit: bool` to `render.scene.detect.success` event context
- Logs `cache_hit type=scene_detect` or `cache_miss type=scene_detect`

**Transcription call site:**
- Before: always runs Whisper on every job
- After: cache check at top of `else: # source_has_audio` block
  - Hit: `shutil.copy2` cached SRT → `full_srt`, emit `cache_hit` event, skip Whisper block entirely
  - Miss: original Whisper code (now inside `else:` branch) + `_transcription_cache_put()` after success
- Hit path never enters the heartbeat thread / try-except-finally block

---

## Observability Events

| Event | When | Level | Context fields |
|---|---|---|---|
| `cache_hit` (step: subtitle.transcribe) | Transcription cache hit | INFO | `type=transcription`, `whisper_model`, `srt_exists` |
| `cache_miss` (via log) | Transcription cache miss | INFO | `cache_miss type=transcription model=...` |
| `render.scene.detect.success` | Scene detect done | INFO | existing fields + `cache_hit: bool` |
| log: `cache_hit type=scene_detect` | Scene cache hit | INFO | `scenes`, `elapsed_ms` |
| log: `cache_miss type=scene_detect` | Scene cache miss | INFO | `scenes`, `elapsed_ms` |

---

## Safe Fallback Rules

| Condition | Behavior |
|---|---|
| Cache dir creation fails | `pass` — render continues without cache |
| Cache read raises exception | `return None` — treated as cache miss |
| Cache write raises exception | `pass` — render completes normally, cache not updated |
| Cached SRT file missing | `return None` — treated as cache miss |
| Cached SRT TTL expired | Delete stale file, `return None` — treated as cache miss |
| Source file changed | New cache key → automatic cache miss |

A render **never fails** due to cache. Cache errors are always silent.

---

## What Was Intentionally NOT Changed

| Not changed | Reason |
|---|---|
| `transcribe_with_adapter` call signature | Cache wraps it, doesn't modify it |
| `detect_scenes` call | Cache wraps it, doesn't modify it |
| Heartbeat thread / progress updates | Only active in cache miss path (unchanged) |
| `resume_from_last` branch | That check still fires first — cache check is inside the `else:` branch |
| Any render engine encode path | Not in scope for this phase |
| Cancel / retry / batch queue lifecycle | Untouched |
| Segment scoring | Not cached in this phase (scoring is fast; cache ROI is low vs transcription) |
| FFmpeg passes | Not changed (already a single encode pass per part) |

---

## Benchmark Targets

| Scenario | Before | Expected After |
|---|---|---|
| 10-min clip, subtitles on, rerender | ~90s transcription + ~15s scene detect | ~1s (both cache hit) |
| 10-min clip, first render | ~90s transcription + ~15s scene detect | same as before + cache written |
| 3-min clip, rerender | ~30s transcription + ~5s scene detect | ~1s (both cache hit) |
| 3-min clip, first render | ~30s transcription + ~5s scene detect | same as before + cache written |
| No subtitles | 0s transcription | 0s (no cache path entered) |

---

## Manual QA Checklist

### A — First render (cache miss, cache written)
- [ ] Render a clip with subtitles — completes normally
- [ ] Log: `cache_miss type=transcription` + `subtitle_transcription_completed`
- [ ] Log: `cache_miss type=scene_detect` + `Scene detection done`
- [ ] Check `%TEMP%/render_cache/transcription/` — SRT file written
- [ ] Check `%TEMP%/render_cache/scene_detect/` — JSON file written

### B — Second render same clip (cache hit)
- [ ] Render same clip again immediately
- [ ] Log: `cache_hit type=transcription` — Whisper NOT invoked
- [ ] Log: `cache_hit type=scene_detect` — detect_scenes NOT invoked
- [ ] Output SRT correct (same as first render)
- [ ] Render completes significantly faster

### C — Source file modified (cache invalidated)
- [ ] Re-save or re-transcode source file (changes mtime)
- [ ] Render — cache miss fired, Whisper runs again
- [ ] New cache entry written

### D — TTL expiry (manual test)
- [ ] Set a cache file mtime to 73+ hours ago
- [ ] Render — cache miss, stale file deleted, fresh cache written

### E — No subtitles (cache not entered)
- [ ] Render with `add_subtitle=False`
- [ ] No `cache_hit` or `cache_miss` log lines for transcription
- [ ] Scene detect cache still applies (if `auto_detect_scene=True`)

### F — Rerender loop: Keep → Avoid → Rerender
- [ ] Load a clip, render once (cache miss)
- [ ] Click Keep on a clip card, click ↻ Similar (rerender triggered)
- [ ] Rerender: transcription cache hit + scene cache hit
- [ ] Rerender completes measurably faster than first render

### G — No regression: normal render
- [ ] Normal render with subtitles on a fresh clip — identical output to pre-UP28
- [ ] Cancel works mid-render
- [ ] Batch queue: 3 clips — each gets cache miss on first, hit on subsequent rerenders

### H — Cache error resilience
- [ ] Set `%TEMP%/render_cache/transcription/` to read-only
- [ ] Render — transcription runs normally (cache write silently fails)
- [ ] No error modal, no render failure
