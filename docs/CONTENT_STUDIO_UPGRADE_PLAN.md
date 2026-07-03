# CONTENT_STUDIO_UPGRADE_PLAN.md

> Status: **PLAN — chờ duyệt.** Tổng hợp từ 2 vòng Architecture Review
> (Software + AI Production, 2026-07-03). Nâng Content Studio từ
> *"execution substrate + provider seam tốt"* (7/10 phần mềm, ~2/10 trục AI)
> lên một **AI Video Production platform**. Chưa viết code.

## Nguyên tắc thiết kế (bất biến)

1. **Tiến hoá, không viết lại.** Mọi thứ cắm lên `engine.visual` seam +
   `content_pipeline` + `ContentPlan` bằng cách **additive**. Không phá
   clips/recap, không phá Sacred Contracts.
2. **AI tất định-điều phối, không agent tự trị.** Nhiều PASS LLM chuyên trách,
   orchestrate bằng code; mỗi pass có prompt/contract/cache/retry/validator/
   regenerate RIÊNG. Chỉ dùng loop kiểu "agent" cho QA-repair và media-verify.
2. **Rẻ trước, đắt sau.** Ưu tiên value/cost/risk. Nền (Bible + validator +
   parallel + draft) trước; media-intelligence + embedding-consistency sau.
3. **Contract-safe.** ContentPlan chỉ thêm field (default trơ). DB additive-only.
   `content_plan_override` replay bit-identical. AI module luôn `return None`.
4. **Offline-first vẫn là mặc định.** Mọi provider online là opt-in + fallback
   local. Platform-scale (distributed/multi-GPU) là fork riêng (Wave 5).

---

## Bản đồ phase (5 wave)

| # | Phase | Wave | Value | Cost | Risk | Phụ thuộc |
|---|---|---|---|---|---|---|
| CU-1 | Draft/Project persistence + autosave | 1 Foundation | ★★★ | ★ | MED | — |
| CU-2 | Parallel scene render + resume/retry | 1 Foundation | ★★★ | ★★ | HIGH | — |
| CU-3 | Quick fixes: negative_prompt/style→provider; consume asset_suggestion | 1 Foundation | ★★ | ★ | LOW | — |
| CU-4 | Multi-pass AI Director + Story/Character Bible + chunking | 2 AI-Core | ★★★ | ★★★ | HIGH | CU-3 |
| CU-5 | Validator + Repair pipeline | 2 AI-Core | ★★★ | ★ | HIGH | CU-4 |
| CU-6 | Character consistency v1 (Bible fragment injection) | 2 AI-Core | ★★★ | ★ | MED | CU-4 |
| CU-7 | Provider Manifest + Registry (capability-aware) | 3 AI-Econ | ★★ | ★★ | MED | — |
| CU-8 | Decision Tree + Budget guard (cost optimizer) | 3 AI-Econ | ★★★ | ★★ | MED | CU-7 |
| CU-9 | Asset Graph + Asset-gen queue/scheduler | 3 AI-Econ | ★★★ | ★★★ | HIGH | CU-7 |
| CU-10 | Media-intelligence verify (vision→regenerate) | 4 AI-Quality | ★★ | ★★★ | HIGH | CU-9 |
| CU-11 | Consistency v2/v3 (seed/reference/embedding) | 4 AI-Quality | ★★★ | ★★★ | HIGH | CU-6,CU-7 |
| CU-12 | ContentPlan JSON Schema + migration registry | 4 AI-Quality | ★★ | ★★ | MED | CU-4 |
| CU-13 | FE editor: store + Timeline + Live Preview + Asset Manager UI + undo/redo | 4 AI-Quality | ★★★ | ★★★ | MED(FE) | CU-1,CU-9 |
| CU-14 | Publish intelligence (SEO/thumbnail/metadata/schedule) | 4 AI-Quality | ★★ | ★★ | MED | CU-4 |
| CU-X | Platform substrate (distributed queue, object store, multi-GPU) | 5 Fork | ★★★ | ★★★★ | CRIT | — |

Risk tier tham chiếu CLAUDE.md: `content_pipeline.py` = CRITICAL-tier (CU-2,4);
AI modules = HIGH (return None tuyệt đối); DB mới = HIGH additive; FE = MEDIUM.

