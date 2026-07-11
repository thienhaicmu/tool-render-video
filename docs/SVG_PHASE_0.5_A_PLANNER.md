# Planner Analysis — Phase 0.5 (structured attrs) + Phase A (auto library-match)

> Lập 2026-07-11 từ **code hiện tại** (đọc thật: `domain/story_plan_v2.py`,
> `ai/llm/story_prompts_v2.py`, `story_parser_v2.py`, `stages/story/visuals_stage.py`,
> `db/story_asset_repo.py`). **Trạng thái: PLAN — chờ user "approved" trước khi Developer chạm code.**
> Thuộc [SVG_ASSET_SYSTEM_PLAN.md](SVG_ASSET_SYSTEM_PLAN.md). **Không dependency mới**
> (0.5+A chỉ dùng 273 asset tĩnh + `match_asset` sẵn có; resvg/procedural là Phase B).

## Mục tiêu (2 phase, làm cùng lượt)
- **0.5:** AI super-plan xuất **thuộc tính có cấu trúc** (region/genre_key + archetype/scene_kind) — token English để tra kho. Tất cả **default "" → Sacred #2 an toàn**; AI để trống được → không đổi hành vi.
- **A:** trước khi gọi AI ảnh, **tự match kho** cho Visual **không có nhân vật** (establishing/setting shot) → dùng nền library ($0), skip AI. Gate `STORY_LIBRARY_FIRST` (default off).

> ⚠️ Phạm vi A cố ý hẹp: chỉ match **background cho visual char-less**. Visual CÓ nhân vật giữ AI (mode ảnh không overlay master → gán nền library sẽ mất nhân vật — xem [SVG_ASSET_SYSTEM_PLAN §1]). Match character-master vẫn base-video-only (đã có). Đúng để A tối thiểu + không sai.

---

## PHASE 0.5 — thay đổi theo file

### F1 · `domain/story_plan_v2.py` — Tier **LOW** (pure dataclass, defensive)
Theo đúng pattern đã có (bgm_cue/char_anchor…). Additive:

1. Enum mới (cạnh các enum khác, ~L55):
   ```python
   REGION = ("cn", "jp", "ko", "vi", "eu", "us", "")
   GENRE_KEY = ("wuxia", "ngontinh", "horror", "fantasy", "codai", "hiendai", "")
   ```
2. `StoryPlan` (~L204): `+ region: str = ""`  `+ genre_key: str = ""` (library scope; ∈ REGION/GENRE_KEY).
3. `CharacterDef` (~L98): `+ archetype: str = ""` (token role English cho match; vd `swordsman|office_worker|princess`).
4. `SettingDef` (~L106): `+ scene_kind: str = ""` (token cảnh English; vd `cafe|forest|throne_room`).
5. `_from_dict` (~L472): thêm `region=_norm(d.get("region"), REGION, "")`, `genre_key=_norm(d.get("genre_key"), GENRE_KEY, "")`.
6. `_character_from` (~L567): `+ archetype=_str(x.get("archetype"))`. `_setting_from` (~L573): `+ scene_kind=_str(x.get("scene_kind"))`.
7. `__all__`: `+ "REGION", "GENRE_KEY"`.

- **Backward-compat:** `asdict/to_json` tự thêm khoá; blob v2 CŨ thiếu 4 khoá → `.get()` trả default "" → replay bit-identical (không đụng field render/cue → CUE SHEET tất định KHÔNG đổi).
- **KHÔNG** đụng `build_cues`/timing/INV → an toàn tất định.

### F2 · `ai/llm/story_prompts_v2.py` — Tier **HIGH** (format-safe)
1. `_SCHEMA` (raw constant, L64): thêm 2 khoá top-level + 1 khoá/character + 1 khoá/setting:
   - top-level: `"region": "cn|jp|ko|vi|eu|us|"`, `"genre_key": "wuxia|ngontinh|horror|fantasy|codai|hiendai|"`.
   - characters[]: `"archetype": "<lowercase English role token, e.g. swordsman|emperor|office_worker|princess|witch|child|ghost — or '' if unsure>"`.
   - settings[]: `"scene_kind": "<lowercase English scene token, e.g. cafe|forest|throne_room|bedroom|garden|street — or '' if unsure>"`.
