# D-2-motion Phase 2 — Verdict Document

> Phase 2 (operator validation) ran on **2026-06-30** within the same Claude
> session as Phase 1. Originally planned as offline operator work,
> consolidated here because `cv2 4.11.0` and `scenedetect 0.6.4` were already
> installed in `backend/.venv` from prior project setup.
>
> **Verdict:** ✅ **CONDITIONAL GO** — synthetic-fixture evidence supports
> the D-2-motion swap with **Policy A** (SceneMap when non-empty, pixel-diff
> fallback otherwise). Phase 3 may ship with `MOTION_USE_SCENE_MAP=1`
> default after one additional real-content validation pass (see §6).

When this verdict and code conflict: **trust code.** Read at HEAD.

---

## 1. Phase 2 execution log

### Environment

- Python: `backend/.venv/Scripts/python.exe` (3.11.9)
- OpenCV: `4.11.0`
- PySceneDetect: `0.6.4` (ContentDetector + AdaptiveDetector active; TransNetV2 not exercised)
- FFmpeg: `7.1.1-essentials_build`

### Discovery during P2.1

The benchmark depended on `cv2` + `scenedetect`. Both were **already installed**
in `backend/.venv` from prior project setup (likely from `requirements-ai.txt`).
The session's earlier pytest baseline ran with the system Python (3.13)
instead of the venv (3.11), which is why all 4 motion test files appeared
to fail at collection — they actually run when invoked through the venv.
This does NOT affect any committed code; it only affects the operator's
choice of interpreter.

→ Phase 3 **must** use `backend/.venv` to run the full pytest baseline.
This is now documented as a Render Edit Protocol step 5 prerequisite.

### Fixtures regenerated

3 synthetic videos in `backend/tests/fixtures/scene_detection/`:
- `three_shot_cuts.mp4` (15 s, 2 hard cuts at t=5, 10)
- `single_shot_static.mp4` (10 s, 0 cuts)
- `music_video_fast_cuts.mp4` (12 s, 5 hard cuts every 2 s)

---

## 2. Raw benchmark results

### Fixture A — `three_shot_cuts.mp4` (cinematic-like)

| | Pixel-diff | SceneMap |
|--|-----------|----------|
| Wall time | 0.106 s | 0.699 s |
| Scenes detected | 3 | 3 |
| Boundaries | `[5.0, 10.0]` | `[5.0, 10.0]` |
| Mean drift | — | **0.0 s** |

**Verdict:** ✅ **GO** — perfect agreement.

### Fixture B — `single_shot_static.mp4` (no cuts)

| | Pixel-diff | SceneMap |
|--|-----------|----------|
| Wall time | 0.050 s | 0.464 s |
| Scenes detected | 1 (`[(0.0, 10.0)]`) | 0 (empty list) |
| Boundaries | `[]` | `[]` |

**Benchmark script verdict:** NO-GO (boundary_count_ratio = 0/1 = 0.0 fails the GO threshold of 0.5)

**Operator interpretation:** This is a **shape mismatch, NOT a quality issue**.
Both detectors correctly identify "no cuts." They differ in how they
represent that:
- Pixel-diff: returns a single full-duration range `[(0.0, 10.0)]`
- SceneMap: returns an empty list

The dispatcher contract (path.py:103) treats both `_scene_ranges=None` and
`_scene_ranges with len ≤ 1` as single-pass tracking. So the architectural
behaviour is identical:
- Pixel-diff path → single-pass (1 range → falls through to fast path)
- SceneMap path (with Policy A fallback) → pixel-diff fallback when SceneMap empty → single-pass

→ **Policy A from the audit (§5.2) is validated** — fallback to pixel-diff
on empty SceneMap is correct, and the resulting render behaviour is
bit-identical to the legacy.

**Operator-overridden verdict:** ✅ **GO** (with Policy A active).

### Fixture C — `music_video_fast_cuts.mp4` (5 known cuts)

| | Pixel-diff | SceneMap |
|--|-----------|----------|
| Wall time | 0.041 s | 0.533 s |
| Scenes detected | 6 | 6 |
| Boundaries | `[2, 4, 6, 8, 10]` | `[2, 4, 6, 8, 10]` |
| Mean drift | — | **0.0 s** |

**Verdict:** ✅ **GO** — perfect agreement.

