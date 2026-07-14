# Story Mode — Canonical Output Templates

> Nguồn sự thật: `backend/app/domain/story_plan_v2.py` (domain), 
> `backend/app/features/render/ai/llm/story_schema_v2.py` (AI contract schema),
> `frontend/src/api/story.ts` (FE types). Khi tài liệu ≠ code: **tin code.**
> Mọi field lạ khi `StoryPlan.from_json` sẽ bị bỏ; giá trị sai → default (an toàn).

Story Mode có **3 nguồn** → gộp thành **2 hình dạng output**:

| Nguồn | `story_source` | Base video? | Template |
|-------|----------------|-------------|----------|
| Từ ý tưởng | `idea` | Không | **Template 1** (SVG storyboard) |
| Dán chương, không video | `paste` | Không | **Template 1** (SVG storyboard) |
| Dán chương, có video nền | `paste` | **Có** (`use_video=true`) | **Template 2** (character-overlay over video) |

Một `StoryPlan` có **2 lớp tách bạch**:
- **CONTRACT** (AI sinh, bất biến): `characters / settings / visuals / timeline`. Đây là thứ FE Review hiển thị + sửa, và là `story_plan_override` khi render.
- **RENDER STATE** (`render`, engine tự điền lúc render, không phải AI): `visual_assets / voices / refs / masters / beat_audio / cues / total_sec`. Rỗng lúc `/api/story/plan`, được điền khi render và lưu vào `jobs.story_plan_json`.

Cấu hình đang chạy (theo `.env`): `STORY_MULTILINE_BEATS=1` (beat mang `lines[]`), `STORY_LEAN_CONTRACT=1` (SVG bỏ 9 nhãn cơ học — engine tự derive).

---

## Template 1 — idea + paste (KHÔNG video) → SVG storyboard

**Cách sinh:** `POST /api/story/plan` với `source="idea"` (hoặc `"paste"`) → engine render bằng `render_format="story"`, `story_plan_override=<plan>`, **không** `use_video`.
**Ảnh:** engine vẽ nền procedural (SVG) từ `setting` + nhân vật của mỗi `visual`; nhân vật ghép overlay theo `lines[].speaker_id`.

### 1A. CONTRACT — beat đa dòng (multiline, mặc định `.env`)

```json
{
  "schema_version": 2,
  "seed": 0,
  "series_id": "",
  "chapter_no": 0,
  "language": "vi",
  "art_style": "anime lofi, warm",
  "aspect_ratio": "9:16",
  "reading_pace": "normal",
  "topic": "Hộp cơm của mẹ",
  "tone": "cảm động, hoài niệm",
  "region": "jp",
  "genre_key": "hiendai",

  "characters": [
    {
      "id": "sachiko", "name": "Sachiko", "canonical_desc": "bà cụ 67 tuổi, tạp dề bạc màu, tóc búi",
      "age": "67", "gender": "female", "voice_gender": "female", "voice_style": "",
      "archetype": "grandma", "asset": ""
    },
    {
      "id": "kenta", "name": "Kenta", "canonical_desc": "nam 35 tuổi, vest công sở, lạnh lùng",
      "age": "35", "gender": "male", "voice_gender": "male", "voice_style": "",
      "archetype": "office_worker", "asset": ""
    }
  ],

  "settings": [
    { "id": "shop", "name": "Cửa hàng bentō", "canonical_desc": "quán cơm cũ, bảng hiệu bạc màu",
      "scene_kind": "market", "asset": "" },
    { "id": "street", "name": "Phố Tsuruhashi", "canonical_desc": "khu phố cũ Osaka lúc chiều",
      "scene_kind": "street", "asset": "" }
  ],

  "visuals": [
    { "id": "v1", "setting_id": "shop",   "prompt": "", "negative_prompt": "",
      "character_ids": ["sachiko"],           "tier": "medium" },
    { "id": "v2", "setting_id": "street", "prompt": "", "negative_prompt": "",
      "character_ids": ["sachiko", "kenta"],  "tier": "medium" }
  ],

  "timeline": [
    {
      "id": "b1", "visual_id": "v1", "focus": "wide", "bgm_mood": "sad",
      "hook": false, "hook_text": "",
      "lines": [
        { "speaker_id": "", "text": "Ở một khu phố cũ gần ga Tsuruhashi, bà Sachiko đã bán cơm hộp suốt hơn ba mươi năm. Cửa hàng nhỏ, bảng hiệu đã bạc màu, nhưng mỗi sáng bà vẫn dậy từ tinh mơ.", "emotion": "normal", "pose": "stand" }
      ]
    },
    {
      "id": "b2", "visual_id": "v2", "focus": "center", "bgm_mood": "tense",
      "hook": true, "hook_text": "\"Bà nhận nhầm người rồi.\"",
      "lines": [
        { "speaker_id": "",        "text": "Hôm ấy công ty cử Kenta đi công tác Osaka. Một đồng nghiệp trông thấy bà đứng trước cửa hàng và gọi lớn.", "emotion": "normal",   "pose": "stand" },
        { "speaker_id": "sachiko", "text": "Kenta, con về rồi à?",                                   "emotion": "happy",   "pose": "wave"  },
        { "speaker_id": "kenta",   "text": "Xin lỗi, bà nhận nhầm người rồi.",                        "emotion": "angry",   "pose": "stand" },
        { "speaker_id": "sachiko", "text": "Xin lỗi… chắc tôi nhầm thật.",                            "emotion": "sad",     "pose": "stand" }
      ]
    }
  ],

  "render": {}
}
```

