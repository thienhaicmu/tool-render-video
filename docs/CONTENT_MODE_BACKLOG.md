# Content Mode — Backlog (dependency-ordered)

> **Nguồn:** Review toàn bộ Content Mode (`render_format="content"`) dựa trên
> implementation thật, 2026-07-07. Backlog này gom 6 hạng mục nâng cấp lớn thành
> các ticket có ID ổn định (CM-x), sắp theo **thứ tự phụ thuộc** thành 5 wave.
>
> **Quy ước tier** (theo `CLAUDE.md` → Blast Radius Order):
> - **CRITICAL** — owns `JobStage`/`JobPartStage` state machine → Render Edit
>   Protocol đầy đủ + explicit approval + full pytest baseline.
> - **HIGH** — schema / AI dispatch / DB / NVENC → Planner + approval + pytest.
> - **LOW** — edit tự do, không cần Planner.
>
> Khi docs và code mâu thuẫn: **tin code.** Đọc file ở trạng thái hiện tại
> trước khi sửa — line range dưới đây là ảnh chụp tại thời điểm review.

---

## Sơ đồ phụ thuộc

```
WAVE 0 (bịt rủi ro, không phụ thuộc gì)
  CM-1  Vá chi phí preview ────────────────┐
  CM-2  Provider interface + fallback thật ─┼── độc lập nhau
  CM-9  Tách file FE theo phase ────────────┘
                    │
WAVE 1 (checkpoint resume — nền cho refactor lớn)
  CM-3  Đọc lại content_plan_json khi resume
  CM-4  Dời scenes_dir khỏi vùng prune          (song song CM-3)
  CM-5  Scene stable `sid` (domain)             (dùng bởi CM-4 & CM-11)
                    │
WAVE 2 (refactor lớn, cần checkpoint ở Wave 1 làm lưới test)
  CM-6  Decompose run_content                    (deps: CM-3, CM-4)
                    │
WAVE 3 (nâng chất lượng AI, cần kiến trúc sạch)
  CM-7  Multi-step quality planning              (deps: CM-2, CM-6)
  CM-8  Prompt versioning + validate + repair    (deps: CM-2)
                    │
WAVE 4 (UX studio, cần FE đã tách + sid)
  CM-10 Undo/redo command stack                  (deps: CM-9)
  CM-11 Timeline drag component                  (deps: CM-9, CM-5)
  CM-12 Asset manager thật                       (deps: CM-9, + backend asset store)
```

**Critical path:** CM-5 → CM-4 → CM-6 → CM-7 (chuỗi dài nhất). Các ticket FE
(CM-9/10/11) chạy song song, không chặn.

---

## WAVE 0 — Bịt rủi ro & gỡ lock-in (không phụ thuộc, làm ngay)

### CM-1 · Vá lỗ hổng chi phí endpoint preview
- **Mục tiêu:** chặn `/visual/preview` + `/narration/preview` đốt quota/tiền không giới hạn.
- **Vấn đề gốc (đã xác minh):** `/api/content/visual/preview` gọi `resolve_scene_visual`
  với provider do client chọn → có thể là `ai_image` (Imagen) / `ai_video` (Veo)
  = 1 asset trả phí mỗi lần bấm, KHÔNG budget, KHÔNG rate-limit
  (`backend/app/features/content/router.py:221-263`). `/narration/preview` tương tự.
- **Scope:** rate-limit token-bucket per-process; ép provider free mặc định, chỉ
  gọi paid khi client gửi `allow_paid=true`; env `CONTENT_PREVIEW_DAILY_CAP`;
  đếm Prometheus (`/metrics`).
- **File:** `backend/app/features/content/router.py` (LOW).
- **Deps:** không.
- **DoD:** preview paid vượt cap → 429 message rõ; test bấm liên tục không vượt
  N call/phút; FE cảnh báo "TỐN PHÍ" khớp hành vi backend.
- **Value: High · Effort: Thấp · Risk: Thấp · Ưu tiên: P0.**

