# ROADMAP — Render Quality Upgrades
## AI Output Quality Improvement Plan

Last updated: 2026-05-20

---

## Active Track: OQ (Output Quality)

### OQ-1 — Subtitle Foundation

| ID | Title | Status | Risk | Scope |
|---|---|---|---|---|
| OQ-1.1 | faster-whisper large-v3 + WhisperX | ✅ Complete + Hardened (2026-05-20) | Low | Transcription engine, word timing, CUDA path |
| OQ-1.2 | Subtitle Intelligence Layer (readability resegmentation) | ✅ Complete (2026-05-20) | Low | Semantic splitting, reading-speed, timing |
| OQ-1.3 | Premium subtitle style system (Anton/Inter/Montserrat, spacing, visual tuning) | ✅ Complete (2026-05-20) | None | Font strategy, letter-spacing, preset differentiation |
| OQ-1.4 | Premium motion subtitle engine (per-preset bounce profiles) | ✅ Complete (2026-05-20) | None | ASS pop-in motion, per-preset differentiation |
| OQ-1.5 | PhoWhisper adapter for Vietnamese | Planned | Low | vi-VN transcription accuracy |

### OQ-2 — Scene Detection

| ID | Title | Status | Risk | Scope |
|---|---|---|---|---|
| OQ-2.1 | Activate AdaptiveDetector | Planned | None | Catch gradual fades |
| OQ-2.2 | Audio silence gap scoring | Planned | None | Additive signal |
| OQ-2.3 | TransNetV2 integration | Future | Medium | Requires threshold recalibration |

### OQ-3 — Reframe / Tracking

| ID | Title | Status | Risk | Scope |
|---|---|---|---|---|
| OQ-3.1 | MediaPipe model_selection=1 (full-range) | Planned | None | Wide-shot face detection |
| OQ-3.2 | ByteTrack inter-frame tracking | Planned | Low | Eliminate 533ms stale position |
| OQ-3.3 | MediaPipe Pose (eye-level anchor) | Planned | Low | Better face framing |

### OQ-4 — Narration / Voice

| ID | Title | Status | Risk | Scope |
|---|---|---|---|---|
| OQ-4.1 | Edge-TTS + Claude SSML humanizer | Planned | None | Semantic pacing |
| OQ-4.2 | BGM sidechain ducking | Planned | None | FFmpeg filter only |
| OQ-4.3 | DeepFilterNet activation | Planned | None | Install package, adapter ready |
| OQ-4.4 | MeloTTS adapter (vi-VN) | Planned | Medium | Self-host, new adapter |

### OQ-5 — Future / S2+

| ID | Title | Status | Risk | Scope |
|---|---|---|---|---|
| OQ-5.1 | CosyVoice2 voice cloning | Future | High | GPU required |
| OQ-5.2 | SAM2 pixel segmentation | Future | High | Frame-level GPU |
| OQ-5.3 | CLIP semantic scene scoring | Future | Medium | Additive signal |

---

## OQ-1.1 + OQ-1.1A Completion Notes

**Completed:** 2026-05-20 (OQ-1.1) + 2026-05-20 (OQ-1.1A hardening)

**What shipped (OQ-1.1):**
- `FasterWhisperAdapter` — faster-whisper large-v3, CUDA float16 auto-detect, CPU int8 fallback
- `WhisperXAdapter` updated — CUDA detection, float16, large-v3 default, batch_size 8 on GPU
- `_detect_fw_device_compute()` — shared CUDA detection via ctranslate2 (no torch dependency)
- `transcribe_with_adapter()` default path — automatically uses faster-whisper when installed
- Render profiles: balanced/quality/best → large-v3 (fast stays base)
- Schema: added `"faster_whisper"` to `subtitle_transcription_engine` Literal
- warmup.py: optional faster-whisper large-v3 warmup step
- `extract_audio_for_transcription()` public helper in subtitle_engine.py

**Hardening applied (OQ-1.1A):**
- `SUPPORTED_ALIGNMENT_LANGUAGES` frozenset — language gate before wav2vec2 alignment
- WhisperXAdapter language gate: unsupported languages skip alignment, write SRT directly, no second transcription pass
- Dispatch: `language_not_supported` result treated as success — no fallback chain triggered
- `_get_fw_model()` GPU safety: CUDA failure → CPU int8 retry, not full fallback to openai-whisper
- Profile rebalance: balanced → `small` (was `large-v3` — too slow for CPU users)
- Warmup comment corrected

**What did NOT change:**
- Subtitle styles, fonts, animations, presets
- ASS format output
- SRT slice/timing logic
- viral scoring, scene scoring, AI orchestrator
- Transcript cache architecture (72h TTL, same key structure)
- Render queue, multi-render, cancel logic
- Any UI or API response format

**Regression risks at ship:**
- None observed. All fallbacks verified in code trace.
- Vietnamese: single-pass transcription, SRT written from transcription result, no alignment warning loop

**Rollback:** `pip uninstall faster-whisper` → system auto-falls back to DefaultWhisperAdapter
