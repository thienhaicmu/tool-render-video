# StoryPlan JSON — Spec cho AGENT sinh kịch bản (paste-JSON)

> Mục đích: bạn tạo một **agent bên ngoài** (ChatGPT/Claude/n8n/Make...) nhận truyện
> hoặc ý tưởng và **xuất ra StoryPlan JSON**. Dán JSON đó vào Story Studio (nguồn
> **"Dán JSON — không AI"**) → app render **NGUYÊN VĂN, $0 AI**. Contract khớp
> `app/domain/story_plan_v2.py`; máy sẽ tự sửa lỗi nhẹ (xem §4) nên agent chỉ cần
> đúng khung, không cần hoàn hảo tuyệt đối. Khi doc ≠ code: **tin code**.

## 1. Luồng sử dụng

```text
Agent của bạn → StoryPlan JSON
  → Story Studio ▸ "Dán JSON" ▸ Kiểm tra & Duyệt   (hoặc API: POST /api/story/validate)
  → máy: normalize + resolver gán nhân vật kho (slot trống) + chip trạng thái
  → Duyệt (sửa được mọi thứ) → Render (readiness gate + composition tự lo)
```

API thay UI: `POST /api/story/validate {"plan": <json>, "has_base_video": false}` →
lấy `plan_normalized`; render bằng `POST /api/render/process` với
`render_format="story"`, `story_source="paste_json"`,
`story_plan_override=<chuỗi JSON>`, `voice_language`, `aspect_ratio`, `output_dir`.

## 2. SYSTEM PROMPT cho agent (dán nguyên khối)

```text
You are a STORY-TO-VIDEO SCRIPTWRITER. Given a story (or an idea + target length),
output ONE valid JSON object — a StoryPlan v2 — and NOTHING else (no prose, no
markdown fences).

═══ OUTPUT SHAPE ═══
{
  "schema_version": 2,
  "language": "vi|en|ja|ko",
  "art_style": "",                         // "" OR an installed style pack id
  "aspect_ratio": "16:9|9:16|1:1",
  "topic": "<short title>", "tone": "<tone>",
  "region": "jp|cn|ko|vi|us|eu|",          // asset-library market hint, "" ok
  "genre_key": "hiendai|codai|wuxia|ngontinh|horror|fantasy|",
  "characters": [
    { "id": "<snake_slug>", "name": "<display name>",
      "canonical_desc": "<LOOK only: age, hair, clothing+colors, props — consistent>",
      "gender": "male|female", "voice_gender": "male|female", "age": "",
      "archetype": "<english role token, e.g. office_worker|student|doctor|samurai>",
      "asset": "" }                        // "" = engine picks from library (best)
  ],
  "settings": [
    { "id": "<slug>", "name": "<place>", "canonical_desc": "<look of the place>",
      "scene_kind": "<english token: cafe|classroom|office|hospital|street|shrine|
                      bedroom|living_room|forest|castle_hall|rooftop|beach|station|...>",
      "asset": "" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "<a settings id>",
      "character_ids": ["<ids of characters PRESENT in this picture, max 3>"] }
  ],
  "timeline": [
    { "id": "b1", "visual_id": "<a visuals id>",
      "focus": "wide|left|center|right|top|bottom|close",
      "bgm_mood": "tense|calm|epic|sad|romantic|mysterious|action|hopeful|dark",
      "pace": "slow|normal|fast", "pause": "none|beat|long",
      "hook": false, "hook_text": "",
      "lines": [
        { "speaker_id": "<a characters id, or \"\" for narrator>",
          "text": "<spoken words in the target language>",
          "emotion": "normal|happy|angry|sad|surprised",
          "pose": "stand|wave|cheer|point|hip" }
      ] }
  ]
}

═══ HARD RULES ═══
1. Every timeline.visual_id exists in visuals; every visuals.setting_id exists in
   settings; every speaker_id/character_ids exists in characters ("" = narrator).
2. AT MOST 15 visuals; REUSE each across many beats (beats in the same place/moment
   share one visual_id). Never one image per beat.
3. One beat = ONE camera shot holding a self-contained mini-scene (~1-3 sentences of
   speech total). DIRECT SPEECH is its own line with the speaker's id — never leave
   quotes inside a narrator line. A beat's lines all happen in the SAME place.
4. Write ONLY in the target language. Keep names/facts of the source story exactly;
   never invent events. Cover the story start → end (the ending must be told).
5. Writing craft: show-don't-tell; short sentences at tension peaks; end scenes on a
   pull; dialogue reveals character/conflict, ≤2 sentences per turn, natural when
   READ ALOUD; no cliches ("time flew by", "couldn't believe his eyes").
6. pace/pause: non-default on only the ~20% emotional beats (fast=action, slow=grief;
   pause "beat" after a reveal, "long" after a cliffhanger). Never output seconds.
7. hook: mark only 1-3 climactic beats hook=true with a SHORT punchy hook_text.
8. Leave every "asset" as "" unless you were given an explicit asset slug list.
9. Do NOT output any render/path/timestamp field or a "render" object.
```

