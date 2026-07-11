# Planner Analysis — Phase B2 (per-beat emotion/pose character overlay)

> Lập 2026-07-11 từ **code hiện tại** (`stages/story/beat_render.py`,
> `stages/story/visuals_stage.py`, `domain/story_plan_v2.py`, `visual/svg_char.py`).
> **Trạng thái: PLAN — chờ user "approved".** Đây là "option (b)" đã hoãn ở
> [SVG_ASSET_SYSTEM_PLAN §3](SVG_ASSET_SYSTEM_PLAN.md). Mục tiêu: nhân vật **đổi cảm
> xúc/tư thế THEO BEAT** (theo lời kể) thay vì key-visual TĨNH → truyện SVG sống động.

## Phát hiện then chốt (đỡ rủi ro nhiều)
**Machinery overlay ĐÃ CÓ SẴN** cho base-video mode (A3), chỉ cần MỞ RỘNG:
- `beat_render._char_overlay_parts(cue, w, h, dur)` → tính scale (`char_scale`), vị trí
  (`char_anchor`), motion (fade/slide/float) → filter overlay. **Dùng lại nguyên.**
- `render_one_cue` overlay `plan.render.masters[speaker_id]` — NHƯNG gate `if use_video`
  (chỉ base-video) + master là **1/nhân vật, không cảm xúc**.
- Cue đã mang `speaker_id / char_anchor / char_scale / char_motion`. Beat đã có `emotion`.
- `svg_char.build_char(opts+expr+pose)` sinh master **trong suốt theo cảm xúc, $0**.

→ N4 = (1) Cue mang thêm `emotion`; (2) sinh master **theo (nhân vật × cảm xúc)** bằng SVG;
(3) key-visual thành **NỀN-ONLY** khi bật overlay (khỏi nhân vật đúp); (4) `render_one_cue`
bật overlay ở **image mode** + chọn master theo `speaker_id + emotion`.

## Quyết định thiết kế (khuyến nghị)
- **Mô hình overlay = nền-only + overlay SPEAKER theo beat** (đúng như base-video A3 mở
  rộng sang ảnh). Chỉ nhân vật ĐANG NÓI hiện + biểu cảm theo `beat.emotion`. Động, bám lời kể.
