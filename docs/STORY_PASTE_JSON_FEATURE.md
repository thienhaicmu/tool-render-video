# Feature Spec — Story "Paste JSON → Render" (source option #3)

> Mục tiêu: người dùng **dán thẳng một StoryPlan JSON** → **Validate** (báo lỗi/cảnh báo + svgPreview) → **Render**, **bỏ qua AI**. Là **option nguồn thứ 3** cạnh `idea` / `paste`, chạy trong **workflow RIÊNG** (BE + FE tách rời).
>
> Dữ liệu hợp đồng (template + master data) sống ở **[STORY_MODE_OUTPUT_TEMPLATES.md](STORY_MODE_OUTPUT_TEMPLATES.md)** — doc này chỉ thêm phần feature-specific: role video, payload, endpoint, workflow.

---

## 0. Ba nguồn Story (sau khi thêm option #3)

| `story_source` | Nhập gì | AI? | Render path |
|----------------|---------|-----|-------------|
| `idea` | 1 ý tưởng | ✅ AI viết truyện | SVG storyboard |
| `paste` | 1 chương text | ✅ AI chuyển thể | SVG storyboard *hoặc* over-video |
| **`paste_json`** ⭐ | **StoryPlan JSON** | ❌ **không AI** | **theo video có/không (mục 1)** |

---

## 1. ⭐ ROLE: CÓ VIDEO vs KHÔNG VIDEO (làm rõ để không đụng role)

**Quyết định bởi DUY NHẤT field `story_base_video_path`** (không phải cờ riêng):

| | `paste_json` KHÔNG video | `paste_json` CÓ video |
|---|--------------------------|------------------------|
| Điều kiện | `story_base_video_path = ""` | `story_base_video_path = "<đường dẫn file>"` (tồn tại) |
| Template áp dụng | **Template 1** (SVG storyboard) | **Template 2** (over-video overlay) |
| Nền hình | Engine **vẽ procedural/library** từ `setting.scene_kind` | **VIDEO là nền** — `visuals` chỉ là mốc nhóm, look bị bỏ |
| Nhân vật | Chibi/library ghép theo `lines[].speaker_id` | Master ghép **đè lên video** theo `char_anchor` |
| Field beat quan trọng | `focus`, `bgm_mood`, `lines[]` | + `source_audio` (mute/duck/keep), `char_anchor/scale/motion` |
| Âm thanh gốc video | — (không có) | Xử lý theo `source_audio` mỗi beat |
| Engine path | `story_pipeline_v2` nhánh `not base_video_path` (SVG) | nhánh `base_video_path` (A2/A3/A4 over-video) |

**Nguyên tắc chống đụng role:** cùng một plan dán tay, chỉ cần **đính kèm hay không đính kèm base video** là chuyển hẳn giữa 2 template + 2 render path. FE phải cho người dùng **chọn rõ**: "Storyboard (không video)" hay "Overlay lên video (đính kèm video)". Validate phải cảnh báo nếu plan Template-2 (có `source_audio`/`char_anchor`) mà **không** đính video, hoặc Template-1 mà lại đính video.

---

## 1b. HAI TEMPLATE ĐẦY ĐỦ (agent sinh JSON theo đúng khuôn này)

> Chỉ điền phần **CONTRACT** (`characters/settings/visuals/timeline`). `render` LUÔN để `{}` — engine tự điền.
> Token `archetype/scene_kind/genre_key/region/emotion/pose/bgm_mood` PHẢI thuộc master data mục 2.4. `asset` = slug thật mục 2.5 (không có → `""`).

