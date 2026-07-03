# Recap / Review Film — Build & Test Guide

> Hướng dẫn build + chạy thử feature **Recap/Review** (render_format="recap")
> end-to-end. (Spec thiết kế gốc `RECAP_REVIEW_SPEC.md` đã được gỡ khỏi `docs/`
> — còn trong git history nếu cần.) Feature đã render thật; xem thêm cấu hình
> recap ở [CONFIGURATION.md](CONFIGURATION.md) và pipeline ở
> [RENDER_PIPELINE.md](RENDER_PIPELINE.md).

## 0. Yêu cầu
- Python venv backend đã cài (`backend/.venv`) + **AI extras** (Whisper):
  `pip install -r backend/requirements-ai.txt` (cần `faster-whisper` để transcribe).
- FFmpeg + ffprobe trên PATH (hoặc bundled).
- Node 18+ cho frontend.
- **1 API key LLM** (Gemini / OpenAI / Claude) — recap bắt buộc cần AI chọn cảnh.
- 1 file phim local (mp4) để thử. Phim dài (30’–2h) là đúng use-case.

## 1. Cấu hình API key (.env ở gốc repo)
```ini
# Chọn 1 provider làm mặc định + key tương ứng
AI_PROVIDER_DEFAULT=gemini
GEMINI_API_KEY=your_key_here
# hoặc OPENAI_API_KEY=... / CLAUDE_API_KEY=...

# UI v2 (bắt buộc để thấy mode selector + live view)
STATIC_UI_VERSION=v2
```
> Recap gọi `select_recap_plan` trực tiếp (không phụ thuộc `LLM_EMIT_RENDER_PLAN`).
> Key cũng có thể truyền qua payload, nhưng .env là cách nhanh nhất để thử.

## 2. Build frontend (xuất ra UI backend phục vụ)
```powershell
cd frontend
npm install        # lần đầu
npm run build      # → backend/static-v2/ (Vite emptyOutDir)
```

## 3. Chạy backend
```powershell
# từ gốc repo
./run-backend-v2.ps1      # đặt STATIC_UI_VERSION=v2 + uvicorn 127.0.0.1:8000
```
Mở http://127.0.0.1:8000 (hoặc chạy Electron: `./run-desktop-v2.ps1`).

## 4. Render thử recap
1. Chọn nguồn = file phim local → **Prepare source** (chờ probe duration).
2. Ở bước **Configure**, mục **CHẾ ĐỘ DỰNG** → chọn **Recap / Review**.
   - Tự set: khung **16:9** + bật **thuyết minh (AI rewrite)**.
   - Các mục clip-only (CLIP DURATION, OUTPUT VIDEOS) tự ẩn.
   - Tùy chọn: vào tab thuyết minh bật thêm **Reaction mode** (freeze cao trào),
     chọn giọng (vd `en-US-AvaNeural`, `vi-VN-HoaiMyNeural`), nhập tone.
3. Bấm **Render**.

## 5. Quan sát (Live build view)
Trong màn rendering, khi AI trả plan xong sẽ hiện **🎬 RECAP — LIVE BUILD**:
- Timeline **act → scene**, màu theo beat (setup/rising/climax/resolution).
- Mỗi **scene** sáng dần theo trạng thái render (xám→cam→xanh; đỏ nếu lỗi).
- **NARRATION SCRIPT** chảy ra theo từng cảnh (preview lời thuyết minh).
- Marker **⏸** ở cảnh có freeze (nếu bật reaction).
- "assembled (demuxer)" khi ghép xong → player hiện video recap.

## 6. Luồng backend tương ứng (để đối chiếu log)
```
STARTING → TRANSCRIBING_FULL (Whisper cả phim)
→ SEGMENT_BUILDING: select_recap_plan → recap.plan.ready
→ RENDERING_PARALLEL: render từng scene (= part)
→ WRITING_REPORT: thẻ act + concat → recap.concat.done → qa → DONE
```
Output: `…_recap.mp4` trong thư mục output của job.

## 7. Công tắc tinh chỉnh (env, đều có mặc định)
| Env | Mặc định | Ý nghĩa |
|-----|----------|---------|
| `RECAP_MAX_SRT_CHARS` | 120000 | Trần ký tự transcript gửi LLM (phim dài) |
| `GEMINI_RECAP_TEMPERATURE` | 0.4 | Temp chọn cảnh (quyết đoán) |
| `GEMINI_RECAP_MAX_TOKENS` | 16384 | Token output plan (phim nhiều cảnh) |
| `RECAP_ACT_CARD_SEC` | 2.5 | Độ dài thẻ tiêu đề act |
| `RECAP_ACT_CARD_BLUR` | 20 | Độ mờ nền thẻ act |
| `RECAP_SUBTITLE_STYLE` | (ASS style) | Style phụ đề narration burn |
| `REACTION_FREEZE_ENABLED` | 1 | Bật freeze (khi reaction) |
| `REACTION_FREEZE_MAX_PER_POINT_SEC` | 2.0 | Trần freeze mỗi điểm |
| `REACTION_FREEZE_MAX_TOTAL_SEC` | 6.0 | Trần tổng freeze/clip |
| `NARRATION_LOUDNORM` | 1 | Chuẩn hoá âm lượng narration |

## 8. Kỳ vọng & giới hạn hiện tại
- Độ dài recap **do AI quyết** theo phim, **không ép trần cứng** (chỉ guard ≤ độ
  dài phim). Phim 2h → recap dài tương ứng; render sẽ lâu (nhiều scene + Whisper).
- Narration **liền mạch** theo act (DIRECTOR'S INTENT) + **burn phụ đề narration**.
- **Đường clips không đổi** — recap chạy orchestrator riêng (`recap_pipeline.py`).

## 9. Khắc phục sự cố
| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Job FAILED "AI returned no usable plan" | Thiếu/ sai API key, hoặc transcript rỗng (phim không có thoại / Whisper lỗi) |
| "transcript empty — cannot select scenes" | Whisper chưa cài (`requirements-ai.txt`) hoặc audio phim trống |
| Không thấy mode selector | FE chưa build lại / `STATIC_UI_VERSION` ≠ v2 |
| Recap dài bất thường / render lâu | Phim dài → nhiều scene; chỉnh giảm bằng prompt hoặc đợi |
| Phụ đề/freeze không khớp | Báo lại để chỉnh `speed` mapping / caps |

## 10. Kiểm thử tự động (đã pass)
```powershell
cd backend; .\.venv\Scripts\Activate.ps1
python -m pytest -q                       # full backend (1815 passed)
python -m pytest tests/test_recap_plan.py -q
cd ../frontend; npx tsc -b; npm test      # FE (510 passed)
```