2. `_rules` (L104): +1 rule: "region/genre_key/archetype/scene_kind là GỢI Ý thư viện — dùng token English viết thường; để '' nếu không chắc (không bịa)."
3. Bump `SUPER_PROMPT_VERSION` `"s4"→"s5"` (L27) + cập nhật comment.
- **Format-safety giữ nguyên:** schema là raw constant (không `str.format`), token mới không có `{}`. `.replace("<MOOD_VOCAB>"…)` không đụng.

### F3 · `story_parser_v2.py` — **KHÔNG SỬA**
Reuse `StoryPlan._from_dict` + `validate_refs` (L74-76) → nhận field mới tự động.

---

## PHASE A — thay đổi theo file

### F4 · `stages/story/visuals_stage.py` — Tier **HIGH** (cô lập, gated)
1. Helper MỚI `_match_library_background(plan, visual)` → `str|None` (best-effort, never raise):
   ```
   if visual.character_ids: return None          # có nhân vật → giữ AI (mode ảnh không overlay)
   s = plan.setting(visual.setting_id)
   name = (s.scene_kind or s.name) if s else ""
   from app.db.story_asset_repo import match_asset
   return match_asset("background", name=name, region=plan.region, genre=plan.genre_key)
   ```
2. Trong `_generate_images` (L61 vùng `gen_visuals`): trước khi gen mỗi visual, nếu
   `os.getenv("STORY_LIBRARY_FIRST","0")=="1"` và match ra path tồn tại →
   `plan.render.visual_assets[v.id]=path`, emit `story.visual.matched`, **loại v khỏi gen_visuals** (skip AI, y như nhánh `_ready`).
3. Không đụng vòng song song / part-status / orchestrator. Chỉ thêm 1 bước lọc trước `_gen_one`.

- **Gate:** `STORY_LIBRARY_FIRST` (đã tồn tại, default off) → **rollback = mặc định**, byte-identical.
- **Sacred #3:** match lỗi/miss → None → gen AI như cũ (degrade). **#8** không đụng (QA sau).
- Emotion/pose (từ `beat.emotion`/registry): **HOÃN** sang Phase B (mode ảnh chưa overlay nhân vật nên chưa dùng được ở A).

---

## Test (focused; full pytest khuyến nghị vì đụng prompt HIGH)
| Test | Kiểm |
|------|------|
| `test_story_plan_v2` (bổ sung) | 4 field mới roundtrip; blob CŨ (thiếu field) load → default ""; `_norm(region)` drop giá trị lạ; **build_cues KHÔNG đổi** (so cue trước/sau) |
| `test_super_prompt` (bổ sung) | `_SCHEMA` chứa `region/genre_key/archetype/scene_kind`; version = s5 |
| `test_super_parser_v2` (bổ sung) | parse blob có 4 field → điền đúng; thiếu → "" |
| `test_story_library_match` (MỚI) | `_match_library_background`: char-less + registry khớp → path; có char_ids → None; miss → None; gate off → `_generate_images` không match |
| `test_story_visual_*`, `test_run_story_v2_e2e` | không regression; STORY_LIBRARY_FIRST=1 + kho seed → skip AI đếm được |

**Baseline:** chạy full pytest TRƯỚC (ghi số) → sau; đụng prompt HIGH nên so số test.

## Rollback
- `STORY_LIBRARY_FIRST=0` (mặc định) → A tắt hoàn toàn.
- Prompt s5: AI để 4 field "" → hành vi như s4. (Muốn revert cứng: hạ version + bỏ 4 dòng schema.)

## Rủi ro & gate
- Tier: F1 **LOW** · F2 **HIGH** (prompt) · F4 **HIGH** (stage cạnh orchestrator). Không đụng state machine (#4/#5), không đụng `story_image.py`/provider (đó là Phase C).
- **KHÔNG dependency mới.** Không đổi default provider (vẫn gpt_image; A chỉ chèn 1 lớp match TRƯỚC khi gen, gated off).
- Gate CLAUDE.md: cần **approved plan (bản này) + user "go ahead"** trước Edit; focused pytest (khuyến nghị full vì prompt).

## Thứ tự thực thi (sau khi duyệt)
1. F1 (domain, LOW) + test → py_compile.
2. F3 xác nhận không cần sửa.
3. F2 (prompt, HIGH) + test → version s5.
4. F4 (visuals_stage, HIGH) + test.
5. full pytest before/after = baseline; e2e với kho seed đo skip-AI.

> Sau 0.5+A ổn (chứng minh match $0 chạy) → mới sang **Phase B** (generator SVG + resvg — cần chốt §4 rasterizer) → **Phase C** (provider `svg` = default, Render Edit Protocol).
