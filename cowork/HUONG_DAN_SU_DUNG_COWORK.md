# Hướng Dẫn Sử Dụng — Render Studio

Hướng dẫn dành cho operator vận hành hệ thống.

---

## Khởi động

### Backend + Desktop (Electron)
```powershell
.\run-desktop.ps1
```

### Backend only (browser tại http://localhost:8000)
```powershell
.\run-backend.ps1
```

### Backend hot-reload (khi phát triển)
```powershell
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Workflow Editor (YouTube)

### Bước 1: Chuẩn bị nguồn

1. Mở tab **Render** trong UI
2. Chọn source mode **YouTube Link**
3. Nhập URL YouTube
4. Chọn channel hoặc nhập thư mục output
5. Nhấn **Download & Edit**
   - Backend tải video về `data/temp/preview/{session_id}/`
   - Preview H.264 được tạo ra (có thể mất 1–2 phút với video dài)
   - Editor view mở ra với video preview

### Bước 2: Chỉnh sửa

Trong Editor view:
- **Trim**: kéo slider hoặc nhấn "Set IN/OUT" khi video đang phát
- **Volume**: kéo slider hoặc nhập số (100% = gốc)
- **Subtitle**: chỉnh font, size, màu, vị trí Y, outline
- **Text Overlay**: nhấn **+ Add Text** để thêm layer, kéo để di chuyển
- **Render settings**: aspect ratio, playback speed, min/max part, FPS, profile, device

### Bước 3: Render

1. Kiểm tra lại cài đặt
2. Nhấn **Bắt đầu Render**
3. Status bar hiển thị `⏳ Đang gửi yêu cầu render…`
4. Nếu thành công → chuyển sang Render view, theo dõi tiến độ
5. Nếu lỗi → editor ở lại, thông báo đỏ hiện trong status bar, nhấn lại để thử lại

---

## Workflow Editor (Local File)

1. Chọn source mode **Local Video File**
2. Chọn file từ máy (hoặc kéo thả)
3. Nhấn **Open Editor**
   - Backend validate file và tạo session
   - Editor mở ra
4. Thực hiện bước 2–3 như trên

---

## Khi Render Thất Bại

### Lỗi "Editor session not found"
- Session đã hết hạn (server khởi động lại, hoặc quá 6 tiếng kể từ khi chuẩn bị)
- Giải pháp: đóng editor, nhấn **Download & Edit** lại

### Lỗi validation (output_dir, source_mode...)
- Thông báo đỏ hiện trong status bar của editor
- Editor không đóng — chỉnh lại và nhấn **Bắt đầu Render** lần nữa

### Job trạng thái "failed"
- Lỗi xảy ra trong pipeline (ffmpeg, Whisper, scene detect...)
- Xem log chi tiết: `data/logs/error.log` hoặc job log

---

## Xem Logs

### Qua UI
```
GET http://localhost:8000/api/jobs/{job_id}/logs?lines=100
```

### Qua terminal (PowerShell)
```powershell
# Lỗi pipeline gần nhất
Get-Content data\logs\error.log -Tail 50

# Tất cả sự kiện pipeline
Get-Content data\logs\app.log -Tail 100

# Lỗi validation request
Get-Content data\logs\request.log -Tail 50

# Log của một job cụ thể
Get-Content channels\<channel_code>\logs\<job_id>.log
```

### Dùng cowork bug capture
```bash
# Ghi lại lỗi vừa xảy ra
npm run capture-error -- \
  --component render_engine \
  --action render \
  --error-name RuntimeError \
  --message "mô tả lỗi"

# Xem danh sách lỗi đã ghi
npm run log_error -- --list

# Xem prompt fix cho lỗi ưu tiên cao nhất
npm run log_error

# Gửi prompt fix cho Claude tự động
npm run log_error:run
```

---

## Debug Render Job

```powershell
# 1. Lấy chi tiết job
curl http://localhost:8000/api/jobs/{job_id}

# 2. Đọc log job
curl "http://localhost:8000/api/jobs/{job_id}/logs?lines=200"

# 3. Bật verbose debug log (cho lần chạy tiếp theo)
$env:RENDER_DEBUG_LOG = "1"
.\run-backend.ps1
```

---

## Cấu Trúc Thư Mục Output

```
channels/
  {channel_code}/
    video_out/          ← output video mặc định
    upload/
      source/           ← bản gốc video đã tải (nếu keep_source_copy=true)
      uploaded/         ← video đã upload TikTok thành công
      failed/           ← video upload thất bại
    logs/
      {job_id}.log      ← log chi tiết từng job render
```

---

## Giới Hạn & Lưu Ý

| Mục | Giá trị |
|---|---|
| Max text layer | 8 |
| Session hết hạn | 6 giờ sau khi tạo (hoặc sau khi server khởi động lại) |
| Preview temp | `data/temp/preview/` — tự xóa khi render xong hoặc khi khởi động |
| Font hợp lệ | Xem `VALID_FONTS` trong `text_overlay.py` (14 fonts) |
| Output folder | Phải kết thúc bằng `video_output` hoặc `video_out` |

---

## Xây Dựng Phân Phối

```powershell
# Backend exe
.\build-backend.bat

# Desktop app đầy đủ (Electron + backend)
.\build-desktop.ps1

# Offline portable
.\build-offline-exe.ps1
```