### TEMPLATE 1 — KHÔNG video (SVG storyboard) · `story_base_video_path=""`
```json
{
  "schema_version": 2, "language": "vi", "aspect_ratio": "9:16",
  "art_style": "anime lofi, warm", "topic": "Hộp cơm của mẹ", "tone": "cảm động",
  "region": "jp", "genre_key": "hiendai",
  "characters": [
    { "id": "sachiko", "name": "Sachiko", "canonical_desc": "bà cụ 67 tuổi, tạp dề bạc màu",
      "age": "67", "gender": "female", "voice_gender": "female", "archetype": "grandma", "asset": "jp_hiendai_grandma_female" },
    { "id": "kenta", "name": "Kenta", "canonical_desc": "nam 35, vest công sở",
      "age": "35", "gender": "male", "voice_gender": "male", "archetype": "office_worker", "asset": "jp_hiendai_office_worker_male" }
  ],
  "settings": [
    { "id": "shop", "name": "Cửa hàng bentō", "scene_kind": "market", "asset": "" },
    { "id": "street", "name": "Phố Tsuruhashi", "scene_kind": "street", "asset": "" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "shop",   "character_ids": ["sachiko"] },
    { "id": "v2", "setting_id": "street", "character_ids": ["sachiko", "kenta"] }
  ],
  "timeline": [
    { "id": "b1", "visual_id": "v1", "focus": "wide", "bgm_mood": "sad", "hook": false, "hook_text": "",
      "lines": [ { "speaker_id": "", "text": "Bà Sachiko đã bán cơm hộp suốt hơn ba mươi năm...", "emotion": "normal", "pose": "stand" } ] },
    { "id": "b2", "visual_id": "v2", "focus": "center", "bgm_mood": "tense", "hook": true, "hook_text": "\"Bà nhận nhầm.\"",
      "lines": [
        { "speaker_id": "sachiko", "text": "Kenta, con về rồi à?", "emotion": "happy", "pose": "wave" },
        { "speaker_id": "kenta",   "text": "Xin lỗi, bà nhận nhầm người rồi.", "emotion": "angry", "pose": "stand" }
      ] }
  ],
  "render": {}
}
```

### TEMPLATE 2 — CÓ video (over-video overlay) · `story_base_video_path="<video>"`
Khác Template 1: `visuals` tối giản (nền là video); mỗi beat thêm **`source_audio`** + **`char_anchor/char_scale/char_motion`** (AI đặt vị trí overlay trên video).
```json
{
  "schema_version": 2, "language": "vi", "aspect_ratio": "9:16",
  "topic": "Người cha ở lễ cưới", "tone": "cảm động", "region": "jp", "genre_key": "hiendai",
  "characters": [
    { "id": "hiroshi", "name": "Hiroshi", "canonical_desc": "cha 63, vest cũ", "gender": "male", "voice_gender": "male", "archetype": "grandpa", "asset": "jp_hiendai_grandpa_male" },
    { "id": "rina", "name": "Rina", "canonical_desc": "con gái 29, váy cưới", "gender": "female", "voice_gender": "female", "archetype": "noblewoman", "asset": "" }
  ],
  "settings": [ { "id": "s1", "name": "Sảnh tiệc", "scene_kind": "", "asset": "" } ],
  "visuals": [ { "id": "v1", "setting_id": "s1", "character_ids": [] } ],
  "timeline": [
    { "id": "b1", "visual_id": "v1", "focus": "center", "motion": "static", "bgm_mood": "sad",
      "source_audio": "duck", "char_anchor": "right", "char_scale": "medium", "char_motion": "fade",
      "hook": false, "hook_text": "",
      "lines": [ { "speaker_id": "", "text": "Một người đàn ông lớn tuổi bước vào lễ cưới.", "emotion": "normal", "pose": "stand" } ] },
    { "id": "b2", "visual_id": "v1", "focus": "center", "motion": "zoom_in", "bgm_mood": "tense",
      "source_audio": "mute", "char_anchor": "left", "char_scale": "large", "char_motion": "slide",
      "hook": true, "hook_text": "\"Người quen.\"",
      "lines": [
        { "speaker_id": "rina",    "text": "Ông ấy chỉ là một người quen cũ.", "emotion": "sad", "pose": "stand" },
        { "speaker_id": "hiroshi", "text": "Vâng. Chúng tôi chỉ là người quen.", "emotion": "sad", "pose": "stand" }
      ] }
  ],
  "render": {}
}
```

---

## 2. BẢNG DATA CẦN THIẾT (cho agent setup)

### 2.1 Request payload — `POST /api/render/process` (submit render)
Wire nhận `RenderRequestPublic`. Field story cần set:

| Field | KHÔNG video | CÓ video | Ghi chú |
|-------|-------------|----------|---------|
| `render_format` | `"story"` | `"story"` | bắt buộc |
| `story_source` | `"paste_json"` | `"paste_json"` | option mới |
| `story_plan_override` | `<JSON string>` | `<JSON string>` | plan dán tay (CONTRACT) |
| `story_base_video_path` | `""` | `"<path video>"` | ⭐ quyết định role |
| `story_voice_mode` | `dialogue`\|`narrator` | như trái | giọng: nhiều voice / 1 narrator |
| `content_background_kind` | `color` | (bỏ qua) | nền fallback khi SVG |
| `content_background_value` | `#101820` | — | màu nền |

