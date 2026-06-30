# Architecture Audit — D-2-motion (Replace motion/crop.py scene detector with SceneMap)

> Phase 1 deliverable D1.1 from the architecture review's D-2-motion plan
> (2026-06-30). Investigates whether the pixel-diff scene detector in
> `motion/crop.py` can be safely replaced by the SceneMap produced by
> `scene_map_stage` (Batch D-2-thin, commit `0caf895`). Output is an
> evidence-backed GO/NO-GO recommendation for Phase 3 implementation.
>
> **Verdict:** ✅ **CONDITIONAL GO** — architecture is compatible by
> construction; the swap requires a feature flag + Phase 2 A/B benchmark
> + a documented fallback policy. Specific risks enumerated below.

When this doc and code conflict: **trust code.** Read at `0caf895` HEAD.

---

## 1. Current state — pixel-diff detector

### 1.1 Where it lives

[`backend/app/features/render/engine/motion/pixel_diff.py:221-277`](../backend/app/features/render/engine/motion/pixel_diff.py#L221-L277).

Public function: `_detect_scene_ranges_in_clip(video_path: str, cfg: MotionCropConfig) -> List[Tuple[float, float]]`.

### 1.2 Algorithm (5 lines)

1. **Downsample** each sampled frame to 160×90, convert BGR→grayscale ([pixel_diff.py:247-248](../backend/app/features/render/engine/motion/pixel_diff.py#L247-L248))
2. **Frame skip** at `fps / 6` (e.g. 5 fps on 30 fps source — [pixel_diff.py:234](../backend/app/features/render/engine/motion/pixel_diff.py#L234))
3. **Pixel-diff** = `mean(absdiff(prev_gray, gray))` ([pixel_diff.py:250](../backend/app/features/render/engine/motion/pixel_diff.py#L250))
4. **Threshold** `cfg.scene_cut_threshold` (default 30.0 — [config.py default](../backend/app/features/render/engine/motion/config.py)) → flag as cut
5. **Debounce** 0.35 s minimum between consecutive cuts ([pixel_diff.py:253](../backend/app/features/render/engine/motion/pixel_diff.py#L253))

### 1.3 Output contract

- **Shape:** `List[Tuple[float, float]]` — chronological, non-overlapping ranges in source-global seconds
- **Time domain:** source-global (range `start_sec` = seconds from file start — [pixel_diff.py:252](../backend/app/features/render/engine/motion/pixel_diff.py#L252))
- **Always non-empty:** worst case returns `[(0.0, duration)]` ([pixel_diff.py:270](../backend/app/features/render/engine/motion/pixel_diff.py#L270))
- **File-open failure:** returns `[(0.0, 0.0)]` — degenerate single-range with zero duration ([pixel_diff.py:224](../backend/app/features/render/engine/motion/pixel_diff.py#L224))
- **Determinism:** yes — pure OpenCV image processing, no RNG

### 1.4 Call site

Single caller: [`motion/crop.py:529`](../backend/app/features/render/engine/motion/crop.py#L529) inside `render_motion_aware_crop`. Gated by `cfg.scene_aware_tracking and not _fuse_window_mode` ([motion/crop.py:527](../backend/app/features/render/engine/motion/crop.py#L527)).

### 1.5 What "scene-aware" gains today

Result feeds [`motion/path.py:103-156`](../backend/app/features/render/engine/motion/path.py#L103-L156). When 2+ ranges:

1. **Per-range dispatcher** calls `build_subject_path_scene` for each `(start_sec, end_sec)` ([path.py:111-118](../backend/app/features/render/engine/motion/path.py#L111-L118))
2. **Tracker re-init** at each scene boundary — subject identity NOT carried (commented in [path_scene.py:130-132](../backend/app/features/render/engine/motion/path_scene.py#L130-L132))
3. **EMA continuity** via `warmup_center`: the previous scene's final crop center seeds `smooth_cx, smooth_cy` so the camera doesn't snap back to frame center ([path_scene.py:133-148](../backend/app/features/render/engine/motion/path_scene.py#L133-L148))

When 0 or 1 range → single-pass fallback path ([path.py:158+](../backend/app/features/render/engine/motion/path.py#L158)), no scene awareness.

---

## 2. Replacement candidate — SceneMap from D-2-thin

### 2.1 Where it lives

[`backend/app/domain/scene_map.py`](../backend/app/domain/scene_map.py) — produced by [`scene_map_stage.run_scene_map`](../backend/app/features/render/engine/pipeline/scene_map_stage.py) which wraps [`scene_detector.detect_scenes`](../backend/app/features/render/engine/pipeline/scene_detector.py).

### 2.2 Algorithm (PySceneDetect + TransNetV2)

- **ContentDetector** threshold 28.0 ([scene_detector.py:360](../backend/app/features/render/engine/pipeline/scene_detector.py#L360))
- **AdaptiveDetector** when available — adaptive_threshold=3.0, min_content_val=15.0 ([scene_detector.py:363-373](../backend/app/features/render/engine/pipeline/scene_detector.py#L363-L373))
- **TransNetV2 merge** (when available) with 0.5 s dedup gap and 0.5 s min scene duration
- **Frame skip** auto-tuned via `_auto_frame_skip(fps)` targeting ~8 fps analysis rate
- **Determinism:** yes for ContentDetector + AdaptiveDetector path; TransNetV2 is deterministic given the model

### 2.3 Output (after stage wrapping)

`SceneMap` dataclass with `shots: list[Shot]`. Each `Shot` carries `start`, `end`, `transition_score`.

To plug into `motion/crop.py`'s contract, we need a **slice helper** that returns `List[Tuple[float, float]]` filtered to a `[start_sec, end_sec]` window — this is **D1.2 deliverable** (separate file in Phase 1).

### 2.4 Persistence

[`jobs.scene_map_json`](../backend/app/db/migration_steps/0014_jobs_add_scene_map_json.py) — populated by `scene_map_stage` for Recap jobs today (Clip jobs would need C.1 wiring). Loaded via `SceneMap.from_json(get_scene_map(job_id))`.

---

## 3. Boundary precision analysis

### 3.1 Side-by-side detection characteristics

| Property | Pixel-diff | SceneMap |
|----------|-----------|----------|
| Resolution analysed | 160×90 (downsampled) | Full / auto-downscaled (720p cap) |
| Sample cadence | fps/6 (~5 fps on 30 fps source) | Auto-tuned ~8 fps |
| Primary signal | Pixel intensity diff over time | Content delta + adaptive luminance |
| Catches mid-shot lighting / zoom | ✅ — registers as "scene cut" | ❌ — only true shot boundaries |
| Catches subtle dialogue cut (continuity-of-take) | ⚠️ depends on threshold | ❌ |
| Catches sharp shot boundary | ✅ | ✅ |
| Catches fade-to-black | ⚠️ depends on rate | ✅ |
| Catches dissolve | ⚠️ often misses | ⚠️ depends on length |

**Conclusion:** the two detectors are NOT equivalent on the same source. They make different editorial classifications of "what is a scene."

### 3.2 Boundary position drift estimate

Both detectors are time-quantized:
- Pixel-diff resolution: `1/(fps/6) ≈ 0.2 s` on 30 fps source
- SceneMap (ContentDetector): `1/(fps/8) ≈ 0.125 s` on 30 fps source

So even on agreed boundaries, position can differ by up to ~0.2 s = ~6 frames @ 30 fps. This is **within the same order** as the existing 0.35 s pixel-diff debounce window — production-acceptable in isolation, but see §4.

---

## 4. EMA state carry analysis — the real risk

Hot path: [`path.py:148-152`](../backend/app/features/render/engine/motion/path.py#L148-L152) and [`path_scene.py:133-148`](../backend/app/features/render/engine/motion/path_scene.py#L133-L148).

### 4.1 Mechanics

After scene N renders, its final crop center `(last_x, last_y)` is converted to a center coordinate `(cx, cy)` and stored as `_warmup_center`. Scene N+1 starts its EMA loop from `smooth_cx = warmup_center[0]`, `smooth_cy = warmup_center[1]` instead of frame center.

```python
# path.py:148-152
if scene_centers:
    _last_x, _last_y = scene_centers[-1]
    _warmup_center = (_last_x + crop_w / 2.0, _last_y + crop_h / 2.0)
```

### 4.2 Why boundary drift matters here

Consider a 30 s source with one true shot boundary at t=15.0 s.

**Pixel-diff scenario:** detects boundary at t=15.1 s (sample-aligned).
- Scene 0 = [0.0, 15.1]
- Scene 1 = [15.1, 30.0]
- The last frame of scene 0 (at t=15.0667) is the LAST frame of the OLD shot — subject is the previous person
- `warmup_center` carries the old subject's crop center into scene 1
- Scene 1's tracker re-locks immediately (`should_detect = True` on entry — [path_scene.py:232](../backend/app/features/render/engine/motion/path_scene.py#L232)), EMA glides over

**SceneMap scenario:** detects boundary at t=14.9 s (TransNetV2 may align differently).
- Scene 0 = [0.0, 14.9]
- Scene 1 = [14.9, 30.0]
- The last frame of scene 0 (at t=14.867) is still the OLD shot
- `warmup_center` carries the old subject's crop center into scene 1
- Same re-lock behaviour

**Conclusion:** boundary drift of ±0.2 s on either side of a true cut does NOT change the qualitative state carry — both detectors carry the prior-shot final position into the new shot's seed. **The risk is bounded.**

### 4.3 Where it could break — false-positive cut in one detector, not the other

This is the **real architectural risk**:

Scenario: a 30 s talking-head clip with a single shot (no real cut). Subject moves slightly at t=10 s (re-positions).

- **Pixel-diff:** registers t=10.0 as a "cut" because the pixel delta crosses threshold during the motion
- **SceneMap:** registers NO cut — this is still the same shot

Today's behaviour with pixel-diff:
- Scene 0 = [0, 10]
- Scene 1 = [10, 30]
- At t=10, tracker re-initializes. If the subject was being tracked smoothly, the re-lock may briefly drop tracking → camera path stutters
- Operators accept this as known behaviour

Future behaviour with SceneMap:
- One single range [0, 30]
- Single-pass tracking — no re-init at t=10
- Subject path is **smoother** (no false-positive re-lock)

→ **In this scenario, SceneMap is clearly better.** Single-pass tracking on a single-shot input is the architecturally correct answer.

### 4.4 Where it could break — true cut detected by one detector, not the other

Scenario: a 30 s clip with a fast crossfade dissolve at t=15 s. Both shots are similar content (e.g. two over-the-shoulder shots of the same conversation).

- **Pixel-diff:** dissolve causes gradual pixel changes — none individually exceeding threshold 30.0 → NO cut detected
- **SceneMap (TransNetV2):** trained on cinematic transitions — likely detects the dissolve as a boundary

Today's behaviour:
- Scene 0 = [0, 30]
- Single-pass tracking through the dissolve
- If the dissolve is between two near-identical compositions, this is fine
- If the dissolve switches subject focus, tracker may briefly lose lock around t=15 then re-acquire

Future behaviour:
- Scene 0 = [0, 15], Scene 1 = [15, 30]
- Tracker re-init at t=15
- If shots are different subjects, re-init is the **right** behaviour
- If shots are similar, re-init introduces a brief lock loss that wasn't there before — **subtle regression**

→ **Verdict:** mixed. Quantitatively measurable via A/B benchmark (Phase 2).

---

## 5. Fallback policy — critical decision point

### 5.1 What happens when SceneMap is unavailable

Failure modes:
- `scene_map_json` is NULL (D-2-thin disabled, kill switch, missing dep)
- `SceneMap.from_json(...)` returns None (malformed blob)
- `SceneMap.is_empty()` (zero shots detected)

### 5.2 Three policy options

| Option | Behaviour when SceneMap absent | Pros | Cons |
|--------|-------------------------------|------|------|
| **A. Fallback to pixel-diff** | Run `_detect_scene_ranges_in_clip` as today | Bit-identical to current behaviour; safest | Two scene-detection codepaths to maintain forever |
| **B. Disable scene-aware** | Set `scene_ranges = None`, run single-pass tracking | Single codepath; matches modern architecture | Loses scene-aware EMA continuity when SceneMap missing — regression for jobs where D-2-thin didn't run |
| **C. Synthetic single range** | Return `[(0.0, duration)]` | Single codepath, never regresses single-pass | Same as B in practice; pointless distinction |

**Audit recommendation: A.** Pixel-diff is cheap (~50ms per clip), production-proven, and required for any job that doesn't have SceneMap (e.g. legacy Recap jobs, future Clip jobs before C.1 wires SceneMap into render_pipeline). Keep both detectors; SceneMap wins when available.

This is implemented as:

```python
# motion/crop.py:529 — proposed Phase 3 edit
if cfg.scene_aware_tracking and not _fuse_window_mode:
    scene_ranges = None
    if persisted_scene_map is not None and not persisted_scene_map.is_empty():
        scene_ranges = persisted_scene_map.slice(
            source_start_sec or 0.0,
            (source_start_sec or 0.0) + (source_duration_sec or duration_from_probe),
        )
    if not scene_ranges:
        scene_ranges = _detect_scene_ranges_in_clip(input_path, cfg)
```

### 5.3 Where `persisted_scene_map` comes from

New optional kwarg on `render_motion_aware_crop`:

```python
def render_motion_aware_crop(
    input_path: str, output_path: str,
    ...,
    scene_map: Optional["SceneMap"] = None,  # NEW Phase 3
) -> str:
```

Caller (`clip_renderer.py:740, 928`) loads the SceneMap from `jobs.scene_map_json` via `get_scene_map(job_id)` + `SceneMap.from_json(...)` and passes it in. When the caller doesn't have a job_id context (e.g. preview tooling), it passes `None` and falls through to pixel-diff. **Sacred Contract #3 spirit preserved.**

---

## 6. Risk matrix (10 failure modes ranked)

| # | Failure mode | Probability | Impact | Mitigation |
|---|--------------|------------|--------|------------|
| 1 | False-positive pixel-diff cut on talking-head → over-segmented today; SceneMap fixes it but operators notice the change | **High** | Low (positive change) | Document in CHANGELOG |
| 2 | Dissolve detected by SceneMap but not pixel-diff → adds a re-lock that wasn't there | Medium | Low | Verifiable in A/B benchmark; per-content-type tuning |
| 3 | SceneMap missing (legacy Recap jobs) → fallback to pixel-diff | High | None | Policy A (fallback) covers this |
| 4 | `SceneMap.slice()` window crosses a shot mid-shot → partial-shot range fed to dispatcher | High (every multi-shot job) | Low | Slice helper clips boundaries; dispatcher already handles partial ranges (pixel-diff also produces them) |
| 5 | `source_start_sec`/`source_duration_sec` not provided to `render_motion_aware_crop` → cannot slice | Medium (preview tool path) | Low | Default to single-pass when window unknown |
| 6 | SceneMap detected boundary lands inside a sentence the LLM picked → cuts mid-sentence in recap | Low (D-2-snap already snaps to nearest shot) | Low (D-2-snap mitigates) | Combine with D-2-snap (already shipped) |
| 7 | `cfg.scene_aware_tracking=False` operator override → pixel-diff and SceneMap both bypassed | Always (by design) | None | Single-pass tracking unchanged |
| 8 | OpenCV crashes inside `_detect_scene_ranges_in_clip` mid-fallback → propagates | Very low | Medium | Existing try/except in pixel_diff.py:271-275 |
| 9 | TransNetV2 over-detects on a music-video → many short shots → multi-scene dispatch loops N times | Low | Medium (perf) | Cap shot count in `SceneMap.slice()` |
| 10 | `MOTION_USE_SCENE_MAP=0` kill switch left on after Phase 3 ship → architecture review gap not closed in production | Low | Low (operational) | Document the flag default in P3 commit message |

---

## 7. Decision tree

```
render_motion_aware_crop called
└─ scene_aware_tracking ON?
   ├─ NO → single-pass tracking (unchanged)
   └─ YES → which detector?
            ├─ MOTION_USE_SCENE_MAP=0 (kill switch) → pixel-diff (today's behaviour, default after Phase 1)
            └─ MOTION_USE_SCENE_MAP=1 (Phase 3 default after Phase 2 GO):
                  ├─ persisted SceneMap available?
                  │   ├─ YES → SceneMap.slice(start, end) → multi-scene dispatch
                  │   └─ NO  → fallback to pixel-diff (Policy A)
                  └─ Slice returned empty? → fallback to pixel-diff
```

---

## 8. GO/NO-GO criteria for Phase 2 → Phase 3

### 8.1 What Phase 2 must measure

For each fixture video, the A/B benchmark script (D1.4) outputs JSON with:

- `boundary_count_pixel_diff: int` vs `boundary_count_scenemap: int`
- `boundary_positions_drift_seconds: list[float]` — for boundaries detected by BOTH, the time delta
- `boundary_diff_pixel_diff_only: list[float]` — boundaries pixel-diff detected, SceneMap didn't
- `boundary_diff_scenemap_only: list[float]` — boundaries SceneMap detected, pixel-diff didn't
- (Optional, needs cv2 + actual tracking) `subject_path_rmse: float` — RMSE of crop centers across the two detectors

### 8.2 GO criteria (suggested — operator can tune)

- `boundary_count` ratio between 0.5× and 2.0× across all fixtures
- `mean(boundary_positions_drift_seconds) < 0.3 s` on common boundaries
- `boundary_diff_scenemap_only` length is mostly true shot cuts (manually verified on 1-2 fixtures)
- `boundary_diff_pixel_diff_only` length is mostly intra-shot motion (not real cuts) — confirms architecture review's claim
- Subject path RMSE (if measured) within 30% of current production output

### 8.3 NO-GO criteria

Any of:
- SceneMap mass-misses true shot boundaries (count ratio < 0.5×)
- Boundary positions wildly differ (mean drift > 1 s) — would invalidate EMA state carry
- Subject path RMSE > 50% — visible quality regression

If NO-GO: ship D-2-prep (just `SceneMap.slice()` helper + audit) and document the deferral. Pixel-diff stays as the production detector.

---

## 9. Sacred Contracts impact

| # | Contract | Impact |
|---|----------|--------|
| 1 | output_rank_score / is_best_* | None — motion/crop.py doesn't touch result_json |
| 2 | RenderRequest additive defaults | None this audit; Phase 3 adds `MOTION_USE_SCENE_MAP` env var (not RenderRequest), default decided by Phase 2 |
| 3 | AI/render → None never raise | Pixel-diff fallback (Policy A) preserves this. SceneMap.slice should also return safe defaults — covered by D1.2 |
| 4 / 5 | Stage / part names | None |
| 6 | WS shape | None — no new events in Phase 3 (existing scene_map.* events from D-2-thin sufficient) |
| 7 | DB sole authority | None — uses existing `jobs.scene_map_json` column |
| 8 | qa_pipeline gate | None |

**CRITICAL pytest gate:** Phase 3 strictly requires cv2 in the test venv (current blocker). Phase 2 explicitly includes this prerequisite.

---

## 10. Final verdict

**✅ CONDITIONAL GO** for D-2-motion (Plan C-strict equivalent).

Conditions:
1. **Fallback Policy A** — keep pixel-diff as the fallback when SceneMap absent. Both detectors live forever; SceneMap wins when available.
2. **Phase 2 A/B benchmark** must pass GO criteria (§8.2). Failure → ship D-2-prep only, defer Plan C-strict.
3. **Feature flag** `MOTION_USE_SCENE_MAP` — default OFF after Phase 1, flip to ON after Phase 2 GO. Permanent kill switch for any future regression.
4. **CRITICAL pytest gate** — Phase 3 only happens after `cv2` is installed in the test venv. No exceptions.

Total path-to-ship: ~3-4 days across 3 phases (Phase 1 this session, Phase 2 offline ~1h, Phase 3 new session 1-2 days).

The "architecture review's #1 visible quality gap" (recap cuts land on dialog boundaries not shot boundaries) is ALREADY largely closed by D-2-snap reconciler (`13cfb6d`). D-2-motion's marginal value is **subject tracking quality during multi-shot cinematic content**, which is real but lower-priority than D-2-snap was.

---

## 11. What Phase 1 ships (this session, after audit)

| D | File | Purpose |
|---|------|---------|
| D1.2 | `backend/app/domain/scene_map.py` + tests | `SceneMap.slice(start, end) -> List[Tuple[float,float]]` — Phase 3 ready |
| D1.3 | `backend/tests/test_motion_scene_dispatch.py` | Mock-based pin of `build_subject_path` dispatch contract — Phase 3 regression net |
| D1.4 | `scripts/benchmark_scene_detection.py` + optional synthetic fixtures | Phase 2 GO/NO-GO tooling |

Plus this audit document.

After Phase 1 commit: Phase 2 is fully unblocked. The next Claude session has everything needed to execute Phase 3 confidently.