## 3. Bảng field (những gì render thật sự dùng)

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `schema_version` | ✅ =2 | khác 2 → validate chặn |
| `language` | ✅ | quyết định TTS engine (vi→Gemini, en/ja/ko→ElevenLabs) + CPS ước tính |
| `art_style` | ⬜ | style pack id đã cài (`jp_anime_clean_v1` / `jp_anime_cinematic_v1` / `jp_anime_soft_drama_v1`) → cả bộ nhân vật+nền theo style; `""` → kho styleless (GEE!ME) |
| `characters[].canonical_desc` | ✅ nên có | **nguồn matching** của resolver (viết NGOẠI HÌNH, tiếng Việt được — có cầu VI→EN) |
| `characters[].asset` | ⬜ | slug kho chính xác (vd `jp_samurai`, `geeme_042`) = 🔒 khoá cứng; `""` = engine tự gán unique |
| `settings[].scene_kind` | ⬜ | token cảnh — khớp nền kho/procedural: cafe, classroom, office, hospital, police_office, laboratory, convenience_store, station, street, living_room, bedroom, executive_office, shrine, traditional_house, forest, castle_hall, temple, market, rooftop, beach, snow, desert, cave, battlefield, graveyard... |
| `settings[].scene_spec` | ⬜ | vẽ nền declarative (xem [STORY_SCENE_SPEC.md](STORY_SCENE_SPEC.md)) — chỉ luồng paste_json |
| `timeline[].lines[]` | ✅ khuyên dùng | đa giọng per-line; beat KHÔNG có `lines` thì dùng `narration`+`speaker_id`+`emotion`+`pose` phẳng (tương thích cũ) |
| `pace` / `pause` | ⬜ | nhãn → máy đổi thành reading_speed (0.88/1/1.12) và pause_after (0/0.7/1.6s); có `reading_speed`/`pause_after` SỐ thì số thắng |
| `hold_sec` | ⬜ | beat câm (không lời) đứng hình N giây |
| Nâng cao (thường bỏ qua — máy tự derive): `motion`, `transition_in`, `bgm_cue`, `bgm_intensity`, `text_anchor`, `char_anchor/scale/motion`, `source_audio` | ⬜ | chỉ điền khi muốn override đạo diễn tự động |
| `render.voices` / `render.masters` / `render.visual_assets` | ⬜ | pick sẵn giọng/master/nền — normalize GIỮ các pick này |

Base video (Template-2 cũ): đính video nền ở UI (`story_base_video_path`) — beat có
thể thêm `source_audio: mute|duck|keep` và `char_anchor/scale/motion` để overlay
nhân vật lên video; không đính video thì các field đó bị bỏ qua.

## 4. Máy sẽ làm gì với JSON của agent (an toàn kể cả JSON lỗi nhẹ)

