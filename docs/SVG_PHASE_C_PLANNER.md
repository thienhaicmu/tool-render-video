# Planner Analysis — Phase C (SVG as the default image path)

> Lập 2026-07-11 từ **code hiện tại**. **Trạng thái: PLAN — chờ user "approved".**
> Nối tiếp Phase 0.5/A (merged) + B (merged: procedural SVG chạy khi `provider=="svg"`
> hoặc `STORY_SVG_GEN=1`). Mục tiêu C: **SVG thành đường MẶC ĐỊNH** cho render mới,
> gpt-image lùi về **opt-in premium** — KHÔNG xóa.

## Nguyên tắc chốt (Sacred #2) — theo tiền lệ `tts_engine`
CLAUDE.md ghi rõ tiền lệ: *"UI mặc định chọn tts_engine=gemini … Backend RenderRequest.tts_engine
vẫn mặc định 'edge' (Sacred #2) — chỉ FE đổi default."* Áp Y HỆT cho image provider:
- **Backend field `story_image_provider` GIỮ default `"gpt_image"`** (render.py:428) + validator
  vẫn coerce unknown→`gpt_image` → **replay job cũ bit-identical** (Sacred #2 nguyên vẹn).
- **FE đổi default gửi `"svg"`** → mọi render MỚI qua FE dùng SVG ($0). gpt-image chọn qua toggle.
- **Không đổi model default** → không đụng replay của job pre-field. Đây là cách "svg là default"
  AN TOÀN nhất (không vi phạm #2), gpt-image vẫn 1 lựa chọn.

## Hiện trạng (verified)
- `models/render.py:428` field default `"gpt_image"`; `:562` validator accept `{gpt_image, pollinations}`, unknown→gpt_image.
- `story_pipeline_v2.py:271-273` (orchestrator, **CRITICAL**) coerce `not in ("gpt_image","pollinations") → "gpt_image"`, rồi `_generate_images(provider=…)`.
- Phase B: `_generate_images` đã xử lý `provider=="svg"` (compose→raster, degrade solid).
- FE story-studio **chưa** gửi `story_image_provider` → backend default áp.
- `render_public.py:181` đã có field trên wire; `render_field_groups.py:56` đã nhóm.

→ Việc còn thiếu để "svg = default": **(1) accept giá trị "svg"** ở 2 validator, **(2) FE default gửi "svg"** (+ toggle premium).

---

## Thay đổi theo file

### C1 · `models/render.py` — Tier **HIGH** (Sacred #2 surface)
- `_validate_story_image_provider` (:562): thêm `"svg"` vào set chấp nhận →
  `return v if v in {"gpt_image", "pollinations", "svg"} else "gpt_image"`. **GIỮ** coerce-default
  `gpt_image` (replay). Cập nhật comment field (:428) `# gpt_image|pollinations|svg`. **Không đổi default.**

### C2 · `story_pipeline_v2.py` — Tier **CRITICAL** (orchestrator — Render Edit Protocol)
- Dòng 272: `if image_provider not in ("gpt_image", "pollinations", "svg"):` (thêm 1 token).
- **Chỉ 1 dòng**, không đụng stage/state machine. Vẫn theo Render Edit Protocol: **full pytest before/after**, edit tối thiểu.

### C3 · Aspect guard (chống méo) — Tier **HIGH** (module B, cô lập)
- `svg_compose`/`svg_scene` hiện cứng 1536×1024 (16:9). Story default 16:9 → khớp. Với 9:16/1:1
  sẽ méo. **Quyết định (khuyến nghị):** làm `compose_visual`/`scene_inner` **nhận w,h** (scene fill
  w×h; zone scale theo w,h) → SVG đúng mọi aspect. *(Nếu hoãn: guard ở `_generate_images` — provider=="svg" mà aspect≠16:9 → fall to gpt-image, tránh méo.)*
- Khuyến nghị **làm aspect-aware** (nhỏ, module mới cô lập) để svg-default đúng mọi tỉ lệ.

### C4 · FE story-studio — Tier **LOW-FE**
- `api/story.ts` (types) + submit payload: thêm `story_image_provider` (union `'svg'|'gpt_image'|'pollinations'`), **default `'svg'`** trong submitRender.
- `frontend/src/types/api.ts`: `story_image_provider?: 'svg'|'gpt_image'|'pollinations'` (nếu chưa có union svg).
- (Tùy chọn, khuyến nghị) InputScreen: toggle nhỏ **"Ảnh: Chibi miễn phí (mặc định) | AI cao cấp"** + cost hint — để user chủ động chọn premium. Không bắt buộc cho "default".
- `tsc -b` + `npm run build`.

### C5 · Docs — Tier LOW
- `CONFIGURATION.md`: ghi `story_image_provider` nhận `svg` (default path); STORY_SVG_GEN là global override.
- `SVG_ASSET_SYSTEM_PLAN.md` §3: đánh dấu Phase C DONE.

---

## Test
| Test | Kiểm |
|------|------|
| `test_story_v2_fields`/model | validator accept "svg"; unknown vẫn →gpt_image; **default field vẫn "gpt_image"** (Sacred #2) |
| `test_story_dispatch` | provider="svg" qua wire → pipeline không coerce về gpt_image |
| `test_story_svg_gen` (bổ sung) | provider="svg" (không cần STORY_SVG_GEN) → svg path |
| `test_svg_compose` (nếu C3 aspect) | 9:16/1:1 → SVG đúng w,h |
| FE | `tsc -b` xanh; submit mặc định "svg" |
| **Full pytest** | before/after = baseline (C2 CRITICAL) |

## Sacred Contracts & rủi ro
- **#2:** field default GIỮ "gpt_image"; validator coerce unknown→gpt_image → **replay bit-identical**. Chỉ thêm "svg" vào set accept (additive). FE đổi default = product decision (như tts_engine).
- **#3:** svg lỗi → degrade (solid cho provider=="svg"). **#8** QA sau. **#4/#5** không đụng.
- **Tier:** C1 HIGH, **C2 CRITICAL (1 dòng, Render Edit Protocol)**, C3 HIGH (module B), C4 LOW-FE.
- **KHÔNG xóa** gpt-image/pollinations. Rollback: FE gửi lại "gpt_image" (hoặc user chọn toggle); backend chưa đổi default nên revert FE là đủ.

## Cổng duyệt đề xuất
1. **C1+C2+C3** (backend accept svg + aspect-aware) — full pytest. → duyệt.
2. **C4** (FE default svg + toggle) — tsc/build. → duyệt.
3. (Tùy chọn) `/verify` render thật 1 truyện = SVG $0.

> Khuyến nghị: **giữ nguyên khuyến nghị "svg default qua FE, backend field conservative"** —
> không đổi model default (an toàn #2 tuyệt đối). Nếu bạn muốn **server-side default cứng = svg**
> (đổi field default), tôi sẽ cảnh báo rõ tác động replay job pre-field + cần duyệt riêng.

> Không code tới khi bạn "approved". Đề xuất bắt đầu C1+C2+C3 (backend), rồi C4 (FE).
