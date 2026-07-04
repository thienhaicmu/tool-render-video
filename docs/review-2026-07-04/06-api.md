# 06 — Review API

## 1. Bề mặt API (REST prefixes)

Từ mã (grep `APIRouter(prefix=...)`), ~14 nhóm prefix + nhiều router mount ở
`main.py`:

`/api/render`, `/api/jobs`, `/api/content`, `/api/settings`, `/api/assets`,
`/api/presets`, `/api/analytics`, `/api/channels`, `/api/system`, `/api/voice`,
`/api/feedback`, `/api/downloader`, `/api/client`, `/api/dev` (gated).

Ngoài ra `main.py` mount thêm: metrics (`/metrics`), outputs, thumbnails,
storage, snapshot, prompt_preview, job_report, job_clone, batch_render, files,
editing, v2 routes (ENABLE_V2).

## 2. Frozen contracts (Sacred)

3 endpoint đóng băng vĩnh viễn:

| Method | Path | Vai trò |
|--------|------|---------|
| POST | `/api/render/process` | Nhận `RenderRequestPublic` (88 field, extra=forbid) → tạo job |
| GET | `/api/jobs/{id}` | Poll trạng thái |
| WS | `/api/jobs/{id}/ws` | Stream tiến độ `{job, parts, summary}` |

`routes/jobs.py` xác nhận WS tại [jobs.py:732](../../backend/app/routes/jobs.py#L732),
polling `GET /{job_id}` tại [:235](../../backend/app/routes/jobs.py#L235). Có
`_ws_fingerprint` ([:711](../../backend/app/routes/jobs.py#L711)) để chỉ đẩy event
khi state đổi → giảm chattiness. **Tốt.**

## 3. REST design review

| Tiêu chí | Đánh giá | Dẫn chứng |
|----------|----------|-----------|
| Naming | Khá nhất quán, resource-based (`/jobs/{id}/parts/{n}/quality`) | jobs.py |
| Versioning | Có `v2/` routes song song (ENABLE_V2) nhưng v1 không version path | main.py:200 |
| Validation | Mạnh — Pydantic + `extra='forbid'` ở wire; validate output_dir/disk/source | _common.py |
| Pagination | Có `limit/offset` (`/jobs/history`, `/content/projects`) | jobs.py:159 |
| Response consistency | TB — vài endpoint trả `{ok:true}`, vài trả object trực tiếp | content/router.py |
| Status code | Đúng REST: 400/404/409/422/502/500 dùng hợp lý | content/router.py, _common.py |
| Auth/AuthZ | **KHÔNG có** (loopback-only, doc 16) | — |
| Rate limit | **KHÔNG có** | — |

## 4. Điểm mạnh

- **Public/Internal split (MT-3):** wire nhận `RenderRequestPublic` 88 field
  `extra='forbid'`; handler mở rộng sang `RenderRequest` 201 field server-side để
  áp validators + fill BE-only defaults. Bảo vệ Sacred #2 mà không phơi 152 field
  ra FE. **Thiết kế API-hardening tốt.**
- **Error classification 3-type** vào log tách biệt (doc 04).
- **HTTP polling luôn functional** song song WS — reliability guarantee cho
  Electron proxy chặn WS.
- **Dedup 2 lớp** ở `/process` chống double-submit (DB scan + recently-cancelled).

## 5. Vấn đề & khuyến nghị

### ⚠ V-API1: Không versioning path cho v1
- **Root cause:** v1 sinh trước khi có nhu cầu version; `extra='forbid'` giúp phát
  hiện field lạ nhưng đổi semantics 1 field vẫn phá client cũ.
- **Ảnh hưởng:** Thấp (desktop 1 client) nhưng chặn tiến hoá.
- **Ngắn hạn:** giữ nguyên (Sacred).
- **Dài hạn:** thêm `payload_schema_version` vào payload để adapter đọc bản cũ.

### ⚠ V-API2: Response shape không đồng nhất
- **Root cause:** mỗi phase thêm endpoint tự do chọn shape.
- **Ảnh hưởng:** Thấp. FE phải biết từng shape.
- **Dài hạn:** chuẩn hoá envelope `{data, error, meta}` cho endpoint MỚI (không
  đụng frozen 3 cái).

### ⚠ V-API3: Không rate-limit trên endpoint AI (content/plan, publish-meta)
- **Root cause:** loopback-only nên bỏ qua.
- **Ảnh hưởng:** TB nếu ai bật `ALLOW_REMOTE=1` — call AI trả phí không giới hạn.
- **Ngắn hạn:** thêm giới hạn concurrency/phút cho các endpoint gọi LLM khi
  `ALLOW_REMOTE=1`.

## 6. Đánh giá

| Trục | Điểm |
|------|------|
| REST design | 7 |
| Validation | 8.5 |
| Consistency | 6.5 |
| Security surface | 5 (doc 16) |
| **Tổng** | **6.8** |
