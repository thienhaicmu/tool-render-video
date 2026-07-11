# Planner Analysis — Phase B (procedural SVG generator in backend)

> Lập 2026-07-11. **Trạng thái: PLAN — chờ user "approved" trước khi Developer chạm code.**
> Thuộc [SVG_ASSET_SYSTEM_PLAN.md](SVG_ASSET_SYSTEM_PLAN.md); nối tiếp [SVG_PHASE_0.5_A_PLANNER.md](SVG_PHASE_0.5_A_PLANNER.md) (đã merged: match kho tĩnh).
> Mục tiêu Phase B: **"không có sẵn trong kho thì tự VẼ"** — sinh SVG chibi từ thuộc tính
> AI-plan rồi rasterize → PNG, offline, $0. Chưa đổi default provider (đó là Phase C).

## ✅ Quyết định kỹ thuật đã CHỐT + verify (gỡ nút thắt §4 của master plan)
- **Rasterizer = `resvg-py`** (PyPI 0.3.3). ĐÃ TEST trong venv sạch: render SVG→PNG
  **RGBA, đúng size**, cùng engine Rust resvg tôi đã dùng vẽ 273 asset → output đồng nhất.
  Pure-Python wheel (Win/Py3.11) — **không bundle exe, không Node subprocess**.
  API: `resvg_py.svg_to_bytes(svg_string=…, width=…, background=…)`.
- **Builder = PORT sang Python** (không gọi Node hot-path): logic SVG chuyển từ
  `chibi.mjs`/`mascot`/scene sang module backend thuần — versioned, testable, offline.
- **Style = chibi-only** (builder chừa tham số `style` để cắm sau). gpt-image GIỮ (Phase C premium).

## Ràng buộc kiến trúc quan trọng (định hình phạm vi B)
Một **Visual** trong StoryPlan = 1 ảnh WIDE 16:9 **có thể chứa nhân vật** (gpt-image sinh
cả cảnh + nhân vật). Kho SVG của ta tách rời **nhân vật (trong suốt)** và **nền (đặc)**.
→ Phase B phải **GHÉP**: nền + nhân vật đặt vào vùng LEFT/CENTER/RIGHT (đúng quy ước prompt)
→ 1 PNG wide. Đây là **compositor**, không chỉ gọi builder.

- **(a) Ghép vào key-visual** (KHUYẾN NGHỊ Phase B): 1 PNG/visual, slot thẳng vào seam
  `_generate_images`/provider — **HIGH, KHÔNG đụng cue renderer (CRITICAL)**.
- **(b) Overlay nhân vật per-beat** (tương lai): dùng master overlay như base-video mode cho
  luồng ảnh → nhân vật đổi cảm xúc/tư thế theo beat. Mạnh hơn nhưng **đụng cue render (CRITICAL)** → **HOÃN** (Phase B2/overlay riêng).

---

## Sub-phase & file

