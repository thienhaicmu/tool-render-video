# OQ-2.2A — XTTS Hardening + Voice Persona Layer
## Premium Narration Quality

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** VOICE QUALITY ONLY — no subtitle, no scene logic, no pacing, no render logic

---

## 1. Current XTTS Audit

### Speaker selection (pre-OQ-2.2A)

```python
_XTTS_SPEAKER_MAP = {"female": "Ana Florence", "male": "Viktor Eka"}
```

Two speakers total. `synthesize_xtts()` accepts `gender` but ignores `content_type`. All renders — viral, tutorial, podcast, gaming, story — get the same voice.

### Caching (pre-OQ-2.2A)

None. `synthesize_xtts()` runs full inference on every call regardless of whether identical text+language+gender has been synthesized before. For a multi-part render of the same script, each part re-synthesizes from scratch.

### CPU safety (pre-OQ-2.2A)

`_get_xtts_model()` falls through to `device="cpu"` when `torch.cuda.is_available()` returns False:
```python
except ImportError:
    device = "cpu"   # torch not installed → CPU
...
device = "cuda" if torch.cuda.is_available() else "cpu"  # no CUDA → CPU
```
CPU XTTS inference is 30–60s per synthesis segment. This turns a production render into a multi-minute stall per part with no warning.

### Prosody (pre-OQ-2.2A)

No prosody differentiation. Speaker identity controls prosody entirely via the neural model. Content type is not passed to `synthesize_xtts()` at all.

---

## 2. Problems Discovered

| # | Problem | Severity |
|---|---|---|
| P1 | Same 2 speakers for all content types — voice has no character match to content | HIGH |
| P2 | No cache — repeated identical synthesis on resume/retry or multi-part render | HIGH |
| P3 | CPU XTTS silently allowed — 30–60s per synthesis unacceptable in production | CRITICAL |
| P4 | `content_type` parameter not forwarded from `generate_narration_audio()` to `synthesize_xtts()` | MEDIUM |
| P5 | No prosody label — can't distinguish calm/energetic in logs | LOW |

---

## 3. XTTS Architecture (post-OQ-2.2A)

### A. Voice Personas

New `_PERSONA_SPEAKER_MAP`: content_type × gender → XTTS v2 built-in speaker name.

Speaker character mapping (XTTS v2 `tts_models/multilingual/multi-dataset/xtts_v2`):

| Content type | Female | Male | Prosody style |
|---|---|---|---|
| viral | Claribel Dervla | Craig Gutsy | energetic |
| gaming | Tammy Grit | Damien Black | energetic |
| montage | Tammy Grit | Craig Gutsy | energetic |
| commentary | Claribel Dervla | Craig Gutsy | energetic |
| tutorial | Daisy Studious | Abrahan Mack | authoritative |
| interview | Alison Dietlinde | Ilkin Urbano | authoritative |
| podcast | Ana Florence | Viktor Eka | conversational |
| vlog | Ana Florence | Viktor Eka | conversational |
| story | Gracie Wise | Baldur Semen | calm |

Fallback: `_PERSONA_DEFAULT_FEMALE = "Ana Florence"`, `_PERSONA_DEFAULT_MALE = "Viktor Eka"`.

All named speakers are verified XTTS v2 built-in voices from the multi-dataset model.

### B. Hash-based synthesis cache

**Cache key:** SHA256 of `text + language + gender + content_type` → 16-char hex prefix.

**Cache storage:** `TEMP_DIR/xtts_cache/{key}.mp3` — shared across jobs.

**Cache check:** Before synthesis, check if `{key}.mp3` exists and is non-empty. Cache hit → copy to output_path and return immediately (no GPU inference).

**Thread safety:** `_XTTS_CACHE_LOCK` guards both in-memory dict and file write.

**No TTL:** Text+language+speaker combinations are deterministic — cache is valid for the server lifetime. File deletion clears cache.

### C. CPU safety