### CM-2 · `ContentDirectorProvider` interface + fallback thật
- **Mục tiêu:** gỡ phụ thuộc cứng Gemini; fallback OpenAI/Claude hoạt động thật.
- **Vấn đề gốc (đã xác minh):** `SUPPORTED_PROVIDERS=("gemini","openai","claude")`,
  `LLM_FALLBACK_ENABLED=1`, NHƯNG chỉ `gemini.py` có `select_content_plan`;
  `_get_content_impl("openai"/"claude")` trả None → skip. Fallback = ảo.
  FE cũng hardcode `ai_provider: 'gemini'`.
- **Scope:** nâng logic 2-pass + CU-5/CU-6 từ `gemini.py:632-710` lên tầng
  dispatch, gọi `provider.call(system, user)`; OpenAI/Claude expose `call`
  (tái dùng `_call_openai_story` / `_call_claude_story` sẵn có).
- **File:** `backend/app/features/render/ai/llm/__init__.py`,
  `providers/gemini.py`, `providers/openai.py`, `providers/claude.py` (HIGH —
  AI safety: mọi path return None, never raise).
- **Deps:** không.
- **DoD:** Planner analysis + approval; full pytest baseline giữ nguyên; test:
  Gemini None → OpenAI/Claude được thử và tạo được plan; import-time không fail
  khi thiếu SDK.
- **Value: High · Effort: Trung bình · Risk: Trung bình · Ưu tiên: P0.**

### CM-9 · Tách `ContentStudio.tsx` theo phase
- **Mục tiêu:** giảm nợ God-component 1342 dòng; mở đường CM-10/11/12.
- **Scope:** tách thành `script/`, `review/`, `monitor/`, `shared/`, `hooks/`.
  Không đổi logic — chỉ di chuyển. Ứng viên tách đầu tiên: `SceneRow` (168 dòng).
  - `ContentStudio.tsx` — state gốc + routing 3 phase (~150 dòng)
  - `hooks/useContentDraft.ts` (từ :122-192), `hooks/usePlanEditor.ts` (từ :580-595)
  - `script/ScriptPhase.tsx` (:318-565), `script/AiDirectorConsole.tsx` (:1092-1125)
  - `review/ReviewPhase.tsx` (:572-635), `review/SceneRow.tsx` (:637-805),
    `review/AiInsights.tsx` (:929-999), `review/CostEstimatePanel.tsx` (:1007-1069)
  - `monitor/ContentMonitor.tsx` (:809-907), `monitor/ContentLiveView.tsx` (:1149-1227)
  - `shared/` — Stepper/HeroHeader/SectionCard/RatioPreview/DurationSlider/Field (:1231-1341)
- **File:** `frontend/src/features/content-studio/**` (LOW-FE).
- **Deps:** không.
- **DoD:** `tsc -b` sạch (KHÔNG `tsc --noEmit`); mỗi file <400 dòng; hành vi UI
  không đổi; build vite cập nhật `backend/static-v2`.
- **Value: Trung bình · Effort: Trung bình · Risk: Thấp · Ưu tiên: P1.**

---

## WAVE 1 — Checkpoint resume (nền tảng cho refactor lớn)

> **Context resume hiện tại (đã trace):** `/resume/{job_id}` nạp lại stored payload
> (có `content_plan_override`) → re-queue `resume_mode=True` → `run_content`.
> Khoảng trống: (G1) `scenes_dir` dưới `TEMP_DIR` bị prune 30 phút; (G2)
> `content_plan_json` được ghi nhưng KHÔNG consumer nào đọc lại (grep xác nhận);
> (G3) startup chỉ mark `interrupted`, không auto-resume; (G4) render bằng AI plan
> tươi (không override) rồi crash → resume re-plan bằng AI → index lệch file disk.
> `run_content` hiện **bỏ qua cờ `resume_mode`** hoàn toàn (chỉ disk-truth per scene).

### CM-3 · Đọc lại `content_plan_json` khi resume
- **Mục tiêu:** đóng G2 + G4 — plan là checkpoint bất biến, index scene khớp file disk.
- **Scope:** đầu `run_content`, khi `resume_mode` và DB có `content_plan_json` →
  ưu tiên nó hơn override/AI; thêm consumer cho `get_content_plan`
  (`jobs_repo.py:254`, hiện 0 caller); log số scene resume.