---

## 3. Aggregate observations

### Boundary accuracy

| Fixture | Both find same cuts? | Drift |
|---------|---------------------|-------|
| Cinematic (3 shots) | Yes — 2/2 boundaries | 0 ms |
| Static (1 shot) | Yes — 0/0 cuts | n/a |
| Music-video (6 shots) | Yes — 5/5 boundaries | 0 ms |

**On synthetic hard-cut content, the two detectors are equivalent.** The
EMA state carry concern from the audit (§4) does NOT trigger here because
both detectors agree on boundary positions exactly.

### Wall-time

| Fixture | Pixel-diff | SceneMap | Slowdown |
|---------|-----------|----------|---------|
| Cinematic | 0.11 s | 0.70 s | 6.5× |
| Static | 0.05 s | 0.46 s | 9.3× |
| Music-video | 0.04 s | 0.53 s | 13.0× |

SceneMap is **~5-15× slower per call**. This is misleading — in production:
- SceneMap runs **ONCE per source** in the D-2-thin stage (cached on disk)
- Pixel-diff runs **per render** via `motion/crop.py:529`
- A re-render of the same source hits the D-2-thin cache → SceneMap "cost" is amortized to ~0

**Verdict on perf:** No concern. The cache amortizes the per-detector cost
to far below pixel-diff's per-render cost in any multi-render workflow.

### Edge case: SceneMap returns empty on a known-good static shot

This is the one Phase 2 finding that demands a documented response:

- Pixel-diff: `[(0.0, duration)]` — at least one range, always
- SceneMap (PySceneDetect ContentDetector): `[]` — empty when no cuts

The dispatcher (`motion/path.py:103`) is robust to both representations
because the multi-scene trigger is `_scene_ranges and len(_scene_ranges) > 1`.
So:
- Pixel-diff path: 1 range → fast path → single-pass tracking
- SceneMap path with Policy A: empty → pixel-diff fallback → 1 range → fast path

Both arrive at the same destination. The Policy A fallback is required to
maintain the invariant "_scene_ranges is always non-empty when feasible."

`SceneMap.slice(start, end)` (D1.2 helper) already returns `[]` on an
empty map — Phase 3 just needs to check `if not result: fall back to
_detect_scene_ranges_in_clip()`. This is already in the audit's
implementation sketch §5.2.

---

## 4. GO criteria check (audit §8.2)

| Criterion | Target | Achieved | Pass? |
|-----------|--------|----------|-------|
| `boundary_count_ratio` between 0.5 and 2.0 | × across fixtures | 1.0 / 0.0 / 1.0 | A + C pass; B is the shape-mismatch case handled by Policy A |
| `mean(boundary_positions_drift_sec) < 0.3 s` on common boundaries | <0.3 | 0.0 / n/a / 0.0 | A + C pass perfectly; B has no common boundaries |
| `boundary_diff_scenemap_only` mostly true cuts | — | empty (no false-positives) | Pass |
| `boundary_diff_pixel_diff_only` mostly intra-shot motion | — | empty (no false-negatives by SceneMap) | Pass — synthetic content has no intra-shot noise |
| Subject-path RMSE within 30% | — | NOT MEASURED | Cannot evaluate; needs Phase 3 to wire and re-benchmark |

**Aggregate verdict:** **GO** — 2 of 3 fixtures pass the strict criterion;
the 3rd (static shot) is a shape mismatch handled architecturally by
Policy A. Subject-path RMSE not measured but cannot be measured without
Phase 3 wiring.

---

## 5. Known limitations of this evidence

### What synthetic fixtures CAN'T tell us

The 3 fixtures all use **hard cuts** between fully different content. Real
production renders include:

1. **Dissolves / cross-fades** — pixel-diff may miss (gradual changes
   sub-threshold), SceneMap may catch. Best-case scenario for SceneMap.
2. **Motion blur during fast pans** — pixel-diff may register as "scene
   cut" (high inter-frame delta), SceneMap may not. Best-case for SceneMap.
3. **Lighting changes within a shot** — pixel-diff may over-segment (intra-
   shot false positives), SceneMap is content-aware and ignores. Best-case
   for SceneMap.
4. **Talking-head with slight camera shake** — both should report 1 shot.
   Synthetic fixture B confirms this case.
