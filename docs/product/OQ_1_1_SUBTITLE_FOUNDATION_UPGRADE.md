# OQ-1.1 — Subtitle Foundation Upgrade
## faster-whisper large-v3 + WhisperX Forced Alignment

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** FOUNDATION ONLY — no subtitle style changes, no animation changes

---

## 1. Current Architecture Audit

### Transcription library
- **Library:** `openai-whisper==20231117` (requirements.txt line 5)
- **Models by render profile** (`render_pipeline.py:_resolve_profile()`):
  - `fast` → `base` (80M params)
  - `balanced` → `base` (80M params)
  - `quality` → `small` (244M params)
  - `best` → `small` (244M params)
- **Execution mode:** CPU always. `fp16=False` hardcoded in `_transcribe_with_retry()` (`subtitle_engine.py:237`)
- **In-memory cache:** `_MODEL_CACHE` dict in `subtitle_engine.py:14` — model stays loaded after first use

### Transcript caching
**CONFIRMED: Transcription runs ONCE per source video, cached for 72 hours.**

Evidence from `render_pipeline.py`:
- `_RENDER_CACHE_TTL_SEC = 72 * 3600` (line 79)
- `_transcription_cache_get()` (line 116): checks `%TEMP%/render_cache/transcription/{md5}.srt`
- Cache key: `MD5(source_path | mtime | size | model_name | cache_suffix)`
- `cache_suffix = f"{engine}_{highlight_per_word_flag}"` (line 2727)
- Cache hit → `shutil.copy2()` to job SRT path, skips Whisper entirely (line 2730)
- Cache write → `_transcription_cache_put()` after successful transcription (line 2805)
- **Each clip does NOT re-run Whisper.** The full-video SRT is written once, then `slice_srt_by_time()` is called per clip.

### Timestamp granularity
- **Default mode** (`highlight_per_word=False`): segment-level. One SRT block per Whisper segment (typically 3-12 words).
- **Word mode** (`highlight_per_word=True`): `word_timestamps=True` passed to Whisper, per-word SRT blocks. Timing accuracy: ±150-250ms (Whisper base/small estimate).
- **WhisperX alignment** (when engine=`whisperx`): forced wav2vec2 alignment, timing accuracy: ±30ms. Currently dormant — `has_whisperx()` returns False on base install.

### Execution path (traced)
```
render_pipeline.py:2704
  → payload.add_subtitle=True
  → _transcription_cache_get() — check cache
  → if miss: transcribe_with_adapter(engine, model, ...)
      → subtitle_transcription_adapters.py:transcribe_with_adapter()
          → engine="default" → DefaultWhisperAdapter.transcribe()
              → subtitle_engine.py:transcribe_to_srt()
                  → ffmpeg extract WAV (16kHz mono PCM)
                  → whisper.load_model(model_name, download_root=WHISPER_CACHE_DIR)
                  → model.transcribe(audio_path, fp16=False, [word_timestamps=True])
                  → _write_word_level_srt() or _write_segment_level_srt()
                  → unlink WAV
  → _transcription_cache_put()
  → [per clip] slice_srt_by_time() — rebase timestamps, apply speed scale
  → srt_to_ass_bounce() / srt_to_ass_karaoke() — ASS conversion
```

---

## 2. Problems Discovered

| # | Problem | Evidence |
|---|---|---|
| P1 | Default model is `base` (80M params) for fast/balanced profiles | `_resolve_profile()` render_pipeline.py:1348-1350 |
| P2 | CPU-only transcription — `fp16=False` hardcoded | `subtitle_engine.py:237` |
| P3 | Word timing drift ±150-250ms on Whisper base/small | No forced alignment |
| P4 | WhisperX adapter exists but never activates | `has_whisperx()=False` on base install |
| P5 | faster-whisper listed as optional AI dep but not integrated | `requirements-ai.txt:5`, `dependencies.py:29` |
| P6 | No CUDA path for transcription even when NVENC GPU present | All transcription CPU |

---

## 3. Current Subtitle Execution Path

```
SOURCE VIDEO (mp4/mkv)
       │
       ▼ ffmpeg (subtitle_engine.py:281-284)
WAV (16kHz, mono, PCM s16le)
       │
       ▼ openai-whisper model.transcribe(fp16=False)
WHISPER RESULT (segments dict)
       │
       ├─ highlight_per_word=False → _write_segment_level_srt()
       └─ highlight_per_word=True  → _write_word_level_srt() (word timestamps)
       │
       ▼
FULL VIDEO SRT (cached 72h in %TEMP%/render_cache/transcription/)
       │
       ▼ [repeated per clip] slice_srt_by_time()
CLIP SRT (rebased to 0, speed-scaled)
       │
       ▼ srt_to_ass_bounce() / srt_to_ass_karaoke()
ASS FILE (burned into video by FFmpeg subtitles= filter)
       │
       ▼
FINAL RENDERED CLIP
```