- **File:** `backend/app/features/render/engine/pipeline/content_pipeline.py`
  (CRITICAL), `backend/app/db/jobs_repo.py` (HIGH).
- **Deps:** không (làm trước CM-6).
- **DoD:** Render Edit Protocol đầy đủ; test kill sau vài scene → resume dùng
  plan cũ, không re-plan, index khớp; full pytest bằng baseline.
- **Value: High · Effort: Cao · Risk: Trung bình · Ưu tiên: P1.**

### CM-4 · Dời `scenes_dir` khỏi vùng prune
- **Mục tiêu:** đóng G1 — scene intermediates sống sót đủ lâu để resume.
- **Scope:** chuyển `scenes_dir` sang `output_dir/.content_work/{job_id}/` HOẶC
  cho prune bỏ qua job `running/interrupted`; cleanup vẫn chỉ khi DONE
  (`content_pipeline.py:715-718`).
- **File:** `content_pipeline.py:129-132` (CRITICAL); prune trong
  `pipeline_cache.py` / `main.py` (HIGH).
- **Deps:** phối hợp CM-5 (đặt tên file theo `sid`).
- **DoD:** resume sau khi prune tick chạy → scene cũ vẫn còn; test prune bỏ qua
  thư mục job active.
- **Value: High · Effort: Trung bình · Risk: Trung bình · Ưu tiên: P1.**

### CM-5 · Scene stable `sid` (domain, additive)
- **Mục tiêu:** temp file & React key bám id ổn định, không lệch khi reorder/resume.
- **Scope:** thêm `sid: str = ""` vào `ContentScene`; backend sinh uuid ngắn khi
  parse nếu trống; temp file `scene_{sid}.mp4`; FE dùng `sid` làm key
  (thay `key={i}`).
- **File:** `backend/app/domain/content_plan.py` (LOW — dataclass thuần, additive);
  `content_pipeline.py` (CRITICAL — đổi cách đặt tên file); FE `SceneRow`.
