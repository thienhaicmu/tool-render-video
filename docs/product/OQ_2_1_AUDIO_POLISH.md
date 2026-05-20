# OQ-2.1 — Audio Polish Layer
## Sidechain Ducking + DeepFilterNet Activation

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** AUDIO POLISH ONLY — no subtitles, no narration engine, no scene logic, no scoring

---

## 1. Current Audio Audit

### Narration path (traced)

- **Generation:** `tts_service.py:generate_narration_mp3()` — edge_tts async, MP3 output, 60s timeout.
- **Output:** `{TEMP_DIR}/{job_id}/voice/narration.mp3`
- **Humanization:** `humanize_narration_text()` — content-type specific pause styles injected.
- **Cleanup (conditional):** `render_pipeline.py:_maybe_cleanup_narration_audio()` — reads `audio_cleanup_engine` from payload. Default: `"none"` → returns path unchanged.
- **Cleanup options:** `NoopAudioCleanupAdapter` ("none") or `DeepFilterNetAdapter` ("deepfilternet") — adapter dispatch in `audio_cleanup_adapters.py`.
- **Call sites:** render_pipeline.py:2239, 4303, 4394

### BGM mixing path (traced)

- **Entry point:** `render_engine.py:render_part()` — takes `input_path` (video with pre-mixed audio or original) and `bgm_path`.
- **BGM gain:** `gain = max(0.01, min(1.0, float(reup_bgm_gain or 0.18)))` — default 0.18 (18%).
- **Volume chains:** `a0_chain = "volume=1.0"` (source), `a1_chain = f"volume={gain}"` (BGM).
- **Speed handling:** `atempo={speed:.4f}` appended to both when speed ≠ 1.0.

### FFmpeg audio chain (traced)

**Primary encode path (BGM + source audio):**
```
filter_complex:
[0:v]{vf_chain}[vout];
[0:a]volume=1.0[a0];
[1:a]volume=0.18[a1];
[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]
```

**Final audio filter (`_build_audio_filter`, `loudnorm_enabled=True`, standard mode):**
```
highpass=f=80,loudnorm=I=-14:LRA=11:TP=-1.0,acompressor=threshold=-18dB:ratio=2:attack=40:release=300:makeup=1.5,alimiter=limit=0.95
```
Applied via `-af` when `bgm_ok=False` (no BGM path). When BGM is present, audio is routed through `-filter_complex` and the loudnorm chain does NOT apply.

**Audio codec:** AAC 192k.

### Volume balancing (traced)

| Layer | Level | Notes |
|---|---|---|
| Source / narration audio | 1.0 (100%) | Fixed |
| BGM | 0.18 (18%) | Static, user-configurable via `reup_bgm_gain` |
| Loudness target | -14 LUFS | `loudnorm=I=-14` (no-BGM path only) |
| Compression | 2:1 @ -18dB, attack=40ms, release=300ms | Gentle, no pumping |
| Limiter | 0.95 ceiling | -0.4 dB |

### DeepFilterNet dormant path (traced)

- **Adapter:** `audio_cleanup_adapters.py:DeepFilterNetAdapter` — fully implemented, NOT dormant.
- **Availability check:** `app.ai.dependencies:has_deepfilternet()` via `importlib.util.find_spec("deepfilternet")`.
- **Processing:** 48kHz PCM → `df.enhance` model → validated output.
- **Timeout:** 180s.
- **Default engine:** `"none"` — `_maybe_cleanup_narration_audio()` returns immediately without calling the adapter.
- **Activation gate:** `payload.audio_cleanup_engine` — must be explicitly set to `"deepfilternet"` to engage. No auto-detection.

---

## 2. Problems Discovered

| # | Problem | Severity | Evidence |
|---|---|---|---|
| P1 | Static BGM mix — no dynamic ducking when voice is present | CRITICAL | render_engine.py:1036 — plain `amix`, no sidechain |
| P2 | BGM at 18% is fixed regardless of voice activity — sounds too loud in quiet speech sections | HIGH | render_engine.py:1026 |
| P3 | DeepFilterNet available but default is "none" — narration noise never cleaned | HIGH | render_pipeline.py:837 |
| P4 | loudnorm chain (`-14 LUFS + acompressor`) only fires when BGM is absent | MEDIUM | `_build_audio_filter()` not applied to `-filter_complex` path |
| P5 | CPU fallback path (NVENC fail) duplicates the amix filter — needs same ducking fix | MEDIUM | render_engine.py:1097 — second amix copy |

