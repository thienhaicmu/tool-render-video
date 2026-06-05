# SPRINT PLAN — RenderPlan Architecture Migration

**Date:** 2026-06-04
**Branch:** `feature/render-engine-upgrade`
**Baseline tag:** `pre-sprint1-baseline` (commit `92233c5`)
**DB backup:** `data/app.db.pre-sprint1.bak`
**Pytest baseline (2026-06-04):** **2069 passed / 1 skipped / 9 failed** (31.5s) — see `pytest_baseline_failures.txt`

⚠️ **Branch drift vs audit ledger:** Audit ledger `docs/review/AUDIT_2026-06-02_followup_4.md:78` ghi baseline = 2077/1/0 lúc đóng Sprint 6.D. Hiện tại 2069/1/9 → 8 test biến mất + 9 fail mới. Phát sinh từ commits sau 2026-06-02:

- `2df66ad` refactor(llm): Phase 1-3 global groq→llm rename + API alias fields
- `f6b51d4` refactor(llm): make llm_* canonical, groq_* as backward-compat aliases
- `e350824` xóa groq
- `a8278ca` fix nhẹ
- `92233c5` fix + improve: priority_rank, preview skip, FOCUS UI, viral hook prompt

### 9 failures rõ root cause

**Group A — 3 LLM provider tests** (root: `app/ai/llm/prompts.py:198` `KeyError: 'end'`)
- `test_claude_provider.py::TestClaudeProvider::test_parses_valid_claude_json_response`
- `test_gemini_provider.py::TestGeminiProvider::test_parses_valid_gemini_json_response`
- `test_openai_provider.py::TestOpenAIProvider::test_parses_valid_openai_json_response`

Template `_USER_TEMPLATE` có placeholder `{end}` mới (do commit "viral hook prompt") nhưng `build_segment_prompt()` caller không cung cấp.

**Group B — 6 preview ffmpeg probers tests** (root: `_ensure_h264_preview()` deliberately no-op, return src)
- `test_preview_ffmpeg_probers.py::TestEnsureH264Preview::test_returns_existing_output_without_probe`
- `::test_returns_src_when_already_safe`
- `::test_copy_remux_used_for_h264_in_non_mp4`
- `::test_copy_remux_not_used_for_hevc`
- `::test_encode_path_uses_duration_cap`
- `::test_copy_remux_fallback_to_encode_on_failure`

✅ **CONFIRMED INTENTIONAL** — `ffmpeg_probers.py:92-98` docstring: "Return the source file directly for preview. Running on Electron/Windows — the OS media layer handles all codecs (HEVC, VP9, AV1, etc.) natively. No transcoding needed."

→ Sprint 1.5: **update 6 tests** theo behavior mới (assertion = src path), không sửa code.

### Pre-flight resolution log

| Action | Result |
|---|---|
| Fix `prompts.py:80-81` escape `{end}`/`{start}` literal braces | ✅ Group A clear (3 tests pass) |
| Identify Group B as intentional | ✅ Defer to Sprint 1.5 (update tests) |
| New Pre-flight baseline | **2072 passed / 1 skipped / 6 failed (Group B documented)** |

---

## Context

Project Reset Audit (2026-06-04, hội đồng kỹ thuật) đã xác định:

- Project khỏe ~72%. Foundation tốt, không cần reset.
- Vision target: `Local Video File → Transcript → Creator Context → AI Director → RenderPlan → Render Engine → Output`
- Workflow hiện tại lệch ~55% vì:
  - Không có `RenderPlan` dataclass thống nhất (AI chỉ sinh `LLMSegment`).
  - Không có `CreatorContextBuilder` module.
  - Decision logic (subtitle style, camera strategy) bị nhúng trong render layer (`stages/part_asset_planner.py`, `stages/part_render_setup.py`).
  - YouTube downloader URL flow còn live trong render path (vẫn giữ standalone download tab).
- Render pipeline có nhiều điểm tạo temp file dư I/O — chưa đo, cần audit.

Toàn bộ phân tích chi tiết: tham chiếu báo cáo audit trong conversation 2026-06-04 (15 phase + CTO verdict).

## Quyết định user (2026-06-04)

| Câu hỏi | Quyết định |
|---|---|
| YouTube từ render path | Xóa khỏi render flow; giữ standalone Downloader tab |
| Branch strategy | Tiếp tục `feature/render-engine-upgrade`, không tách |
| Scope plan | Chi tiết Sprint 1-6, mỗi sprint vẫn cần approve riêng trước Developer |
| prepare-source endpoint | Audit frontend Sprint 1 rồi quyết keep/delete |
| Sprint 6 timing | Sau Sprint 4 (có thể parallel với Sprint 5) |

---

## Sprint Roadmap

