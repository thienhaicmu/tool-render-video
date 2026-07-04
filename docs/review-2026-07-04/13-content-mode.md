# 13 — Content Mode (module quan trọng nhất — review toàn diện)

`render_format="content"` — orchestrator `run_content`
([content_pipeline.py:110](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L110), 553 dòng).
Khác biệt căn bản: **KHÔNG có footage nguồn** — video được tạo từ script + TTS +
visual sinh ra.

## 1. Workflow

```
POST /api/content/plan {script,...} → ContentPlan (Review, KHÔNG render)   [tùy chọn]
        ▼ user sửa
POST /api/render/process {render_format:"content", content_plan_override}
        ▼ run_content:
  ANALYZING: plan = override (đã duyệt) HOẶC select_content_plan (AI Director)
  SEGMENT_BUILDING: seed part rows theo scene; emit content.plan.ready
  pre-pass: decide_provider mỗi scene (decision tree + budget) UP FRONT [CU-8]
  RENDERING(_PARALLEL): mỗi scene =
      synthesize_scene_narration (TTS) → resolve_scene_visual (provider seam)
      → render_content_scene (subtitle + mux)   [disk-truth resume]
  WRITING_REPORT: concat_clips(scenes) → mix_with_bgm(duck) → QA → DONE
```

## 2. Backend surface (`/api/content`)

`content/router.py` (282 dòng):
- `POST /plan` — sinh ContentPlan (Review step), 502 khi AI None (Sacred #3).
- `POST /narration/preview` + `GET /narration/audio/{token}` — preview TTS/scene,
  token 32-hex chống path traversal (`_TOKEN_RE`).
- `POST|PUT|GET|DELETE /projects` — CRUD draft (content_projects, migration 0016).
- `POST /publish-meta` — SEO metadata (CU-14).

## 3. Visual provider seam (điểm kiến trúc tốt)

`engine/visual/` — registry 4 provider: `local(0) < stock(1) < ai_image(2) <
ai_video/Veo(3)`. `decision.py` decision tree **tất định**:
1. Per-scene override → local.
2. Provider offline → local.
3. Không có prompt → local.
4. AI asset_suggestion chỉ **downgrade** (không upgrade).
5. Scene ngắn (<6s) → ai_video downgrade ai_image (Veo lãng phí).
6. Budget guard → downgrade tier rẻ hơn / local.

**Triết lý "cheapest sufficient, chỉ downgrade" → bật lên không bao giờ đắt hơn
user chọn.** Thiết kế bảo vệ chi phí xuất sắc.

## 4. Đánh giá theo checklist yêu cầu

| Mục | Kết luận |
|-----|----------|
| Workflow | Đúng, mạch lạc; Review 2-bước tách plan/render là điểm cộng lớn |
| UI | **Yếu** — FE chỉ 1 file 709 dòng (doc 05), chưa tận dụng hết BE |
| Backend | Chắc — plan/preview/projects/publish + provider seam |
| Prompt | `content_prompts` riêng; ContentPlan có emotion/speed/pause/subtitle |
| AI orchestration | decision tree + budget UP FRONT (deterministic) — tốt |
| State machine | Sacred #4/#5 tuân thủ; part status QUEUED/RENDERING/DONE/FAILED |
| Rendering | Parallel scene, disk-truth resume, partial success (≥1 scene) |
| Task/history | Job row + result_json chuẩn; project draft persistence riêng |
| Template | **Chưa có template engine** — ContentPlan tự do, không preset/template |
| Cache | Narration preview dưới cache root (prune tự động) |
| Database | content_projects table + content_plan_json col |
| Media | TTS→visual→subtitle→mux→concat→BGM; mượn recap_assembler |
| Extensibility | Provider seam mở (thêm provider = drop module + registry) |

## 5. Điểm mạnh riêng

1. **Review workflow 2-bước** — user duyệt/sửa plan trước khi tốn compute.
2. **Provider decision tree + budget** — kiểm soát chi phí AI xuất sắc.
3. **CU-11 stable seed** — cùng nhân vật/style → look nhất quán qua scenes
   (`_stable_seed` [:86](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L86)).
4. **Partial success** — ≥1 scene render là đủ để giao (không all-or-nothing).
5. **Publish intelligence** (CU-14) — sinh SEO title/desc/tags/thumbnail.

## 6. Vấn đề

### CONTENT-1: FE quá mỏng so với BE (ưu tiên cao)
- **Root cause:** studio mới nhất, FE chưa tách component.
- **Ảnh hưởng:** Cao cho sản phẩm — Content được tuyên bố "quan trọng nhất" nhưng
  UX Review/scene-edit chưa xứng backend.
- **Ngắn hạn:** tách `ContentStudio.tsx` → steps/ (Plan · Review · Scene · Render).
- **Dài hạn:** chia sẻ component render/progress với clip-studio.

### CONTENT-2: Chưa có Template Engine
- **Root cause:** v1 tập trung script→video linh hoạt.
- **Ảnh hưởng:** TB — user phải mô tả mọi thứ; không có "mẫu" (news/vlog/quote…)
  tái sử dụng ngoài `content_type` gợi ý.
- **Dài hạn:** Template Engine (scene layout + style preset + BGM mood) — doc 20.

### CONTENT-3: Trùng orchestration với recap/clips
- `_safe_filename`, `_set_stage`, terminal `result_json` gần y hệt (doc 14).

### CONTENT-4: Budget preflight thiếu (doc 06/09)
- Budget guard chạy trong khi render; không estimate hiển thị trước cho user.

### CONTENT-5: Parallel workers cap — ĐÃ XÁC MINH AN TOÀN
- Content dùng `CONTENT_MAX_PARALLEL` (mặc định 3) không tính NVENC session
  ([:284](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L284)).
- **Xác minh code:** content scene encode là **libx264/CPU-only**
  ([content_scene_render.py:337-343](../../backend/app/features/render/engine/stages/content_scene_render.py#L337-L343))
  và background cũng libx264-only (comment [content_background.py:11](../../backend/app/features/render/engine/stages/content_background.py#L11):
  "must never contend for an NVENC hardware"). → Cap theo CPU là **đúng**, không
  tranh NVENC. Chỉ bước concat cuối (`recap_assembler.concat_clips`) dùng
  `h264_nvenc` (1 lần, external semaphore acquire) → 1 session, an toàn.
- **Kết luận:** không phải bug. Đây là ví dụ thiết kế NVENC-aware nhất quán —
  đường parallel dùng CPU, đường NVENC single-shot có semaphore.

## 7. Điểm

| Trục | Điểm |
|------|------|
| Backend | 8 |
| Provider seam / cost control | 9 |
| Review workflow | 8.5 |
| Frontend/UX | 5 |
| Template/extensibility | 6 |
| Duplicate | 5.5 |
| **Tổng** | **7.0** |
