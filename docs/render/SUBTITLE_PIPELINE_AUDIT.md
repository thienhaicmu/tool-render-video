# Subtitle Pipeline Audit

**Branch**: `feature/ai-output-upgrade`  
**Date**: 2026-05-18  
**Scope**: `render_pipeline.py` subtitle flow (`_process_one_part`), `subtitle_engine.py`, temp file paths, resume cache

---

## Reported Symptoms

- Multiple output clips show identical subtitle content
- Subtitle timing is wrong (subtitles appear at wrong positions relative to speech)
- Subtitles do not follow clip boundaries
- CTA subtitle occasionally appears at the start of a clip instead of the end

---

## Canonical Repro Conditions

| Symptom | Trigger |
|---|---|
| CTA appears at t=0 | `resume_from_last=True`, `cta_enabled=True`, existing `_part_NNN.srt` in workdir |
| Double hook / double emphasis text | `resume_from_last=True`, mutations enabled, existing `_part_NNN.srt` in workdir |
| Timing drift (subtitle early vs video) | `target_platform=tiktok` or `instagram_reels` with any `playback_speed != 1.0` |
| Identical subtitles across parts | Not reproduced in normal code path; see P3 below |

---

## Subtitle Pipeline — Canonical Flow

```
source video
    └─ segment_builder → seg["start"], seg["end"] (absolute source timestamps)
            └─ _effective_start = seg["start"] + _trim_offset + _visual_trim
                    └─ full_srt  (work_dir/{slug}_full.srt, once per job)
                            └─ slice_srt_by_time(full_srt → srt_part, _effective_start, seg["end"],
                                                 rebase_to_zero=True, playback_speed=_eff_speed)
                                    └─ _srt_meta = {subtitle_count, first_start, first_end, last_start, last_end}
                                            ├─ subtitle_translate (optional) → translated_srt_part
                                            ├─ _apply_subtitle_edits_to_srt (optional, in-place)
                                            ├─ apply_market_hook_text_to_srt (optional, in-place)
                                            ├─ apply_market_line_break_to_srt (optional, in-place)
                                            ├─ apply_hook_subtitle_format (optional, in-place)
                                            ├─ subtitle_emphasis_pass → write_srt_blocks (in-place)
                                            ├─ _append_cta_block_to_srt (uses _srt_meta["last_end"])
                                            └─ srt_to_ass_bounce / srt_to_ass_karaoke → ass_part
                                                        └─ render_part_smart(raw_part, final_part, ass_part)
```

### File path uniqueness

| File | Path pattern | Unique per |
|---|---|---|
| `full_srt` | `work_dir/{slug}_full.srt` | job |
| `srt_part` | `work_dir/{slug}_part_{idx:03d}.srt` | part |
| `ass_part` | `work_dir/{slug}_part_{idx:03d}.ass` | part |
| `translated_srt_part` | `work_dir/{slug}_part_{idx:03d}_translated.srt` | part |
| `work_dir` | `TEMP_DIR/{job_id}/` | job |

All per-part files have a unique path. File collision is **structurally impossible** in a single job run.

---

## Findings

### [P0] Resume cache leaves `_srt_meta = {}` → CTA appended at t=0

**Location**: `render_pipeline.py:3447–3460, 3740`

**Code path**:

```python
needs_srt = not (payload.resume_from_last and srt_part.exists() and srt_part.stat().st_size > 0)
# ...
if needs_srt:
    _srt_meta = slice_srt_by_time(...)   # only set here
# ... mutations happen unconditionally ...
if _cta_enabled:
    _last_sub_end = float(_srt_meta.get("last_end") or 0)  # line 3740 — returns 0.0 when needs_srt=False
    _append_cta_block_to_srt(str(_ass_srt_source), _cta_text, _last_sub_end, _eff_dur)
```

`_srt_meta` is never initialized before the `if needs_srt:` block. When the resume cache hits (`needs_srt=False`), `_srt_meta` resolves to `{}` and `.get("last_end")` returns `None`, coerced to `0.0`. The CTA subtitle block is appended at timestamp 0.0, overlapping the first line of speech.

**Blast radius**: Any job with `resume_from_last=True` + `cta_enabled=True` where the per-part SRT already exists.

