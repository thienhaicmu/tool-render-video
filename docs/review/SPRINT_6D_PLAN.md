# Sprint 6.D — God-File Decomposition Plan

**Status:** Plan committed, no code moved. Per CLAUDE.md ⛔ Issue 4
("Remaining God Files"), decomposition requires "a dedicated multi-phase
plan + explicit user approval before any code touches." This document
IS that plan.

Future sessions execute one phase at a time. User must explicitly say
"execute Sprint 6.D-X.Y" to start a phase.

---

## §1 — Goals + non-goals

### Goals

- Each of the 3 god files reduced to **≤ 800 lines** (or ≤ 50% of original,
  whichever lands first) — the de-facto "single-screen" maintainability
  ceiling.
- Each extraction preserves byte-for-byte external behavior. Pytest
  baseline unchanged after every commit.
- Every extraction lands in its own commit with `git revert`-safe scope.
- After Sprint 6.D the audit ledger Issue 4 can be marked closed.

### Non-goals

- No rewrites. Move existing code into new modules; do not redesign while
  moving.
- No API changes. Public symbols imported elsewhere keep their import
  paths or get a re-export shim.
- No "while I'm here" improvements. Each commit is a pure mechanical
  extraction.

---

## §2 — CLAUDE.md constraints honored

| Rule | How honored |
|---|---|
| **Render Edit Protocol** | Every commit follows steps 1–9: read docs, plan, approve, baseline pytest, read actual file, minimal Edit, post-edit pytest, no regression-fixing in same session. |
| **Sacred Contracts 1–8** | All 8 contracts (result_json, RenderRequest defaults, AI return-None, job stage names, part stage names, _emit_render_event signature, app.db sole authority, qa_pipeline not bypassed) must remain intact after every extraction. Reviewer agent's auto-reject checklist is the gate. |
| **Frozen Stage Names** | String literals `QUEUED/DOWNLOADING/.../DONE/FAILED` for jobs and `QUEUED/WAITING/CUTTING/TRANSCRIBING/RENDERING/DONE/FAILED/SKIPPED` for parts cannot be renamed during a move. |
| **NVENC semaphore pattern** | Sprint 4.2 centralized NVENC handling — must not be undone by an extraction. |
| **Additive-only DB rule** | Decomposition does not touch the DB layer. |

---

## §3 — Per-file analysis

### §3.1 — render_pipeline.py (1525 lines)

Verified structure:

- One module-level helper: `_validate_text_layers_or_400` (line 198)
- One god function: `run_render_pipeline` (line 224 → file end at 1525) —
  ~1300 lines, single function

Sprint A–F refactors already extracted stage modules (`pipeline_segment_selection`,
`pipeline_ranking`, `pipeline_render_loop`, etc.). What remains is the
**glue code that wires those stages together**.

Logical sections inside `run_render_pipeline`:

1. Lines ~232–300: payload normalization, channel resolution, output-dir setup
2. Lines ~300–450: source preparation (download/local)
3. Lines ~450–700: TTS narration (optional)
4. Lines ~700–820: pre-render dispatch (`run_groq_only_pre_render` call)
5. Lines ~820–1000: full-video Whisper transcription
6. Lines ~1000–1180: per-part dispatch via `run_render_loop`
7. Lines ~1180–1280: output ranking + result_json assembly
8. Lines ~1280–1525: finalize, manifest writing, cleanup

Proposed extractions (revised after planning pushback — see §11 changelog):

The original plan ordered these least → most risky. After re-examination,
**1.5 (finalize block) is actually the safest first move** because it's
the last contiguous block of `run_render_pipeline` — a natural cleavage
point at end-of-function, not a middle-of-function slice. Doing 1.5 first
drops the function by ~245 lines in one safe commit and makes the
remaining ~1280-line middle easier to slice for 1.1–1.4.

| Phase | Extract | Target module | Risk |
|---|---|---|---|
| **6.D-1.5** | Finalize block (~1280–1525) — **execute first** | `orchestration/pipeline_finalize.py` | MEDIUM (touches Sprint 6.A backup + Sprint 6.C metrics hooks; both are 5-line additive blocks that copy verbatim) |
| **6.D-1.1** | Payload normalization + channel resolution (~232–300) | `orchestration/pipeline_setup.py` | LOW |
| **6.D-1.2** | Output-dir + manifest setup (~290–340) | (same file as 1.1) | LOW |
| **6.D-1.3** | Source preparation block (~300–450) | `orchestration/pipeline_source_prep.py` | MEDIUM |
| **6.D-1.4** | TTS narration block (~450–700) | `orchestration/pipeline_narration.py` | MEDIUM |

**Stop condition:** if any extraction would drop `run_render_pipeline`
below ~600 lines, stop. The 800-line ceiling is the goal; over-extraction
creates indirection without value.