---

## WAVE 1 — Foundation (rẻ, value cao, risk thấp — LÀM TRƯỚC)

### CU-1 — Draft/Project persistence + autosave  *(MED)*
**Vấn đề:** ContentPlan chỉ sống trong FE `useState` + gửi qua `content_plan_override`.
Đóng tab giữa Review = mất trắng. Không có project entity.
**Deliverables:**
- DB: bảng `content_projects` (id, title, script, plan_json, config_json,
  status[draft|rendered], created/updated) — additive migration (0016).
- Backend: `features/content/router.py` +CRUD: `POST/GET/PUT /api/content/projects`,
  `GET /api/content/projects` (list), autosave endpoint.
- FE: autosave plan+config lên server (debounce), reopen từ danh sách, "Draft".
**Contract:** không đụng RenderRequest; render vẫn nhận `content_plan_override`.
**Test:** CRUD + autosave roundtrip; migration additive.
**Acceptance:** đóng/mở lại tab → plan còn nguyên.
**Trade-off:** +1 bảng DB, +API; rẻ, giá trị vận hành lớn nhất.

### CU-2 — Parallel scene render + resume/retry  *(HIGH / CRITICAL-tier)*
**Vấn đề:** `run_content` render **tuần tự**; 20 scene × (TTS+Whisper+ffmpeg+Veo)
cộng dồn — bottleneck #1. Không resume: fail scene 15/20 → làm lại từ 0.
**Deliverables:**
- `run_content` vòng scene → `ThreadPoolExecutor` (tái dùng pattern
  `pipeline_render_loop.run_render_loop`), tôn trọng `NVENC_SEMAPHORE` +
  `MAX_CONCURRENT_JOBS`.
- Resume disk-truth: scene clip đã render + QA-valid → tái dùng khi retry
  (như `part_renderer` resume-skip). Visual cache đã có → không regen AI.
**Risk:** CRITICAL (owns JobPartStage state machine). Theo Render Edit Protocol:
Planner analysis + full pytest baseline trước/sau + edit tối thiểu.
**Test:** full pytest; e2e nhiều scene song song; resume sau fail.
**Acceptance:** thời gian render N scene giảm ~tuyến tính theo worker; retry chỉ
render lại scene fail.
**Trade-off:** phức tạp hơn + phải giữ đúng cancel/semaphore; nhưng đây là điểm
hiệu năng lớn nhất.

### CU-3 — Quick fixes  *(LOW)*
- `provider_ai_image`/`provider_ai_video`: **truyền `negative_prompt` + style**
  vào API (hiện lưu mà không dùng).
- Consume `asset_suggestion` như gợi ý mặc định cho Decision (chuẩn bị CU-8).
**Test:** provider nhận đủ tham số (mock). **Risk thấp.**

---

## WAVE 2 — AI Core (chất lượng — NỀN cho mọi thứ AI)

### CU-4 — Multi-pass AI Director + Story/Character Bible + chunking  *(HIGH)*
**Vấn đề:** 1 call Gemini ôm hết → chất lượng sụp scene cuối, trần token, không
regenerate riêng, **không có Character model** → không thể nhất quán.
**Deliverables:**
- `content/ai/director/`: orchestrator tất định:
  - `pass_understand` → **StoryBible** (characters[{id,name,canonical_desc}],
    setting, timeline, hook, CTA, tone).
  - `pass_narration` → per-chunk (act/episode ~5–10 scene), đọc Bible +
    tóm tắt chunk trước → nhất quán + context bị chặn.
  - `pass_visual` → visual_prompt (inject Bible; chuẩn bị CU-6).
- ContentPlan += `story_bible` (dataclass, additive, default rỗng). Scene +=
  `characters:[id]`, `continuity`.
