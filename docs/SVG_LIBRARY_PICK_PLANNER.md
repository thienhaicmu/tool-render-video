# Planner Analysis — Library-Pick (AI plan chooses assets from the library)

> Lập 2026-07-11 từ **code hiện tại** (`db/story_asset_repo.py`, `ai/llm/story_prompts_v2.py`,
> `ai/llm/story_director_v2.py`, `ai/llm/__init__.py`, `engine/pipeline/story_pipeline_v2.py`,
> `domain/story_plan_v2.py`, `engine/visual/svg_compose.py`). **Trạng thái: PLAN — chờ user
> "approved".** Realize ý định gốc: **AI plan tự QUYẾT ĐỊNH chọn nhân vật/cảnh cụ thể từ kho**
> (thay vì fuzzy-match hoặc procedural). Gate `STORY_LIBRARY_PICK` (default off) → an toàn/so sánh.

## Nguyên tắc
- **Định nghĩa kho cho AI** = catalog gọn từ registry (90 nhóm nhân vật + 38 nhóm nền), nhét vào super-prompt.
- **AI xuất lựa chọn** = slug cụ thể (`CharacterDef.asset`, `SettingDef.asset`), "" nếu không khớp.
- **Render dùng ĐÚNG file** theo slug (exact), fallback dần.
- **Thứ tự chọn mới:** `asset` (AI chọn) → `match_asset(scene_kind/name)` (fuzzy) → procedural SVG → gpt-image (premium).
  Procedural = lớp phủ coverage, không còn mặc định.

---

## B1 · Catalog + repo helpers — Tier **LOW** (`db/story_asset_repo.py`, defensive)
1. `get_by_slug(slug) -> str|None` — exact slug → on-disk path (verify tồn tại). Never raises.
2. `build_library_catalog(region="", genre="", cap=200) -> str` — gom base+variant (bỏ hậu tố
   `_angry/_sad/_surprised/_happy/_wave/_cheer/_point/_hip/_day/_night`), format 1 dòng/asset:
   ```
   CHARACTERS:
     cn_wuxia_swordsman_male_young | cn/wuxia | male | emotions: angry,sad,surprised
     ...
   BACKGROUNDS:
     cn_wuxia_bamboo_forest | cn/wuxia | day,night
     ...
   ```
   ~128 dòng ≈ 2-3K token → **nhét full, KHÔNG scope** (fit 1 super-call). `region/genre` để lọc tuỳ chọn sau.
   Mô tả = slug-tokens (đủ v1); nâng cấp: đọc `desc` từ sidecar `{file}.json` khi có.
3. **Test** `test_story_asset_repo` (bổ sung): `get_by_slug` exact/miss/file-gone→None; `build_library_catalog` gom variant, chứa slug, rỗng khi kho trống.

## B2 · Nhét catalog vào super-prompt — Tier **HIGH** (mirror `prior_context`, format-safe)
Plumbing **y hệt `prior_context`** (đã có sẵn cùng đường):

| File | Thay đổi |
|------|----------|
| `ai/llm/story_prompts_v2.py` | + `_library_block(library_catalog)` (như `_series_memory_block`, nối chuỗi VERBATIM, "" khi rỗng) · thêm param `library_catalog=""` vào `build_super_story_prompt`/`build_super_idea_prompt` · thêm 1 rule: *"chỉ chọn slug CÓ trong ASSET LIBRARY; khớp thì `asset=<slug>`, không thì ''"* · bump `SUPER_PROMPT_VERSION` s5→s6 |
| `ai/llm/story_director_v2.py` | + param `library_catalog=""` cho `run_super_plan` + `_plan_long_chapter`; truyền vào `build_super_*` (cạnh `prior_context`, dòng 175-176/192-193) |
| `ai/llm/__init__.py` | + param `library_catalog=""` cho `generate_story_plan_v2`; truyền vào `run_super_plan` (dòng 319) |
| `engine/pipeline/story_pipeline_v2.py` | trong `_resolve_story_plan_v2`: khi `STORY_LIBRARY_PICK=1` → `library_catalog = story_asset_repo.build_library_catalog(...)`; truyền vào `generate_story_plan_v2` (dòng 125-131, cạnh `prior_context`) |

- **Schema (_SCHEMA)**: characters[] `+ "asset": "<library character slug or ''>"`; settings[] `+ "asset": "<library background slug or ''>"`.
- **Gate:** catalog rỗng (STORY_LIBRARY_PICK off) → `_library_block` = "" → prompt **byte-identical s5** ⇒ AI không có gì để chọn → `asset` để "". Rollback tự nhiên.

## B3 · Schema fields — Tier **LOW** (domain, Sacred #2)
- `domain/story_plan_v2.py`: `CharacterDef += asset: str=""`, `SettingDef += asset: str=""`
  (đúng pattern `archetype`/`scene_kind` Phase 0.5). `_character_from`/`_setting_from` `+asset=_str(x.get("asset"))`.
  `__all__` không đổi. **Default "" → replay bit-identical; cue sheet không đụng.**
