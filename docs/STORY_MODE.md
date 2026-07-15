# Story Mode — Tài liệu chuẩn (code-verified, 2026-07-15)

> Viết từ source hiện tại sau đợt nâng cấp GĐ1→GĐ4 (commits `43ee6001..ca53a2eb`).
> Khi doc và code mâu thuẫn: **tin code**. Biến môi trường đầy đủ:
> [CONFIGURATION.md](CONFIGURATION.md) (mục Story). Spec cho agent sinh JSON:
> [STORY_MODE_OUTPUT_TEMPLATES.md](STORY_MODE_OUTPUT_TEMPLATES.md).

Story Mode biến **ý tưởng / chương truyện / StoryPlan JSON** thành video kể chuyện
minh hoạ: nhân vật từ kho hoạ sĩ (đa style), lồng tiếng đa giọng theo nhân vật,
nhạc nền theo mood, chạy offline sau khi plan xong ($0 ảnh).

## 1. Ba luồng input

| Nguồn (UI) | `story_source` | AI | Đường đi |
|---|---|---|---|
| Sáng tác từ ý tưởng | `idea` | 2 call (Writer → Structure) | Writer viết trọn truyện theo ngân sách ký tự |
| Truyện có sẵn | `paste` | 3 call (Understanding → Writer → Structure) | Trích fact có kiểm chứng → chuyển thể |
| Dán JSON (không AI) | `paste_json` | 0 call | Render VERBATIM `story_plan_override` |

Cả ba hội tụ về **StoryPlan v2** (`app/domain/story_plan_v2.py`) — contract bất biến
giữa plan và render.

## 2. Sinh nội dung — Story Compiler (GĐ1)

```text
[paste] chương gốc
  → PASS 1 UNDERSTANDING (JSON-mode call): nhân vật/địa điểm/quan hệ + SỰ KIỆN
    theo thứ tự, mỗi sự kiện kèm CÂU TRÍCH NGUYÊN VĂN
      ↳ validator máy (story_understanding.py): khớp trích dẫn vào chương —
        coverage / thứ tự / mất-đoạn-kết
  → PASS 2 WRITER (prose call, KHÔNG JSON — _call_*_writer, temp 0.8):
    kịch bản screenplay-lite ([SCENE:]/NARR:/Tên (emotion): "...")
    + 7 luật văn + 14 style-pack thể loại + checklist "phủ đủ sự kiện"
      ↳ validator: speaker tồn tại, MAJOR event coverage, tail, độ dài
      ↳ thiếu MAJOR event → MỘT vòng repair có chủ đích (STORY_SCRIPT_REPAIR)
      ↳ [idea] ngân sách = duration × CPS × 1.8; ngắn → loop đo len(script)
  → PASS 3 STRUCTURE (strict-schema call sẵn có): script → StoryPlan,
    "never rewrite — wording verbatim"; CHARACTER TABLE ghim id;
    lines[] đa giọng; nhãn pace/pause (label-only → reading_speed/pause_after)
  → fallback: compiler fail bất kỳ đâu → đường 1-call cũ (không mất render)
```

Gate: `STORY_COMPILER=1` (mặc định; `=0` → legacy s24 bit-identical).
`STORY_MULTILINE_BEATS` unset = auto theo compiler. Prompt version: **s25**
(`ai/llm/story_prompts_v2.py`); orchestration: `ai/llm/story_director_v2.py`.

## 3. Nhân vật & kho asset (GĐ2 + GĐ3)

### Kho style-aware
```text
data/asset_library/{kind}/{region}/{genre}/{style?}/{slug}.png  (+ {slug}.png.json sidecar)
  character/us/hiendai/geeme_001..100.png          style="" (dùng chung mọi style)
  character/jp/{hiendai|codai}/{style}/jp_*.png     24 vai × 3 style JP
  background/... (66 nền procedural style="" + 12 nền JP × 3 style)
```
- `style` = style-pack id (`jp_anime_clean_v1|jp_anime_cinematic_v1|jp_anime_soft_drama_v1`).
- `active_library_style(story_art_style)` map input UI → style đã cài; mọi query
  (`get_by_slug/best_asset/catalog`) ưu tiên biến thể style hoạt động, fallback styleless.
- Importers: `scripts/import_geeme_pack.py`, `scripts/import_jp_library.py`,
  vision-tagging `scripts/tag_geeme_pack.py`. Rebuild bộ JP:
  `scripts/build_jp_three_style_library.py` → import lại.

### Resolver-first (GĐ3 — `engine/visual/character_resolver.py`)
AI **chỉ mô tả** nhân vật; engine gán asset deterministic:
1. Lock series (`characters.asset_slug`, migration 0026) → `matched_exact`
2. Pick tay ở Review / slug trong JSON dán → `matched_exact`
3. Chấm điểm mô tả (cầu VI→EN ~40 từ khoá ngoại hình) + hard-filter giới tính
   + **unique** (không trùng mặt) → `matched` / `needs_approval` / `missing`

Trạng thái nằm ở `plan.render.asset_status` → chip trên Review + field
`asset_resolution` của `/plan`, `/validate`. Nhân vật `missing` render KHÔNG overlay
(kèm WARNING) — không thế thân bừa. Gate: `STORY_CHAR_RESOLVER=1`.
Series memory (`pipeline/story_series_memory.py`): lock mặt + giọng + "story so far".

