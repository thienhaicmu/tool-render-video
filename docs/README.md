# Documentation — AI Video Render Studio

> Bộ tài liệu này viết từ source code hiện tại (không dựa audit cũ). Khi tài
> liệu và code mâu thuẫn: **tin code**. Cập nhật gần nhất **2026-07-15** — Story
> Mode nâng cấp GĐ1→GĐ4 (Story Compiler 3-call, kho asset style-aware + identity
> resolver, readiness gate, composition engine); doc Story hợp nhất vào
> [STORY_MODE.md](STORY_MODE.md). Các doc phase/plan đã hoàn thành được gỡ khỏi
> `docs/` (còn trong git history).

AI Video Render Studio là một ứng dụng desktop **offline-first** để biến video
dài (file local hoặc tải về từ YouTube/TikTok) thành các clip ngắn dạng dọc
(short-form) có phụ đề, overlay, lồng tiếng và nhạc nền — chọn cảnh bằng AI.

Stack: **FastAPI + Uvicorn + SQLite (WAL) + FFmpeg + Whisper + OpenCV + yt-dlp**
ở backend; **React + Vite (TypeScript) + Zustand** ở frontend; vỏ **Electron**
cho desktop.

## Bản đồ tài liệu

| Tài liệu | Nội dung |
|----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Kiến trúc tổng thể, các thành phần, mô hình tiến trình/luồng, vòng đời job |
| [RENDER_PIPELINE.md](RENDER_PIPELINE.md) | Pipeline render: các stage, render từng part, các Sacred Contract |
| [AI_INTEGRATION.md](AI_INTEGRATION.md) | Tích hợp LLM (Gemini/OpenAI/Claude), RenderPlan, prompt, quy tắc an toàn AI |
| [DATABASE.md](DATABASE.md) | Schema SQLite, mô hình kết nối, migration additive-only |
| [CONFIGURATION.md](CONFIGURATION.md) | Toàn bộ biến môi trường + đường dẫn dữ liệu |
| [API_CONTRACT.md](API_CONTRACT.md) | REST + WebSocket API, các contract đóng băng |
| [FRONTEND.md](FRONTEND.md) | Cấu trúc frontend React + vỏ Electron |
| [STORY_MODE.md](STORY_MODE.md) | **Story Mode chuẩn (GĐ1→GĐ4)**: compiler 3-call, resolver + identity lock, readiness gate, composition, API, kill-switch |
| [STORY_MODE_OUTPUT_TEMPLATES.md](STORY_MODE_OUTPUT_TEMPLATES.md) | **Spec StoryPlan JSON cho agent ngoài** (system prompt sẵn dán + ví dụ render được) |
| [STORY_SCENE_SPEC.md](STORY_SCENE_SPEC.md) | scene_spec — vẽ nền declarative trong JSON dán |
| [OFFLINE_JP_VISUAL_LIBRARY.md](OFFLINE_JP_VISUAL_LIBRARY.md) | Bộ hình JP 3-style (24 vai + 12 nền) — kiến trúc + fallback |
| [STYLE_PACK_SPEC.md](STYLE_PACK_SPEC.md) | Chuẩn Lottie character pack (mua/cài/recolor/render offline) |
| [CONTENT_MODE_BACKLOG.md](CONTENT_MODE_BACKLOG.md) | Backlog Content Mode |

## Đọc theo nhu cầu

- **Mới vào dự án** → [ARCHITECTURE.md](ARCHITECTURE.md) trước, rồi [RENDER_PIPELINE.md](RENDER_PIPELINE.md).
- **Sửa pipeline render** → bắt buộc đọc [RENDER_PIPELINE.md](RENDER_PIPELINE.md) + phần "Render Edit Protocol" trong [/CLAUDE.md](../CLAUDE.md).
- **Thêm/đổi API** → [API_CONTRACT.md](API_CONTRACT.md) (lưu ý các path bị đóng băng).
- **Sửa AI/LLM** → [AI_INTEGRATION.md](AI_INTEGRATION.md) (quy tắc: AI module luôn `return None`, không bao giờ `raise`).
- **Đổi schema DB** → [DATABASE.md](DATABASE.md) (chỉ được additive-only).

## Nguyên tắc bất biến (tóm tắt)

1. `data/app.db` là nguồn chân lý duy nhất của trạng thái job — không xoá, không sửa trực tiếp.
2. Mọi module AI phải bắt hết exception và trả `None` khi lỗi.
3. `qa_pipeline.py` là cổng kiểm tra output duy nhất — không bao giờ bypass.
4. Tên stage/part và shape sự kiện WebSocket bị đóng băng (frontend khớp string trực tiếp).
5. Migration DB chỉ được phép thêm (additive-only).

Chi tiết đầy đủ các "Sacred Contract" nằm trong [/CLAUDE.md](../CLAUDE.md).