- Parser reuse `_from_dict` → **không sửa** `story_parser_v2.py`.
- `validate_refs`: KHÔNG ép asset (render tự verify tồn tại → miss thì fallback).

## B4 · Render dùng file kho theo slug — Tier **HIGH** (`svg_compose.py`)
- **Nền:** `_bg_layer` — thứ tự: `setting.asset` (get_by_slug, + biến thể `_{tod}` nếu suy được) → `match_asset(scene_kind)` (như hiện tại) → `scene_inner` procedural. Embed base64 như hiện tại.
- **Nhân vật:** trong `compose_visual`, mỗi `character_ids`: nếu `character.asset` → `get_by_slug(asset)` (+ `_{emotion}` variant nếu N4/beat) → **embed file kho** vào zone (thay `char_inner` procedural); không → `preset→char_inner` như hiện tại.
  - File kho nhân vật = PNG full-body trong suốt (1024×1536) → đặt `<g transform="translate,scale"><image href=data:...></g>` đúng zone (như char_inner).
- `visuals_stage._gen_one` (svg branch) không đổi (compose lo hết). Base-video master path (`_generate_character_masters`) có thể dùng `character.asset` ưu tiên (nâng cấp nhỏ).
- **Sacred #3:** slug miss/file gone → fallback fuzzy/procedural, không raise.

---

## Luồng đầy đủ (STORY_LIBRARY_PICK=1)
```
pipeline: build_library_catalog() ──► super-prompt [ASSET LIBRARY]
AI plan:  character.asset="cn_wuxia_swordsman_male_young", setting.asset="cn_wuxia_bamboo_forest"
render (svg_compose):
   nền   = get_by_slug(setting.asset) [+_night] → embed ; else match_asset ; else procedural
   nhân vật = get_by_slug(character.asset) [+_angry] → embed ; else procedural chibi
```
→ **Kho được AI chọn & dùng thật.** Ghép N4: `_{emotion}` variant đổi theo beat.

## Test & DoD
| Test | Kiểm |
|------|------|
| `test_story_asset_repo` | get_by_slug, build_library_catalog (gom variant, format) |
| `test_super_prompt_v2` | catalog rỗng→prompt như s5; catalog có→chứa `[ASSET LIBRARY]`+slug; schema có `"asset"`; version s6 |
| `test_story_plan_v2`/`test_super_parser_v2` | CharacterDef/SettingDef.asset roundtrip + default "" |
| `test_svg_compose` (bổ sung) | setting.asset→embed đúng file; character.asset→embed file kho (không procedural); miss→fallback |
| `test_library_pick` (mới) | end-to-end resolve: plan có asset → compose dùng đúng slug path |
| **Full pytest** | before/after = baseline (prompt HIGH) |
| runtime verify | render thật `STORY_LIBRARY_PICK=1` truyện wuxia → AI chọn slug hợp lý, ảnh dùng đúng file kho |

## Sacred Contracts & rủi ro
- **#2:** `asset` default "" (domain) + `story_image_provider` không đổi; catalog gate off → prompt byte-identical s5 → replay bit-identical.
- **#3:** catalog build lỗi/slug miss → degrade (fuzzy/procedural), never raise. **#8** QA sau. **#4/#5** không đụng.
- **Tier:** B1 LOW · **B2 HIGH** (prompt) · B3 LOW (domain) · **B4 HIGH** (compose). Không đụng orchestrator state machine / `story_image.py` / cue renderer.
- **Rollback:** `STORY_LIBRARY_PICK=0` (default) → catalog không nhét, asset "" → hành vi như hiện tại (procedural/fuzzy).
- **Rủi ro chất lượng chọn:** slug-tokens đủ phân biệt phần lớn; asset na ná → thêm sidecar `desc`. AI chọn sai slug (không có trong kho) → get_by_slug miss → fallback (an toàn).

## Cổng duyệt đề xuất
1. **B1** (repo catalog + get_by_slug, LOW) — test + xem catalog text mẫu. → duyệt.
2. **B2+B3** (prompt + schema, HIGH/LOW) — **PoC: chạy 1 super-call thật xem AI có chọn slug hợp lý** trước khi làm B4. → duyệt.
3. **B4** (render consume, HIGH) — test + runtime verify render thật. → duyệt.

## Quan hệ với các phase khác
- **Thay vị trí** procedural: procedural (Phase B/C) tụt xuống lớp coverage; library-pick lên đầu.
- **Ghép N4** (overlay emotion): AI chọn nhân vật kho → N4 swap `{asset}_{emotion}` theo beat. Nên làm **library-pick TRƯỚC N4** (N4 dùng chính asset AI chọn).
- **Fuzzy match Phase A** vẫn giữ làm tầng giữa (AI để "" nhưng scene_kind khớp kho).

> Không code tới khi bạn "approved". Đề xuất bắt đầu **B1** (catalog, LOW, không rủi ro), rồi **PoC B2+B3** (xem AI chọn thế nào) trước khi commit B4.
