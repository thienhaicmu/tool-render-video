# Architecture Review — AI Video Render Studio · 2026-07-04

Review kiến trúc toàn diện, dựa trên đọc mã nguồn thực tế (không suy đoán). Mọi
nhận định có dẫn chứng `file:line`. Điểm trung bình hệ thống **~7.0/10** — chín cho
desktop offline-first, chưa sẵn sàng SaaS.

| # | Tài liệu | Nội dung chính |
|---|----------|----------------|
| 01 | [overview](01-overview.md) | Tổng quan, 3 mode, bảng điểm, mức sẵn sàng |
| 02 | [architecture](02-architecture.md) | Sơ đồ FE→…→Output, phân tầng, startup, dependency |
| 03 | [workflow](03-workflow.md) | Vòng đời job, chuỗi stage 3 mode, Review workflow |
| 04 | [backend](04-backend.md) | Module, repository, model/DTO, worker/scheduler |
| 05 | [frontend](05-frontend.md) | Routing, store, api/ws, Clip vs Content studio |
| 06 | [api](06-api.md) | REST surface, frozen contracts, validation |
| 07 | [database](07-database.md) | SQLite WAL, schema, migration, concurrency |
| 08 | [render-engine](08-render-engine.md) | Part lifecycle, NVENC, QA gate, God-file |
| 09 | [ai-workflow](09-ai-workflow.md) | Provider dispatch, Story Intelligence, guardrails |
| 10 | [media-pipeline](10-media-pipeline.md) | FFmpeg safety, subtitle, audio, motion, assemble |
| 11 | [clip-mode](11-clip-mode.md) | Deep-dive Clip |
| 12 | [recap-mode](12-recap-mode.md) | Deep-dive Recap (3-pass + deterministic) |
| 13 | [content-mode](13-content-mode.md) | Deep-dive Content (provider seam + budget) |
| 14 | [comparison](14-comparison.md) | So sánh 3 mode, duplicate, abstraction đề xuất |
| 15 | [performance](15-performance.md) | CPU/GPU/thread/Whisper/cache/DB |
| 16 | [security](16-security.md) | Auth, devtools, injection, path, CSP, ma trận rủi ro |
| 17 | [technical-debt](17-technical-debt.md) | Critical→Low + bảng ưu tiên |
| 18 | [bug-report](18-bug-report.md) | Bug active / latent / verified-safe / cần chạy |
| 19 | [roadmap](19-roadmap.md) | Kiến trúc tương lai + roadmap 5 phase |
| 20 | [final-review](20-final-review.md) | Executive Summary: sẵn sàng, 10 rủi ro, 10 ưu điểm, 20 việc |

## Cách đọc
- Muốn nắm nhanh → đọc **01** rồi **20**.
- Muốn hành động → **17** (nợ) + **18** (bug) + **19/20** (20 việc ưu tiên).
- Muốn hiểu sâu 3 mode → **11 / 12 / 13** + **14**.

## Lưu ý phương pháp
- Review **tĩnh** (đọc code). Chưa chạy `pytest` trong phiên — doc 18 §D liệt kê
  4 mục cần chạy để xác nhận. Việc đầu tiên nên làm: thiết lập baseline test count.
- Khi docs mâu thuẫn code: **tin code** (theo CLAUDE.md).