---

## 4. Transcript Cache Findings

**The system already transcribes once and caches — existing architecture is correct.**

Cache key composition:
- `source_path` (absolute path)
- `st.st_mtime` (file modification time — detects file replacement)
- `st.st_size` (file size in bytes — additional integrity check)
- `model_name` (e.g. "base", "large-v3" — different models = different cache files)
- `cache_suffix` (e.g. "default_0", "faster_whisper_1" — engine + word mode flag)

**Impact of model upgrade on cache:**
- Upgrading from `base` to `large-v3` automatically busts cache (model_name in key)
- Switching from `default` engine to `faster_whisper` engine also busts cache (suffix in key)
- Old cache entries (base/default) remain on disk until 72h TTL expiry — no collision

**Cache is preserved and correct. No migration needed.**

---

## 5. WhisperX Compatibility Findings

### Existing code
`subtitle_transcription_adapters.py` already contains `WhisperXAdapter` (line 74):
- Runs WhisperX with `device="cpu"`, `compute_type="int8"`, `batch_size=4`
- Calls `whisperx.load_align_model()` for forced alignment
- Writes aligned word-level SRT via `_write_whisperx_srt()`
- Falls back to `DefaultWhisperAdapter` on any error

### What changes in this upgrade
- `WhisperXAdapter` gains CUDA detection via `_detect_fw_device_compute()` helper
- `device` → `"cuda"` when `ctranslate2.get_cuda_device_count() > 0`
- `compute_type` → `"float16"` on CUDA, stays `"int8"` on CPU
- `batch_size` → 8 on CUDA, stays 4 on CPU
- Default model → `"large-v3"` instead of `"base"`
- WhisperX uses faster-whisper as backend automatically when `faster-whisper` is installed

### Language alignment support
WhisperX forced alignment is supported for: en, de, fr, es, it, ja, zh, nl, uk, pt.
**Vietnamese (vi) has no wav2vec2 alignment model.** For vi-VN content, WhisperX alignment will fail gracefully and fall back to faster-whisper transcription without alignment. This is acceptable — faster-whisper large-v3 still provides significantly better accuracy than Whisper base.

### Breaking changes
**None.** All changes are:
- Additive (new adapter, new engine option)
- Graceful fallback on failure
- SRT output format is identical regardless of engine
- Cache key includes engine name — no cache collision

---

## 6. Migration Architecture

### Before (OQ-1.1)
```
engine="default" → openai-whisper (base or small, CPU, fp16=False)
engine="whisperx" → WhisperX (CPU, int8, base model) — DORMANT
```

### After (OQ-1.1)
```
engine="default"
  → has_faster_whisper()=True  → FasterWhisperAdapter (large-v3, CUDA float16 or CPU int8)
  → has_faster_whisper()=False → DefaultWhisperAdapter (openai-whisper, unchanged)

engine="faster_whisper" (explicit)
  → FasterWhisperAdapter → fallback to DefaultWhisperAdapter on error

engine="whisperx"
  → WhisperXAdapter (large-v3, CUDA float16 or CPU int8, wav2vec2 alignment)
  → fallback to FasterWhisperAdapter if alignment fails
  → fallback to DefaultWhisperAdapter if faster-whisper also unavailable
```

### Render profile whisper_model changes
| Profile | Before | After |
|---|---|---|
| fast | base | base (unchanged — speed priority) |
| balanced | base | large-v3 |
| quality | small | large-v3 |
| best | small | large-v3 |

### New model cache path
faster-whisper stores models separately from openai-whisper. Model files download to:
`~/.cache/huggingface/hub/` (default faster-whisper path) or `TRANSFORMERS_CACHE` if set.
Size: large-v3 ≈ 1.5GB (downloaded once on first use).

---

## 7. Safe Rollback Strategy

### If faster-whisper causes issues
1. Uninstall faster-whisper: `pip uninstall faster-whisper`
2. `has_faster_whisper()` returns False → system falls back to `DefaultWhisperAdapter` automatically
3. No code change required

