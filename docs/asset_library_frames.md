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

---

## 📚 BỘ CHI TIẾT MỞ RỘNG — thêm style + dải phụ đề

> Add-only. Mỗi frame: **ô mô tả** + **🔑 ghi chú**. **Cách dùng:** prompt hoàn chỉnh =
> *nội dung ô* **+ TAIL** bên dưới. Frame = **PNG trong suốt, 1024×1536 (9:16)**, **giữa
> rỗng ≥80%**, chỉ có viền/hoạ tiết ở rìa.

**TAIL (frame — dán vào cuối MỌI prompt bên dưới):**
```
completely empty transparent center, thin elegant edge only, vertical 9:16 orientation. Transparent background, clean alpha, no background fill, no scene, no people, no photo, no text, no logo, no watermark. Symmetrical, tileable-looking edges.
```

---

### 📝 Dải phụ đề / lower-third (rất hay dùng — `style=minimal`)

**Dải gradient mờ dưới** · `subtitle_gradient_band` · `frame/minimal/subtitle_gradient_band.png`
```
Decorative minimal subtitle band, a soft dark gradient fading upward across only the bottom quarter of the image (opaque at the very bottom, fully transparent by mid-height), no side or top borders, the whole upper area completely empty and transparent,
```
🔑 chỉ mờ đáy, phần trên trong suốt hẳn — không che nhân vật

**Thẻ bo tròn dưới — có bóng** · `subtitle_rounded_card` · `frame/minimal/subtitle_rounded_card.png`
```
Decorative minimal subtitle card, a single semi-transparent dark rounded rectangle centered in the lower third with a soft drop shadow, generous padding inside, the rest of the image completely empty and transparent,
```
🔑 1 thẻ bo tròn ở 1/3 dưới, có bóng nhẹ

**Dải neon dưới — viền sáng** · `subtitle_neon_band` · `frame/neon/subtitle_neon_band.png`
```
Decorative modern subtitle band, a dark semi-transparent bar across the lower third with a thin glowing cyan-magenta neon outline and soft bloom, the rest of the image empty and transparent,
```
🔑 thanh dưới + viền neon phát sáng

---

### 🀄 Wuxia / Á Đông (`style=wuxia`)

**Mây cuộn bốn góc — vàng** · `cloud_scroll_corners` · `frame/wuxia/cloud_scroll_corners.png`
```
Decorative Chinese ornamental corner frame, elegant gold auspicious-cloud (ruyi) scroll motifs only at the four corners, thin gold hairline connecting the edges,
```
🔑 mây ruyi vàng ở 4 góc, viền chỉ mảnh

**Song long chầu — đỉnh/đáy** · `twin_dragon_top_bottom` · `frame/wuxia/twin_dragon_top_bottom.png`
```
Decorative Chinese ornamental frame, two symmetrical red-and-gold stylized dragons facing each other along the top edge and a matching cloud band along the bottom, the sides left thin and open,
```
🔑 2 rồng đối xứng cạnh trên + dải mây đáy

---

### 🌸 Sakura / ngôn tình (`style=sakura`)

**Mưa cánh hoa — mép trên** · `sakura_petal_rain_top` · `frame/sakura/sakura_petal_rain_top.png`
```
Decorative soft romantic frame, a cluster of pastel-pink sakura blossoms in the top corners with drifting petals falling down along the edges, delicate and airy, the center fully empty,
```
🔑 chùm hoa góc trên + cánh rơi dọc mép

**Ruy băng tim — góc dưới** · `ribbon_heart_bottom` · `frame/sakura/ribbon_heart_bottom.png`
```
Decorative cute romantic frame, a soft pink ribbon and small hearts gathered at the bottom corners with thin trailing lines up the sides, pastel palette, empty center,
```
🔑 nơ hồng + tim ở góc dưới, dây mảnh lên cạnh

---

### 🇰🇷 Hanbok (`style=hanbok`) · ✨ Gold (`style=gold`)