## 4. Render pipeline (`pipeline/story_pipeline_v2.py`)

```text
resolve plan (override → resume → compiler) → derive_beat_styling
→ RESOLVER (GĐ3) → READINESS GATE (GĐ4b, 8 tiêu chí — story_readiness.py)
→ key-visuals SVG (nền-only) + overlay masters per (speaker,emotion,pose)
→ TTS per-beat/per-line (đa giọng; resume bỏ qua beat có audio — STORY_TTS_REUSE)
→ CUE SHEET định thức (duration TTS thật + seed)
→ render cue song song (libx264 CPU, không đụng NVENC; resume reuse clip — STORY_CUE_REUSE)
→ assemble xfade → BGM placed per-beat → QA (#8) → DONE (result_json đủ Sacred #1)
```

### Composition (GĐ4a — `engine/visual/composition.py`)
Một nguồn hình học cho compose + overlay: layout theo số nhân vật; nhân vật bên
phải **mirror để đối mặt**; khung dọc 9:16 reflow (×0.85 + slot dạt biên); chữ hook
chọn **góc trên trống** so với slot bị chiếm (token nội bộ `top_left/top_right`,
enum plan không đổi).

### Readiness (GĐ4b)
FAIL chặn render: timeline rỗng / không visual / thư mục xuất không ghi được /
đĩa <1GB. Còn lại WARN (identity thiếu, lệch thời lượng, thiếu key TTS trả phí...)
hiện ở `/plan` + monitor. Gate: `STORY_READINESS_GATE=1`.

## 5. API surface (`features/story/router.py` + render dispatch)

| Endpoint | Vai trò |
|---|---|
| `POST /api/story/plan` | Plan đồng bộ (giữ tương thích) |
| `POST /api/story/plan/async` + `GET /api/story/plan/async/{id}` | Plan chạy nền (FE dùng mặc định — compiler chạy phút với chương dài) |
| `POST /api/story/validate` | Preflight JSON dán (không AI) + resolver + trả `plan_normalized` |
| `POST /api/story/visual/svg-preview`, `/character/reference-sheet`, `/narration/preview`, `GET /voices` | Preview WYSIWYG ở Review |
| `GET/POST /api/story/projects*` | Project + autosave + versions + trash |
| `GET/POST /api/story/assets*` | Kho asset (list/scan/image/delete) |
| `POST /api/render/process` với `render_format="story"` | Render (dispatch `run_story_v2`) |
| `GET /api/jobs/{id}/story-plan`, `/story-visual/{vid}` | Monitor polling + thumbnail |

Response `/plan` (additive): `authoring_mode`, `asset_resolution`, `readiness`,
`cost_preflight.estimated_llm_calls`, `warnings` (lint + readiness + độ dài).

## 6. Bản đồ file

| Tầng | File |
|---|---|
| Domain | `app/domain/story_plan_v2.py` |
| Compiler | `ai/llm/story_prompts_v2.py` · `story_director_v2.py` · `story_understanding.py` · `story_schema_v2.py` · providers `_call_*_writer` |
| Resolver/Identity | `engine/visual/character_resolver.py` · `db/story_repo.py` · migration 0026 · `pipeline/story_series_memory.py` |
| Kho asset | `db/story_asset_repo.py` (style-aware) · `scripts/import_*.py`, `tag_geeme_pack.py` |
| Render | `pipeline/story_pipeline_v2.py` · `stages/story/*` · `engine/visual/{composition,svg_compose}.py` · `audio/story_narration.py` · `pipeline/story_readiness.py` |
| Visual v2 (styles) | `engine/visual/v2/*` (look_spec, anime_char, theme_pack, jp_catalog, lottie_pack, styles) — xem [OFFLINE_JP_VISUAL_LIBRARY.md](OFFLINE_JP_VISUAL_LIBRARY.md), [STYLE_PACK_SPEC.md](STYLE_PACK_SPEC.md) |
| FE | `frontend/src/features/story-studio/*` · `api/story.ts` |

## 7. Công tắc lùi (rollback từng lớp)

| Env=0 | Trở về |
|---|---|
| `STORY_COMPILER` | 1-call legacy (prompt s24, schema cũ, multiline off) |
| `STORY_CHAR_RESOLVER` | AI tự pick slug từ catalog (catalog đủ 2 section) |
| `STORY_READINESS_GATE` | Chỉ log, không chặn |
| `STORY_TTS_REUSE` / `STORY_CUE_REUSE` | Resume làm lại toàn bộ |
| `STORY_SCRIPT_REPAIR` / `STORY_PLAN_REPAIR` | Không repair |
| `STORY_SERIES_MEMORY` / `STORY_LIBRARY_PICK` | Tắt memory / catalog |

## 8. Kiểm thử

~130 test chuyên Story (`backend/tests/test_story_*`, `test_character_resolver`,
`test_asset_library_styles`, `test_visual_v2_*`, `test_lottie_pack`, `test_story_gd4`).
Toàn suite: `python -m pytest` (3191 pass tại thời điểm viết).
