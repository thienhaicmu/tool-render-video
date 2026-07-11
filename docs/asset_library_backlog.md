# Story Asset Library — BACKLOG khâu tạo hình

Kế hoạch **sản xuất** kho asset offline (không phải code — code AL0-AL5 đã xong).
Mục tiêu: có sẵn **nhân vật · nền · frame · đồ vật** để Story Mode dùng mặc định
(library-first) thay vì gọi AI mỗi lần → **tiết kiệm tiền + nhất quán tuyệt đối**.

> **Checklist thực thi file-level (đợt 1):** [asset_library_R1_runbook.md](asset_library_R1_runbook.md)
> — danh sách từng file để tick + cơ chế library-first (asset nào giúp mode nào) + verify.

Nguồn prompt:
- Nhân vật → [asset_library_characters.md](asset_library_characters.md)
- Nền → [asset_library_backgrounds.md](asset_library_backgrounds.md)
- Frame → [asset_library_frames.md](asset_library_frames.md)
- Template + đồ vật + quy ước + nguồn CC0 → [asset_library_prompts.md](asset_library_prompts.md)

Đích lưu: `APP_DATA_DIR/asset_library/{kind}/{region}/{genre}/{slug}.png`
(xem `asset_library_prompts.md §0`). Sinh xong → app **Quét kho** (nút 🗂️ trong Review,
hoặc `POST /api/story/assets/scan`) → asset xuất hiện trong picker.

---

## 0. Định nghĩa "Done" (acceptance mỗi asset)

- [ ] Đúng path theo quy ước (`{kind}/{region}/{genre}/{slug}.png`)
- [ ] Nhân vật/đồ vật/frame: **nền trong suốt thật** (mở trên nền carô kiểm tra alpha)
- [ ] Nền: ảnh **đặc, 16:9, KHÔNG người**
- [ ] Frame: **giữa rỗng ≥80%**, viền mảnh
- [ ] Không chữ/logo/watermark; không méo tay/khuôn mặt (nhân vật)
- [ ] (Tuỳ chọn) sidecar `{file}.json` ghi `license`/`source`/`tags` nếu tải CC0
- [ ] `scan_library` index được (hiện trong picker, đúng kind/region/genre)

---

## 1. Ưu tiên (đợt 1 — tối thiểu chạy được)

Mục tiêu đợt 1: đủ để render **1 thị trường trọng điểm** end-to-end bằng kho.

| # | Hạng mục | Số lượng | Nguồn prompt | Ưu tiên |
|---|---|---|---|---|
| B1 | Nhân vật JP hiện đại (Haruto/Yuki/Tanaka/Emi + phụ) | ~10 | characters.md | P0 |
| B2 | Nền JP hiện đại (cafe/phố đêm/lớp học/đền sakura) | 4 | backgrounds.md | P0 |
| B3 | Frame phổ dụng (lower-third · viền mảnh · sakura) | 3 | frames.md | P0 |
| B4 | Đồ vật JP cơ bản (điện thoại · tách cà phê · cặp sách) | 3 | prompts.md §4 | P1 |
| B5 | `asset_sources.json` seed (license/source theo family) | 1 | prompts.md §8 | P1 |

**Kết quả đợt 1:** bật `STORY_LIBRARY_FIRST=1`, tạo 1 truyện JP hiện đại → nhân vật
lặp lại tự khớp master từ kho, nền gán qua picker → **render $0**.

---

## 2. Đợt 2 — phủ thị trường

| # | Hạng mục | Số lượng ước | Nguồn |
|---|---|---|---|
| C1 | Nhân vật CN wuxia/cổ đại | ~10 | characters.md |
| C2 | Nhân vật KO cổ trang + hiện đại | ~8 | characters.md |
| C3 | Nhân vật VI cổ trang + hiện đại | ~8 | characters.md |
| C4 | Nhân vật EU fantasy + US hiện đại | ~10 | characters.md |
| C5 | Nền CN/KO/VI/EU/US (mỗi vùng 3-5) | ~20 | backgrounds.md |
| C6 | Frame theo style (wuxia/hanbok/gold/neon/horror/festive) | ~10 | frames.md |
| C7 | Phản diện · phụ · trẻ em · người già · quái vật | ~15 | characters.md §2B |

---

## 3. Đợt 3 — chiều sâu & biến thể (rẻ)

- **Biến thể cảm xúc** nhân vật chủ chốt: bình thản / vui / giận / buồn / chiến đấu
  (giữ nguyên prompt, đổi `{EXPRESSION}`) — tăng biểu cảm khi overlay.
- **Biến thể thời gian** cho nền: bình minh/trưa/hoàng hôn/đêm (đổi `{TIME/LIGHT}`,
  hậu tố slug `_night`…) — bộ cảnh nhất quán 1 địa điểm.
- **Đồ vật/frame** bổ sung theo nhu cầu truyện thực tế.

---

## 4. Quy trình sản xuất (batch)

1. Chọn hạng mục (vd B1), mở file prompt tương ứng.
2. Sinh từng ảnh (gpt-image-1 với thiết lập ở đầu mỗi file: transparent/opaque, kích thước).
3. **Kiểm alpha/nội dung** theo acceptance §0; sinh lại nếu lỗi (thêm token âm).
4. Lưu đúng path quy ước; (tuỳ chọn) viết sidecar `{file}.json`.
5. Sau mỗi batch: **Quét kho** → xác nhận asset lên picker đúng kind/region/genre.
6. Tick tiến độ ở §5.

> **Mẹo nhất quán + rẻ:** cùng 1 nhân vật/địa điểm → giữ NGUYÊN prompt + `seed` cố định,
> chỉ đổi 1 biến (cảm xúc/thời gian). Sinh 1 lần → **khoá** → tái dùng miễn phí.

---

## 5. Bảng theo dõi (tick khi xong)

### Đợt 1 (P0/P1)
- [ ] B1 — Nhân vật JP hiện đại (~10)
- [ ] B2 — Nền JP hiện đại (4)
- [ ] B3 — Frame phổ dụng (3)
- [ ] B4 — Đồ vật JP cơ bản (3)
- [ ] B5 — `asset_sources.json` seed

### Đợt 2
- [ ] C1 CN · [ ] C2 KO · [ ] C3 VI · [ ] C4 EU/US
- [ ] C5 Nền đa vùng · [ ] C6 Frame theo style · [ ] C7 Phản diện/phụ/trẻ em/già/quái vật

### Đợt 3
- [ ] Biến thể cảm xúc nhân vật chủ chốt
- [ ] Biến thể thời gian cho nền
- [ ] Đồ vật/frame theo nhu cầu

---

## 6. Rủi ro & lưu ý pháp lý

- **KHÔNG** tải nhân vật stylized từ Canva/Pixabay/Pexels/Freepik để phát hành lại
  (vi phạm license khi asset vào video xuất ra) — tự sinh. Xem `prompts.md §7`.
- Nền/đồ vật có thể **tải CC0** (Openverse / The Met / Kenney / OpenGameArt) — **bắt
  buộc** ghi `license`/`source` vào sidecar hoặc `asset_sources.json`.
- Kho nằm ở `APP_DATA_DIR` (không commit vào repo) — sao lưu thủ công nếu cần.
