# 16 — Review Security

> Bối cảnh: đây là **desktop offline-first**, bind loopback. Mô hình đe dọa chính
> KHÔNG phải attacker từ xa mà là (a) sai cấu hình deploy remote, (b) input độc
> hại (path/filter injection), (c) devtools bật nhầm.

## 1. Authentication / Authorization

- **KHÔNG có auth trên BẤT KỲ endpoint nào** — có chủ đích cho loopback.
- **Bind guard (B1):** `app.main` gọi `assert_main_bind_safe(...)` **import-time**,
  từ chối khởi động khi bind non-loopback mà không có `ALLOW_REMOTE=1`
  ([main.py:150-153](../../backend/app/main.py#L150-L153)). Docker set ALLOW_REMOTE=1.
- **Đánh giá:** hợp lý cho desktop. **Rủi ro:** nếu user/ops bật `ALLOW_REMOTE=1`
  (hoặc reverse-proxy) thì **toàn bộ** surface (render/jobs/files/dev) phơi ra
  mạng không auth. Không có lớp auth tùy chọn để bật kèm.

**Khuyến nghị:** thêm optional token auth (header `X-App-Token`) kích hoạt tự động
khi `ALLOW_REMOTE=1`, để remote-mode không đồng nghĩa no-auth.

## 2. devtools.py — shell execution (3 lớp phòng thủ)

- Router **không mount** trừ `ENABLE_DEVTOOLS=1` (main.py:164).
- Mount-time loopback gate fail-closed (`assert_devtools_safe`).
- Request-time loopback check `is_loopback_client` ([devtools.py:22](../../backend/app/routes/devtools.py#L22)).
- **Đánh giá:** phòng thủ tốt, defense-in-depth. Giữ nguyên; không nới lỏng.

## 3. Path traversal (upload/file serving)

- `routes/files.py` — `_safe_filename` strip `../` + path separators, lưu **chỉ**
  dưới `APP_DATA_DIR/editor-uploads` ([files.py:35-51](../../backend/app/routes/files.py#L35-L51)).
- Content narration audio token 32-hex regex chống traversal
  ([content/router.py:50,158](../../backend/app/features/content/router.py#L50)).
- **Đánh giá:** tốt. **Cần kiểm thêm:** các endpoint serve output/thumbnail
  (`outputs.py`, `thumbnails.py`, `stream_part`) — output_dir do user cấu hình;
  cần đảm bảo không cho serve file ngoài output_dir/channels qua job_id giả.

## 4. Command / FFmpeg / SQL injection

- **FFmpeg:** dùng **list argv** (không `shell=True` — grep xác nhận 0 kết quả
  trong engine). `safe_filter_path()` escape filter graph. → **Không có command
  injection.** Đây là điểm rất tốt (path filter injection là lỗi thầm lặng phổ biến).
- **SQL:** repo dùng parameterized `?`. F-string execute chỉ 2 chỗ:
  - `download_repo.py:51` `SET {cols}` — `cols` là **tên cột** (không phải giá
    trị user); giá trị parameterized. **LOW risk** — cần xác nhận `cols` sinh từ
    whitelist field, không từ key payload tùy ý (nếu từ key payload → column
    injection giới hạn). **Khuyến nghị:** whitelist tên cột.
  - migration 0003 `ALTER RENAME {name}` — tên hằng nội bộ. An toàn.

## 5. Secrets / API keys

- API key LLM resolve qua `_resolve_api_key` + `key_pool.py`. Không thấy hardcode
  key trong code đọc. `.claude/settings.json` không chứa secret (CLAUDE.md).
- **Cần kiểm:** key lưu ở đâu (creator_prefs?) và có mã hoá at-rest không — với
  desktop thường lưu plaintext local; chấp nhận được nhưng nên ghi rõ.

## 6. XSS / CSP

- **CSP** áp cho v2 UI ([main.py:228-249](../../backend/app/main.py#L228)):
  `default-src 'self'`, script hash-pinned, `frame-ancestors 'none'`,
  `X-Frame-Options DENY`, `nosniff`. **Tốt** cho một app local.
- WS connect-src pin `ws://127.0.0.1:8000` / `localhost:8000`.

## 7. Rate limiting

- **Không có.** Với loopback OK; với remote/LLM-cost endpoint → rủi ro (doc 06).

## 8. Ma trận rủi ro

| Rủi ro | Khả năng | Ảnh hưởng | Mức |
|--------|----------|-----------|-----|
| Remote deploy no-auth (ALLOW_REMOTE=1) | Thấp | Rất cao | **HIGH** |
| devtools bật production | Rất thấp (3 gate) | Rất cao | MED |
| Column injection download_repo | Rất thấp | Thấp | LOW |
| Path traversal output serving | Thấp | TB | LOW-MED (cần kiểm) |
| API key plaintext at-rest | TB | TB | LOW (desktop) |
| No rate-limit LLM endpoint (remote) | Thấp | TB (cost) | LOW-MED |

## 9. Đánh giá

| Trục | Điểm |
|------|------|
| Injection defense (ffmpeg/sql) | 9 |
| Path safety | 8 |
| CSP/headers | 8 |
| Auth model | 4 (no-auth by design; thiếu optional auth cho remote) |
| Secrets | 6 |
| **Tổng (desktop)** | **7.0** · **Tổng (nếu remote)** | **4.5** |