- **Deps:** không; là input của CM-4, CM-11.
- **DoD:** blob v1/v2/v3 cũ load được (default ""); reorder không phá cache;
  additive-only (Sacred Contract #2).
- **Value: Trung bình · Effort: Trung bình · Risk: Trung bình · Ưu tiên: P1.**

---

## WAVE 2 — Refactor lớn (cần checkpoint Wave 1 làm lưới an toàn)

### CM-6 · Decompose `run_content` thành stage modules
- **Mục tiêu:** gỡ God-function ~680 dòng (`content_pipeline.py:110-791`); test
  được từng stage; giảm blast radius.
- **Vấn đề gốc:** `_render_one_scene` là closure bắt ~15 biến ngoài scope →
  không test được độc lập (chỉ e2e).
- **Scope (6 bước trích tuần tự, chạy pytest sau mỗi bước):**
  1. `scene_stage.render_one_scene(ctx, i, scene, provider)` — từ :398-535 (khó nhất)
  2. `provider_stage.plan_scene_providers` — từ :355-396 (thuần deterministic)
  3. `plan_stage.resolve_plan` — từ :180-317 (override/AI + refine + fit + audit)
  4. `assembly_stage.assemble_scenes` — từ :581-676 (xfade/concat + BGM)
  5. `finalize_stage.finalize` — từ :678-781 (QA + thumbnail + repoint + result_json)
  6. `context.ContentRenderContext` — dataclass frozen thay closure capture
  - `run_content` co còn ~120 dòng orchestrator + state machine.
- **File:** `content_pipeline.py` (CRITICAL) + 6 module mới
  `engine/stages/content/` (LOW/MEDIUM).
- **Deps:** CM-3, CM-4 (checkpoint test bit-identical); nên sau CM-5.
- **Bất biến không được đổi:** stage sequence
  `STARTING→ANALYZING→SEGMENT_BUILDING→RENDERING/RENDERING_PARALLEL→WRITING_REPORT→DONE`;
  part `QUEUED→RENDERING→DONE/FAILED`; result_json 3 key
  (`output_rank_score`, `is_best_output`, `is_best_clip`); QA gate không nuốt
  exception; partial-success `completed_with_errors`; `close_thread_conn()` finally.
- **DoD:** hành vi bit-identical (test chụp result_json keys + stage sequence
  không đổi TRƯỚC/SAU); mỗi stage có unit test; e2e content 8 test giữ nguyên;
  mỗi stage = 1 commit revert được.
- **Value: High · Effort: Cao · Risk: Trung bình · Ưu tiên: P2.**

---

## WAVE 3 — Nâng chất lượng AI (cần kiến trúc sạch)

### CM-7 · Multi-step quality planning (fast vs quality)
- **Mục tiêu:** giảm lỗi "God prompt" (Pass B làm 14 nhiệm vụ cùng lúc — quên
  visual_prompt, narration lệch duration).
- **Scope:** env `CONTENT_PLAN_MODE=quality` chạy
  `understand → structure → narration → visual → validate`; mode `fast` =
  Pass B hiện tại, mặc định (không regress, không tăng cost). Tái dùng
  `build_story_bible_prompt` (understand) + `build_content_narration_refine_prompt`
  (narration) sẵn có; thêm prompt `structure` + `visual`.
- **File:** `content_prompts.py`, `ai/llm/__init__.py` (HIGH), `plan_stage.py` (từ CM-6).
- **Deps:** CM-2 (interface), CM-6 (plan_stage tách sẵn).
- **DoD:** mode fast không regress (A/B); quality mode ra plan hợp lệ; ai_eval
  (nếu có) chất lượng ≥ fast.
- **Value: Trung bình · Effort: Cao · Risk: Trung bình · Ưu tiên: P3.**

### CM-8 · Prompt versioning + JSON-schema validate + LLM-repair
- **Mục tiêu:** giảm parse-fail; trace regression chất lượng theo version.
- **Scope:** registry `content.plan.v3`; validate dict theo schema trước khi
  build ContentPlan; parse fail → 1 vòng LLM-repair bounded rồi parse lại
  (trước khi `_salvage_json` bỏ cuộc); log version vào result_json.
- **File:** `content_prompts.py`, `content_parser.py` (HIGH).
- **Deps:** CM-2.
- **DoD:** test schema reject plan thiếu narration; repair phục hồi 1 case
  truncated; vẫn return None nếu bất khả (Sacred #3).
- **Value: Trung bình · Effort: Trung bình · Risk: Thấp · Ưu tiên: P3.**

---

## WAVE 4 — UX Studio (cần FE đã tách)

### CM-10 · Undo/redo command stack
- **Scope:** `usePlanEditor` (past/present/future, cap ~50); mọi edit qua `apply`;
  bind Ctrl+Z / Ctrl+Shift+Z; autosave lắng nghe `present`. Plan đã immutable →
  undo/redo rẻ.
- **File:** `review/hooks/usePlanEditor.ts` (từ CM-9).
- **Deps:** CM-9.
- **DoD:** undo/redo cho add/remove/move/edit scene; autosave không lưu state
  trung gian sai.
- **Value: Trung bình · Effort: Thấp · Risk: Thấp · Ưu tiên: P3.**

### CM-11 · Timeline drag component
- **Scope:** thanh scene rộng ∝ `est_duration_sec`, màu theo role, badge audit,
  drag reorder → `moveScene` qua command stack, ruler tổng vs target (dùng
  `durationFit` sẵn có). Data đã đủ trong `plan.scenes` — không cần API mới.
- **File:** `review/Timeline.tsx` (mới).
- **Deps:** CM-9, CM-5 (dùng `sid` cho drag key), CM-10 (reorder qua stack).
- **DoD:** drag reorder khớp thứ tự render; click block scroll tới SceneRow.
- **Value: Trung bình · Effort: Trung bình · Risk: Thấp · Ưu tiên: P4.**

### CM-12 · Asset manager thật
- **Scope:** panel gom preview đã sinh, "pin" ảnh vào `scene.visual_source=image`
  / `visual_path`, reuse 1 ảnh cho nhiều scene; cần backend asset store bền vững
  (bảng asset cho content — migration additive).
- **File:** `review/AssetPanel.tsx` + backend content_repo/asset table (HIGH).
- **Deps:** CM-9; backend asset store.
- **DoD:** pin ảnh → render dùng đúng ảnh đã chọn (không sinh lại); asset survive reload.
- **Value: Thấp · Effort: Cao · Risk: Trung bình · Ưu tiên: P4.**

---

## Bảng tổng hợp ưu tiên

| ID | Ticket | Wave | Tier | Deps | Value | Risk | P |
|----|--------|------|------|------|-------|------|---|
| CM-1 | Vá chi phí preview | 0 | LOW | — | High | Thấp | P0 |
| CM-2 | Provider interface + fallback | 0 | HIGH | — | High | TB | P0 |
| CM-9 | Tách file FE | 0 | LOW-FE | — | TB | Thấp | P1 |
| CM-3 | Đọc lại plan khi resume | 1 | CRITICAL | — | High | TB | P1 |
| CM-4 | Dời scenes_dir | 1 | CRITICAL | CM-5 | High | TB | P1 |
| CM-5 | Scene stable sid | 1 | LOW/CRIT | — | TB | TB | P1 |
| CM-6 | Decompose run_content | 2 | CRITICAL | CM-3,4 | High | TB | P2 |
| CM-7 | Multi-step planning | 3 | HIGH | CM-2,6 | TB | TB | P3 |
| CM-8 | Prompt version+repair | 3 | HIGH | CM-2 | TB | Thấp | P3 |
| CM-10 | Undo/redo | 4 | LOW-FE | CM-9 | TB | Thấp | P3 |
| CM-11 | Timeline drag | 4 | LOW-FE | CM-9,5 | TB | Thấp | P4 |
| CM-12 | Asset manager | 4 | HIGH | CM-9 | Thấp | TB | P4 |

**Cổng phê duyệt bắt buộc:** CM-2, CM-3, CM-4, CM-5, CM-6, CM-7, CM-8 chạm file
CRITICAL/HIGH → mỗi cái cần **Planner analysis riêng + explicit approval + full
pytest baseline** theo Render Edit Protocol trước khi Developer chạm code.
CM-1, CM-9, CM-10, CM-11 là LOW tier → giao Developer trực tiếp.

---

## Trạng thái (cập nhật khi triển khai)

| ID | Trạng thái | Ngày | Commit / Ghi chú |
|----|-----------|------|------------------|
| CM-1 | ✅ DONE | 2026-07-07 | Rate limit + paid daily cap + off-switch + Prometheus `content_preview_total`; `content/router.py`, `services/metrics.py`; test `test_content_preview_guard.py` (7 test). Env: `CONTENT_PREVIEW_RATE_PER_MIN`/`_DAILY_CAP`/`_PAID_DISABLED` (docs/CONFIGURATION.md). Chưa commit. |
| CM-2 | ✅ DONE | 2026-07-07 | Phương án B — orchestrator dùng chung `ai/llm/content_director.py`; gemini delegate (bit-identical), openai/claude thêm `_call_*_content` + `select_content_plan` → fallback thật. Dọn dead imports/const gemini; gate CU-4 dời sang content_director (cập nhật test multipass_gate + wave2). Test mới `test_content_provider_fallback.py` (7). Env: `OPENAI/CLAUDE_CONTENT_MAX_TOKENS`/`_TEMPERATURE`, `CLAUDE_CONTENT_CACHE`. Full pytest 2568 passed. Chưa commit. |
| CM-3 | ⬜ TODO | — | — |
| CM-4 | ⬜ TODO | — | — |
| CM-5 | ⬜ TODO | — | — |
| CM-6 | ⬜ TODO | — | — |
| CM-7 | ⬜ TODO | — | — |
| CM-8 | ⬜ TODO | — | — |
| CM-9 | ⬜ TODO | — | — |
| CM-10 | ⬜ TODO | — | — |
| CM-11 | ⬜ TODO | — | — |
| CM-12 | ⬜ TODO | — | — |