- Prompts tách theo pass + `prompt_version` pin vào plan.
- Cache per-pass (llm_cache namespace riêng). Retry per-pass.
**Contract:** AI module return None; plan cũ (không bible) vẫn load (SC #3/#2).
**Test:** mỗi pass parse→None on garbage; chunking; bible roundtrip; e2e
mock 3 pass.
**Acceptance:** script dài/nhiều scene → scene cuối không kém scene đầu;
regenerate được từng pass.
**Trade-off:** +2–3 call/độ trễ/chi phí; đổi lại chất lượng ổn định + regenerate
riêng + testable. Với video: thắng.

### CU-5 — Validator + Repair pipeline  *(HIGH, rẻ)*
**Vấn đề:** Gemini → parser → render luôn; không kiểm.
**Deliverables:** `content/ai/quality/validator.py`:
- Schema check + semantic (scene có narration? duration hợp lý? character
  referenced tồn tại trong Bible? visual_prompt có khi provider=AI?).
- Repair: tất định trước (điền default, drop scene rỗng, clamp); **LLM-repair**
  chỉ cho cái code không sửa được (opt-in).
**Test:** plan lỗi từng loại → validator bắt + repair; never raise.
**Acceptance:** không plan lỗi nào lọt xuống render.

### CU-6 — Character consistency v1 (fragment injection)  *(MED)*  — phụ thuộc CU-4
**Vấn đề:** "Napoleon mỗi scene một mặt". 
**Deliverables:** pass_visual **inject canonical description fragment** của mỗi
character (từ Bible) vào visual_prompt mọi scene có character đó. Model-agnostic,
gần như miễn phí.
**Test:** scene chứa character X → visual_prompt chứa fragment canonical.
**Acceptance:** nhất quán nhân vật cải thiện rõ (đánh giá thủ công + guard test
fragment injection).
**Trade-off:** nhất quán một phần (chưa seed/reference — để CU-11).

---

## WAVE 3 — AI Economics & Provider Platform

### CU-7 — Provider Manifest + Registry  *(MED)*
**Vấn đề:** seam resolve theo tên; không có metadata capability → Decision/Cost
không route được.
**Deliverables:** `VisualProvider` protocol + **Manifest** (kind: image/video;
supports: reference/seed; cost_tier; max_res; aspect_ratios; latency) +
`registry`. Providers hiện có khai báo manifest.
**Contract:** `resolve_scene_visual` giữ nguyên chữ ký; registry là lớp trong.
**Test:** registry liệt kê providers + manifest; route theo capability.

### CU-8 — Decision Tree + Budget guard  *(MED)*  — phụ thuộc CU-7
**Vấn đề:** user quyết provider; scene 5s tĩnh có thể gọi Veo phí cao vô ích.
**Deliverables:** `media/decision/policy.py` (rule-based trước):
`scene(duration,role,motion,budget) → cheapest sufficient`
(local/stock < image+KenBurns < AI image+motion < AI video). **Budget guard**
per-project (cap chi phí; vượt → hạ cấp provider/skip). User override được.
**Test:** ma trận scene→provider; budget cap chặn Veo.
**Acceptance:** chi phí AI/project có trần; scene ngắn không gọi Veo.

### CU-9 — Asset Graph + Asset-gen queue/scheduler  *(HIGH)*  — phụ thuộc CU-7
**Vấn đề:** mỗi scene sinh mới; cache chỉ theo (prompt,size); sinh inline tuần tự.
**Deliverables:**
- **Asset Graph**: node = asset{source,prompt,provider,cost,character_refs,
  version,metadata}; edge = scene→asset (reuse|crop|motion-variant). Bảng
  `content_assets` (additive).
- **Asset-gen phase** tách khỏi render: gom request → dedup qua graph → schedule
  theo provider (rate-limit/cost/latency), **song song chỗ được**, retry/priority
  → rồi Render.
**Test:** dedup reuse; scheduler parallel + retry; graph invalidation cơ bản.
**Acceptance:** scene trùng subject reuse asset; asset-gen song song, tách render.

---

## WAVE 4 — AI Quality cao cấp + Editor + Production

### CU-10 — Media-intelligence verify  *(HIGH, đắt → tiered)*  — phụ thuộc CU-9
Vision call (Gemini vision) chấm "asset khớp prompt/scene?" → regenerate nếu lệch
(vòng lặp có cap). Opt-in/tiered (1 vision call/asset). Sửa bệnh "battlefield→anime".

### CU-11 — Consistency v2/v3  *(HIGH)*  — phụ thuộc CU-6,CU-7
Seed cố định per character/style; reference image (image-to-image, providers hỗ
trợ theo manifest); embedding/LoRA per character (xuyên series). Route theo
capability manifest (CU-7).

### CU-12 — ContentPlan JSON Schema + migration registry  *(MED)*  — phụ thuộc CU-4
JSON Schema versioned + migration v1→vN + validation report (tách khỏi
`from_json` defensive). Bền vững plan lưu trữ dài hạn (đi cùng CU-1 projects).

### CU-13 — FE editor evolution  *(MED, FE lớn)*  — phụ thuộc CU-1,CU-9
`content-studio/` tách store (Zustand: project/plan/assets/undo-redo/autosave),
`api/`, sub-components: ScriptEditor · PlanReview(SceneEditor+PropertyPanel) ·
**AssetManager (candidate/approve/replace/regenerate)** · **NarrationTimeline** ·
**Live Preview (thumbnail scene trước full render)** · Monitor. Virtualized
scene list. Đây là bước biến "wizard" thành "editor" thật.

### CU-14 — Publish intelligence  *(MED)*  — phụ thuộc CU-4
Từ ContentPlan (topic/tone/audience) sinh title/description/tags + chọn
thumbnail-frame; nối vào Publish có sẵn của app. SEO/schedule/analytics.

---

## WAVE 5 — Platform substrate (FORK CHIẾN LƯỢC — chỉ khi vượt desktop)

> **Trạng thái (2026-07-03): quyết định = KHÔNG fork bây giờ.** Deliverable
> Wave 5 là ADR, không phải code: [CONTENT_STUDIO_PLATFORM_FORK_ADR.md](CONTENT_STUDIO_PLATFORM_FORK_ADR.md).
> Chốt Option A (giữ offline-first/1-SQLite/in-process). Option B (seam
> abstraction: `JobQueue` + `AssetStore` protocol, impl mặc định = code hiện
> tại) là bước đầu tiên KHI có trigger scale thật; Option C (Redis+Postgres+S3+
> multi-GPU) là fork deployment riêng, không nằm trên nhánh desktop. Không đụng
> substrate cho tới khi có trigger (xem ADR §6).

### CU-X — Distributed  *(CRITICAL, quyết định sản phẩm)*
100 scene/2h/500 project/multi-GPU: tách **deployment server** — job queue thật
(thay in-process), asset object store (thay local cache), multi-GPU render
sharding, batch render. **Kiến trúc offline-first/1-SQLite/in-process của app
mâu thuẫn với cái này** → cần bạn quyết. Tin tốt: seam provider + ContentPlan +
Decision Tree **mang sang được**; chỉ substrate thực thi đổi.

---

## Thứ tự đề xuất & "bắt đầu ở đâu"

**Wave 1 trước (CU-1,2,3):** rẻ nhất, value/risk tốt nhất, sửa 2 nỗi đau vận
hành lớn nhất (mất-việc + render chậm) + vá bug rõ. Không phụ thuộc AI.

**Rồi Wave 2 (CU-4,5,6):** đây là nơi "AI Production Platform" khác "app render"
— multi-pass + Bible + validator + consistency-v1 là **nền cho toàn bộ AI còn
lại**. CU-4 là hạng mục lớn nhất cả chương trình.

**Wave 3 (CU-7,8,9):** kinh tế + platform provider (chặn chi phí, reuse asset,
parallel gen).

**Wave 4/5:** cao cấp (vision-verify, embedding, editor UI, publish) và fork
platform — làm sau khi nền AI vững.

**Khuyến nghị bắt đầu:** **CU-1 + CU-3** (rất rẻ, độc lập) song song, rồi **CU-2**
(theo Render Edit Protocol, full pytest), rồi mở **CU-4** như một mini-chương
trình riêng (Planner spec chi tiết trước khi code, vì đây là HIGH-tier AI lớn).

## Cross-cutting

- **Contracts phải giữ:** ContentPlan additive + defensive load; RenderRequest
  additive default trơ; AI return None; QA gate không bypass; DB additive-only;
  seam chữ ký ổn định.
- **Test strategy:** mỗi phase có test riêng; CU-2/CU-4 chạy **full pytest
  baseline trước/sau**; provider/AI test offline (mock API); e2e ffmpeg thật cho
  render.
- **Rollout:** mỗi phase = commit feat + build dist (nếu chạm FE) + full pytest
  0-regression; giữ nhánh `feat/content-*` per wave.