**Risk re-categorization for 1.5:** downgraded from HIGH (in original plan)
to MEDIUM because the touchpoints with Sprint 6.A and 6.C are isolated
5-line additive blocks. The actual blast radius of moving 245 lines of
finalize is small — pytest covers the upsert + manifest writing paths.

### §3.2 — part_renderer.py (2101 lines)

Verified structure:

- `class PartRenderContext` (line 101) — ~50-line state holder
- `prepare_part_assets()` (line 157) — ~600 lines, asset planning per part
- `process_one_part()` (line 769) — ~1330 lines, per-part execution

`process_one_part` is the bigger problem. It traverses the
WAITING → CUTTING → TRANSCRIBING → RENDERING state machine for one clip.
Frozen part-stage names mean the function must remain a single logical unit
visible to a reader.

Proposed extractions:

| Phase | Extract | Target module | Risk |
|---|---|---|---|
| **6.D-2.1** | `PartRenderContext` (101–156) | `stages/part_render_context.py` | LOW (pure data) |
| **6.D-2.2** | `prepare_part_assets` (157–768) | `stages/part_asset_planner.py` | MEDIUM (calls back into render_pipeline helpers) |
| **6.D-2.3** | CUT stage block inside `process_one_part` | `stages/part_cut.py` | HIGH |
| **6.D-2.4** | TRANSCRIBE stage block | `stages/part_transcribe.py` | HIGH |
| **6.D-2.5** | RENDER + validate stage block | `stages/part_render_encode.py` | CRITICAL — calls FFmpeg + qa_pipeline |

Phases **2.3–2.5 are the riskiest in the entire plan.** They require:

- Passing all the function's local variables through explicit args
  (no closures across the move).
- Pin part-status string transitions at the exact lines they appear today.
- Full pytest after each extraction.

If 2.3–2.5 prove too risky during execution, the alternative is: leave
`process_one_part` as one big function and accept `part_renderer.py`
landing above 800 lines.

### §3.3 — motion_crop.py (2512 lines)

Verified structure (selected highlights):

- Lines 1–280: caches + ML dependencies (mediapipe, opencv)
- Lines 280–340: `MotionCropConfig` class
- Lines 340–485: helpers (codec flags, font detection, ffprobe, IoU)
- Lines 487–557: `_ByteTrackSubject` class (tracker)
- Lines 559–1058: detection + scoring helpers (~30 functions)
- Lines 1059–1389: `build_subject_path` (~330 lines)
- Lines 1389–1909: `build_subject_path_scene` (~520 lines, biggest single function)
- Lines 1909–2050: legacy motion path
- Lines 2052–2111: scene detection within clips
- Lines 2113–2139: `build_motion_path` (dispatcher)
- Lines 2139–2512: `render_motion_aware_crop` (~370 lines — FFmpeg invocation)

Proposed extractions (revised after planning pushback — see §11 changelog):

| Phase | Extract | Target module | Risk |
|---|---|---|---|
| **6.D-3.1** | Caches + ML lazy imports (1–130) | `services/motion_crop_cache.py` | LOW |
| **6.D-3.2** | `MotionCropConfig` + `_apply_content_type_to_cfg` | `services/motion_crop_config.py` | LOW |
| **6.D-3.3** | Generic helpers (codec flags, fonts, ffprobe, IoU, smoothing) | `services/motion_crop_utils.py` | LOW |
| **6.D-3.4** | `_ByteTrackSubject` + tracker creation | `services/motion_crop_tracker.py` | MEDIUM |
| **6.D-3.5a** | Detection helpers (`_detect_subjects_in_frame`, `_pick_best_subject`, `prepare_detection_frame`) | `services/motion_crop_detection.py` | MEDIUM |
| **6.D-3.5b** | Scoring helpers (`_score_subject_candidate`, `_is_plausible_subject`, `_filter_subject_candidates`, `_same_subject`, `_subject_*`) | `services/motion_crop_scoring.py` | MEDIUM |
| **6.D-3.5c** | Trackerless guard helpers (`_apply_trackerless_center_guard`, `_trackerless_*`) | `services/motion_crop_trackerless.py` | MEDIUM |
| **6.D-3.6a** | `build_subject_path` (~330 LOC, contiguous) | `services/motion_crop_path.py` | HIGH |
| **6.D-3.6b** | `build_subject_path_scene` (~520 LOC — may need further split during execution if interior seams exist) | (same file as 3.6a) | HIGH |
| **6.D-3.7** | Legacy motion path + scene-range detection | `services/motion_crop_legacy.py` | LOW (rarely-used code path) |
| **6.D-3.8** | `render_motion_aware_crop` stays in `motion_crop.py` | — | (target file ends at ~370 lines after all extractions) |