### 1B. CONTRACT — beat đơn dòng (khi `STORY_MULTILINE_BEATS=0`)

Beat KHÔNG có `lines[]`; dùng field legacy `narration` + `speaker_id` + `emotion` + `pose` (một beat = một câu của một người):

```json
{
  "id": "b2", "visual_id": "v2", "focus": "center", "bgm_mood": "tense",
  "hook": true, "hook_text": "\"Bà nhận nhầm người rồi.\"",
  "narration": "Xin lỗi, bà nhận nhầm người rồi.",
  "speaker_id": "kenta", "emotion": "angry", "pose": "stand"
}
```

> `effective_lines()` gộp cả 2 dạng: có `lines[]` → dùng nó; không → tổng hợp 1 line từ `narration/speaker_id`. FE dùng `beatLines(b)` tương đương.

---

## Template 2 — paste CÓ video nền → character-overlay over video

**Cách sinh:** `POST /api/story/plan` với `source="paste"` **và có base video** → engine render với `render_format="story"`, `story_plan_override=<plan>`, **`use_video=true`** + file video nguồn.
**Ảnh:** VIDEO là toàn bộ hình nền (look của `visuals` bị bỏ qua — chỉ là mốc nhóm). Mỗi beat: engine ghép **master nhân vật đang nói** đè lên video, và xử lý **âm thanh gốc của video** theo `source_audio`.

Khác Template 1: `visuals` tối giản (không nhân vật cũng được); beat mang thêm **`source_audio`** (mute/duck/keep) + **`char_anchor`/`char_scale`/`char_motion`** do AI quyết vị trí overlay trên video.

```json
{
  "schema_version": 2,
  "seed": 0,
  "language": "vi",
  "art_style": "",
  "aspect_ratio": "9:16",
  "reading_pace": "normal",
  "topic": "Người cha ở lễ cưới",
  "tone": "cảm động",
  "region": "jp",
  "genre_key": "hiendai",

  "characters": [
    { "id": "hiroshi", "name": "Hiroshi", "canonical_desc": "cha 63 tuổi, vest cũ, tay chai sần",
      "age": "63", "gender": "male", "voice_gender": "male", "voice_style": "",
      "archetype": "grandpa", "asset": "" },
    { "id": "rina", "name": "Rina", "canonical_desc": "con gái 29 tuổi, váy cưới",
      "age": "29", "gender": "female", "voice_gender": "female", "voice_style": "",
      "archetype": "noblewoman", "asset": "" }
  ],

  "settings": [
    { "id": "s1", "name": "Sảnh tiệc cưới", "canonical_desc": "", "scene_kind": "", "asset": "" }
  ],

  "visuals": [
    { "id": "v1", "setting_id": "s1", "prompt": "", "negative_prompt": "",
      "character_ids": [], "tier": "medium" }
  ],

  "timeline": [
    {
      "id": "b1", "visual_id": "v1", "focus": "center", "motion": "static",
      "transition_in": "cut", "bgm_mood": "sad", "bgm_cue": "under", "bgm_intensity": "med",
      "text_anchor": "auto", "hook": false, "hook_text": "",
      "source_audio": "duck",
      "char_anchor": "right", "char_scale": "medium", "char_motion": "fade",
      "lines": [
        { "speaker_id": "", "text": "Trong lễ cưới sang trọng, một người đàn ông lớn tuổi bước vào, trên tay cầm một hộp gỗ nhỏ.", "emotion": "normal", "pose": "stand" }
      ]
    },
    {
      "id": "b2", "visual_id": "v1", "focus": "center", "motion": "zoom_in",
      "transition_in": "cut", "bgm_mood": "tense", "bgm_cue": "under", "bgm_intensity": "high",
      "text_anchor": "top", "hook": true, "hook_text": "\"Chỉ là một người quen.\"",
      "source_audio": "mute",
      "char_anchor": "left", "char_scale": "large", "char_motion": "slide",
      "lines": [
        { "speaker_id": "rina",    "text": "Ông ấy… chỉ là một người quen cũ của gia đình.", "emotion": "sad",   "pose": "stand" },
        { "speaker_id": "hiroshi", "text": "Vâng. Chúng tôi chỉ là người quen.",             "emotion": "sad",   "pose": "stand" }
      ]
    }
  ],

  "render": {}
}
```

