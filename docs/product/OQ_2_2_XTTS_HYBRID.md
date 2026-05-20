# OQ-2.2 — XTTS Hybrid Narration
## Premium Narration Engine

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** NARRATION ENGINE ONLY — no subtitles, no audio ducking, no scene logic

---

## 1. Current Narration Audit

### Edge-TTS implementation (traced)

**Function:** `tts_service.py:generate_narration_mp3()` (lines 103–147)

**Parameters:** `text, language, gender, rate, job_id, voice_id=None, output_path=None, content_type="vlog"`

**Execution path:**
1. `humanize_narration_text()` — content-type specific pause insertion
2. `_effective_rate_for()` — content-type rate nudge (vlog +0%, tutorial -8%, gaming +12%)
3. `resolve_voice_profile(language, gender, voice_id)` → Edge voice ID
4. `edge_tts.Communicate(text, voice_id, rate=rate).save(mp3_path)` with 60s timeout
5. Output: `{TEMP_DIR}/{job_id}/voice/narration.mp3`

### Voice selection (traced)

- `voice_profiles.py:VOICE_PROFILES` — maps language × gender → Edge neural voice ID
- `vi-VN female → vi-VN-HoaiMyNeural`, `en-US female → en-US-JennyNeural`, etc.
- `voice_id` parameter overrides gender-based selection
- Supported: vi-VN, en-US, en-GB, ja-JP

### Narration caching

**None.** Narration is regenerated on every render. No hash-based deduplication, no TTL, no disk cache.

### Render timing dependency

- Narration is **post-render mixed** via `audio_mix_service.py:mix_narration_audio()`
- `replace_original` mix mode: FFmpeg `-shortest` clips video to narration audio length
- `keep_original_low` mix mode: original audio kept, narration mixed at 100%
- No segment re-timing based on narration duration

### Failure behavior

- All 3 call sites (render_pipeline.py:2227, 4292, 4383) wrapped in `try/except`
- Failure → `voice_audio_path = None` → render continues with original audio
- Recovery event emitted: `"recovery_success"` + "AI narration failed — rendered without voice"
- **Render never aborts on TTS failure**

### GPU/VRAM usage for narration

- Edge-TTS: CPU-only, zero GPU usage
- NVENC semaphore (`NVENC_SEMAPHORE`) controls only video encode sessions
- No GPU semaphore for audio/TTS — needs to be added for XTTS

### Existing XTTS infrastructure

**None.** Zero XTTS, Coqui, or voice-cloning files in backend. Only `edge_tts` is used.

---

## 2. Problems Discovered

| # | Problem | Severity |
|---|---|---|
| P1 | Edge-TTS is a streaming TTS from Microsoft — voice quality is good but not premium/natural | HIGH |
| P2 | Same voice for all content types — no character differentiation | MEDIUM |
| P3 | No GPU narration path — no pathway to higher-quality local model | HIGH |
| P4 | No VRAM semaphore for audio — XTTS would need one | MEDIUM |

---

## 3. XTTS Architecture

### XTTS v2 — Coqui TTS

**Model:** `tts_models/multilingual/multi-dataset/xtts_v2`
**Package:** `TTS` (Coqui) — `pip install TTS` or `pip install coqui-tts`
**Languages supported (confirmed):** en, vi, ja, de, fr, es, it, pt, pl, tr, ru, nl, cs, ar, zh, hu, ko, hi
**GPU VRAM:** ~2.7 GB model + ~0.5 GB inference = ~3.2 GB peak → **safe for RTX 3060 12GB**
**Quality:** Significantly more natural prosody than neural streaming TTS
**Output:** 24kHz WAV → converted to MP3 by FFmpeg for pipeline compatibility

### Hybrid routing

```
RenderRequest.tts_engine
    "edge" (default) → generate_narration_mp3()  ← unchanged behavior
    "xtts"           → synthesize_xtts()          ← new path
                          ↓
                     XTTS unavailable? → edge fallback
                     XTTS fails?       → edge fallback
```

### Files

| File | Role |
|---|---|
| `backend/app/services/tts_xtts_adapter.py` | XTTS v2 adapter: model cache, semaphore, synth → MP3 |
| `backend/app/ai/dependencies.py` | Add `has_xtts()` |
| `backend/app/services/tts_service.py` | Add `generate_narration_audio()` router |
| `backend/app/models/schemas.py` | Add `tts_engine: Literal["edge", "xtts"] = "edge"` |
| `backend/app/orchestration/render_pipeline.py` | Update import + 3 call sites |

---

## 4. Hybrid Routing Strategy

### `generate_narration_audio()` (tts_service.py)

New function, same signature as `generate_narration_mp3()` plus `tts_engine: str = "edge"`.

- `tts_engine="edge"` → delegates to `generate_narration_mp3()` unchanged
- `tts_engine="xtts"` + package unavailable → logs warning → edge fallback
- `tts_engine="xtts"` + synthesis fails → logs warning → edge fallback
- No render abort path — all failures route to edge