### B1 · Rasterizer plumbing — Tier **MEDIUM** (mới, cô lập)
- `requirements.txt` (hoặc `requirements-ai.txt`): `+ resvg-py`. **Lazy-import + degrade** (Sacred #3):
  thiếu wheel → generator return None → pipeline về AI/solid bg (base install vẫn chạy).
- MỚI `features/render/engine/visual/svg_raster.py`: `render_svg(svg:str, w:int, h:int, opaque_bg:str="")→bytes|None` (wrap `svg_to_bytes`, never raise) + `save_svg_png(svg, out_path, w, h, opaque_bg)`.
- **Test** `test_svg_raster.py`: SVG hợp lệ → PNG RGBA đúng size; opaque_bg → không alpha; thiếu dep (monkeypatch import None) → None.

### B2 · Character SVG builder + preset registry — Tier **HIGH** (mới, cô lập)
- MỚI `features/render/engine/visual/svg_char.py`: port `chibi()` (đầu to/thân mập/mắt to
  + emotion happy/angry/sad/surprised + pose wave/cheer/point/hip + outfit shirt/dress/robe/gown
  + hat/props). Pure str→str, never raise.
- MỚI `features/render/engine/visual/svg_presets.py`: bảng **archetype × region × genre → opts**
  (da/tóc/kiểu tóc/trang phục/màu/phụ kiện) — **suy từ roster 90 nhóm đã dựng** (chuyển từ
  `genchibi.mjs`). Lookup: `preset(archetype, region, genre, gender)→opts` với fallback dần
  (exact → archetype-only → generic). Unknown → 1 "everyman" mặc định.
- MỚI `svg_mascot.py` (tùy chọn, sau): thú/linh vật.
- **Test** `test_svg_char.py`: mỗi outfit/emotion/pose ra SVG hợp lệ (parse resvg OK); preset
  lookup fallback; unknown archetype → default; PNG alpha đúng.

### B3 · Scene SVG builder — Tier **HIGH** (mới, cô lập)
- MỚI `features/render/engine/visual/svg_scene.py`: port scene helpers (gradient + silhouette
  theo `scene_kind` + `tod` day/night). `scene(scene_kind, region, genre, tod)→svg` (16:9, opaque).
  Fallback: scene_kind lạ → gradient trung tính theo genre.
- **Test** `test_svg_scene.py`: scene_kind phổ biến (cafe/forest/throne_room…) ra SVG hợp lệ; tod night tint; unknown → fallback.

### B4 · Compositor (wide key-visual) — Tier **HIGH** (mới, cô lập)
- MỚI `features/render/engine/visual/svg_compose.py`:
  `compose_visual(plan, visual, w, h)→svg`:
  1. Nền = library match (Phase A `match_asset`) **hoặc** `svg_scene(setting.scene_kind,…)` embed base64.
  2. Đặt nhân vật (`visual.character_ids`) vào vùng theo số lượng: 1→center, 2→left+right, 3→
     left/center/right (đúng quy ước prompt "clear LEFT/CENTER/RIGHT zones"). Mỗi nhân vật =
     `svg_char(preset(char.archetype, plan.region, plan.genre_key, char.gender))` scale + translate.
  3. (emotion per-beat KHÔNG áp ở B — key-visual tĩnh; để B2/overlay).
- Kết quả 1 SVG wide → `svg_raster.save_svg_png` → PNG như gpt-image trả.
- **Test** `test_svg_compose.py`: 0/1/2/3 nhân vật → layout đúng; nền match vs scene-built; render PNG opaque đúng size.

### B5 · Wire vào pipeline (gated) — Tier **HIGH** (đụng `visuals_stage.py`)
- `visuals_stage._generate_images`: sau lớp match Phase A, với visual còn lại: nếu
  `provider=="svg"` **hoặc** env `STORY_SVG_GEN=1` (mới, default off) → `_gen_one` gọi
  `svg_compose`→`save_svg_png` thay `generate_visual_image`. Miss/lỗi → giữ AI/solid (Sacred #3).
- **KHÔNG** đổi default provider (vẫn gpt_image) — Phase C mới đổi.
- **Test** cập nhật `test_story_library_match`/`test_story_visual_*`: `STORY_SVG_GEN=1` → visual sinh bằng SVG (đếm không gọi gpt-image); default off → như cũ.

---

## Luồng thuộc tính (Phase 0.5 → B)
```
AI plan (s5): character.archetype/gender + plan.region/genre_key + setting.scene_kind
   → svg_presets.preset(archetype,region,genre,gender) → chibi opts
   → svg_char(opts) ⊕ svg_scene(scene_kind,region,genre,tod) → svg_compose → PNG
```
AI để trống hint → preset fallback "everyman"/gradient (vẫn ra ảnh, degrade mềm).

## Test & DoD
- Mỗi module unit (parse resvg OK + fallback). `STORY_SVG_GEN=1` e2e: 1 truyện render **0 gpt-image**, video qua QA #8.
- **Full pytest** before/after = baseline (đụng `visuals_stage` HIGH). py_compile mọi file mới.
- **DoD:** bật `STORY_SVG_GEN=1` → visual char-less lấy nền kho/scene-built; visual có nhân vật ghép chibi lên nền; PNG hợp lệ; gate off → byte-identical.

## Sacred Contracts & rủi ro
- **#2:** provider vẫn default gpt_image; env mới default off. Không đổi wire/RenderRequest ở B.
- **#3:** thiếu resvg-py / preset miss / compose lỗi → None → degrade AI/solid, không raise.
- **#8** QA sau; **#4/#5** cue/part không đụng (compositor tạo PNG TRƯỚC cue render, không sửa cue renderer).
- **Tier:** B1 MEDIUM; B2/B3/B4 HIGH nhưng **module mới cô lập**; B5 HIGH (`visuals_stage`, gated).
  **KHÔNG chạm** `story_image.py`/`render.py`/state machine (Phase C).
- **Rollback:** `STORY_SVG_GEN=0` (default) → tắt hoàn toàn; gỡ resvg-py → degrade tự động.

## Cổng duyệt đề xuất (làm từng cụm, duyệt giữa chừng)
1. **B1** (rasterizer, MEDIUM) — nhỏ, chứng minh raster trong backend. → duyệt.
2. **B2+B3** (builder+scene+preset, HIGH) — lõi nghệ thuật; test parse. → duyệt (xem PNG mẫu).
3. **B4+B5** (compositor + wire, HIGH) — ghép + gate; full pytest + e2e. → duyệt.
4. Sau B ổn (SVG render $0 chạy) → **Phase C** (provider `svg` = default, Render Edit Protocol).

## Ước lượng
Bulk = port builder (B2/B3, ~vài trăm dòng SVG-math từ JS đã proven) + preset table (suy từ roster). Rủi ro chủ yếu là công sức port, không phải kiến trúc (rasterizer + builder đã verify).

> Không code tới khi bạn "approved". Đề xuất bắt đầu **B1** (nhỏ, cô lập) để chốt raster trong backend, rồi B2+B3.