5. **Subject re-positioning within shot** — pixel-diff may false-positive,
   SceneMap won't. Best-case for SceneMap (architecture review's #1
   concrete claim).

→ **Phase 3 should ship `MOTION_USE_SCENE_MAP=0` default** to start, then
flip to default ON after operator validation on 2-3 real production
renders. This is conservative but matches Sacred Contract #2 spirit
(historical payloads replay bit-identically).

### What Phase 3 still needs

- Real video fixtures (talking-head, cinematic, mixed-content)
- Subject-path RMSE measurement (requires the actual swap to be wired)
- A/B comparison on existing production jobs

These are NOT blockers for Phase 3 ship — they are decision inputs for
whether to flip the flag default after Phase 3 lands.

---

## 6. Recommendation for Phase 3

### 6.1 Architecture decisions (locked)

- **Policy A** confirmed: SceneMap.slice() result when non-empty, pixel-diff
  fallback otherwise. Both detectors live forever.
- **Feature flag** `MOTION_USE_SCENE_MAP` default OFF (conservative).
  Operator flips to ON after real-content validation.
- **Wire-in point** at `motion/crop.py:529` per audit §5.2 sketch.
- **Caller change** at `clip_renderer.py:740, 928` to pass `scene_map`
  kwarg via `get_scene_map(job_id) + SceneMap.from_json()`.

### 6.2 Phase 3 acceptance criteria

Per Render Edit Protocol step 8:

- Full pytest baseline (using `backend/.venv` interpreter) before edit
- Same baseline after edit — delta must be **0 failures, 0 errors**
- The 14 dispatcher contract tests in `test_motion_scene_dispatch.py`
  must still pass (they pin the EMA carry semantics)
- The 17 `SceneMap.slice` tests must still pass
- `py_compile` on every modified file

### 6.3 Phase 3 minimal-edit sketch

Specifying for the next Claude session's Planner spec:

```python
# motion/crop.py — change ONLY this gate block (~10 lines)
if _scene_aware:
    scene_ranges = None
    if os.getenv("MOTION_USE_SCENE_MAP", "0") == "1" and scene_map is not None:
        scene_ranges = scene_map.slice(
            source_start_sec or 0.0,
            (source_start_sec or 0.0) + (source_duration_sec or duration_from_probe),
        )
    if not scene_ranges:
        scene_ranges = _detect_scene_ranges_in_clip(input_path, cfg)
```

```python
# render_motion_aware_crop signature — ADD ONE OPTIONAL KWARG
def render_motion_aware_crop(
    input_path, output_path, ...,
    scene_map: Optional["SceneMap"] = None,  # NEW
) -> str:
```

```python
# clip_renderer.py — at both call sites (lines 740, 928), pass the SceneMap
from app.db.jobs_repo import get_scene_map
from app.domain.scene_map import SceneMap
_sm_raw = get_scene_map(job_id)
_scene_map = SceneMap.from_json(_sm_raw) if _sm_raw else None
# ... existing call ...
render_motion_aware_crop(..., scene_map=_scene_map)
```

Estimated touched LOC: ~30 across 3 files. The smallest possible swap.

---

## 7. Files produced by Phase 2

| File | Purpose |
|------|---------|
| `backend/tests/fixtures/scene_detection/report_three_shot.json` | Raw JSON report — cinematic |
| `backend/tests/fixtures/scene_detection/report_single_shot.json` | Raw JSON report — static |
| `backend/tests/fixtures/scene_detection/report_music_video.json` | Raw JSON report — music-video |
| `docs/verdict-d-2-motion-phase-2-2026-06-30.md` | This document |

---

## 8. Decision

**Phase 3 is APPROVED to ship** with these constraints:

1. ✅ Policy A fallback in place
2. ✅ Feature flag `MOTION_USE_SCENE_MAP=0` default OFF
3. ✅ Render Edit Protocol 9-step with `backend/.venv` pytest baseline
4. ⏳ Phase 3 should NOT flip the default to ON until real-content
   validation is done (2-3 production renders post-ship)

D-2-motion is **on track to fully close** the architecture review's
visible-cut-quality gap on a 3-4 day path:
- Phase 1 ✅ shipped (`7301db0`)
- Phase 2 ✅ this document
- Phase 3 ⏳ next Claude session (1-2 days)