> **Cơ chế strict = chính `story_source="paste_json"`** (không thêm cờ boolean riêng). Pipeline thấy source này → override BẮT BUỘC hợp lệ; sai → **báo lỗi, KHÔNG rơi xuống gọi AI**. Thêm giá trị `"paste_json"` vào `story_source` là additive (job cũ chỉ có paste/idea, không ảnh hưởng — Contract #2 an toàn).

> `aspect_ratio`, `language`, `art_style` LẤY TỪ PLAN (top-level của StoryPlan), không cần trùng lặp ở request.

### 2.2 Endpoint Validate (MỚI) — `POST /api/story/validate`
```jsonc
// request
{ "plan": <StoryPlan JSON hoặc string>, "has_base_video": false }
// response
{
  "ok": true,
  "errors": [],            // hard-fail: parse lỗi / schema_version≠2 / timeline rỗng / visual rỗng / ref dangling
  "warnings": [            // mềm (lint, không chặn): reuse lint_story_plan (multiline-aware)
    "2 character(s) defined but none speaks — background-only",
    "length ~78s vs target — edit timeline",
    "plan has source_audio/char_anchor but no base video attached (Template-2 fields ignored)"
  ],
  "estimated_total_sec": 612.3,
  "beat_count": 61, "character_count": 4, "image_count": 3,
  "plan_normalized": { /* plan sau validate_refs+reindex+cap_visuals, render:{} */ }
}
```

### 2.3 Endpoint Preview (ĐÃ CÓ) — `POST /api/story/visual/svg-preview`
```jsonc
// request
{ "plan": <StoryPlanV2>, "visual_ids": [] }   // []/omit = tất cả visual
// response
{ "items": [ { "visual_id": "v1", "token": "…", "url": "…" } ] }
```
> Dùng ngay để xem trước nhân vật/nền. Với `paste_json + video` thì preview chỉ minh hoạ nhân vật/anchor (nền thật là video).

### 2.4 Master data (đầy đủ ở [STORY_MODE_OUTPUT_TEMPLATES.md](STORY_MODE_OUTPUT_TEMPLATES.md) mục "MASTER DATA")
| Bảng | Nội dung | Số lượng |
|------|----------|----------|
| `archetype` | token nhân vật procedural | **56** |
| `scene_kind` | token nền procedural | **61** |
| `genre_key` | wuxia, **xianxia**, ngontinh, horror, fantasy, codai, hiendai | 7 |
| `region` | cn, jp, ko, vi, eu, us | 6 |
| `emotion` / `pose` | normal/happy/angry/sad/surprised · stand/wave/cheer/point/hip | 5 / 5 |
| `bgm_mood` | tense/calm/epic/sad/romantic/mysterious/action/hopeful/dark | 9 |
| Thư viện asset (DB `story_assets`) | character/background/frame theo `{kind}/{region}/{genre}/{slug}` | **614** (char 465+, bg 58+, frame 8) |
| Voices TTS | vi/ko=gemini, en/ja=elevenlabs (female/male pools) | — |

> `asset` = slug chính xác trong thư viện (nay có 614); không khớp → procedural. Bảng slug thật lấy bằng `SELECT kind,region,genre,slug FROM story_assets`.

### 2.5 Quy ước slug thư viện (614 asset hiện có)
```
character:  {region}_{genre}_{archetype}[_{emotion}|_{pose}]      (variant emotion/pose cho nhân vật chính)
background: {region}_{genre}_{scene_kind}[_night]
frame:      frame/{style}/{name}
```
Ví dụ: `jp_hiendai_office_worker_male`, `cn_ngontinh_heroine_female_sad`, `jp_hiendai_cafe`, `cn_xianxia_waterfall_night`.

**Character theo genre (count):** codai 108 (cn34/jp30/ko21/eu19/vi3/us1) · fantasy 90 (eu80/jp9/vi1) · hiendai 225 (jp91/vi57/us38/ko29/eu9/cn1) · ngontinh 75 (cn38/ko28/vi9) · wuxia 30 (cn) · xianxia 11 (cn) · horror 1.
**Background theo genre:** codai 19 · hiendai 14 · fantasy 11 · ngontinh 6 · wuxia 7 · xianxia 5 · horror 4.
> emotion variant có sẵn: `_happy/_angry/_sad/_surprised`; pose variant: `_wave/_cheer/_point/_hip` (chỉ nhân vật protagonist-class). Thiếu variant → engine dùng base slug hoặc procedural.

### 2.6 FULL MASTER DATA đang có (agent chọn token/slug TỪ ĐÂY)

**`archetype` — 56 token procedural (dùng khi không có slug thư viện khớp):**
`angel, archer, assassin, astronaut, bard, businessman, cafe_staff, ceo, chef, child, cowboy, demon, detective, doctor, dwarf, elf, emperor, fairy, farmer, firefighter, geisha, general, ghost, grandma, grandpa, heroine, idol, immortal, king, knight, mage, maid, merchant, monk, monk_warrior, ninja, noblewoman, nurse, office_worker, orc, pirate, police, princess, ranger, robot, salaryman, samurai, scholar, soldier, student, swordsman, teacher, vampire, villain, waiter, witch`

**`scene_kind` — 61 token procedural:**
`alley, bamboo_forest, battlefield, bazaar, beach, bedroom, cafe, castle, castle_hall, cave, cemetery, city, classroom, cliff, clinic, coffee_shop, courtyard, desert, dunes, dungeon, forest, garden, graveyard, hall, home, hospital, imperial_hall, inn, kitchen, lake, library, living_room, market, mountain, ocean, office, pagoda, palace, palace_courtyard, park, peak, river, rooftop, ruins, school, seaside, shrine, skyline, snow, snowfield, street, study, tavern, temple, throne_room, torii, war, waterfall, winter, woods, yard`

**`genre_key`:** wuxia, xianxia, ngontinh, horror, fantasy, codai, hiendai · **`region`:** cn, jp, ko, vi, eu, us
**`emotion`:** normal, happy, angry, sad, surprised · **`pose`:** stand, wave, cheer, point, hip
**`bgm_mood`:** tense, calm, epic, sad, romantic, mysterious, action, hopeful, dark · **`focus`:** wide, left, center, right, top, bottom, close

**LIBRARY SLUG đang có — CHARACTER (116 base, +variant emotion/pose):**
- `hiendai` (49): jp_hiendai_{office_worker,salaryman,businessman,ceo,chef,waiter,cafe_staff,nurse,maid,idol,robot,child,student,grandma,grandpa}_{m/f}, vi_hiendai_{child,student,farmer,grandma,grandpa,teacher}, us_hiendai_{office_worker,businessman,ceo,chef,doctor,detective,farmer,firefighter,police,robot,soldier}, ko_hiendai_{office_worker,student,cafe_staff,doctor,idol}, cn_hiendai_teacher_male, eu_hiendai_detective_male
- `codai` (28): cn_codai_{emperor,king,general,scholar,merchant,soldier,grandpa,grandma,noblewoman,princess}, jp_codai_{samurai,swordsman,assassin,monk,geisha,noblewoman}, ko_codai_{king,general,archer,noblewoman,princess}, eu_codai_{knight_m/f,maid}, vi_codai_{scholar,monk,merchant}, us_codai_pirate
- `ngontinh` (11): cn_ngontinh_{heroine,noblewoman,princess,scholar,student_m/f}, ko_ngontinh_{idol_m/f,noblewoman,scholar}, vi_ngontinh_heroine
- `fantasy` (18): eu_fantasy_{angel_m/f,archer_m/f,bard_m/f,demon_m/f,fairy,mage_m/f,orc,pirate,ranger_m/f,villain}, jp_fantasy_demon_male, vi_fantasy_fairy_female
- `wuxia` (6): cn_wuxia_{assassin_m/f,monk,monk_warrior,swordsman_female,villain} · `xianxia` (3): cn_xianxia_{heroine,immortal_m/f} · `horror` (1): eu_horror_witch_female

**LIBRARY SLUG đang có — BACKGROUND (40 base, +variant `_night` cho ngoài trời):**
- `hiendai`: jp_hiendai_{beach,cafe,office}, us_hiendai_{beach,hospital,office,rooftop}, ko_hiendai_rooftop, vi_hiendai_park, eu_hiendai_library
- `codai`: cn_codai_{courtyard,library,market,temple}, jp_codai_shrine, ko_codai_{courtyard,snow}, vi_codai_{market,temple}, us_codai_desert
- `ngontinh`: cn_ngontinh_{courtyard,garden}, ko_ngontinh_{cafe,garden,park}
- `fantasy`: eu_fantasy_{battlefield,cave,desert,market,ruins}, vi_fantasy_waterfall
- `wuxia`: cn_wuxia_{battlefield,inn,snow,temple} · `xianxia`: cn_xianxia_{cave,ruins,waterfall} · `horror`: {eu,us}_horror_graveyard

---

## 3. Backend cần làm (4 điểm — từ design review)
| # | Việc | File | Tier |
|---|------|------|------|
| B1 | `StoryPlan.normalize_for_render()` = `validate_refs+reindex+cap_visuals` + `render=RenderState()` | `domain/story_plan_v2.py` | LOW |
| B2 | Áp B1 cho nhánh override trong `_resolve_plan` | `story_pipeline_v2.py` | MEDIUM |
| B3 | Endpoint `POST /api/story/validate` (reuse `lint_story_plan`) + cảnh báo mismatch video/template | `features/story/router.py` | MEDIUM |
| B4 | Thêm giá trị `"paste_json"` vào `story_source` (validator) + strict trong `_resolve_plan` (source=paste_json + override lỗi → raise, KHÔNG gọi AI) | `models/render.py`(+public validator), `story_pipeline_v2.py` | HIGH (Contract #2 additive — chỉ thêm giá trị enum, không field mới) |

## 4. Frontend — workflow RIÊNG
- Thêm **option #3 "Paste JSON"** ở màn chọn nguồn (cạnh idea/paste).
- Màn riêng: **textarea JSON** + **toggle "Đính kèm video nền"** (set `story_base_video_path`) → làm rõ role.
- Nút **Validate** → `/api/story/validate` → hiện errors (chặn) / warnings / độ dài + **svgPreview**.
- Nút **Render** → `/api/render/process` với payload mục 2.1.
- Tái dùng UI Review/preview có sẵn; KHÔNG trộn vào flow idea/paste.

## 5. Kiểm thử
- B1 normalize: ref dangling scrub, render reset, cap.
- `/api/story/validate`: valid→ok; dangling→error; rỗng→error; ngắn→warning; Template-2-không-video→warning.
- strict: `story_source="paste_json"` + override lỗi → job fail rõ, **mock AI xác nhận KHÔNG gọi**.
- Contract #2: thêm giá trị `"paste_json"` không phá job cũ (paste/idea vẫn như trước).
- E2E: dán plan thật → validate → normalize → build_cues → renderable + `line_overlays` populate.
- Master-data sync: `tests/test_master_data_sync.py` (đã có) — mọi genre/region/token phải khớp enum.

---

## 6. ⭐ LUẬT ĐỒNG BỘ DATA (agent BẮT BUỘC tuân theo)

Khi agent **sinh ra nhân vật/nền/token MỚI** (archetype mới, slug thư viện mới, genre/region mới), PHẢI cập nhật lại NGAY để master data không lệch — nếu không, plan dùng token đó sẽ **fallback procedural hoặc bị schema từ chối**:

1. **Archetype mới** → thêm vào `svg_presets._ARCH` (backend) VÀ liệt kê ở **mục 2.6** file này.
2. **Scene_kind mới** → thêm vào `svg_scene._SCENES` VÀ mục 2.6.
3. **Genre/region mới** → thêm vào `story_plan_v2.GENRE_KEY`/`REGION` (domain) VÀ mục 2.6 (nếu thiếu, `tests/test_master_data_sync.py` sẽ ĐỎ).
4. **Slug thư viện mới** → sinh file PNG đúng quy ước `{kind}/{region}/{genre}/{slug}.png` (dùng `scripts/gen_svg_library.py` hoặc đặt tay) → chạy `story_asset_repo.scan_library()` để nạp DB → cập nhật danh sách slug ở **mục 2.5 + 2.6**.
5. Sau mọi thay đổi data: chạy `python -m pytest tests/test_master_data_sync.py` (phải xanh) rồi mới coi là đồng bộ.

> Nguyên tắc: **file instruction này = ảnh chụp master data hiện tại**. Data thật (enum + builder + thư viện DB) là nguồn gốc; file này phải luôn phản ánh đúng chúng. Sinh mới mà quên cập nhật = data lệch = nhân vật/nền ra sai.