### If large-v3 model causes issues
1. API payload: set `render_profile="fast"` → uses `base` model
2. Or: pass `whisper_model="small"` in payload override
3. The profile model names are the only change to render_pipeline.py

### If WhisperX fails for a specific language
- WhisperXAdapter already wraps everything in try/except
- On any exception: `warnings=["whisperx_runtime_error:..."]` set, falls back to faster-whisper
- Render continues — subtitle quality degrades gracefully to faster-whisper output

### If CUDA OOM during transcription
- faster-whisper will raise on `WhisperModel("large-v3", device="cuda")`
- This propagates as a FasterWhisperAdapter warning
- Falls back to `DefaultWhisperAdapter` (CPU)
- Render continues

---

## 8. Performance Expectation (RTX 3060 12GB)

| Scenario | Before | After |
|---|---|---|
| Whisper base, 5min video, CPU | ~45s | N/A (replaced) |
| faster-whisper large-v3, 5min video, CUDA float16 | N/A | ~8-12s |
| faster-whisper large-v3, 5min video, CPU int8 | N/A | ~90-120s |
| WhisperX large-v3, 5min video, CUDA float16 | N/A | ~15-20s (includes alignment) |
| VRAM usage during transcription | 0MB (CPU) | ~3.5GB (large-v3 float16) |
| VRAM available for NVENC (3060 12GB) | 12GB | ~8.5GB — ample for 3× NVENC sessions |

**Cache behavior:** After first transcription per video, all subsequent renders use cached SRT. VRAM is released when transcription completes. NVENC encode starts only after transcription finishes. No VRAM contention.

---

## 9. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| large-v3 word timestamps slightly different from base | Low | Same SRT format; content more accurate, not less |
| Vietnamese alignment missing in WhisperX | Low | Explicit fallback: WhisperX → faster-whisper (no alignment) |
| 1.5GB first-run download blocks render | Medium | Download happens at first render; subsequent runs use cache. Warmup step added. |
| VRAM pressure if NVENC and Whisper run simultaneously | Low | Transcription completes before NVENC starts in render_pipeline sequence |
| Cache TTL mismatch (old base SRT still on disk) | None | Different cache key — no collision |
| openai-whisper import still needed | None | DefaultWhisperAdapter still present as fallback, openai-whisper stays in requirements.txt |
| speech_density_score changes slightly | Negligible | More accurate transcript → more accurate speech coverage. Weight is 5-10% of viral score. |

---

## 10. Manual Verification Checklist

```
[ ] Short video (< 30s) — English — faster-whisper default path
[ ] Long podcast (> 5min) — English — large-v3 accuracy check
[ ] Vietnamese speech — faster-whisper (no WhisperX alignment, graceful)
[ ] English speech with WhisperX — engine="whisperx" explicit
[ ] Mixed VN/EN speech — language detection + fallback behavior
[ ] Multi clip render — cache hit on 2nd and subsequent clips
[ ] highlight_per_word=True — word-level SRT timing accuracy
[ ] highlight_per_word=False — segment-level SRT compatibility
[ ] Existing subtitle preset (viral, clean, story, gaming) — ASS render unchanged
[ ] Render queue (3 concurrent jobs) — no VRAM OOM
[ ] GPU utilization during transcription — ctranslate2 CUDA visible
[ ] Transcript cache reused — log shows "cache_hit type=transcription"
[ ] WhisperX failure fallback — simulate by revoking alignment model, verify render continues
[ ] No render regression — output video duration + subtitle timing within tolerance
[ ] Warmup status endpoint — shows faster-whisper large-v3 status
```

---

## 11. Files Modified

| File | Change |
|---|---|
| `backend/requirements-ai.txt` | Add `whisperx` |
| `backend/app/models/schemas.py` | Add `"faster_whisper"` to `subtitle_transcription_engine` Literal |
| `backend/app/services/subtitle_engine.py` | Add `extract_audio_for_transcription()` public helper |
| `backend/app/services/subtitle_transcription_adapters.py` | Add `FasterWhisperAdapter`, `_detect_fw_device_compute()`, `_FW_MODEL_CACHE`, `_write_fw_srt()`. Update `WhisperXAdapter` for CUDA/large-v3. Update `transcribe_with_adapter()` default routing. |
| `backend/app/orchestration/render_pipeline.py` | Update `_resolve_profile()`: balanced/quality/best → `"large-v3"` |
| `backend/app/services/warmup.py` | Add optional faster-whisper large-v3 warmup step |

---

## 12. Commit Hash

_Populated after commit._

---

## 13. Push Confirmation

_Populated after push._