---

## 3. Current Mix Weaknesses

### P1 — Static mixing
`[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]` — linear mix. BGM is always at 18%. During a short speech pause, BGM jumps to full (18% of full volume with loudnorm). During fast speech, BGM overlaps voice. No energy trade-off.

### P2 — Music energy not preserved during pauses
The mix is so static that even a 0.5s breath pause sounds "wrong" — BGM pops back full because it was never ducked. This is the "cheap audio feel" described in the goal.

### P3 — Narration noise never cleaned
DeepFilterNet would remove background hiss, echo, and room tone from TTS narration, but it is gated behind an explicit API parameter that no default render uses.

---

## 4. Audio Polish Architecture

### OQ-2.1 pass: Two targeted changes

**Change A: Sidechain ducking in `_build_audio_mix_filter()`**

New helper replaces the inline `amix` string. When `BGM_DUCKING_ENABLED=1` (default):
```
[a1][a0]sidechaincompress=threshold=0.015:ratio=3:attack=200:release=1000[bgm_ducked];
[a0][bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]
```

**Change B: DeepFilterNet auto-activation in `_maybe_cleanup_narration_audio()`**

When `AUDIO_CLEANUP_AUTO=1` (default) and `has_deepfilternet()` is True, auto-upgrade engine from "none" to "deepfilternet". Explicit `payload.audio_cleanup_engine` overrides this (e.g., "none" forced via API still disables it).

---

## 5. Ducking Strategy

### Filter: `sidechaincompress`

```
[a1][a0]sidechaincompress=threshold=0.015:ratio=3:attack=200:release=1000[bgm_ducked]
```

| Parameter | Value | Rationale |
|---|---|---|
| Signal | a1 (BGM) | BGM is what gets compressed |
| Sidechain | a0 (voice/source) | Voice triggers the compression |
| threshold | 0.015 (~-36.5 dBFS) | Triggers when voice is clearly present, not on room noise |
| ratio | 3:1 | BGM drops to ~40% when voice is above threshold — audible but unobtrusive |
| attack | 200ms | Gradual engagement — no sudden chop at start of speech |
| release | 1000ms | Slow fade-back — music returns smoothly on breath pauses |

### Why NOT aggressive ducking?

CapCut reference: BGM audible during pauses, subtly under during speech. Not silent. Ratio 3:1 at threshold 0.015 produces roughly:
- During active speech at -12 dBFS: BGM volume ~0.08–0.10 (vs static 0.18) — 44–55% reduction
- During breath pauses / silence: BGM returns to full 0.18 over ~1 second

This matches the "premium creator mix" feel without pumping artifacts.

### Opt-out

Set env `BGM_DUCKING_ENABLED=0` to revert to plain amix (pre-OQ-2.1 behavior).

---

## 6. DeepFilterNet Strategy

### Auto-activation

```python
if engine == "none" and os.environ.get("AUDIO_CLEANUP_AUTO", "1") == "1":
    from app.ai.dependencies import has_deepfilternet as _has_dfn
    if _has_dfn():
        engine = "deepfilternet"
```

Fires at the top of `_maybe_cleanup_narration_audio()` before the early return.

### When it fires

- Package `deepfilternet` (or `df`) is installed
- `AUDIO_CLEANUP_AUTO` is `"1"` (default)
- `payload.audio_cleanup_engine` was not explicitly set (or was `"none"`)

### When it does NOT fire

- `deepfilternet` not installed → `has_deepfilternet()` returns False → no change
- `AUDIO_CLEANUP_AUTO=0` set in env → auto-upgrade skipped
- `payload.audio_cleanup_engine` explicitly set to any value → explicit value wins

### Safety

- DeepFilterNet validates output duration matches input within tolerance (±5%) — duration mismatch returns original
- 180s timeout prevents stall
- Failed cleanup returns original audio path unchanged — render continues

### "Only when useful" constraint

DeepFilterNet is applied to narration audio (TTS output). TTS output ALWAYS benefits from noise cleanup — edge_tts produces mild background noise and room resonance. This is a safe application target. It is NOT applied to original video audio.