Render pipeline replaces `generate_narration_mp3(...)` with `generate_narration_audio(..., tts_engine=getattr(payload, "tts_engine", "edge"))` at all 3 call sites.

### Default behavior

`tts_engine` field defaults to `"edge"` in `RenderRequest`. All existing renders continue to use Edge-TTS with zero behavior change.

---

## 5. Performance Expectations

| Engine | First call | Subsequent calls | VRAM | CPU |
|---|---|---|---|---|
| Edge-TTS | ~2-5s (network) | ~2-5s (network) | 0 MB | Minimal |
| XTTS v2 (GPU) | ~15-30s (model load) | ~3-8s | ~3.2 GB | Low |
| XTTS v2 (CPU) | ~60-120s (model load) | ~30-60s | 0 MB | High |

**GPU detection:** XTTS adapter uses `torch.cuda.is_available()` — auto-selects CUDA. RTX 3060 uses CUDA path.

**Semaphore:** `XTTS_MAX_SESSIONS=1` (default, env-configurable). One concurrent XTTS synthesis at a time. Multi-render jobs queue — no VRAM overflow.

**Model cache:** Model loaded once, kept in `_XTTS_MODEL_CACHE` for server lifetime. No reload cost after first synthesis.

---

## 6. Compatibility Impact

| Component | Impact |
|---|---|
| Default render path (`tts_engine="edge"`) | None — `generate_narration_mp3()` called exactly as before |
| `generate_narration_mp3()` function | None — unchanged, still exported |
| OQ-2.1 sidechain ducking | None — fires after narration is on disk |
| OQ-2.1 DeepFilterNet cleanup | None — `_maybe_cleanup_narration_audio()` unchanged |
| Render timing (mix_narration_audio) | None — output is still MP3, same pipeline |
| Subtitle timing | None |
| Scoring | None |
| Render queue / multi-render | Safe — XTTS semaphore serializes GPU access |
| Vietnamese narration | Safe — XTTS v2 supports "vi" language code |

---

## 7. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| XTTS synthesis fails → render abort | None | try/except in `generate_narration_audio()` → edge fallback |
| XTTS not installed → render abort | None | `has_xtts()` check before import; immediate edge fallback |
| XTTS VRAM spike with multi-render | Low | `_XTTS_SEMAPHORE` (max 1 session) serializes GPU access |
| XTTS model download on first use (~2.1 GB) | Low | Happens on first `tts_engine="xtts"` call; edge path unaffected |
| XTTS output duration mismatch vs edge | None | Both produce spoken narration at natural rate; timing is post-render |
| `tts_engine` field breaks API | None | Pydantic Literal with default "edge"; old requests without field unchanged |
| Circular import: tts_service → tts_xtts_adapter | None | Adapter imported lazily inside function body |

---

## 8. Manual Verification Checklist

```
[ ] tts_engine="edge" (default): renders behave exactly as before OQ-2.2
[ ] tts_engine="xtts": XTTS synthesizes and outputs audible MP3
[ ] tts_engine="xtts" + TTS package absent: falls back to edge, render completes
[ ] tts_engine="xtts" + synthesis error: falls back to edge, render completes
[ ] Vietnamese voice (vi-VN): XTTS path works (xtts language="vi")
[ ] English voice (en-US): XTTS path works (xtts language="en")
[ ] Japanese voice (ja-JP): XTTS path works (xtts language="ja")
[ ] GPU path: XTTS uses CUDA on RTX 3060, not CPU fallback
[ ] CPU path: XTTS works on CPU when CUDA unavailable (slower but functional)
[ ] Multi-render: XTTS semaphore serializes GPU access, no VRAM overflow
[ ] OQ-2.1 ducking unaffected: sidechain ducking still fires in BGM mix
[ ] OQ-2.1 DeepFilterNet: still auto-activates when installed
[ ] Render speed: XTTS GPU synthesis < 10s for typical narration length
[ ] Export stable: MP3 output feeds mix_narration_audio unchanged
[ ] Log entries: xtts_synthesis_start, xtts_synthesis_complete in logs
[ ] Fallback log: xtts_unavailable_fallback or xtts_synthesis_failed_fallback emitted on fallback
```

---

## 9. Files Modified

| File | Change |
|---|---|
| `backend/app/services/tts_xtts_adapter.py` | New — XTTS adapter: model cache, semaphore, synth → WAV → MP3 |
| `backend/app/ai/dependencies.py` | Add `has_xtts()` and entry in `get_ai_dependency_status()` |
| `backend/app/services/tts_service.py` | Add `generate_narration_audio()` routing function |
| `backend/app/models/schemas.py` | Add `tts_engine: Literal["edge", "xtts"] = "edge"` |
| `backend/app/orchestration/render_pipeline.py` | Update import; update 3 `generate_narration_mp3` call sites |

---

## 10. Commit Hash

`[pending]`

---

## 11. Push Confirmation

`[pending]`