Replace CPU fallback with explicit RuntimeError:
```python
def _require_cuda() -> str:
    try:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("xtts_cuda_unavailable")
        return "cuda"
    except ImportError:
        raise RuntimeError("xtts_torch_missing")
```

RuntimeError propagates to `generate_narration_audio()` → caught → edge fallback. No stall.

### D. Prosody presets

`_CONTENT_TYPE_PROSODY` maps content_type → prosody label (energetic/authoritative/conversational/calm). Used for:
1. Logging — `xtts_synthesis_start` now includes `prosody=...`
2. Future hook point for text preprocessing
3. Documents the intended vocal character per content type

---

## 4. Persona Routing

`synthesize_xtts()` new parameter: `content_type: str = "vlog"`

Speaker resolution:
```python
_persona = _PERSONA_SPEAKER_MAP.get(content_type, {})
speaker = _persona.get(gender, _PERSONA_DEFAULT_FEMALE if gender == "female" else _PERSONA_DEFAULT_MALE)
```

`generate_narration_audio()` in tts_service.py passes `content_type=content_type` to `synthesize_xtts()`.

---

## 5. Compatibility Impact

| Component | Impact |
|---|---|
| OQ-2.2 `tts_engine="edge"` path | None — edge path unchanged |
| OQ-2.2 `tts_engine="xtts"` default behavior | Changed: speaker now varies by content_type; voice sounds more appropriate |
| OQ-2.1 ducking / DeepFilterNet | None — fires after narration is on disk |
| Render pipeline call sites | None — `synthesize_xtts()` signature change is internal; `generate_narration_audio()` signature unchanged |
| `tts_engine="xtts"` on CPU-only machine | Changed: now fails fast → edge fallback instead of 30–60s CPU stall |
| Cache warm: first synthesis | Same cost as pre-OQ-2.2A (full inference) |
| Cache warm: repeat synthesis | Near-zero cost (file copy) |

---

## 6. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Speaker name not found in XTTS model | Low | All named speakers verified for xtts_v2; persona map has 2 fallbacks |
| Cache dir not writable | Low | `mkdir(parents=True, exist_ok=True)`; synthesis continues without cache write |
| Cache collision (16-char SHA256 prefix) | Negligible | 16-char hex = 2^64 space; collision probability negligible for production volumes |
| CPU users lose XTTS entirely | None | Was already broken (30-60s stall); now fails fast to edge |
| Cache file from old render re-used with different speaker | None | Speaker is part of cache key (via content_type+gender) |

---

## 7. Manual Verification Checklist

```
[ ] viral content_type: XTTS uses Claribel Dervla (female) / Craig Gutsy (male)
[ ] tutorial content_type: XTTS uses Daisy Studious (female) / Abrahan Mack (male)
[ ] podcast content_type: XTTS uses Ana Florence / Viktor Eka (unchanged from OQ-2.2)
[ ] story content_type: XTTS uses Gracie Wise / Baldur Semen
[ ] gaming content_type: XTTS uses Tammy Grit / Damien Black
[ ] Cache hit: second synthesis of same text returns instantly (no GPU inference)
[ ] Cache hit: log shows xtts_synthesis_cache_hit
[ ] No CUDA: synthesize_xtts() raises RuntimeError → edge fallback fires
[ ] No CUDA: log shows xtts_unavailable_fallback, render completes with edge voice
[ ] Prosody label in log: xtts_synthesis_start includes prosody=energetic/calm/etc.
[ ] OQ-2.2 default (tts_engine="edge"): no behavioral change
[ ] Multi-render: two jobs synthesizing same text share cache, second is instant
[ ] content_type forwarded correctly: generate_narration_audio() → synthesize_xtts()
```

---

## 8. Files Modified

| File | Change |
|---|---|
| `backend/app/services/tts_xtts_adapter.py` | Add persona map, prosody map, cache, CPU safety. Update `synthesize_xtts()` signature. |
| `backend/app/services/tts_service.py` | Pass `content_type=content_type` to `synthesize_xtts()`. |

---

## 9. Commit Hash

`[pending]`

---

## 10. Push Confirmation

`[pending]`
