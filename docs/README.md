# Documentation — AI Video Render Studio

> Bộ tài liệu này viết từ source code hiện tại (không dựa audit cũ). Khi tài
> liệu và code mâu thuẫn: **tin code**. Cập nhật gần nhất **2026-07-03** — bổ
> sung: giọng đọc **Gemini TTS**, **render monitor** thiết kế lại (dashboard,
> step indicator, theme-aware), recap tôn trọng `add_subtitle` + ghép tập nhanh,
> vá deadlock motion-crop. Các doc phase/plan/audit đã xong được gỡ khỏi `docs/`
> (còn trong git history).

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
| [CONTENT_STRATEGY.md](CONTENT_STRATEGY.md) | Chiến lược nội dung / các lớp "intelligence" chọn & xếp hạng clip |
| [STORY_ROADMAP.md](STORY_ROADMAP.md) | Plan tổng tối ưu Story Mode v2 (chi phí/chất lượng/tốc độ/UI) theo phase |
| [RECAP_TESTING.md](RECAP_TESTING.md) | Hướng dẫn kiểm thử chế độ recap (video dài, act-structured) |

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