motion_crop.py is the **easiest** of the three despite being the largest.
The functions are mostly pure (helpers don't share state), and the layered
structure (cache → config → helpers → tracker → detection → path → render)
is already implicit.

---

## §4 — Risk matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hidden cross-file closures | MEDIUM | HIGH | Each extraction commit runs full pytest immediately; regression = revert |
| Frozen stage name accidentally renamed | LOW | CRITICAL | Grep-locked: every commit greps for stage strings before merge |
| Import cycle introduced | MEDIUM | MEDIUM | New modules import from siblings, not back into parent; caught at compile time |
| NVENC semaphore pattern broken | LOW | HIGH | Touchpoints in part_renderer are external acquire-then-call patterns that the codemod must preserve verbatim |
| Sacred Contract violated | LOW | CRITICAL | Every commit body includes Reviewer auto-reject checklist |

---

## §5 — Recommended execution order

**Across files** (easiest to riskiest):

1. `motion_crop.py` first (phases 3.1 → 3.7) — pure-function helpers,
   low coupling
2. `render_pipeline.py` middle (phases 1.1 → 1.5) — top-level glue, already
   partially decomposed
3. `part_renderer.py` last (phases 2.1 → 2.5) — frozen stage transitions
   make extractions delicate

**Within each file** (easiest to riskiest): the order in the per-file tables above.

**Per-phase gate:** every commit ends with green pytest + zero changes to
`docs/review/` audit-ledger findings. Red pytest = revert + stop.

---

## §6 — Per-phase commit template

```
refactor(<area>): Sprint 6.D-<N.M> — extract <unit> to <target_module>

Plan reference: docs/review/SPRINT_6D_PLAN.md §3.<X>.<Y>

Scope of this commit:
- Move <lines NNN-MMM of <source>> verbatim into <target>
- Update <source>'s import to re-export the moved symbol(s)
- Update <consumers> import paths (full grep included below)

What this does NOT do:
- No logic changes
- No signature changes
- No new tests (the existing pytest suite gates correctness)
- No "while I'm here" cleanups

Pytest: NNN passed (NNN baseline), 0 failed.
Grep for frozen stage names: unchanged.
Sacred Contract checklist: 8/8 intact.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## §7 — Stop conditions

Halt the entire Sprint 6.D if any of the following:

1. **Full pytest baseline drops** at any extraction — revert, investigate,
   restart from baseline (currently 2077 passed, 0 failed, 1 skipped as
   of commit `f361dcb`).
2. **A grep diff shows any frozen stage name renamed.** Critical
   Contract 4/5 violation.
3. **`_emit_render_event` signature changes.** Critical Contract 6.
4. **Any AI module under `backend/app/ai/**` gains a `raise` from a
   public entry point.** Critical Contract 3.
5. **A single commit grows beyond ~300 LOC moved.** Breaks the commit
   into smaller phases.

---

## §8 — User-approved defaults

Captured from the planning conversation:

- **Cadence:** one phase per session (forces tight Reviewer gate per phase)
- **Start file:** `motion_crop.py` (lowest coupling)
- **Done-enough criterion:** each god file ≤ 800 lines OR ≤ 50% of
  original, whichever lands first
- **Plan persistence:** this document, `docs/review/SPRINT_6D_PLAN.md`
- **Execution gate:** user explicitly says "execute Sprint 6.D-X.Y" for
  each phase. No phases run on the back of a generic "proceed" message.

---

## §9 — Summary

| File | Lines now | Target | Phases | Highest-risk phase |
|---|---|---|---|---|
| `motion_crop.py` | 2512 | ~370 (`render_motion_aware_crop` alone) | 7 | 6.D-3.6 (path builders) |
| `render_pipeline.py` | 1525 | ~500–700 (`run_render_pipeline` skeleton) | 5 | 6.D-1.5 (finalize) |
| `part_renderer.py` | 2101 | ~800–1000 (process_one_part may stay) | 5 | 6.D-2.5 (render+validate) |

**Total Sprint 6.D scope:** 23 commits across 3 files (after 2.4 re-scope
and 2.5 split — see §11 changelog). Estimated 5–8 sessions at one phase
per session.

**Net diff per phase:** ~+300 / −300 LOC (pure moves; lines relocate).

---

## §10 — Phase index (quick reference for future sessions)

| Phase ID | File | Target | Risk |
|---|---|---|---|
| 6.D-3.1 | motion_crop.py | services/motion_crop_cache.py | LOW |
| 6.D-3.2 | motion_crop.py | services/motion_crop_config.py | LOW |
| 6.D-3.3 | motion_crop.py | services/motion_crop_utils.py | LOW |
| 6.D-3.4 | motion_crop.py | services/motion_crop_tracker.py | MEDIUM |
| 6.D-3.5a | motion_crop.py | services/motion_crop_detection.py | MEDIUM |
| 6.D-3.5b | motion_crop.py | services/motion_crop_scoring.py | MEDIUM |
| 6.D-3.5c | motion_crop.py | services/motion_crop_trackerless.py | MEDIUM |
| 6.D-3.6a | motion_crop.py | services/motion_crop_path.py (build_subject_path) | HIGH |
| 6.D-3.6b | motion_crop.py | services/motion_crop_path.py (build_subject_path_scene; may split further) | HIGH |
| 6.D-3.7 | motion_crop.py | services/motion_crop_legacy.py | LOW |
| 6.D-1.5 | render_pipeline.py | orchestration/pipeline_finalize.py | MEDIUM (downgraded — execute first) |
| 6.D-1.1 | render_pipeline.py | orchestration/pipeline_setup.py | LOW |
| 6.D-1.2 | render_pipeline.py | (same file as 1.1) | LOW |
| 6.D-1.3 | render_pipeline.py | orchestration/pipeline_source_prep.py | MEDIUM |
| 6.D-1.4 | render_pipeline.py | orchestration/pipeline_narration.py | MEDIUM |
| 6.D-2.1 | part_renderer.py | stages/part_render_context.py | LOW |
| 6.D-2.2 | part_renderer.py | stages/part_asset_planner.py | MEDIUM |
| 6.D-2.3 | part_renderer.py | stages/part_cut.py | HIGH |
| 6.D-2.4 | part_renderer.py | stages/part_render_setup.py (was: part_transcribe.py — RE-SCOPED, see §11 entry 3) | HIGH |
| 6.D-2.5a | part_renderer.py | stages/part_render_encode.py (FFmpeg encode core, ~216 LOC) | HIGH |
| 6.D-2.5b | part_renderer.py | stages/part_voice_mix.py (voice TTS + audio mix, ~230 LOC) | HIGH |
| 6.D-2.5c | part_renderer.py | stages/part_render_finalize.py (pacing + scoring + qa_pipeline, ~430 LOC) | CRITICAL |
| 6.D-2.5d | part_renderer.py | stages/part_done.py (quality intel + cover + DONE, ~100 LOC) | HIGH |

To execute a phase, the user says e.g. **"execute Sprint 6.D-3.1"** —
that session reads this plan, executes only the named phase, gates on
green pytest, and stops.

---

## §11 — Changelog

| Date | Change |
|---|---|
| Initial commit (`419bb32`) | Original plan: 17 phases, motion_crop 7 / render_pipeline 5 / part_renderer 5. |
| Pushback revision (`0d8f643`) | Phase 3.5 split into 3.5a/b/c (the original "~30 functions" violated §7 stop condition #5). Phase 3.6 split into 3.6a/b (original 850 LOC violated same rule). render_pipeline phases reordered to put 1.5 first because it's the safest contiguous end-of-function slice; downgraded from HIGH to MEDIUM. Total phases now 20 (was 17). |
| Mid-execution revision (this commit) | **Phase 2.4 re-scoped.** Plan originally listed 2.4 as "TRANSCRIBE stage block → `part_transcribe.py`". By the time 2.4 ran (after 2.2 had extracted `prepare_part_assets` to `part_asset_planner.py`), all per-part TRANSCRIBE logic — `transcribe_with_adapter(...)`, `_read_srt_meta`, per-part SRT writes — already lived inside `prepare_part_assets`. No TRANSCRIBE-only block remained in `process_one_part`. Phase 2.4 was re-scoped to **"RENDER pre-flight"** → `stages/part_render_setup.py` (encoding params + progress-timer thread + cache key + PartExecutionPlan + CameraStrategy + feature-flag warning, ~100 LOC). Executed in commit `ef12803`. **Phase 2.5 split into 2.5a/b/c/d.** Original plan listed 2.5 as a single CRITICAL ~600 LOC commit. Audit at the start of 2.5 found ~977 LOC remaining in process_one_part (lines 254-1230 post-2.4), with Sacred Contract #8 (`qa_pipeline`) surface concentrated in one ~270-LOC sub-block. Single commit would be 3.3× the §7 advisory cap of 300 LOC. Split into: **2.5a** FFmpeg encode core (~216 LOC, HIGH) → `part_render_encode.py`; **2.5b** voice TTS + audio mix (~230 LOC, HIGH) → `part_voice_mix.py`; **2.5c** pacing + intro/outro + scoring + qa_pipeline validation (~430 LOC, **CRITICAL** — Sacred Contract #8 surface) → `part_render_finalize.py`; **2.5d** quality intel + cover frame + `JobPartStage.DONE` + cleanup (~100 LOC, HIGH — Sacred Contract #5 terminal transition) → `part_done.py`. Recommended execution order: 2.5a → 2.5d → 2.5b → 2.5c (saves the CRITICAL phase for last when surrounding seams are settled). Total phases now 23 (was 20 was 17). |
