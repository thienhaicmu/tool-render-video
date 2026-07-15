# Style Pack Spec — Lottie Character Packs (GĐ2, hướng A)

> Story Mode dùng **bộ nhân vật Lottie do hoạ sĩ vẽ** (mua/tải về) thay vì hình vẽ
> procedural. Engine tự **đổi màu theo identity nhân vật** (tóc/da/trang phục từ
> `CharacterLook`) và render offline bằng `rlottie-python` — ảnh master cho màn
> Review + chuỗi frame RGBA cho video (nhân vật CHUYỂN ĐỘNG, không còn ảnh tĩnh).
> Code: `backend/app/features/render/engine/visual/v2/lottie_pack.py`.

## 1. Checklist khi MUA/TẢI một pack (việc của bạn)

Nguồn: [LottieFiles](https://lottiefiles.com) (Marketplace + Free), IconScout, Envato.
Tìm từ khoá: `character animation pack`, `character idle walk talk`, `mascot rig`.

Một pack ĐẠT YÊU CẦU khi:

- [ ] **Định dạng Lottie JSON** (không phải chỉ GIF/MP4/AEP). Ưu tiên export Bodymovin chuẩn.
- [ ] **Cùng MỘT nhân vật trong nhiều hành động** (tối thiểu: idle/stand, talk, walk;
      tốt hơn: wave, point, run, sit, cheer, sad, surprised).
- [ ] **Nhìn thẳng hoặc 3/4**, nền TRONG SUỐT (không có background bake vào layer).
- [ ] **Fill màu phẳng (solid fills)** — engine v1 đổi màu solid fill/stroke tĩnh;
      gradient/animated-color sẽ giữ nguyên màu gốc (vẫn dùng được, chỉ không đổi màu).
- [ ] **License thương mại** cho video xuất bản (kể cả YouTube monetized). Lưu file
      license vào thư mục pack.
- [ ] Ưu tiên pack có **nhiều nhân vật cùng style** (nam/nữ/già/trẻ) — mỗi nhân vật
      cài thành một pack, cùng "họ style" trên UI.

Kiểm tra nhanh trước khi mua: tải preview JSON (nếu có) → kéo vào
https://lottiefiles.com/preview — chạy được là rlottie gần như chắc chắn render được.

## 2. Cài một pack

```
%APP_DATA_DIR%/style_packs/{pack_id}/     # hoặc env STYLE_PACKS_DIR
  pack.json          # manifest (bạn/tôi viết — 5 phút/pack)
  anims/*.json       # các file Lottie mua về (giữ nguyên)
  LICENSE.txt        # bằng chứng license
```

Pack xuất hiện tự động trên UI dưới id `lottie:{pack_id}` (styles.list_styles()).

## 3. pack.json (manifest)

```json
{
  "name": "Office Guy",
  "desc": "Nhân vật văn phòng nam — 8 hành động",
  "fps": 30,
  "actions": {
    "stand":  {"file": "anims/idle.json",  "loop": true},
    "talk":   {"file": "anims/talk.json",  "loop": true},
    "wave":   {"file": "anims/wave.json",  "loop": false},
    "point":  {"file": "anims/point.json", "loop": false},
    "run":    {"file": "anims/run.json",   "loop": true},
    "*":      {"file": "anims/idle.json",  "loop": true}
  },
  "emotions": {
    "sad":    {"file": "anims/sad_idle.json", "loop": true}
  },
  "colors": {
    "#4a3b2f": ["hair", 1.0],
    "#2f261e": ["hair", 0.65],
    "#f2c9a0": ["skin", 1.0],
    "#3a5a8c": ["outfit_primary", 1.0],
    "#22355a": ["outfit_primary", 0.6],
    "#e8e6e0": ["outfit_secondary", 1.0]
  }
}
```

- **actions**: map vocab pose của engine (`stand, wave, point, cheer, hands_hips,
  cross_arms, think, bow, fight, hold, run, sit, kneel` + `talk` cho beat có thoại)
  → file Lottie. `"*"` = fallback bắt buộc. Pose thiếu tự rơi về `"*"`.
- **emotions**: (tuỳ chọn) override theo cảm xúc (`happy, sad, angry, ...`) — ưu tiên
  hơn action.
- **colors**: bảng đổi màu identity — liệt kê các mã màu hoạ sĩ dùng trong JSON và
  slot đích: `hair | skin | eye | outfit_primary | outfit_secondary | accent` + hệ số
  sáng/tối (giữ được các tầng shade của hoạ sĩ). Lấy mã màu: mở JSON tìm `"ty":"fl"`
  → `"c":{"k":[r,g,b,a]}` (giá trị 0-1; ×255 → hex), hoặc dùng LottieFiles editor xem
  palette. Để `{}` nếu không cần đổi màu (mỗi nhân vật một pack riêng).

## 4. Engine dùng pack như thế nào (đã chạy, có test)

| API | Dùng cho |
|---|---|
| `render_master(pack_id, look, emotion, pose, out_path, w, h)` | Ảnh tĩnh RGBA — Review master, contact sheet, composite tĩnh |
| `render_frames(pack_id, look, pose, emotion, duration_sec, fps, w, h)` | Chuỗi PNG RGBA phủ đúng thời lượng cue (loop/hold) — cache content-addressed tại `CACHE_DIR/lottie_renders` |
| `styles.render_character("lottie:{id}", ...)` | Hợp đồng chung với mọi style (SVG `<image>` embed) |

Giới hạn v1 (chấp nhận, nâng sau): đổi màu chỉ áp dụng cho solid fill/stroke tĩnh
(gradient + animated color giữ nguyên); chưa có mirror-facing cho animation bất đối
xứng (dùng transform lật ở compositor); text layer trong Lottie không hỗ trợ.

## 5. Trạng thái wiring

CHƯA nối vào render pipeline (GĐ2 gate): sau khi bạn cài pack thật đầu tiên, chạy
sample sheet để duyệt → duyệt xong mới wire (masters/overlay dùng `render_master`,
cue render dùng `render_frames` làm overlay động, style chọn trên UI qua
`list_styles`). Pin bằng `tests/test_lottie_pack.py` (9 test) — registry, recolor,
cache, fallback, degrade-khi-thiếu-renderer đều có test.
