# SVG Asset System — Review & Plan (procedural art thay AI sinh hình)

> Lập 2026-07-11. **Trạng thái: PLAN — chờ duyệt.** Chưa sửa dòng code pipeline nào.
> Nguồn: đã sản xuất **273 asset SVG→PNG** vào `data/asset_library/` + builder chibi/
> mascot/scene (scripts scratchpad) + registry `asset_library/asset_registry.json`.
> Docs↔code mâu thuẫn → tin code. Đây là hồi đáp cho yêu cầu: (1) dựng bộ data để AI
> chọn nhân vật khớp bối cảnh, (2) không khớp thì **vẽ SVG procedural trong code** theo
> AI plan, (3) **thay toàn bộ tính năng AI sinh hình**.

---

## 0. Đã làm (asset offline)

| Loại | Số | Ghi chú |
|------|----|---------|
| Nhân vật | 174 file / **90 nhóm gốc** | chibi trẻ em; 6 vùng × nhiều thể loại + thú/linh vật + cưỡi ngựa/xe; biến thể **cảm xúc** (happy/angry/sad/surprised) + **tư thế** (wave/cheer/point/hip) |
| Nền | 68 file / **38 nhóm** | nhiều thể loại + cảnh nhà/sân vườn + **biến thể ngày/đêm** |
| Đồ vật · Frame | 15 · 16 | |
| **Registry** | `asset_registry.json` | gom base + variants + tags (suy từ slug/region/genre) — **bộ data cho AI match** |

Kho ở `APP_DATA_DIR/asset_library` (local, không commit). Style **chibi phẳng** — hợp
truyện thiếu nhi/tối giản; **không** tả thực/điện ảnh (giới hạn cốt lõi của hướng này).

---

## 1. Cơ chế library-first HIỆN CÓ trong code (đã verify)

Hạ tầng để "AI chọn asset thay vì sinh AI" **đã tồn tại một phần**:

| Thành phần | Vai trò | File |
|-----------|---------|------|
| `scan_library` / `match_asset` | index kho + tìm asset khớp theo kind/region/genre + name-similarity | `db/story_asset_repo.py` |
| `STORY_LIBRARY_FIRST` (default off) | auto-match **character master** trước khi gọi AI | `stages/story/visuals_stage.py:296` |
| AssetPicker (Review) | user gán **nền/nhân vật** library → `visual_assets`/`masters` → render skip AI | `frontend/.../PlanReview/AssetPicker.tsx` |
| `_ready(vid)` skip | Visual đã có file (từ picker/override) → **không** gọi AI | `visuals_stage.py:55` |

**Khoảng trống hiện tại (điểm cần vá):**
1. `match_asset` auto chỉ chạy cho **character master** ở **base-video mode**. Luồng ảnh
   mặc định (`_generate_images`) **không** tự match — nền/nhân vật vào qua **picker thủ công**.
2. AI plan (StoryPlan v2) **đã** xuất `characters[]` (name/canonical_desc/gender) +
   `settings[]` (name) + `visuals[]` (character_ids/setting_id) → **đủ dữ liệu để auto-match**,
   nhưng pipeline chưa dùng chúng để tra kho tự động cho visual thường.
3. Chưa có **procedural generator** trong backend — kho là ảnh tĩnh, hết asset là hết.

---

## 2. Kiến trúc đề xuất (3 tầng, degrade dần — Sacred #3)

```
AI plan (StoryPlan v2: characters/settings/visuals + thuộc tính)
   │
   ├─(A) MATCH kho tĩnh   → match_asset(region,genre,role,name) → có? dùng file (FREE, nhất quán)
   │        │ không khớp
   ├─(B) VẼ SVG procedural → build_svg(attrs từ AI plan) → rasterize → PNG (FREE, vô hạn biến thể)
   │        │ lỗi/không phù hợp
   └─(C) AI image (gpt-image) → chỉ khi bật premium (fallback cuối, tả thực)
```

Nguyên tắc: **A → B → C**. A/B miễn phí + offline. C giữ lại làm **tùy chọn premium**
(khuyến nghị **không xóa hẳn** — xóa mất khả năng tả thực + là frozen-behavior lớn).

---

## 3. Kế hoạch theo phase