---

## RENDER STATE — engine tự điền lúc render (cả 2 template)

Sau khi render, `render` được điền và lưu vào `jobs.story_plan_json`. FE `StoryMonitor` / reattach đọc phần này. **Không tự tay viết** — chỉ để hiểu hình dạng đầy đủ:

```json
"render": {
  "visual_assets": { "v1": "…/v1.png", "v2": "…/v2.png" },
  "voices":  { "sachiko": ["elevenlabs", "<voice_id>"], "kenta": ["edge", "vi-VN-NamMinhNeural"] },
  "refs":    { },
  "masters": {
    "sachiko:sad:stand":  "…/master_sachiko_sad_stand.png",
    "kenta:angry:stand":  "…/master_kenta_angry_stand.png"
  },
  "beat_audio": {
    "b2": {
      "path": "…/beat_b2.mp3", "dur": 6.42, "words": [],
      "spans": [
        { "start": 0.0, "end": 2.1, "speaker_id": "sachiko", "emotion": "happy", "pose": "wave",  "anchor": "left"   },
        { "start": 2.1, "end": 4.0, "speaker_id": "kenta",   "emotion": "angry", "pose": "stand", "anchor": "center" }
      ]
    }
  },
  "cues": [
    {
      "beat_id": "b2", "visual_id": "v2", "start_sec": 3.4, "end_sec": 9.8,
      "crop_from": [0.11,0.11,0.78,0.78], "crop_to": [0.11,0.11,0.78,0.78],
      "transition": "cut", "transition_sec": 0.0, "hook": true, "hook_text": "\"Bà nhận nhầm người rồi.\"",
      "audio_path": "…/beat_b2.mp3",
      "bgm_mood": "tense", "bgm_cue": "under", "bgm_intensity": "med", "text_anchor": "auto",
      "speaker_id": "", "char_anchor": "center", "char_scale": "medium", "char_motion": "fade",
      "emotion": "normal", "pose": "stand", "source_audio": "mute",
      "line_overlays": [
        { "start": 0.0, "end": 2.1, "speaker_id": "sachiko", "emotion": "happy", "pose": "wave",  "anchor": "left"   },
        { "start": 2.1, "end": 4.0, "speaker_id": "kenta",   "emotion": "angry", "pose": "stand", "anchor": "center" }
      ]
    }
  ],
  "total_sec": 9.8
}
```

> **Quy tắc vàng (đã sửa ở FIX 1):** với beat **một người nói**, TTS đi đường one-voice → `beat_audio.spans` rỗng; `build_cues` **tự derive một `line_overlay` phủ trọn beat** từ `primary_speaker()` để nhân vật vẫn lên hình. Beat narrator-only (`speaker_id=""`) → không overlay (đúng). `line_overlays` là thứ QUYẾT ĐỊNH nhân vật có hiện hay không — `masters[speaker:emotion:pose]` phải tồn tại tương ứng.

---

## Envelope API — `POST /api/story/plan` (thứ FE Review nhận)

```jsonc
{
  "plan": { /* StoryPlan CONTRACT ở trên, render:{} */ },
  "image_count": 2,
  "beat_count": 61,
  "estimated_total_sec": 612.3,          // ước lượng theo ký tự/cps (KHÔNG phải TTS thật)
  "character_count": 2,
  "source_truncated": false,             // idea/chapter có bị cắt đuôi không (cap env)
  "source_chars": 8051,
  "source_char_limit": 20000,            // idea cap = STORY_MAX_IDEA_CHARS (bỏ hardcode 8000)
  "warnings": [                          // lint mềm — hiển thị làm gợi ý ở Review
    "length is ~120s vs target ~600s (20% of requested) — edit the timeline or regenerate to reach the length",
    "2 character(s) defined but none speaks on any beat — the video will render background-only (no character on screen)"
  ],
  "cost_preflight": { "visual_count": 2, "character_count": 2, "premium_image_count": 0,
                      "image_cost_usd": 0.0, "estimated_llm_cost_usd": 0.01, "estimated_cost_usd": 0.01 }
}
```

