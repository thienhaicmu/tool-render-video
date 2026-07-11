# Story Asset Library — NỀN / KHUNG CẢNH (prompt chi tiết, copy-ready)

Mỗi cảnh nền có **1 prompt tự chứa** — copy dán thẳng vào gpt-image-1. Nền là ảnh
**ĐẶC** (không trong suốt), **wide 16:9**, **KHÔNG người** — để nhân vật (transparent
master) đè lên khi render.

## ⚙️ Thiết lập máy
- gpt-image-1: `background="opaque"`, `output_format="png"`, **1536×1024 (ngang 16:9)**
- Path lưu suy từ slug: `background/{region}/{genre}/{slug}.png`
- `region` = `cn | jp | ko | vi | eu | us` · `genre` = `wuxia | ngontinh | horror | fantasy | codai | hiendai`
- Cùng một địa điểm nhiều cảnh → giữ NGUYÊN prompt + đổi `{TIME/LIGHT}` (bình minh /
  trưa / hoàng hôn / đêm) để ra bộ cảnh nhất quán. Nền/địa danh cũng có thể tải CC0
  (Openverse / The Met / Wikimedia) — xem `asset_library_prompts.md §7`.

## 🧩 Cấu trúc prompt (đã gộp sẵn vào từng cảnh)
```
Premium {STYLE} background art, wide cinematic establishing shot of {CẢNH},
{TIME/LIGHT}, {MOOD/ATMOSPHERE}, layered depth, atmospheric perspective.
Empty scene, absolutely no people, no characters, no animals, unobstructed
foreground so a character can be composited in later.
Horizontal 16:9 composition, highly detailed, cinematic color grading.
No text, logo, watermark, border, frame, people.
```
**{STYLE} theo genre:** wuxia→`cinematic ink-wash wuxia/xianxia` · ngontinh→`soft romantic anime` · horror→`dark eerie cinematic` · fantasy→`epic fantasy matte painting` · codai→`historical realistic painting` · hiendai→`modern cinematic anime`

---

## 🇨🇳 CN — wuxia / cổ đại

**Đại điện hoàng cung — uy nghi**
Slug `cn_wuxia_imperial_hall` · `background/cn/wuxia/cn_wuxia_imperial_hall.png`
`Premium cinematic ink-wash wuxia/xianxia background art, wide cinematic establishing shot of a grand ancient Chinese imperial throne hall, red lacquered pillars, golden dragon carvings, long red carpet, hanging silk lanterns, soft god-rays from high windows, solemn majestic atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Rừng trúc sương sớm — thanh tịnh**
Slug `cn_wuxia_bamboo_forest` · `background/cn/wuxia/cn_wuxia_bamboo_forest.png`
`Premium cinematic ink-wash wuxia/xianxia background art, wide cinematic establishing shot of a misty green bamboo forest with a narrow stone path, morning fog and soft light beams, dew, tranquil serene atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Đỉnh núi tiên hiệp — mây phủ**
Slug `cn_wuxia_mountain_peak` · `background/cn/wuxia/cn_wuxia_mountain_peak.png`
`Premium cinematic ink-wash wuxia/xianxia background art, wide cinematic establishing shot of towering jagged xianxia mountain peaks piercing a sea of clouds, a lone stone platform, distant floating pagoda, sunrise glow, epic ethereal atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Khách điếm cổ — về đêm**
Slug `cn_wuxia_inn_night` · `background/cn/wuxia/cn_wuxia_inn_night.png`
`Premium cinematic ink-wash wuxia/xianxia background art, wide cinematic establishing shot of the interior of an ancient Chinese wooden inn at night, wooden tables and benches, red lanterns, a staircase to upper rooms, warm candlelight, moody quiet atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Sân luyện võ — hoàng hôn**
Slug `cn_wuxia_training_courtyard` · `background/cn/wuxia/cn_wuxia_training_courtyard.png`
`Premium cinematic ink-wash wuxia/xianxia background art, wide cinematic establishing shot of a martial-arts sect courtyard with stone floor, wooden training dummies, weapon racks, curved-roof halls behind, golden-hour light, disciplined calm atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

---

## 🇯🇵 JP — hiện đại / samurai

**Quán cà phê ấm — ban ngày**
Slug `jp_hiendai_cozy_cafe` · `background/jp/hiendai/jp_hiendai_cozy_cafe.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of a cozy Japanese cafe interior, wooden counter, shelves of cups, warm pendant lights, a window with soft daylight and street bokeh, calm inviting atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Phố Tokyo đêm — neon**
Slug `jp_hiendai_tokyo_street_night` · `background/jp/hiendai/jp_hiendai_tokyo_street_night.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of a narrow Tokyo backstreet at night, glowing neon signs, izakaya lanterns, wet asphalt reflections, vending machines, vibrant moody atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Lớp học chiều — nắng vàng**
Slug `jp_hiendai_classroom_afternoon` · `background/jp/hiendai/jp_hiendai_classroom_afternoon.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of a Japanese high-school classroom in late afternoon, rows of wooden desks, blackboard, large windows with warm orange sunset light, nostalgic quiet atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Đền sakura — mùa xuân**
Slug `jp_codai_shrine_sakura` · `background/jp/codai/jp_codai_shrine_sakura.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of a traditional Japanese shrine with a red torii gate, stone lanterns, blooming sakura trees, falling petals, soft spring daylight, serene peaceful atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

---

## 🇰🇷 KO — cổ trang (hanbok) / hiện đại

**Cung điện Joseon — sân trong**
Slug `ko_codai_palace_courtyard` · `background/ko/codai/ko_codai_palace_courtyard.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of a Joseon-era Korean palace courtyard, ornate green-and-red dancheong wooden halls, stone paving, distant mountains, clear morning light, dignified elegant atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Làng hanok — hoàng hôn**
Slug `ko_codai_hanok_village` · `background/ko/codai/ko_codai_hanok_village.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of a traditional Korean hanok village alley, tiled curved roofs, earthen walls, stone steps, warm sunset glow, nostalgic calm atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Căn hộ Seoul hiện đại — ban ngày**
Slug `ko_hiendai_seoul_apartment` · `background/ko/hiendai/ko_hiendai_seoul_apartment.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of a clean modern Seoul apartment living room, minimalist furniture, large window overlooking a city skyline, soft daylight, calm contemporary atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

