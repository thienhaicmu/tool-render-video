# Story Asset Library — FRAME / KHUNG HÌNH (prompt chi tiết, copy-ready)

Frame là **PNG NỀN TRONG SUỐT** — chỉ có **viền/hoạ tiết ở rìa**, **giữa rỗng hoàn
toàn**, để lồng lên video dọc (9:16) làm khung trang trí hoặc dải lower-third cho phụ
đề. Không phải nền, không có người.

## ⚙️ Thiết lập máy
- gpt-image-1: `background="transparent"`, `output_format="png"`, **1024×1536 (dọc, hợp video 9:16)**
- Path lưu suy từ slug: `frame/{style}/{slug}.png`
- `style` = `wuxia | sakura | hanbok | gold | neon | horror | minimal | festive`
- Khung phải chừa **giữa trống ~80%** để không che mặt nhân vật/khung hình chính.

## 🧩 Cấu trúc prompt (đã gộp sẵn vào từng frame)
```
Decorative {STYLE} border frame, ornamental edges and corners only, completely
empty transparent center (at least 80% of the image is empty), thin elegant border
hugging the outer edge, vertical 9:16 orientation.
Transparent background, clean alpha, no background fill, no scene, no people,
no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.
```

---

## 🀄 Wuxia / cổ trang Á Đông (`style=wuxia`)

**Góc mực tàu — cành trúc**
Slug `ink_bamboo_corner` · `frame/wuxia/ink_bamboo_corner.png`
`Decorative ink-wash wuxia border frame, delicate black bamboo branches and ink splashes growing only from the four corners, completely empty transparent center (at least 80% of the image is empty), thin elegant border hugging the outer edge, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

**Viền mây rồng — vàng đỏ**
Slug `dragon_cloud_border` · `frame/wuxia/dragon_cloud_border.png`
`Decorative Chinese ornamental border frame, red-and-gold stylized dragon and cloud motifs running along all four edges, completely empty transparent center (at least 80% of the image is empty), thin elegant border hugging the outer edge, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

## 🌸 Sakura / ngôn tình (`style=sakura`)

**Viền hoa anh đào — hồng pastel**
Slug `sakura_petal_border` · `frame/sakura/sakura_petal_border.png`
`Decorative soft romantic border frame, pastel-pink sakura blossoms and drifting petals along the edges and corners, completely empty transparent center (at least 80% of the image is empty), thin elegant border hugging the outer edge, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

**Vòng hoa tim — dễ thương**
Slug `heart_floral_wreath` · `frame/sakura/heart_floral_wreath.png`
`Decorative cute romantic border frame, a thin ring of small flowers and tiny hearts around the outer edge, completely empty transparent center (at least 80% of the image is empty), soft pink and cream palette, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

## 🇰🇷 Hanbok / Joseon (`style=hanbok`)

**Viền hoạ tiết dancheong**
Slug `dancheong_border` · `frame/hanbok/dancheong_border.png`
`Decorative Korean dancheong border frame, traditional green-red-blue geometric palace patterns along all edges and corners, completely empty transparent center (at least 80% of the image is empty), thin elegant border hugging the outer edge, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

## ✨ Sang trọng / vàng kim (`style=gold`)

**Khung vàng cổ điển**
Slug `gold_ornate_frame` · `frame/gold/gold_ornate_frame.png`
`Decorative ornate golden border frame, classic baroque gold filigree scrollwork around the entire edge, completely empty transparent center (at least 80% of the image is empty), elegant thin metallic gold border, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

**Góc vàng tối giản — Art Deco**
Slug `gold_deco_corners` · `frame/gold/gold_deco_corners.png`
`Decorative Art Deco border frame, thin gold geometric line corners only at the four corners, completely empty transparent center (at least 90% of the image is empty), minimal luxury style, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

## 🌐 Hiện đại / neon (`style=neon`)

**Viền neon phát sáng**
Slug `neon_glow_border` · `frame/neon/neon_glow_border.png`
`Decorative modern neon border frame, a thin glowing cyan-and-magenta neon rectangle outline hugging the outer edge with soft light bloom, completely empty transparent center (at least 90% of the image is empty), vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

**Khung công nghệ — HUD góc**
Slug `tech_hud_corners` · `frame/neon/tech_hud_corners.png`
`Decorative futuristic HUD border frame, thin cyan sci-fi interface brackets and tick marks at the four corners, completely empty transparent center (at least 90% of the image is empty), clean tech aesthetic, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

## 🕯️ Kinh dị (`style=horror`)

**Viền tối — vệt máu**
Slug `horror_vignette_border` · `frame/horror/horror_vignette_border.png`
`Decorative dark horror border frame, torn grungy black edges with faint dried-blood streaks and a heavy dark vignette around the border, completely empty transparent center (at least 80% of the image is empty), eerie ominous style, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

## ◾ Tối giản / phổ dụng (`style=minimal`)

**Dải phụ đề dưới — lower third**
Slug `subtitle_lower_third` · `frame/minimal/subtitle_lower_third.png`
`Decorative minimal subtitle band, a single soft semi-transparent dark rounded bar positioned only across the lower third, the entire rest of the image completely empty and transparent, no border on the other edges, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark.`

**Viền mảnh trắng — sạch sẽ**
Slug `thin_white_border` · `frame/minimal/thin_white_border.png`
`Decorative minimal border frame, a single thin clean white rounded-rectangle outline hugging the outer edge, completely empty transparent center (at least 92% of the image is empty), modern minimal style, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical.`

---

## 🎉 Lễ hội (`style=festive`)

**Viền đèn lồng — Tết / lễ**
Slug `lantern_festive_border` · `frame/festive/lantern_festive_border.png`
`Decorative festive border frame, small red-and-gold hanging lanterns and warm string lights along the top and side edges, completely empty transparent center (at least 80% of the image is empty), celebratory warm style, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.`

---

> **Kiểm tra sau khi sinh:** mở PNG trên nền carô — **giữa phải trong suốt hoàn toàn**.
> Nếu giữa bị mờ/nền đặc → thêm `empty transparent center, hollow, no fill` và sinh lại.
> Frame render đè **trên cùng** nên viền quá dày sẽ che nhân vật — ưu tiên bản mảnh.
