# 19 — Roadmap & Kiến trúc tương lai

## Phần A — Kiến trúc tương lai (PHẦN 20 của đề bài)

### Nguyên tắc: giữ offline-first, tách lớp orchestration chung, mở seam plugin

```
                 ┌─────────────────────────────────────────────┐
                 │            Orchestration Core               │
                 │  _orchestrator_base (stage/finalize/fs)     │
                 │  concurrency (semaphores, locks)            │
                 └───────────────┬─────────────────────────────┘
        ┌────────────────┬───────┴────────┬──────────────────┐
        ▼                ▼                ▼                  ▼
   Clip Pipeline   Recap Pipeline   Content Pipeline    (Future modes)
        └────────────────┴───────┬────────┴──────────────────┘
                                  ▼
   ┌──────────────┬───────────────┬──────────────┬───────────────┐
   │  AI Engine   │ Media Engine  │ Render Engine│ Template Engine│
   │ (llm+whisper │ (cut/concat/  │ (ffmpeg/     │ (scene layout/ │
   │  +scoring)   │  audio/subtitle│  nvenc/motion│  style preset) │
   └──────────────┴───────────────┴──────────────┴───────────────┘
                                  ▼
              Provider Seams (LLM providers · Visual providers · TTS providers)
```

### Các "Engine" đề xuất (tách khỏi orchestrator)
1. **AI Engine** — dispatch LLM/Whisper/scoring, đã gần đạt (ai/llm). Thêm eval harness.
2. **Media Engine** — cut/concat/audio/subtitle/thumbnail trung lập (gom
   recap_assembler ra khỏi stages/).
3. **Render Engine** — ffmpeg/nvenc/motion, tách primitive concurrency (TD-C2).
4. **Template Engine** (mới) — cho Content: scene layout + style preset + BGM mood.
5. **Asset Engine** (mở rộng) — asset library + provider prefetch + cache.
6. **Workflow/Pipeline Engine** — `_orchestrator_base` hoá 3 mode (TD-H2).

### Có nên microservice / event-driven?
- **KHÔNG cho desktop** — modular monolith là đúng. Microservice/queue ngoài chỉ
  hợp lý NẾU chuyển hướng SaaS cloud (doc 20 §sẵn sàng). Khi đó: tách render worker
  thành process/container, thay ThreadPool→queue (Redis/RabbitMQ), thay
  SQLite→Postgres + object storage. Repo pattern hiện tại giúp việc này khả thi.

## Phần B — Roadmap 5 Phase (PHẦN 21)

### Phase 1 — Quick Win (1-2 tuần, LOW risk, ROI cao)
1. **TD-C2**: nâng `JOB_SEMAPHORE`/lock/count → `engine/concurrency.py` (gỡ coupling).
2. Khử duplicate: `_safe_filename` → `engine/util/fs.py`; `_set_stage` factory.
3. Whitelist `download_repo` cols (TD-L5).
4. Chạy full `pytest`, thiết lập **baseline test count** ghi vào doc.
5. Xác minh LLM render-plan cache active (PERF-3); bật nếu tắt.
6. Tách `ContentStudio.tsx` → steps/ (bước đầu).

### Phase 2 — Architecture Refactor (3-6 tuần, có kế hoạch)
1. **`_orchestrator_base.py`**: `finalize_render_job()` gom Sacred #1 keys 1 nơi
   (TD-H2) — giảm rủi ro lệch giữa 3 mode.
2. Gom recap_assembler → `engine/media/assembly.py` (TD-M4).
3. Rút block lớn khỏi `render_pipeline.py` (TD-C1) — từng block một, full pytest
   giữa mỗi bước (Render Edit Protocol).
4. `PartRenderContext.for_recap()` factory (RECAP-3).

### Phase 3 — Performance (2-4 tuần)
1. Debounce progress write (PERF-1).
2. Prefetch visual asset song song cho Content (PERF-4).
3. Cache render-plan theo hash prompt (PERF-3).
4. Migration atomic + surface trạng thái ở /health (LAT-5).

### Phase 4 — Scalability / Reliability (tùy hướng sản phẩm)
1. **Nếu giữ desktop:** DB export/backup định kỳ (DB-4); "intelligence profile"
   gom env flag (TD-H3); optional token auth khi remote (TD-H4/doc16).
2. **Nếu hướng SaaS:** tách render worker process; Postgres + object storage;
   auth + multi-tenant + rate-limit; queue ngoài.

### Phase 5 — AI Upgrade
1. **Eval harness gắn CI** (golden-set) đo viral-pick + recap-coverage regression
   (AI-3) — đây là điều kiện tiên quyết để nâng prompt an toàn.
2. Template Engine cho Content (TD/CONTENT-2).
3. Preflight cost estimate hiển thị trước render (CONTENT-4).
4. Mở rộng provider (content select_content_plan cho openai/claude — hiện Gemini-only).
5. Publish/Scheduling pipeline (panel `publish` đang placeholder).

## Phần C — 20 việc ưu tiên (tổng hợp, thứ tự thực thi)

Xem doc 20 §"20 việc cần ưu tiên tiếp theo" — danh sách hành động rút gọn.