**Minimal fix**:
```python
_srt_meta: dict = {}
if needs_srt:
    _srt_meta = slice_srt_by_time(...)
elif srt_part.exists() and srt_part.stat().st_size > 0:
    # Read metadata from existing file so CTA / logging use correct timestamps
    _srt_meta = _read_srt_meta(str(srt_part))
```

Where `_read_srt_meta` calls the existing `slice_srt_by_time` return-value shape (or a lightweight parser that returns the same keys).

---

### [P1] Resume cache: mutations re-applied to already-mutated SRT

**Location**: `render_pipeline.py:3560–3729`

**Code path**:

All mutation calls (`_apply_subtitle_edits_to_srt`, `apply_market_hook_text_to_srt`, `apply_market_line_break_to_srt`, `apply_hook_subtitle_format`, `subtitle_emphasis_pass`) run **unconditionally** after the `if needs_srt:` block. They modify `_ass_srt_source` (the per-part SRT) in place. When `needs_srt=False`, `_ass_srt_source` points to the SRT file that was already written and mutated in the previous run.

Result on second resume pass:
- Hook text is appended a second time to blocks that already have it
- Emphasis tags (uppercase, bold, highlight markers) are applied twice
- Market line breaks are inserted again into already-broken lines
- CTA block is appended at t=0 (P0 above)

The fact that `needs_ass=True` may be triggered means the ASS is regenerated from the double-mutated SRT — visible garbage in subtitles.

**Minimal fix**: Guard mutations behind `if needs_srt:` (since they operate on the SRT), or add an idempotency stamp to the SRT header that the mutation functions can check.

---

### [P2] Platform speed delta not applied to subtitle slice speed

**Location**: `render_pipeline.py:3450, 3997–4001`

**Subtitle slice speed** (line 3450):
```python
_eff_speed = max(0.5, min(1.5, float(payload.playback_speed or 1.0)))
```

**Render playback speed** (lines 3997–4001):
```python
playback_speed=float(
    seg.get("variant_playback_speed")
    or max(0.5, min(1.5, float(payload.playback_speed or 1.07)
           + _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0)))
)
```

Platform speed deltas (`_PLATFORM_PROFILES`):
- `tiktok`: `speed_delta=+0.08`
- `youtube_shorts`: `speed_delta=0.0` (no drift)
- `instagram_reels`: `speed_delta=-0.06`

At `payload.playback_speed=1.07`:
- TikTok video plays at **1.15x**, subtitles timed for **1.07x** → **7% timing drift**
- Instagram Reels video plays at **1.01x**, subtitles timed for **1.07x** → **5.6% timing drift (opposite direction)**
- On a 60s clip this is up to ~4.2s off by the end

The drift is cumulative from the start of each clip, so it becomes visible on clips longer than ~15s.

**Minimal fix**: Pass the platform-adjusted speed to `slice_srt_by_time`:
```python
_platform_speed_delta = _PLATFORM_PROFILES.get(_target_platform, {}).get("speed_delta", 0.0)
_eff_speed = max(0.5, min(1.5, float(payload.playback_speed or 1.0) + _platform_speed_delta))
```

Note: the commit `259858b fix: prevent subtitle speed from applying twice` added `apply_playback_speed=False` to the `slice_srt_by_time` call (line 3451). That fix prevents speed-adjusted timestamp compression in the SRT file — this fix is a **different and separate concern** (the raw timestamp window for slice selection). Verify the interaction: if `apply_playback_speed=False` stays, the slice window shifts correctly but timestamps in the output SRT remain unreduced, which is correct because the setpts filter handles actual playback speed.

---

### [P3] "Identical subtitles across parts" — no confirmed root cause in normal path

**Analysis**: In a non-resume run, file paths are unique, `_effective_start` is per-part, and `slice_srt_by_time` uses `(start, end)` from absolute source timestamps. No code path allows two parts to share a subtitle file.

**Candidate upstream causes** (require reproduction data to confirm):

1. **Segments have incorrect timestamps** — if `segment_builder.py` emits segments with `seg["start"]` and `seg["end"]` values that overlap or repeat, multiple parts slice the same time window and therefore get the same subtitle content.

2. **`full_srt` has sparse coverage** — if the source transcript covers only the first N seconds and all clips extend beyond that region, `slice_srt_by_time` returns the same N subtitles for every part (the only non-empty range).

3. **`full_srt` is not refreshed between parallel parts** — confirmed not an issue; `full_srt` is read-only after initial creation and all parts read from it independently.