- **Env-gate `STORY_CHAR_OVERLAY` (default OFF)** → mặc định giữ compose baked hiện tại
  (Sacred #2). Bật = mô hình overlay.
- **Chỉ SVG masters** (rẻ, $0). gpt-image master theo từng cảm xúc = quá đắt → overlay mode
  yêu cầu `provider=svg` (hoặc chỉ dùng SVG cho master, nền vẫn có thể là ảnh/kho).

---

## Sub-phase & file

### D1 · Cue mang `emotion` — Tier **LOW** (domain, defensive)
- `domain/story_plan_v2.py`: `Cue` += `emotion: str = "normal"`; `build_cues` copy
  `emotion=(b.emotion or "normal")` (additive; cạnh `speaker_id/char_anchor`). `_render_from`
  parse thêm (replay). **Không đổi timing/INV** → cue sheet tất định giữ nguyên với default.

### D2 · Sinh master theo (nhân vật × cảm xúc) SVG — Tier **HIGH** (visuals_stage)
- `stages/story/visuals_stage.py`: hàm mới `_generate_emotion_masters(plan, ...)` — khi
  `STORY_CHAR_OVERLAY=1`: với mỗi `speaker_id` xuất hiện + tập cảm xúc dùng trong timeline,
  `svg_char.build_char(preset(archetype,region,genre,gender) + expr=emotion_expr(emo))` →
  `svg_raster.save_svg_png(..., transparent)` → `plan.render.masters[f"{cid}:{emo}"]=path`.
  Best-effort (Sacred #3). Content-addressed cache (1 lần/(cid,emo)).
- Gọi trong `story_pipeline_v2` khi overlay mode (cạnh chỗ `_generate_character_masters` A3).

### D3 · Key-visual NỀN-ONLY khi overlay — Tier **HIGH** (svg_compose)
- `svg_compose.compose_visual(plan, visual, w, h, chars=True)`: thêm cờ `chars`; overlay mode
  gọi với `chars=False` → chỉ nền (khỏi bake nhân vật → không đúp với overlay).
- `visuals_stage._gen_one` (svg branch): overlay mode → `compose_visual(..., chars=False)`.

### D4 · `render_one_cue` bật overlay ở image mode — Tier **CRITICAL** (Render Edit Protocol)
- `beat_render.render_one_cue`: đổi điều kiện overlay (dòng 240-244):
  ```
  want_overlay = os.getenv("STORY_CHAR_OVERLAY","0")=="1" and char_anchor!="none"
  if (use_video or (not use_video)) and want_overlay:   # image mode cũng overlay
      cid = cue.speaker_id
      m = masters.get(f"{cid}:{cue.emotion}") or masters.get(cid)   # emotion → fallback plain
      if _ok_file(m): overlay_master = m
  ```
- Overlay input `[2]` + filtergraph `[bg][fg]overlay` **giữ nguyên** (đã có). Ken Burns vẫn chạy
  cho nền ([0:v] path). Chỉ THÊM nhánh overlay khi image + gate on. **Off → byte-identical.**
- **Render Edit Protocol:** baseline full pytest → edit tối thiểu → full pytest = baseline;
  runtime verify render thật.

### D5 · char_anchor cho overlay — Tier **MEDIUM** (quyết định)
- Overlay cần `char_anchor != none`. Hiện AI (s4/s5) tự set; truyện SVG thường để "none".
- **Quyết định:** khi `STORY_CHAR_OVERLAY=1` và beat có `speaker_id` mà `char_anchor=="none"`
  → default 1 anchor (vd luân phiên left/right theo speaker, hoặc center). Thêm ở build_cues
  hoặc trong overlay resolve. Giữ tất định (theo speaker_id hash/seed).

---

## Luồng (overlay mode)
```
beat.emotion + speaker_id + char_anchor
  → D2: svg_char(preset + expr) → master[cid:emo] (transparent, $0)
  → D3: compose nền-only key-visual (Ken Burns nền)
  → D4: render_one_cue overlay master[speaker:emotion] tại char_anchor, scale char_scale,
        motion char_motion  (dùng lại _char_overlay_parts)
```

## Test & DoD
| Test | Kiểm |
|------|------|
| `test_story_plan_v2` | Cue.emotion roundtrip + build_cues carries beat.emotion; default "normal" khi thiếu (cue sheet bất biến) |
| `test_svg_char` | build_char per-emotion master hợp lệ (đã có) |
| `test_char_overlay` (mới) | `_generate_emotion_masters` điền `masters[cid:emo]`; gate off → rỗng; compose chars=False → nền-only |
| `test_beat_render` (mới/bổ sung) | overlay mode + image → filtergraph có `[fg]overlay`; off → không (byte-identical) |
| **Full pytest** | before/after = baseline (D4 CRITICAL) |
| runtime verify | render thật 1 truyện `STORY_CHAR_OVERLAY=1` → xem nhân vật đổi cảm xúc theo beat |

## Sacred Contracts & rủi ro
- **#2:** env `STORY_CHAR_OVERLAY` default off → mặc định giữ baked compose; Cue.emotion default "normal" → replay bit-identical.
- **#3:** master/compose lỗi → không overlay (nền vẫn render). **#8** QA sau. **#4/#5** stage/part không đụng.
- **Tier:** D1 LOW · D2/D3 HIGH · **D4 CRITICAL** (`beat_render` = cue render core, Render Edit Protocol) · D5 MED.
- **Rollback:** `STORY_CHAR_OVERLAY=0` (default) → byte-identical toàn bộ.
- **Rủi ro thẩm mỹ:** overlay chỉ hiện SPEAKER (khác baked hiện tất cả). Đây là chủ đích (bám lời kể) — đánh giá qua runtime verify; nếu không thích, gate off là về baked.

## Cổng duyệt đề xuất
1. **D1+D2+D3** (domain + masters + compose nền-only, HIGH/LOW) — test, xem master mẫu. → duyệt.
2. **D4+D5** (cue render overlay, CRITICAL) — Render Edit Protocol + runtime verify render thật. → duyệt.

## Đánh giá / khuyến nghị
Đòn bẩy chất lượng lớn nhất còn lại (cảm xúc chạy theo lời kể) và **rủi ro vừa** nhờ tái dùng
machinery A3 sẵn có + gate off mặc định. Nên làm — nhưng D4 chạm cue render CRITICAL nên tách
cổng duyệt + Render Edit Protocol + verify thật trước khi coi là xong.

> Không code tới khi bạn "approved". Đề xuất bắt đầu **D1+D2+D3** (không đụng CRITICAL), rồi **D4+D5**.
