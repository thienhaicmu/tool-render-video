# RenderPlan Architecture Migration — Complete Log

**Date opened:** 2026-06-04 (Pre-flight)
**Date closed:** 2026-06-04 (Sprint 4.H)
**Branch:** `feature/render-engine-upgrade`
**Tags:** `pre-sprint1-baseline` → `sprint-1-done-2026-06-04` → `sprint-2-done-2026-06-04` → `sprint-3-done-2026-06-04` → **`sprint-4-done-2026-06-04`**
**Total commits:** 22
**Pytest trajectory:** 2069/1/9 → **2332/1/0** (+263 net, 0 regression)

Tài liệu này là master log của migration từ vision "AI Video Editor"
trong báo cáo audit hội đồng (2026-06-04) sang implementation thực tế.
Mô hình đích: `Local Video → Transcript → Creator Context Builder →
AI Director → RenderPlan → Render Engine`.

Trước migration: hệ thống có `LLMSegment` (chỉ chọn clip), backend tự
quyết subtitle/camera/audio/ranking, không có CreatorContext layer.

Sau migration: AI Director sinh **full RenderPlan** trong 1 round-trip,
Render Engine consume từ plan, backward compat 100% qua feature flag.

## Pre-flight

| Commit | Phase | LOC delta | Pytest | Mô tả |
|---|---|---|---|---|
| `4fb10df` | Pre-flight prompts.py fix | +313 / -2 | 2069/1/9 → 2072/1/6 | Production bug fix: `prompts.py:80-81` literal `{end}`/`{start}` braces gây KeyError mọi LLM call. 2-line escape fix. Plus initial SPRINT_PLAN doc. |

## Sprint 1 — Clean + YouTube removal + Doc sync + Temp audit

5 phases, **6 commits**.

| Commit | Phase | LOC delta | Pytest |
|---|---|---|---|
| `fc8b713` | 1.1 Dead code purge | 0 / -397 | 2072/1/6 |
| `899c708` | 1.2 YouTube removal khỏi render path | +169 / -192 | 2077/1/6 |
| `561b72d` | 1.5 Group B test fix (intentional `_ensure_h264_preview` no-op) | +23 / -126 | 2077/1/0 ✓ Clean |
| `2f275c7` | 1.3 Doc sync (PROJECT_MAP, ARCHITECTURE, RENDER_PIPELINE) | +144 / -22 | 2077/1/0 |
| `b6f544b` | 1.4 Temp file audit (read-only inventory 23 files) | +0 / +0 doc | 2077/1/0 |

**Key changes:**
- Removed `caption_engine.py`, `routes/platform_downloader.py` shim, `ai/analysis/groq/`, broken `ai-team-framework` submodule, `frontend/src/api/download.ts`
- Archived `mockup-screens/`, `mockup-screens-c/`, `design/ui-prototype.html` → `docs/archive/mockups_2026-06-04/`
- YouTube URL path khỏi render flow (giữ standalone Downloader feature)
- Generated audit `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` cho Sprint 6 P0 baseline

## Sprint 2 — RenderPlan Skeleton

3 phases (2.1, 2.2, 2.3), **3 commits**.

| Commit | Phase | LOC delta | Pytest |
|---|---|---|---|
| `ddc7065` | 2.1 RenderPlan dataclass + DB column + jobs_repo helpers | +812 | 2116/1/0 |
| `66e3ab7` | 2.2 Builder shim (`render_plan_builder.py`) | +529 | 2145/1/0 |
| `0848d3a` | 2.3 Pipeline wire-up (Render Edit Protocol) | +194 / -1 | 2152/1/0 |

**Key artifacts:**
- `backend/app/domain/render_plan.py` — `RenderPlan` + 5 sub-dataclasses (`ClipPlan`, `SubtitlePolicy`, `CameraStrategy`, `AudioPlan`, `OutputConfig`)
- `backend/app/db/migration_steps/0001_jobs_add_render_plan_json.py` — additive ALTER TABLE
- `backend/app/db/jobs_repo.py`: `update_render_plan` + `get_render_plan` helpers
- `PartRenderContext.render_plan: Optional[RenderPlan]` field (Sprint 2.3)
- Sprint 2.2 builder shim retired in Sprint 4.H

## Sprint 6 P0 (LOW-risk) — Cache hygiene quick wins

Inserted between Sprint 2 và Sprint 3 per user decision. **1 commit**.

| Commit | Phase | LOC delta | Pytest |
|---|---|---|---|
| `1db0df3` | 6 P0 LOW-risk (xtts cache prune + text_overlay cleanup + _part_mp3 guarantee) | +435 / -4 | 2168/1/0 |