---

## Bảng field + enum (CONTRACT)

**Top-level StoryPlan:** `schema_version`(2) · `seed` · `series_id` · `chapter_no` · `language`(vi/en/ja/ko) · `art_style` · `aspect_ratio`(16:9/9:16/1:1) · `reading_pace` · `topic` · `tone` · `region`(cn/jp/ko/vi/eu/us/"") · `genre_key`(wuxia/ngontinh/horror/fantasy/codai/hiendai/"").

**CharacterDef:** `id` · `name` · `canonical_desc` · `age` · `gender`(male/female/"") · `voice_gender` · `voice_style` · `archetype`(token tiếng Anh) · `asset`(slug thư viện hoặc "").

**SettingDef:** `id` · `name` · `canonical_desc` · `scene_kind` · `asset`.

**Visual:** `id` · `setting_id`→Setting · `character_ids[]`→Character · `tier`(low/medium/high) · `prompt`/`negative_prompt`(SVG bỏ qua; video bỏ qua).

**Line (multiline):** `speaker_id`(→Character hoặc ""=người kể) · `text` · `emotion`(normal/happy/angry/sad/surprised) · `pose`(stand/wave/cheer/point/hip).

**Beat:** `id` · `visual_id`→Visual · `focus`(wide/left/center/right/top/bottom/close) · `bgm_mood`(tense/calm/epic/sad/romantic/mysterious/action/hopeful/dark) · `hook`(bool) · `hook_text` · `lines[]`.
- Chỉ nhánh **video (full schema)** thêm: `motion`(zoom_in/out,pan_*,static) · `transition_in`(cut/fade/slide/zoom/flash/to_black) · `bgm_cue`(under/intro/outro/none) · `bgm_intensity`(low/med/high) · `source_audio`(mute/duck/keep) · `char_anchor`(none/left/center/right) · `char_scale`(small/medium/large) · `char_motion`(static/fade/slide/float) · `text_anchor`(auto/top/bottom/left/right).
- Nhánh **SVG lean** BỎ 9 field cơ học trên (engine tự derive qua `derive_beat_styling`).
- Legacy single-line: `narration` · `speaker_id` · `emotion` · `pose` (thay `lines[]`).

---

## MASTER DATA — kho tra cứu để điền template ĐÚNG

> Cách khớp: `archetype` và `scene_kind` khớp **EXACT** (chuẩn hoá lower + khoảng trắng/gạch → `_`).
> Token lạ → **fallback** (nhân vật = "everyman" trung tính + tinh chỉnh theo `gender`; nền = scene mặc định).
> `asset` phải là **slug chính xác** trong thư viện — **thư viện hiện RỖNG (0 dòng)** ⇒ luôn để `asset=""`, mọi thứ vẽ **procedural**.
> Nguồn: `svg_presets._ARCH`, `svg_scene._SCENES`, `story_asset_repo` (DB `story_assets`), `story_voice_cast.list_voices`.

### `CharacterDef.archetype` — 56 token hợp lệ (procedural chibi)

| Nhóm | Token |
|------|-------|
| Hiện đại / nghề | `office_worker` `salaryman` `businessman` `ceo` `student` `teacher` `scholar` `doctor` `nurse` `chef` `waiter` `cafe_staff` `maid` `idol` `police` `firefighter` `detective` `farmer` `soldier` `astronaut` `robot` |
| Gia đình / tuổi | `child` `grandma` `grandpa` |
| Cổ trang / Á Đông | `swordsman` `samurai` `ninja` `assassin` `general` `emperor` `king` `princess` `noblewoman` `geisha` `scholar` `merchant` `monk` `monk_warrior` `immortal` `heroine` |
| Fantasy / phương Tây | `knight` `mage` `witch` `vampire` `elf` `dwarf` `orc` `demon` `angel` `fairy` `archer` `ranger` `bard` `pirate` `cowboy` `villain` |

> Không có token "bride/old_man/old_woman" → dùng gần nhất: bride→`noblewoman`/`princess`, ông già→`grandpa`, bà già→`grandma`. Không rõ → để `""` + đặt `gender` (nữ tự thành váy).

### `SettingDef.scene_kind` — 61 token hợp lệ (nền procedural)