4. **Race condition in parallel execution** — `idx` and `seg` are captured by value at `executor.submit(_process_one_part, idx, seg)` call time. No closure mutation issue was found.

**Recommended diagnostic step**: Emit `part_srt_path` + first two subtitle lines to the render event log (`subtitle_part_sync` already does this for normal runs — confirm it fires for every part).

---

### [P4] `apply_hook_subtitle_format` has no exception guard

**Location**: `render_pipeline.py:3627–3646`

```python
if _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
    _hook_orig_len = _ass_srt_source.stat().st_size
    _hook_blocks = apply_hook_subtitle_format(str(_ass_srt_source))   # no try/except
    if _hook_blocks > 0:
        needs_ass = True
```

All adjacent mutation calls (`apply_market_hook_text_to_srt`, `subtitle_emphasis_pass`) are inside `try/except` blocks. This one is not. An exception here will abort the entire part render.

**Minimal fix**: Wrap in `try/except Exception` with a `logger.warning` fallback, matching the pattern of the surrounding mutation calls.

---

## Broken Path Summary

```
resume_from_last=True, cta_enabled=True, srt_part exists
  → needs_srt = False
  → _srt_meta = {}            ← never populated
  → mutations run against stale (already-mutated) SRT in-place
  → _last_sub_end = 0.0       ← P0: CTA at t=0
  → double hook text           ← P1: visible SRT corruption on second resume
  → ASS regenerated from       ← P1: garbage subtitles if needs_ass=True
    double-mutated SRT
```

```
target_platform=tiktok, payload.playback_speed=1.07
  → _eff_speed for slice = 1.07
  → render playback_speed = 1.15
  → subtitle timestamps timed for 1.07x video
  → video plays 7% faster than subtitles expect
  → progressive drift: ~0.07s/s, ~4.2s off at 60s mark   ← P2: timing drift
```

---

## Regression Risk

| Fix | Regression risk |
|---|---|
| Initialize `_srt_meta` from existing SRT on resume | Low — only affects resume path, adds a lightweight SRT read |
| Guard mutations behind `if needs_srt:` | Medium — must verify mutation ordering; double-check translation resume path (`_needs_translated` is cached separately) |
| Apply platform speed delta to `_eff_speed` | Medium — changes subtitle timing behavior for TikTok/Instagram; must verify against `apply_playback_speed=False` (commit `259858b`) to confirm no double-application |
| Wrap `apply_hook_subtitle_format` in try/except | Low — pure defensive hardening |

---

## Recommended Debug Logging Additions

Add to `subtitle_part_sync` event context (lines 3481–3496) for all resume-path runs:

```python
"resume_cache_hit_srt": not needs_srt,
"resume_cache_hit_ass": not needs_ass,
"srt_meta_from_resume": needs_srt is False,  # flags that _srt_meta may be stale
```

Add to `cta_appended` event context (line 3758):

```python
"last_sub_end_source": "live" if needs_srt else "resume_missing",
```

Add after ASS conversion for per-part forensics:

```python
_job_log(effective_channel, job_id,
    f"subtitle_file_chain part={idx} "
    f"srt={srt_part} srt_size={srt_part.stat().st_size if srt_part.exists() else 0} "
    f"ass={ass_part} ass_size={ass_part.stat().st_size if ass_part.exists() else 0} "
    f"source_srt={_ass_srt_source} needs_srt={needs_srt} needs_ass={needs_ass}",
    kind="debug"
)
```

---

## Manual QA Checklist

- [ ] Run a job with `resume_from_last=False` and `cta_enabled=True` on TikTok — verify CTA appears at end of each clip, not at 0:00
- [ ] Run a job with `resume_from_last=True` (workdir exists, `_part_NNN.srt` present) and `cta_enabled=True` — verify CTA appears at correct position
- [ ] Compare subtitle timing on TikTok vs YouTube Shorts for the same source and `playback_speed=1.07` — TikTok should show drift before fix, align after
- [ ] Run a two-part job, inspect `_part_001.srt` and `_part_002.srt` content — confirm they contain different subtitle lines
- [ ] Enable `resume_from_last=True`, run once, interrupt, resume — inspect subtitle files for double hook text or double emphasis markup
- [ ] Run a job with `apply_hook_subtitle_format` returning 0 blocks — confirm part render completes normally