**Ngũ sắc obangsaek — bốn góc** · `obangsaek_corners` · `frame/hanbok/obangsaek_corners.png`
```
Decorative Korean traditional corner frame, obangsaek five-color (blue, red, yellow, white, black) geometric dancheong patterns at the four corners, a thin connecting border,
```
🔑 hoạ tiết ngũ sắc Hàn ở 4 góc

**Vòng nguyệt quế vàng** · `gold_laurel_wreath` · `frame/gold/gold_laurel_wreath.png`
```
Decorative golden frame, two symmetrical gold laurel branches curving up the left and right sides meeting with a small emblem at the top, classic award style, empty center,
```
🔑 2 nhánh nguyệt quế vàng 2 bên, huy hiệu đỉnh

---

### 🌐 Neon/tech · 🕯️ Horror

**Viền glitch scanline** · `glitch_scanline_border` · `frame/neon/glitch_scanline_border.png`
```
Decorative cyber glitch frame, a thin glowing rectangle outline with subtle RGB chromatic-split glitch and faint horizontal scanlines along the edges, dark tech aesthetic, empty center,
```
🔑 viền glitch RGB + scanline mờ

**Kính nứt — kinh dị** · `cracked_glass_border` · `frame/horror/cracked_glass_border.png`
```
Decorative horror frame, jagged cracked-glass fractures spreading inward from the four corners with a dark vignette hugging the edges, eerie and tense, the center clear and empty,
```
🔑 kính nứt lan từ góc + vignette tối

**Mạng nhện góc** · `cobweb_corners` · `frame/horror/cobweb_corners.png`
```
Decorative horror frame, delicate grey spiderwebs stretched across the top-left and bottom-right corners with a faint dark vignette, creepy abandoned mood, empty center,
```
🔑 mạng nhện 2 góc chéo + vignette nhẹ

---

### 🍃 Style MỚI — nature · vintage · comic · kids · festive

**Dây lá xanh — thiên nhiên** (`style=nature`) · `leaf_vine_border` · `frame/nature/leaf_vine_border.png`
```
Decorative botanical frame, thin green leafy vines and small wildflowers winding along all four edges and corners, fresh natural style, empty center,
```
🔑 dây lá + hoa dại quấn mép

**Giấy cũ rách — vintage** (`style=vintage`) · `vintage_paper_torn` · `frame/vintage/vintage_paper_torn.png`
```
Decorative vintage frame, aged sepia torn-paper edges with faint coffee stains and a subtle deckled border hugging the outer edge, nostalgic old-document look, empty transparent center,
```
🔑 mép giấy rách sepia + vệt ố (giữa vẫn trong suốt)

**Đường tốc độ manga — góc** (`style=comic`) · `manga_speed_lines_corners` · `frame/comic/manga_speed_lines_corners.png`
```
Decorative manga frame, dynamic black radial speed lines bursting inward only from the four corners, high-contrast comic style, the center fully empty and transparent,
```
🔑 speed line đen toả từ 4 góc

**Nét vẽ nguệch ngoạc — trẻ em** (`style=kids`) · `crayon_doodle_border` · `frame/kids/crayon_doodle_border.png`
```
Decorative playful kids frame, a colorful hand-drawn crayon doodle border with stars, hearts and squiggles around the edges, cheerful childish style, empty center,
```
🔑 viền sáp màu + sao/tim/nguệch ngoạc

**Bông tuyết mùa đông** (`style=festive`) · `snowflake_winter_border` · `frame/festive/snowflake_winter_border.png`
```
Decorative winter festive frame, delicate white-and-icy-blue snowflakes and frost crystals along the edges and corners with a faint frosty glow, cozy holiday style, empty center,
```
🔑 bông tuyết trắng-xanh băng + sương giá mép

**Pháo giấy confetti — mép trên** (`style=festive`) · `confetti_top_border` · `frame/festive/confetti_top_border.png`
```
Decorative celebration frame, colorful confetti and party streamers falling from the top edge and corners, festive cheerful style, the lower area empty and transparent,
```
🔑 confetti + ruy băng rơi từ mép trên