### Opt-out

Set env `AUDIO_CLEANUP_AUTO=0` to disable auto-activation.

---

## 7. Compatibility Impact

| Component | Impact |
|---|---|
| BGM mixing (BGM + source audio path) | Changed: sidechain ducking instead of plain amix. Audio energy preserved; BGM ducks during speech. |
| BGM mixing (no source audio path) | None — uses `-filter:a volume=...` directly, no amix |
| NVENC GPU encode path | Changed: same ducking applied in CPU fallback |
| `_build_audio_filter()` (no-BGM path) | None — unchanged, still applies loudnorm chain |
| DeepFilterNet adapter implementation | None — adapter unchanged |
| Narration generation (TTS) | None — TTS path unchanged |
| `_maybe_cleanup_narration_audio()` | Changed: auto-upgrade "none" to "deepfilternet" when conditions met |
| Subtitle timing | None |
| OQ-1.2 intelligence | None |
| OQ-1.3/1.4 style/motion | None |
| AI scoring | None |
| Render queue / multi-render | None — stateless audio filter |
| Render speed | Minor: DeepFilterNet adds processing time (up to 180s cap) when installed |

---

## 8. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `sidechaincompress` not supported in old FFmpeg | Low | Available since FFmpeg 3.x. `sidechaincompress` in lavfi is standard. Check: `ffmpeg -filters | grep sidechain` |
| Ducking too aggressive — music nearly silent | Low | threshold=0.015, ratio=3 is conservative; ratio=4 would be aggressive. Opt-out via `BGM_DUCKING_ENABLED=0` |
| Ducking pumping artifacts | Low | attack=200ms + release=1000ms prevents rapid changes |
| DeepFilterNet artifacts on clean TTS | Low | Has_deepfilternet guard + duration validation + 180s timeout fallback |
| DeepFilterNet slows render significantly | Medium | Only fires if package installed. `AUDIO_CLEANUP_AUTO=0` opt-out. Timeout 180s |
| BGM mixing unchanged when no source audio | None | Code path already separate — no amix when `input_has_audio=False` |
| NVENC fallback path broken | None | CPU fallback path receives same `_build_audio_mix_filter()` call |

---

## 9. Manual Verification Checklist

```
[ ] Talking-head video + BGM: BGM audibly ducks during speech sections
[ ] Talking-head video + BGM: BGM returns smoothly during breath pauses (no hard pop)
[ ] No aggressive pumping: BGM volume change is gradual (200ms attack, 1000ms release)
[ ] No BGM + source audio: render unchanged (no amix path)
[ ] BGM volume preserved in silence: BGM not muted during speaker pauses
[ ] Voice intelligibility improved vs pre-OQ-2.1 (voice clearer over BGM)
[ ] DeepFilterNet auto-activates when package installed (check log: audio_cleanup_applied)
[ ] DeepFilterNet does NOT activate when package absent (check log: no audio_cleanup entries)
[ ] DeepFilterNet artifact check: TTS voice sounds natural, not robotic
[ ] Vietnamese speech safe: DeepFilterNet runs on audio bytes, language-agnostic
[ ] English speech safe: same
[ ] Render completes successfully with BGM ducking enabled
[ ] NVENC GPU path + BGM: ducking applied correctly
[ ] NVENC CPU fallback + BGM: ducking applied correctly (same filter)
[ ] Multi-render stable: stateless filter per render_part call
[ ] Export stable: AAC 192k output unchanged
[ ] BGM_DUCKING_ENABLED=0 opt-out works: plain amix when env is 0
[ ] AUDIO_CLEANUP_AUTO=0 opt-out works: "none" stays "none" when env is 0
[ ] Log entries: audio_cleanup_applied fires when deepfilternet is used
```

---

## 10. Files Modified

| File | Change |
|---|---|
| `backend/app/services/render_engine.py` | Add `_build_audio_mix_filter()`. Replace both inline `amix` strings (primary + CPU fallback). |
| `backend/app/orchestration/render_pipeline.py` | Add DeepFilterNet auto-upgrade logic in `_maybe_cleanup_narration_audio()`. |

---

## 11. Commit Hash

`[pending]`

---

## 12. Push Confirmation

`[pending]`