### PHASE 0 — Consolidate (✅ ĐÃ LÀM hôm nay)
- 273 asset + `asset_registry.json` (90 nhóm nhân vật, 38 nhóm nền, tags).
- Convention path + scan/match đã chạy. **Không cần code mới.**

### PHASE A — Auto library-match cho luồng ảnh mặc định  · Tier **HIGH**  · ✅ DONE (2026-07-11)
> Merged `af973f01`. `_match_library_background` (char-less → nền kho), gate `STORY_LIBRARY_FIRST`.
> Chi tiết: [SVG_PHASE_0.5_A_PLANNER.md](SVG_PHASE_0.5_A_PLANNER.md).

**Mục tiêu:** AI plan → tự tra kho cho MỌI visual (không chỉ base-video master), trước khi gọi bất kỳ generator nào.
- `visuals_stage._generate_images`: trước khi gen 1 Visual, thử
  `match_asset('background', name=setting.name, region, genre)` cho nền +
  (nếu 1-nhân-vật) `match_asset('character', name=char.name, ...)`; khớp → set
  `visual_assets[vid]=path`, **skip AI**. Env `STORY_LIBRARY_FIRST` mở rộng ý nghĩa (vẫn default off → Sacred #2).
- Map `genre` truyện → thư mục kho (art_style/genre hint đã có trong plan).
- Emotion/pose: chọn variant theo `beat.emotion`/`char_anchor` nếu có (registry liệt kê sẵn).
- **Test:** match đúng region/genre; miss → path rỗng (degrade); e2e skip AI đếm được.
- **Rủi ro:** HIGH (đụng `visuals_stage`, gần orchestrator). Không đụng state machine.

### PHASE B — Procedural SVG generator trong backend  · Tier **HIGH** (mới, cô lập)  · ✅ DONE (2026-07-11)
> Merged `e547ec7c`. `svg_raster/char/presets/scene/compose.py` + gate `STORY_SVG_GEN`; rasterizer `resvg-py`.
> Chi tiết: [SVG_PHASE_B_PLANNER.md](SVG_PHASE_B_PLANNER.md).

**Mục tiêu:** port builder chibi/mascot/scene (đang ở Node scratchpad) → backend Python,
sinh SVG từ thuộc tính AI plan rồi rasterize → PNG. "Không có sẵn thì tự vẽ."
- **Module mới** `features/render/engine/visual/svg_char.py` + `svg_scene.py` (pure, no I/O
  ngoài ghi file; Sacred #3 return None on error).
- **Thuộc tính đầu vào** (AI plan phải xuất — thêm field vào CharacterDef/SettingDef,
  Sacred #2 default rỗng): `skin,hair,hair_style,outfit_kind,outfit_color,accessory,
  emotion,pose` cho nhân vật; `scene_kind,palette,tod` cho nền. AI đã suy được từ
  canonical_desc — chỉ cần prompt xuất thêm map gọn (enum cố định).
- **Rasterize** (quyết định kỹ thuật — xem §4).
- **Test:** attrs → SVG hợp lệ → PNG có alpha đúng size; offline, no network.
- **Rủi ro:** HIGH nhưng **cô lập** (module riêng, chưa thay default).

### PHASE C — Provider "svg" + đổi default  · Tier **HIGH→CRITICAL** (Render Edit Protocol)  · ✅ DONE (2026-07-11)
> Provider `svg` accepted (model + orchestrator validator); compose aspect-aware (16:9/9:16/1:1);
> FE story-studio **default = svg** ($0) + toggle Chibi/Free/Premium. Backend field default GIỮ
> `gpt_image` (Sacred #2 — replay bit-identical); gpt-image = premium opt-in, KHÔNG xóa. Full pytest 2957.
> Chi tiết: [SVG_PHASE_C_PLANNER.md](SVG_PHASE_C_PLANNER.md).

**Mục tiêu:** thêm `story_image_provider="svg"` (procedural) song song `gpt_image|pollinations`;
đặt **svg = default**; gpt-image thành opt-in premium.
- `story_image.generate_visual_image`: nhánh `provider=='svg'` → gọi PHASE B (A đã thử match trước).
- `models/render.py`: `story_image_provider` default đổi "gpt_image"→"svg" (**cân nhắc kỹ Sacred #2**:
  đây là đổi hành vi mặc định cho job MỚI — job cũ replay giữ nguyên giá trị đã lưu).
- **KHÔNG xóa** gpt-image/pollinations (giữ tùy chọn tả thực + backward-compat).
- **Test:** **full pytest** before/after (đụng CRITICAL surface); e2e render 1 truyện = SVG, 0 chi phí AI.
- **Rủi ro:** CAO — đổi default + đụng `story_image.py`(HIGH)/pipeline. Cần Planner + duyệt rõ.

### PHASE D — UX + mở rộng data  · Tier LOW-MED
- Registry hiển thị trong AssetPicker (lọc theo emotion/pose/tod).
- Tool sinh asset chạy được từ backend (thay scratchpad) → bổ sung kho theo nhu cầu.
- ai_eval so chất lượng cảm nhận SVG vs gpt-image trên tập truyện thật.

---

## 4. Quyết định kỹ thuật cần chốt (chặn PHASE B)

| Vấn đề | Lựa chọn | Khuyến nghị |
|--------|----------|-------------|
| **Rasterize SVG→PNG trong backend** | (a) `cairosvg` (Python, cần cairo native — khó trên Windows) · (b) `resvg-py`/`vtracer` · (c) **bundle Node + `@resvg/resvg-js`** (đã CHỨNG MINH chạy tốt: alpha, size, 273 ảnh) · (d) Pillow (không raster SVG) | **(c)** — đã proven, prebuilt binary, không cần build tool; gọi qua subprocess. Hoặc (b) nếu muốn thuần Python. |
| **AI plan xuất thuộc tính** | prompt thêm enum (skin/hair/outfit/emotion/pose/scene) | thêm vào super-prompt (HIGH, format-safe); default rỗng → generator tự suy từ canonical_desc |
| **Style** | chibi cố định | chấp nhận cho truyện thiếu nhi/tối giản; giữ gpt-image cho tả thực (đừng xóa) |
| **Nơi build asset** | scratchpad Node (hiện tại) → backend | port builder sang `scripts/` + module engine để tái tạo/mở rộng offline |

---

## 5. Sacred Contracts & rủi ro

- **#2** field mới (`story_image_provider` đổi default, thuộc tính SVG) — default an toàn;
  job cũ replay **bit-identical** (giữ giá trị đã lưu). Verify additive.
- **#3** generator/match **return None → degrade** (A miss→B, B lỗi→C/solid bg), không raise.
- **#8** output cuối vẫn qua qa_pipeline. **#4/#5** không đổi stage/part.
- **Tier:** `visuals_stage.py`/`story_image.py` = HIGH; đổi default provider chạm CRITICAL surface → **Render Edit Protocol** (baseline→edit→full pytest).
- **Rollback:** mỗi phase 1 env; đặt provider về `gpt_image` là về hành vi cũ 100%.

---

## 6. Đánh giá thẳng thắn (trước khi bạn duyệt)

- ✅ **Lợi:** chi phí ảnh **≈ $0** + nhất quán tuyệt đối + offline thật + vô hạn biến thể (emotion/pose/tod) — đúng triết lý dự án.
- ⚠️ **Mất:** style chibi **không tả thực/điện ảnh**. "Thay TOÀN BỘ AI sinh hình" nghĩa là mọi truyện thành hoạt hình phẳng. → **Khuyến nghị: SVG làm DEFAULT, gpt-image giữ làm premium opt-in**, thay vì xóa — vừa đạt mục tiêu $0, vừa không mất năng lực + không phá frozen-behavior.
- ⚠️ Procedural chibi khó đẹp cho **cảnh phức tạp / nhân vật đặc thù** — vẫn nên có picker thủ công (đã có) làm lớp tinh chỉnh.

---

## 7. Đề xuất bước kế tiếp (chờ bạn "go ahead")

1. **Chốt §4** (rasterizer = Node/resvg? style = chibi-only? giữ hay xóa gpt-image?).
2. Tôi viết **Planner analysis** chi tiết cho **PHASE A** (thay đổi từng dòng `visuals_stage.py`, test) — tier HIGH, cần duyệt trước khi Developer chạm.
3. Sau A ổn → PHASE B (generator Python) → PHASE C (đổi default, Render Edit Protocol).

> Không code pipeline nào bắt đầu tới khi bạn duyệt từng phase. Asset + registry + builder đã sẵn sàng làm nền.