`alley` `bamboo_forest` `battlefield` `bazaar` `beach` `bedroom` `cafe` `castle` `castle_hall` `cave` `cemetery` `city` `classroom` `cliff` `clinic` `coffee_shop` `courtyard` `desert` `dunes` `dungeon` `forest` `garden` `graveyard` `hall` `home` `hospital` `imperial_hall` `inn` `kitchen` `lake` `library` `living_room` `market` `mountain` `ocean` `office` `pagoda` `palace` `palace_courtyard` `park` `peak` `river` `rooftop` `ruins` `school` `seaside` `shrine` `skyline` `snow` `snowfield` `street` `study` `tavern` `temple` `throne_room` `torii` `war` `waterfall` `winter` `woods` `yard`

> Token lạ → nền mặc định (gradient trung tính). Chọn token gần nghĩa nhất với `SettingDef.canonical_desc`.

### `CharacterDef.asset` / `SettingDef.asset` — thư viện offline

DB `story_assets` **hiện rỗng** → **luôn `asset=""`**. (Khi có seed thư viện: slug theo `ASSET_LIBRARY_DIR/{kind}/{region}/{genre}/{slug}.png`, `kind ∈ character|background`; AI copy slug chính xác, sai/không có → `""`.)

### `render.voices` — giọng TTS theo ngôn ngữ (per-character override)

| Lang | Engine | Female | Male |
|------|--------|--------|------|
| `vi` | gemini | Kore, Aoede, Leda, Callirrhoe | Puck, Charon, Fenrir, Orus |
| `ko` | gemini | Kore, Aoede, Leda, Callirrhoe | Puck, Charon, Fenrir, Orus |
| `en` | elevenlabs | 21m00Tcm4TlvDq8ikWAM, EXAVITQu4vr4xnSDxMaL, MF3mGyEYCl7XYWbV9V6O | TxGEqnHWrfWFTfGW9XjX, ErXwobaYiN019PkySvjV, VR6AewLTigWG4xSOukaG |
| `ja` | elevenlabs | (như `en`) | (như `en`) |

> Voice do engine tự cast theo `voice_gender`; ghi đè bằng `render.voices[char_id] = [engine, voice_id]`. `GET /api/story/voices?language=` trả bảng này cho FE.

### Enum LABEL (AI chỉ phát nhãn — engine resolve giây/pixel/màu)

| Field | Giá trị |
|-------|---------|
| `language` | `vi` `en` `ja` `ko` |
| `aspect_ratio` | `16:9` `9:16` `1:1` |
| `region` | `cn` `jp` `ko` `vi` `eu` `us` `""` |
| `genre_key` | `wuxia` `ngontinh` `horror` `fantasy` `codai` `hiendai` `""` |
| `gender` / `voice_gender` | `male` `female` `""` |
| `tier` | `low` `medium` `high` |
| `emotion` (line/beat) | `normal` `happy` `angry` `sad` `surprised` |
| `pose` (line/beat) | `stand` `wave` `cheer` `point` `hip` |
| `focus` (beat) | `wide` `left` `center` `right` `top` `bottom` `close` |
| `bgm_mood` (beat) | `tense` `calm` `epic` `sad` `romantic` `mysterious` `action` `hopeful` `dark` |
| `motion` ¹ | `zoom_in` `zoom_out` `pan_left` `pan_right` `pan_up` `pan_down` `static` |
| `transition_in` ¹ | `cut` `fade` `slide` `zoom` `flash` `to_black` |
| `bgm_cue` ¹ | `under` `intro` `outro` `none` |
| `bgm_intensity` ¹ | `low` `med` `high` |
| `source_audio` ¹ | `mute` `duck` `keep` (chỉ có tác dụng khi CÓ video nền) |
| `char_anchor` ¹ | `none` `left` `center` `right` |
| `char_scale` ¹ | `small` `medium` `large` |
| `char_motion` ¹ | `static` `fade` `slide` `float` |
| `text_anchor` ¹ | `auto` `top` `bottom` `left` `right` |

¹ = field cơ học: nhánh **SVG lean** BỎ (engine tự derive); chỉ nhánh **video full-schema** để AI đặt. `focus`/`bgm_mood`/`emotion`/`pose` luôn do AI đặt ở cả 2 nhánh.

## FE Review đọc/sửa gì (mirror `frontend/src/api/story.ts`)
- Hiển thị + sửa: `topic/tone`, `characters` (name/canonical_desc/archetype/gender/voice), `visuals` (setting_id/character_ids), `timeline` beats qua `beatLines()` (mỗi line: speaker/text/emotion/pose, hook/hook_text/focus/bgm_mood).
- Chỉ đọc: `estimated_total_sec`, `image_count`, `beat_count`, `warnings`, `source_truncated`.
- FE `Cue` là bản rút gọn (chỉ `beat_id/visual_id/start_sec/end_sec/transition/hook/hook_text`) cho timeline preview.
```