**Key changes:**
- `services/maintenance.py`: 2 new prune helpers + scheduler wire
- `services/text_overlay.py`: renamed private → public `get_text_overlay_temp_dir`
- `stages/part_voice_mix.py`: best-effort glob cleanup of per-part MP3 (`part_{idx:03d}*.mp3`)

## Sprint 3 — Creator Context Builder

2 phases (backend + FE), **2 commits**.

| Commit | Phase | LOC delta | Pytest |
|---|---|---|---|
| `3daa41d` | 3 Creator Context Builder backend + AI wire | +982 | 2224/1/0 |
| `62133a3` | 3-FE Settings UI + API endpoint | +804 | 2233/1/0 |

**Key artifacts:**
- `backend/app/domain/creator_context.py` — `CreatorContext` dataclass + `to_prompt_hint()` + `is_empty()`
- `backend/app/ai/context/creator_context.py` — `CreatorContextBuilder`
- `backend/app/db/creator_repo.py`: extension for nested storage (no DB migration — uses existing `prefs_json TEXT`)
- `backend/app/orchestration/llm_stage.py:_build_editorial_hint` wire-up
- `backend/app/routes/settings.py` — `/api/settings/creator-context`
- `frontend/src/features/settings/SettingsScreen.tsx` — `CreatorContextSection` panel
- `frontend/src/api/creatorContext.ts` — typed client

## Sprint 4 — AI Director Full RenderPlan

8 phases, **8 commits** (closure: `docs/review/SPRINT_4_2026-06-04.md`).

| Commit | Phase | LOC delta | Pytest |
|---|---|---|---|
| `7b3b758` | 4.A Parser dual-mode | +530 | 2257/1/0 |
| `70a1d94` | 4.B Prompt dual-mode | +493 | 2274/1/0 |
| `e2ac767` | 4.C Provider dispatch dual-mode | +746 / -12 | 2297/1/0 |
| `ae19d25` | 4.D Pipeline wire CRITICAL | +278 / -35 | 2307/1/0 |
| `ac5a65e` | 4.E subtitle_policy consume CRITICAL | +260 / -3 | 2325/1/0 |
| `514d60a` | 4.F camera_strategy consume CRITICAL | +254 / -4 | 2340/1/0 |
| `fcd9184` | 4.G Ranks consume CRITICAL | +370 / -7 | 2359/1/0 |
| `dbd758a` | 4.H Builder shim removal | +101 / -613 | 2332/1/0 |

**Key invariants pinned (across all 8 phases):**
- Feature flag `LLM_EMIT_RENDER_PLAN` strict `== "1"` (Sprint 4.D)
- Per-field merge with safe fallback (Sprint 4.E/F/G)
- Sacred Contract #1 absolute (output_rank_score / is_best_output / is_best_clip set unconditionally in `_compute_output_ranking_entry`)
- Sacred Contract #3 absolute (every helper catches all exceptions → None)
- Source-level pin tests for resolver wire-up + event source enum + import existence

## Cumulative LOC delta

```
Source code:
  +deleted:  -1,419   (caption_engine, groq, shim, builder, tests of removed)
  +added:    +3,150  (RenderPlan + builder + parser + prompts dual + CreatorContext + resolvers + wire + tests)
  +modified: ~+1,200 net (renames, doc sync, comment block updates)
  
Test code:
  +tests added:    +263  (sentinels + consume + dataclass + builder + providers + flag-gate tests)
  +tests deleted:    -27 (builder shim tests retired in Sprint 4.H)
  
Net: ~+1,700 source + +263 tests
```

## Sacred Contracts — full audit

Mọi commit Sprint 1-4 verified:

- **#1 result_json aliases preserved** — Sprint 4.G is the only commit
  that touched ranking logic; the `_compute_output_ranking_entry`
  helper at `pipeline_ranking.py:225-247` sets all 3 keys
  unconditionally before any consume vs legacy branch runs.
- **#2 RenderRequest defaults additive** — `LLM_EMIT_RENDER_PLAN`
  default OFF; `render_plan_json` column default NULL; every Sprint
  4.E/F/G resolver returns legacy fallback when `ctx.render_plan` is
  None. Baseline behaviour byte-identical when flag OFF.
- **#3 AI modules return None on failure** — Pre-flight commit
  (`4fb10df`) restored the contract for `prompts.py:_USER_TEMPLATE.
  format()`. Sprint 4 added 4 new resolvers + 1 new dispatcher
  function + 3 new provider functions — every one wrapped in
  `try/except` surfacing `None`.
