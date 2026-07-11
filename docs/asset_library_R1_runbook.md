# Asset Library — R1 Runbook (đợt 1, file-level checklist)

> Lập 2026-07-11. **Bổ sung** cho [asset_library_backlog.md](asset_library_backlog.md)
> (category-level) bằng danh sách **từng file** để tick khi sản xuất. Sản xuất **thủ
> công** qua prompt catalog (đã copy-ready). Prompt đầy đủ nằm trong các catalog —
> runbook chỉ trỏ dòng, **không paste lại** (tránh drift). Convention verified từ
> [`story_asset_repo._parse_path`](../backend/app/db/story_asset_repo.py) + AssetPicker.

## 0. Cơ chế library-first (verified) — asset nào giúp mode nào

Đọc kỹ trước khi sản xuất, để không phí công:

| Kind | Đường tiêu thụ (verified) | Mode dùng được |
|------|---------------------------|----------------|
| **background** | Review picker → `render.visual_assets[vid]=path` → `_generate_images._ready()` skip AI ([VisualsPanel.tsx:123](../frontend/src/features/story-studio/PlanReview/VisualsPanel.tsx#L123)) | **Mọi mode** — dùng ngay. ⚠️ Chỉ gán cho Visual **không có nhân vật** (establishing shot); gán vào visual có nhân vật sẽ làm mất nhân vật |
| **character** | (a) Picker → `render.masters[cid]`; (b) auto-match `STORY_LIBRARY_FIRST=1` trong `_generate_character_masters` | **Chỉ base-video mode** (master trong suốt overlay lên base video). Mode ảnh mặc định KHÔNG overlay master |
| **frame** | *(chưa có picker/consumer trong pipeline default)* | **Tương lai** — index được nhưng render chưa dùng. Sản xuất để dành |
| **object** | *(chưa có picker/consumer)* | **Tương lai** — như frame |

> Kết luận: giá trị **ngay** = **background** (mode ảnh) + **character** (mode base-video).
> frame/object sản xuất theo backlog nhưng đánh dấu "để dành".

## 1. Thiết lập chung

- Đích lưu: `ASSET_LIBRARY_DIR` = `APP_DATA_DIR/asset_library` (default,
  [config.py:60](../backend/app/core/config.py#L60)).
- gpt-image-1 settings theo kind (xem đầu mỗi catalog):
  - character/frame/object → `background="transparent"`, PNG, **1024×1536** (dọc).
  - background → `background="opaque"`, PNG, **1536×1024** (ngang 16:9), **KHÔNG người**.
- Cùng 1 nhân vật/địa điểm → giữ NGUYÊN prompt + seed cố định → sinh 1 lần → khoá.
- Sau mỗi batch: kiểm acceptance §5 → **Quét kho** (§4).

## 2. Danh sách file đợt 1 (~20 + 1 manifest)

### B1 — Nhân vật JP hiện đại (10) · `character/jp/hiendai/{slug}.png`
Prompt: [asset_library_characters.md](asset_library_characters.md) §🇯🇵 NHẬT — HIỆN ĐẠI.

- [ ] `jp_hiendai_haruto_office_worker_male` — L28
- [ ] `jp_hiendai_yuki_cafe_staff_female` — L32
- [ ] `jp_hiendai_tanaka_ceo_male` — L36
- [ ] `jp_hiendai_emi_child_girl` — L40
- [ ] `jp_hiendai_sato_office_lady_female` — L44
- [ ] `jp_hiendai_kenji_salaryman_male` — L48
- [ ] `jp_hiendai_aoi_university_student_female` — L52
- [ ] `jp_hiendai_ren_highschool_boy` — L56
- [ ] `jp_hiendai_mei_highschool_girl` — L60
- [ ] `jp_hiendai_hiroshi_grandpa_male` — L64

### B2 — Nền JP (4)
Prompt: [asset_library_backgrounds.md](asset_library_backgrounds.md) §🇯🇵 JP.

- [ ] `background/jp/hiendai/jp_hiendai_cozy_cafe.png` — L55
- [ ] `background/jp/hiendai/jp_hiendai_tokyo_street_night.png` — L59
- [ ] `background/jp/hiendai/jp_hiendai_classroom_afternoon.png` — L63
- [ ] `background/jp/codai/jp_codai_shrine_sakura.png` — L67 *(lưu ý: dưới `jp/codai`)*

### B3 — Frame phổ dụng (3) — *để dành, chưa render*
Prompt: [asset_library_frames.md](asset_library_frames.md).

- [ ] `frame/minimal/subtitle_lower_third.png` — L91
- [ ] `frame/minimal/thin_white_border.png` — L95
- [ ] `frame/sakura/sakura_petal_border.png` — L39

### B4 — Đồ vật JP (3) — *để dành, chưa render* · `object/jp/{slug}.png`
Prompt: template [asset_library_prompts.md §4](asset_library_prompts.md) (đồ vật, transparent).

- [ ] `object/jp/phone.png` (điện thoại)
- [ ] `object/jp/coffee_cup.png` (tách cà phê)
- [ ] `object/jp/schoolbag.png` (cặp sách)

### B5 — Provenance manifest (1)
- [ ] `asset_library/asset_sources.json` — seed license/source theo family. Shape +
  ví dụ: [asset_library_prompts.md §8](asset_library_prompts.md). Nhân vật tự sinh →
  `license: ai-generated`. (Tuỳ chọn; scan có default `ai-generated`/`local` nếu thiếu.)

## 3. Convention nhắc lại (sai path → không index)

```
character/{region}/{genre}/{slug}.png     region=jp genre=hiendai
background/{region}/{genre}/{slug}.png
object/{region}/{slug}.png                 (chỉ region, KHÔNG genre)
frame/{style}/{slug}.png                    (style, KHÔNG region/genre)
```
`transparent` mặc định = True cho character/object/frame, False cho background —
scan tự suy từ kind, khỏi khai báo.

## 4. Quét kho (index)

```
Backend chạy → POST /api/story/assets/scan     (hoặc nút "↻ Quét kho" trong AssetPicker)
→ {"indexed": N, "pruned": M, "root": "…/asset_library"}
```
Kiểm: `GET /api/story/assets?kind=character&region=jp` → thấy 10 nhân vật ·
`?kind=background&region=jp` → thấy 4 nền.

## 5. Acceptance mỗi asset (§0 backlog)

- [ ] Đúng path convention (§3).
- [ ] character/object/frame: **alpha thật** (mở trên nền carô — giữa/xung quanh trong suốt).
- [ ] background: **đặc, 16:9, KHÔNG người**.
- [ ] frame: **giữa rỗng ≥80%**, viền mảnh.
- [ ] Không chữ/logo/watermark; không méo tay/mặt (nhân vật).
- [ ] scan index được (hiện trong picker đúng kind/region/genre).

## 6. Verify end-to-end (chứng minh giảm chi phí)

1. **Mode ảnh** — 1 truyện JP ngắn (paste) → Review → ở 1 Visual establishing (không
   nhân vật) bấm picker nền → chọn 1 nền JP → Render. Kỳ vọng: log `_ready → skip`
   cho visual đó, **số ảnh gpt-image giảm 1**; video qua QA #8.
2. **Mode base-video** — `STORY_LIBRARY_FIRST=1` + cấp base video → Render 1 truyện có
   nhân vật tên khớp kho (vd "Haruto"). Kỳ vọng: log `match_asset` khớp master →
   **0 gpt-image cho master đó**.
3. Đo trước/sau: số call gpt-image = số visual/master lấy từ kho.

## 7. Ghi chú

- Chi phí sinh ~20 ảnh: ~$0.8–1.4 (gpt-image-1), 1 lần → khoá vĩnh viễn.
- Kho ở `APP_DATA_DIR` — **không commit repo**; sao lưu thủ công nếu cần.
- Pháp lý: nhân vật **luôn tự sinh** (không tải Canva/Freepik — vi phạm license khi vào
  video xuất ra). Nền/đồ vật có thể bổ sung CC0 + ghi `asset_sources.json`
  ([backlog §6](asset_library_backlog.md)).
- frame/object đợt 1 = **để dành**: khi pipeline thêm consumer (frame overlay / object
  picker) sẽ dùng ngay, không phải sinh lại.