- **Normalize**: ref hỏng bị scrub (visual ma → remap, speaker ma → narrator), id trùng
  được đánh số lại, visuals vượt trần bị remap KHÔNG mất beat, render-state lạ bị xoá
  (trừ các pick §3 dòng cuối), field lạ bị bỏ, giá trị sai enum → default.
- **Resolver (GĐ3)**: slot `asset:""` → gán nhân vật kho theo `canonical_desc`
  (unique, lọc giới tính); trả trạng thái từng nhân vật ở `/validate` + chip Duyệt.
- **Đạo diễn tự động**: motion/transition/bgm placement/vị trí overlay được derive;
  2 nhân vật đối thoại tự đứng đối mặt; hook tự né mặt; 9:16 tự reflow.
- **Readiness (GĐ4)**: cảnh báo thiếu asset/lệch thời lượng... trước khi render.
- **Không bao giờ** gọi AI cho luồng paste_json — JSON là nguồn chân lý.

## 5. Ví dụ hoàn chỉnh (render được ngay)

```json
{
  "schema_version": 2, "language": "vi", "art_style": "jp_anime_clean_v1",
  "aspect_ratio": "16:9", "topic": "Ca trực định mệnh", "tone": "ấm áp",
  "region": "jp", "genre_key": "hiendai",
  "characters": [
    { "id": "minh", "name": "Minh", "gender": "male", "voice_gender": "male",
      "archetype": "doctor",
      "canonical_desc": "bác sĩ trẻ tóc đen, áo blouse trắng, đeo kính", "asset": "" },
    { "id": "lan", "name": "Lan", "gender": "female", "voice_gender": "female",
      "archetype": "nurse",
      "canonical_desc": "y tá tóc nâu buộc cao, đồng phục xanh nhạt", "asset": "" }
  ],
  "settings": [
    { "id": "benh_vien", "name": "Hành lang bệnh viện", "scene_kind": "hospital",
      "canonical_desc": "hành lang bệnh viện đêm, đèn trắng lạnh", "asset": "" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "benh_vien", "character_ids": ["minh", "lan"] }
  ],
  "timeline": [
    { "id": "b1", "visual_id": "v1", "focus": "wide", "bgm_mood": "calm",
      "pace": "normal", "pause": "none", "hook": true, "hook_text": "Ca trực cuối",
      "lines": [
        { "speaker_id": "", "text": "Hai giờ sáng, hành lang bệnh viện chỉ còn tiếng máy đo nhịp tim.", "emotion": "normal", "pose": "stand" }
      ] },
    { "id": "b2", "visual_id": "v1", "focus": "center", "bgm_mood": "romantic",
      "pace": "slow", "pause": "beat", "hook": false, "hook_text": "",
      "lines": [
        { "speaker_id": "lan", "text": "Anh chưa về sao?", "emotion": "surprised", "pose": "stand" },
        { "speaker_id": "minh", "text": "Còn một bệnh nhân... và còn một điều tôi chưa kịp nói.", "emotion": "happy", "pose": "point" }
      ] }
  ]
}
```

Dán khối trên vào Story Studio ▸ "Dán JSON" — máy sẽ tự gán `minh`→một bác sĩ nam
trong kho (JP style clean), `lan`→một nữ y tá, hai người render đứng đối mặt, mỗi
người một giọng riêng, hook "Ca trực cuối" nằm góc trống của khung hình.

## 6. Checklist review nhanh output của agent

- [ ] Một JSON object duy nhất, không markdown fence
- [ ] `schema_version: 2` + mọi ref khớp (speaker/visual/setting)
- [ ] ≤15 visuals, mỗi visual được nhiều beat dùng lại
- [ ] Mọi lời thoại nằm trong `lines[]` với đúng `speaker_id`
- [ ] `canonical_desc` mô tả NGOẠI HÌNH (resolver ăn cái này)
- [ ] Có kết truyện; 1-3 hook; pace/pause chỉ ở beat đắt giá
- [ ] Không có field `render`, không giây/timestamp tự chế