---

## 🇻🇳 VI — cổ trang / hiện đại

**Đình làng Việt — cây đa giếng nước**
Slug `vi_codai_village_communal_house` · `background/vi/codai/vi_codai_village_communal_house.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of a traditional Vietnamese village with an ancient communal house (đình làng), a large banyan tree, a stone well, rice paddies behind, soft warm daylight, peaceful rural atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Phố cổ Hội An — đèn lồng đêm**
Slug `vi_codai_hoian_lanterns` · `background/vi/codai/vi_codai_hoian_lanterns.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of Hoi An ancient town street at night, colorful silk lanterns strung overhead, yellow-walled old houses, riverside reflections, warm festive glow, romantic tranquil atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Quán cà phê Sài Gòn — hiện đại**
Slug `vi_hiendai_saigon_cafe` · `background/vi/hiendai/vi_hiendai_saigon_cafe.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of a trendy Saigon rooftop cafe, potted plants, string lights, low tables, a view of city buildings at dusk, relaxed warm atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

---

## 🇪🇺 EU — fantasy / trung cổ / kinh dị

**Đại sảnh lâu đài — fantasy**
Slug `eu_fantasy_castle_hall` · `background/eu/fantasy/eu_fantasy_castle_hall.png`
`Premium epic fantasy matte painting background art, wide cinematic establishing shot of a grand medieval castle great hall, tall stone arches, banners, iron chandeliers, a long wooden table, colored light from stained-glass windows, majestic heroic atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Rừng phép thuật — sương xanh**
Slug `eu_fantasy_enchanted_forest` · `background/eu/fantasy/eu_fantasy_enchanted_forest.png`
`Premium epic fantasy matte painting background art, wide cinematic establishing shot of an enchanted forest, giant ancient trees, glowing blue mushrooms, drifting fireflies, teal mist and light shafts, mysterious magical atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Quảng trường trung cổ — ban ngày**
Slug `eu_codai_medieval_town_square` · `background/eu/codai/eu_codai_medieval_town_square.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of a medieval European town square, cobblestone ground, timber-framed houses, market stalls, a stone fountain, clear daytime light, lively historical atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Lâu đài ma — kinh dị**
Slug `eu_horror_haunted_manor` · `background/eu/horror/eu_horror_haunted_manor.png`
`Premium dark eerie cinematic background art, wide cinematic establishing shot of the interior of an abandoned haunted Victorian manor, decaying wallpaper, a broken chandelier, dusty covered furniture, cold moonlight through cracked windows, dread and unease atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

---

## 🇺🇸 US — hiện đại / miền tây / kinh dị

**Văn phòng thành phố — ban ngày**
Slug `us_hiendai_city_office` · `background/us/hiendai/us_hiendai_city_office.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of a modern open-plan American office, glass partitions, desks with monitors, a wall of windows overlooking a skyline, bright daylight, professional busy-but-empty atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Đường phố Mỹ — hoàng hôn**
Slug `us_hiendai_suburban_street` · `background/us/hiendai/us_hiendai_suburban_street.png`
`Premium modern cinematic anime background art, wide cinematic establishing shot of an American suburban street, rows of houses with front lawns, parked cars, tall trees, warm golden-hour light, calm everyday atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Thị trấn miền tây — trưa nắng**
Slug `us_codai_western_town` · `background/us/codai/us_codai_western_town.png`
`Premium historical realistic painting background art, wide cinematic establishing shot of an old American Wild West frontier town main street, wooden saloon, dusty dirt road, hitching posts, distant desert mesas, harsh noon sunlight, rugged lonely atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

**Nhà bỏ hoang — kinh dị đêm**
Slug `us_horror_abandoned_house` · `background/us/horror/us_horror_abandoned_house.png`
`Premium dark eerie cinematic background art, wide cinematic establishing shot of the interior of an abandoned American farmhouse at night, peeling paint, an overturned chair, moonlight through torn curtains, cold blue shadows, tense frightening atmosphere, layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.`

---

> **Biến thể rẻ:** với mỗi slug, sinh 1 bản rồi đổi `{TIME/LIGHT}` (bình minh / trưa /
> hoàng hôn / đêm) để có bộ 3-4 cảnh cùng địa điểm — nhất quán, chi phí thấp. Lưu thêm
> hậu tố thời gian vào slug (vd `..._night`).