| Sprint | Tuần | Risk | Mục tiêu |
|---|---|---|---|
| Pre-flight | 0.5d | — | Baseline + tag + backup |
| Sprint 1 | 2 | MEDIUM | Clean dead code + YouTube khỏi render path + Temp File Audit (read-only) |
| Sprint 2 | 2 | MEDIUM | `RenderPlan` dataclass + DB column `render_plan_json` + builder adapter |
| Sprint 3 | 2 | MEDIUM | `CreatorContextBuilder` module + DB columns + frontend UI |
| Sprint 4 | 3 | **CRITICAL** | AI Director sinh full RenderPlan, migrate decision logic ra khỏi render layer |
| Sprint 5 | 2 | MEDIUM | services/ subdomain reorg, merge legacy_renderer, split motion_crop_path |
| Sprint 6 | 3 | HIGH-CRITICAL | Temp file optimization (sau Sprint 4) |
| **Total** | **~14 tuần** | | net -2700 LOC + perf 20-30%↑ (mục tiêu) |

---

## Sprint 1 — Chi tiết

### Pre-flight checklist (đã chạy 2026-06-04)

- [x] Verify branch clean: `git status --short` = clean
- [x] Backup DB: `data/app.db` → `data/app.db.pre-sprint1.bak`
- [x] Tag baseline: `pre-sprint1-baseline` @ commit `92233c5`
- [x] Pytest baseline: **2072 passed / 1 skipped / 6 failed** (sau khi fix Group A trong Pre-flight). Còn 6 Group B intentional → Sprint 1.5 update tests.
- [x] Plan doc: this file

### Sprint 1 tasks

**1.1 Dead code delete (1 ngày, risk: LOW)**

| Action | Target |
|---|---|
| DELETE | `backend/app/services/caption_engine.py` (354 LOC, 0 caller) |
| DELETE | `backend/app/routes/platform_downloader.py` (shim 3 LOC) |
| DELETE | `backend/app/services/platform_downloader/` (folder duplicate) |
| DELETE | `backend/app/ai/analysis/groq/` (folder rỗng + pycache) |
| CLEAN | `backend/app/orchestration/__pycache__/groq_only_pipeline*.pyc` |
| DELETE | `frontend/src/api/download.ts` (41 LOC, 0 component import) |
| ARCHIVE | `mockup-screens/`, `mockup-screens-c/` → `docs/archive/mockups/` |
| ARCHIVE | `prototype.html`, `render-flow.html` → `docs/archive/prototypes/` |
| AUDIT | `ai-team-framework/`, `workflows/`, `rules/`, `design/` top-level dirs |

**1.2 YouTube khỏi render path (2-3 ngày, risk: MEDIUM)**

Workflow đích:
```
User → Tab Download standalone → tải về local file
User → Tab Render → file picker chọn local file → render
```

| Order | Action |
|---|---|
| 1 | Audit `frontend/src/features/clip-studio/render/RenderWorkflow.tsx` xem có URL input không |
| 2 | REMOVE UI: input URL khỏi render screen (nếu có) |
| 3 | REMOVE wire frontend gọi `prepare-source` với YouTube URL (nếu có) |
| 4 | DELETE `routes/render.py:347-396` (YouTube branch trong `prepare_source()`) |
| 5 | DELETE `routes/render.py:684+` (legacy `quick_process` YouTube path) |
| 6 | DECIDE `prepare-source` endpoint: keep (chỉ local) hoặc delete (theo audit step 1) |
| 7 | MODIFY `schemas.py` — `PrepareSourceRequest.youtube_url: Optional[str] = None`, `model_config = ConfigDict(extra="ignore")` (backward compat stored jobs) |
| 8 | MODIFY `schemas.py` — xóa `"youtube"` khỏi `QuickProcessRequest.source` allowed values |
| 9 | DELETE/UPDATE test cũ liên quan YouTube → render path |
| 10 | NEW `tests/test_youtube_blocked_from_render.py` — gate test |

**KEEP nguyên (standalone downloader):**
- `frontend/src/features/downloader/DownloaderScreen.tsx`
- `frontend/src/features/clip-studio/download/DownloadTab.tsx` (monitor jobs)
- `frontend/src/api/platformDownloader.ts`
- `backend/app/features/downloader/` (router + adapters + service)
- `backend/app/services/downloader.py` (yt-dlp wrapper)
- `backend/app/services/cookie_extractor.py`
- `backend/app/db/download_repo.py` + `download_jobs` table
- `requirements.txt` yt-dlp, playwright

**1.3 Doc sync (½ ngày, risk: LOW)**