- **#4-5 stage names frozen** — `JobStage` (QUEUED → DOWNLOADING →
  RENDERING → DONE) and `JobPartStage` (QUEUED → WAITING → CUTTING
  → TRANSCRIBING → RENDERING → DONE) literals untouched across all
  22 commits.
- **#6 `_emit_render_event` signature frozen** — 4 new events added
  during Sprint 4 (`render.plan.ai_emitted`, `render.plan.ai_fallback`,
  `render.plan.persisted`, `camera_strategy_applied`). Each uses the
  canonical `channel_code` / `job_id` / `event` / `level` / `message`
  / `step` / `context` kwarg shape. Additive context keys
  (`rank_source`, `reframe_mode_source`, `subtitle_style_source`)
  added but never removed.
- **#7 SQLite additive-only** — 1 migration added (`0001_jobs_add_
  render_plan_json` in Sprint 2.1). No DROP / RENAME / type change.
  Sprint 3 stored CreatorContext under a nested key of existing
  `prefs_json TEXT` column → no migration needed.
- **#8 qa_pipeline never bypassed** — `qa_pipeline.py` untouched
  across all 22 commits.

## Tags

| Tag | Commit | Mô tả |
|---|---|---|
| `pre-sprint1-baseline` | `92233c5` | Trạng thái trước session 2026-06-04 |
| `sprint-1-done-2026-06-04` | `b6f544b` | Sprint 1 đóng (5 phases) |
| `sprint-2-done-2026-06-04` | `0848d3a` | Sprint 2 đóng (3 phases) |
| `sprint-3-backend-done-2026-06-04` | `3daa41d` | Sprint 3 backend + AI wire (no FE) |
| `sprint-3-done-2026-06-04` | `62133a3` | Sprint 3 full (backend + FE) |
| `sprint-4-done-2026-06-04` | `dbd758a` | Sprint 4 full (8 phases, AI Director full RenderPlan) |

## Sprint còn lại (theo plan)

| Sprint | Risk | Mô tả |
|---|---|---|
| **5** Polish + Reorg | MEDIUM | services/ subdomain reorg (motion_crop/ + audio/) + LLMSegment retire + `_to_scored_dict` retire + 2 CameraStrategy reconcile + dead code purge + documentation finalize (this commit is phase 5.5) |
| **6** Temp file optimization HIGH-risk P0 | **CRITICAL** | `raw_part` in-memory + `_base_clip_out` gating. ROI cao (4.5-7.5 GB / 50-part). Render Edit Protocol |

## Bài học chính

1. **Pre-flight bug fix value cao.** `prompts.py:80-81` literal brace bug đã broken mọi LLM call trong production. Phát hiện trong Step 5 baseline check (audit Group A). Sprint 4 không thể bắt đầu trên broken AI layer.

2. **Sprint chia phase nhỏ hơn = pytest delta = 0 mỗi phase.** Render Edit Protocol Step 9 STOP gate buộc tách phase đủ nhỏ để không vi phạm 1 lần. Sprint 4 chia 8 phases × 0 regression = an toàn tuyệt đối.

3. **Planner subagent giúp catch fact errors trong Leader brief.** Mọi CRITICAL phase Planner phát hiện ≥ 1 fact sai. Ví dụ: ranking decision không nằm ở `pipeline_ranking.py` mà ở `render_pipeline.py:1037`; 2 CameraStrategy classes không clash runtime; shim luôn produce rank > 0 → consume leak risk.

4. **Per-field merge thắng all-or-nothing.** Mỗi consume phase chấp nhận partial plan, fallback legacy per field. AI có thể incremental adopt new shape.

5. **Source-level pin tests rẻ + đáng tin.** ~15 pin tests Sprint 4 catch regression class chính (event tag deletion, import drop, source ordering change). Cheap insurance.

6. **`bool` default `False` là semantic blocker.** Defer `emphasis_pass` (Sprint 4.E) + `motion_aware_crop` (Sprint 4.F) + tracker (Sprint 4.F) cùng lý do. Future SubtitlePolicy/CameraStrategy schema phải có explicit sentinel hoặc `Optional[bool]`.

7. **F.5 (rank consume) là warning lớn nhất.** Shim leak có thể vi phạm Contract #2 dù pipeline-level flag check ON. Resolver tự gate trên env (`os.getenv`) là deterministic + Contract-safe. Lesson cho future consume sites.

## Verification

```
git rev-parse --verify sprint-4-done-2026-06-04  # commit sha
cd backend && python -m pytest tests --tb=no -q  # expect: 2332 passed / 1 skipped / 0 failed
git log --oneline pre-sprint1-baseline..HEAD     # 22 commits
```