| Action | File |
|---|---|
| FIX | `PROJECT_MAP.md:41` — xóa ref `ai_director.py` đã removed Phase G |
| FIX | `docs/ARCHITECTURE.md` — vision "Local file primary, standalone downloader = side tool" |
| FIX | `docs/RENDER_PIPELINE.md` — update flow |
| KEEP | `CLAUDE.md` stage name `DOWNLOADING` (frozen per Sacred Contract #4), update docstring giải thích "DOWNLOADING giờ = local file staging" |
| NEW | `docs/review/SPRINT_1_2026-06-04.md` — closure record (write at sprint end) |
| NEW | `docs/review/YOUTUBE_RENDER_PATH_REMOVAL_2026-06-04.md` — migration record |

**1.4 Temp File Audit (3-4 ngày, READ-ONLY, risk: NONE)**

Mục tiêu: liệt kê toàn bộ điểm tạo temp file/dir trong render pipeline, classify, đề xuất ưu tiên cho Sprint 6.

23 file có tempfile/tmp pattern (đã grep):
- orchestration: `render_pipeline.py`, `llm_pipeline.py`, `pipeline_source_prep.py`
- stages: `part_cut.py`, `part_renderer.py`, `part_render_encode.py`, `part_render_finalize.py`, `part_asset_planner.py`, `part_voice_mix.py`, `part_render_context.py`
- services: `subtitle_transcription_adapters.py`, `subtitles/ass_core.py`, `tts_service.py`, `tts_xtts_adapter.py`, `text_overlay.py`, `preview/ffmpeg_probers.py`, `preview/session_service.py`, `manifest_writer.py`, `maintenance.py`
- routes: `render.py`

Classification cho mỗi điểm:

| Field | Ví dụ |
|---|---|
| File:line | `stages/part_cut.py:88` |
| Loại | audio_temp / video_temp / srt / ass / cache / staging |
| Lifetime | 1 part / 1 job / 72h cache |
| Cleanup | finally block / maintenance scheduler / never |
| Size order | KB / MB / GB |
| Pipeline cost | I/O write + read again? lần thứ N? |
| Có thể stream/pipe? | yes/no/maybe |
| Có thể in-memory? | yes nếu < 50MB |
| Có cache hit ích lợi? | yes/no |

Output: `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` — inventory + Top 10 hotspot + P0/P1/P2 đề xuất.

**1.5 Test gap + baseline reconciliation (1-1.5 ngày, risk: LOW-MEDIUM)**

⚠️ **CORRECTION audit:** `tests/test_gemini_provider.py`, `test_claude_provider.py`, `test_openai_provider.py` ĐÃ TỒN TẠI từ trước. Audit cũ sai. KHÔNG cần tạo mới.

**Việc thật của 1.5:**

| Task | Mục đích |
|---|---|
| FIX | `app/ai/llm/prompts.py:198` template `_USER_TEMPLATE` — cung cấp `end` hoặc xóa placeholder thừa. Verify với 3 test provider pass lại |
| INVESTIGATE | `services/preview/ffmpeg_probers.py::ensure_h264_preview()` — quyết định behavior intentional (cập nhật 6 test) hay regression (fix code về cũ) |
| NEW | `tests/test_youtube_blocked_from_render.py` — gate test: POST /api/render/prepare-source với source_mode='youtube' phải reject |

**Mục tiêu cuối Sprint 1:** baseline về 2078/1/0 (2069 hiện tại + 9 fix + 1 new gate test = 2079... actual tùy fix outcome).

### Sprint 1 gate

- pytest pass = baseline + 3 test mới
- Backend start clean, `/api/render/process` với local file OK
- Tab Download standalone hoạt động đầy đủ (verify UI)
- `grep -r "youtube_url" backend/app/routes` chỉ còn 1 chỗ schema backward-compat
- Frontend RenderWorkflow không có URL input
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` hoàn thành
- Closure doc `docs/review/SPRINT_1_2026-06-04.md`

---

## Sprint 2-6 — Outline

Chi tiết Sprint 2-6 đã được hội đồng plan đầy đủ trong conversation 2026-06-04. Outline ngắn:

### Sprint 2 — RenderPlan Skeleton (2 tuần)

- NEW `backend/app/domain/render_plan.py` — dataclass `RenderPlan` + sub-dataclasses (ClipPlan, SubtitlePolicy, CameraStrategy, AudioPlan, OutputConfig)
- DB additive migration: `ALTER TABLE jobs ADD COLUMN render_plan_json TEXT DEFAULT NULL`
- NEW `backend/app/orchestration/render_plan_builder.py` — adapter shim convert LLMSegment + scattered decisions → RenderPlan
- MODIFY `render_pipeline.py`, `stages/part_renderer.py` đọc RenderPlan với fallback null

### Sprint 3 — Creator Context Builder (2 tuần)

- NEW `backend/app/domain/creator_context.py`
- NEW `backend/app/ai/context/creator_context.py` — `CreatorContextBuilder`
- NEW `backend/app/db/creator_repo.py`
- DB migration thêm columns vào `creator_prefs`
- Frontend settings screen cho CreatorContext config
- Inject CreatorContext vào AI prompt

### Sprint 4 — AI Director Full RenderPlan (3 tuần, CRITICAL)

- REWRITE `ai/llm/prompts.py` — output JSON = RenderPlan subset
- REWRITE `ai/llm/parser.py` — parse RenderPlan
- MIGRATE decision logic ra khỏi:
  - `stages/part_asset_planner.py:395-419` (subtitle style)
  - `stages/part_asset_planner.py:300+` (market hook text apply)
  - `stages/part_render_setup.py:202, 228` (camera/motion strategy)
  - `orchestration/pipeline_ranking.py:11-93` (market reranking)
- DELETE `render_plan_builder.py` adapter (AI sinh thẳng RenderPlan)
- Render Edit Protocol 9 bước bắt buộc per PR

### Sprint 5 — Polish & Reorg (2 tuần)

- MOVE `services/motion_crop_*` → `services/motion_crop/` subfolder
- MOVE `services/audio_*` → `services/audio/` subfolder
- RENAME `orchestration/audio_pipeline.py` → `audio_cleanup.py`
- MERGE `services/render/legacy_renderer.py` (491 LOC) vào `base_clip_renderer.py`
- SPLIT `services/motion_crop_path.py` (977 LOC) → 2 files
- DELETE backward-compat shims (LLMSegment, groq_*) sau migration stored jobs
- Audit mixed DB connection model
- Final doc: `docs/RENDERPLAN.md`, `docs/CREATOR_CONTEXT.md`, update ARCHITECTURE

### Sprint 6 — Temp File Optimization (3 tuần, HIGH-CRITICAL)

Dựa trên `TEMP_FILE_AUDIT_2026-06-04.md` từ Sprint 1.

Dự đoán P0:
- Skip per-part Whisper re-extract audio
- Inline subtitle ASS qua filter graph (không write file)
- Pipe TTS audio → mix (không write WAV intermediate)
- Render cache prune (`maintenance.py` Issue 3 CLAUDE.md)

Bắt buộc:
- Centralize temp dir qua `services/temp_manager.py`
- Performance baseline + verify trên 3-5 video sample
- Sacred Contract #8 (qa_pipeline) không thay đổi

---

## Cross-sprint protocol

| File touched | Protocol |
|---|---|
| `render_pipeline.py`, `stages/part_renderer.py`, `part_render_finalize.py`, `motion_crop.py`, `motion_crop_path.py`, `qa_pipeline.py` | Render Edit Protocol 9 bước, full pytest |
| `schemas.py` | Sacred Contract #2 — additive, new field default False/None |
| `routes/*.py` | Frozen API contracts — additive only |
| Database migrations | Additive only, NEVER DROP/RENAME (download_jobs sẽ giữ orphan nếu có lúc nào đó xóa downloader) |
| `data/app.db` | NEVER touch directly |

Branch: tiếp tục `feature/render-engine-upgrade`. Commit per sub-task. Tag `sprint-N-done-YYYY-MM-DD` cuối mỗi sprint.

## Rollback gate

Nếu bất kỳ sprint nào pytest delta > 0:
1. STOP
2. Revert PR cuối
3. Không fix trong cùng session
4. Tạo `docs/review/REGRESSION_*.md`
5. Plan riêng để fix

## Risk register

| Risk | Sprint | Mức | Mitigation |
|---|---|---|---|
| Pydantic deserialize fail vì stored jobs có `youtube_url` | 1 | HIGH | `extra = "ignore"` trong schemas |
| DOWNLOADING stage name không còn phù hợp nhưng frozen | 1 | LOW | Giữ giá trị, update docstring |
| Render Plan column null trong jobs cũ → fallback path | 2 | MEDIUM | Fallback bắt buộc trong part_renderer |
| AI prompt rewrite làm thay đổi semantic clip selection | 4 | HIGH | A/B test trên 5-10 video samples trước rollout |
| Decision logic migration làm vỡ render quality | 4 | CRITICAL | Render Edit Protocol + full regression video sample |
| Services subdomain reorg vỡ import chain | 5 | MEDIUM | Shim 1 sprint, grep-replace có verify |
| Mixed DB connection unify gây race | 5 | HIGH | Test stress với parallel jobs |
| Temp optimization làm giảm output quality | 6 | CRITICAL | qa_pipeline + manual visual review trên 3-5 sample |

---

## Approval log

| Date | Sprint | Approver | Status |
|---|---|---|---|
| 2026-06-04 | Pre-flight | user | approved |
| | Sprint 1 | | (chờ user approve trước khi Developer chạy code) |
