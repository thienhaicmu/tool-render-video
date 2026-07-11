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

---

## 📚 BỘ CHI TIẾT MỞ RỘNG — dàn đều 6 vùng

> Add-only. Mỗi nền: **ô mô tả** + **🔑 yếu tố khoá** (giữ khi sinh biến thể) + **⏱ gợi ý biến thể thời gian**.
> **Cách dùng:** prompt hoàn chỉnh = *nội dung ô* **+ TAIL** bên dưới. Nền = **ĐẶC** (opaque),
> **16:9 (1536×1024)**, **TUYỆT ĐỐI KHÔNG người/động vật**, tiền cảnh trống để ghép nhân vật sau.

**TAIL (nền — dán vào cuối MỌI prompt bên dưới):**
```
layered depth, atmospheric perspective. Empty scene, absolutely no people, no characters, no animals, unobstructed foreground so a character can be composited in later. Horizontal 16:9 composition, highly detailed, cinematic color grading. No text, logo, watermark, border, frame, people.
```
**{STYLE} theo genre:** wuxia→`cinematic ink-wash wuxia/xianxia` · ngontinh→`soft romantic anime` · horror→`dark eerie cinematic` · fantasy→`epic fantasy matte painting` · codai→`historical realistic painting` · hiendai→`modern cinematic anime`.

---

### 🇨🇳 CN — mở rộng

**Đình bên hồ sen — ngôn tình** · `cn_ngontinh_lakeside_pavilion` · `background/cn/ngontinh/cn_ngontinh_lakeside_pavilion.png`
```
Premium soft romantic anime background art, wide cinematic establishing shot of an ancient Chinese lakeside pavilion with curved red-tiled roofs, wooden railings, a stone bridge, blooming lotus on a calm lake, weeping willows, soft pink sunset light, dreamy tender atmosphere,
```
🔑 khoá: đình mái đỏ + cầu đá + sen + liễu rủ | ⏱ biến thể: `_dawn` sương hồng · `_night` trăng + đèn lồng

**Vách núi tuyết — wuxia** · `cn_wuxia_snowy_cliff` · `background/cn/wuxia/cn_wuxia_snowy_cliff.png`
```
Premium cinematic ink-wash wuxia/xianxia background art, wide cinematic establishing shot of a windswept snowy mountain cliff edge, jagged frozen rocks, a lone bare pine, swirling snow, distant white peaks under a pale cold sky, harsh solitary epic atmosphere,
```
🔑 khoá: vách đá tuyết + tùng trơ + đỉnh trắng xa | ⏱ biến thể: `_storm` bão tuyết · `_dusk` chiều tím lạnh

**Thượng Hải đêm — hiện đại** · `cn_hiendai_shanghai_night` · `background/cn/hiendai/cn_hiendai_shanghai_night.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of the Shanghai Bund skyline at night, glowing neon skyscrapers, a wide river with light reflections, distant towers, a moody vibrant city glow,
```
🔑 khoá: skyline neon + sông phản chiếu + tháp cao | ⏱ biến thể: `_rain` mưa bokeh · `_dusk` hoàng hôn tím

**Chợ đêm cổ trang — cổ đại** · `cn_codai_night_market` · `background/cn/codai/cn_codai_night_market.png`
```
Premium historical realistic painting background art, wide cinematic establishing shot of an ancient Chinese night street market, rows of wooden stalls with red lanterns, hanging silk banners, a stone-paved street, warm lantern glow, lively bustling-but-empty atmosphere,
```
🔑 khoá: sạp gỗ + đèn lồng đỏ + đường lát đá | ⏱ biến thể: `_rain` phố ướt · `_festival` thêm pháo hoa

---

### 🇯🇵 JP — mở rộng

**Phòng ngủ đêm — hiện đại** · `jp_hiendai_bedroom_night` · `background/jp/hiendai/jp_hiendai_bedroom_night.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of a cozy small Japanese bedroom at night, a low bed with soft sheets, a desk with a warm lamp, a window with city lights and a moon, plush rug, calm intimate atmosphere,
```
🔑 khoá: giường thấp + đèn bàn ấm + cửa sổ ánh đèn phố | ⏱ biến thể: `_day` nắng sáng · `_rain` mưa cửa sổ

**Trong tàu điện — hiện đại** · `jp_hiendai_train_interior` · `background/jp/hiendai/jp_hiendai_train_interior.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of the interior of a Japanese commuter train, rows of seats, overhead handrails and straps, large windows showing a blurred city passing, cool daylight, quiet everyday atmosphere,
```
🔑 khoá: ghế dài + tay nắm trần + cửa sổ phố mờ | ⏱ biến thể: `_night` đèn vàng + phố đêm · `_sunset` nắng cam

**Sân thành cổ — samurai/cổ đại** · `jp_codai_castle_courtyard` · `background/jp/codai/jp_codai_castle_courtyard.png`
```
Premium historical realistic painting background art, wide cinematic establishing shot of a Japanese feudal castle courtyard, white-walled tenshu keep with dark tiled roofs behind, stone walls, raked gravel, a few pine trees, clear morning light, dignified solemn atmosphere,
```
🔑 khoá: thiên thủ trắng + tường đá + sỏi + tùng | ⏱ biến thể: `_sakura` hoa anh đào · `_dusk` hoàng hôn

**Lễ hội matsuri đêm — hiện đại** · `jp_hiendai_festival_night` · `background/jp/hiendai/jp_hiendai_festival_night.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of a Japanese summer festival street at night, rows of food stalls (yatai) with paper lanterns, hanging decorations, a distant torii, warm festive glow and soft bokeh, joyful lively-but-empty atmosphere,
```
🔑 khoá: sạp yatai + đèn giấy + torii xa | ⏱ biến thể: `_fireworks` pháo hoa trời · `_rain` phố ướt lấp lánh

---

### 🇰🇷 KO — mở rộng

**Công viên sông Hàn — hiện đại** · `ko_hiendai_han_river_park` · `background/ko/hiendai/ko_hiendai_han_river_park.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of a Seoul Han River park at dusk, a wide river, a long bridge with lights, city skyline behind, green lawns and a walking path, warm golden-hour glow, relaxed calm atmosphere,
```
🔑 khoá: sông Hàn + cầu đèn + skyline + bãi cỏ | ⏱ biến thể: `_night` đèn cầu rực · `_spring` hoa anh đào

**Văn phòng Seoul — hiện đại** · `ko_hiendai_office` · `background/ko/hiendai/ko_hiendai_office.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of a sleek modern Korean corporate office, glass-walled meeting rooms, rows of clean desks with monitors, a wall of windows overlooking a city, bright cool daylight, professional atmosphere,
```
🔑 khoá: phòng họp kính + bàn màn hình + tường kính | ⏱ biến thể: `_night` đèn trần + phố đêm · `_sunset` nắng cam

**Điện rồng Joseon — cổ trang** · `ko_codai_throne_room` · `background/ko/codai/ko_codai_throne_room.png`
```
Premium historical realistic painting background art, wide cinematic establishing shot of a Joseon-era Korean royal throne hall interior, an ornate red-and-gold throne under a painted sun-and-moon folding screen, dancheong-patterned columns, polished wood floor, solemn majestic atmosphere,
```
🔑 khoá: ngai đỏ-vàng + bình phong nhật-nguyệt + cột dancheong | ⏱ biến thể: `_candle` ánh nến đêm · `_dawn` bình minh

---

### 🇻🇳 VI — mở rộng

**Phố cổ Hà Nội — hiện đại** · `vi_hiendai_hanoi_oldquarter` · `background/vi/hiendai/vi_hiendai_hanoi_oldquarter.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of a Hanoi Old Quarter street, narrow tube houses with faded yellow walls, tangled overhead wires, small shopfronts and plastic stools, string lights, warm nostalgic evening glow, cozy lively-but-empty atmosphere,
```
🔑 khoá: nhà ống vàng + dây điện chằng + ghế nhựa + đèn dây | ⏱ biến thể: `_rain` phố ướt · `_morning` sáng sớm phở

**Đại nội Huế — cổ trang** · `vi_codai_imperial_hue` · `background/vi/codai/vi_codai_imperial_hue.png`
```
Premium historical realistic painting background art, wide cinematic establishing shot of the Hue Imperial City, a grand red-and-gold Vietnamese palace gate with curved tiled roofs, ornate dragon motifs, a wide stone courtyard, a flag tower behind, soft warm daylight, majestic historical atmosphere,
```
🔑 khoá: cổng cung đỏ-vàng + mái cong + sân đá + kỳ đài | ⏱ biến thể: `_dusk` hoàng hôn · `_mist` sương sớm

**Ruộng bậc thang — hiện đại/thiên nhiên** · `vi_hiendai_rice_terrace` · `background/vi/hiendai/vi_hiendai_rice_terrace.png`
```
Premium modern cinematic background art, wide cinematic establishing shot of northern Vietnam rice terraces, layered green-and-gold curved paddies on a mountainside, thin water reflections, distant misty mountains and a small stilt house, soft morning light, serene majestic atmosphere,
```
🔑 khoá: ruộng bậc thang cong + núi sương + nhà sàn nhỏ | ⏱ biến thể: `_harvest` lúa vàng · `_sunset` chiều cam

---

### 🇪🇺 EU — mở rộng

**Hang rồng — fantasy** · `eu_fantasy_dragon_lair` · `background/eu/fantasy/eu_fantasy_dragon_lair.png`
```
Premium epic fantasy matte painting background art, wide cinematic establishing shot of a vast cavern dragon lair, piles of gold coins and treasure, massive stone pillars, glowing lava cracks, hanging chains, dramatic orange-and-red light, ominous epic atmosphere,
```
🔑 khoá: kho vàng + cột đá + khe dung nham + xích | ⏱ biến thể: `_cold` hang băng xanh · `_ruins` thêm xương rồng

**Nội thất nhà thờ lớn — cổ đại** · `eu_codai_cathedral_interior` · `background/eu/codai/eu_codai_cathedral_interior.png`
```
Premium historical realistic painting background art, wide cinematic establishing shot of a grand Gothic cathedral interior, towering stone columns and pointed arches, tall stained-glass windows casting colored light beams, a long aisle, candlelight, awe-inspiring sacred atmosphere,
```
🔑 khoá: cột Gothic + vòm nhọn + kính màu + lối đi dài | ⏱ biến thể: `_night` chỉ ánh nến · `_dawn` tia nắng vàng

**Phố Paris — hiện đại** · `eu_hiendai_paris_street` · `background/eu/hiendai/eu_hiendai_paris_street.png`
```
Premium modern cinematic background art, wide cinematic establishing shot of a charming Parisian street, Haussmann-style cream buildings with iron balconies, a corner cafe with awnings and small tables, cobblestones, distant Eiffel Tower, soft warm afternoon light, romantic relaxed atmosphere,
```
🔑 khoá: nhà Haussmann kem + café góc + tháp Eiffel xa | ⏱ biến thể: `_rain` phố ướt · `_night` đèn vàng + Eiffel sáng

---

### 🇺🇸 US — mở rộng

**Quán diner cổ điển — hiện đại** · `us_hiendai_classic_diner` · `background/us/hiendai/us_hiendai_classic_diner.png`
```
Premium modern cinematic anime background art, wide cinematic establishing shot of a retro American 1950s diner interior, red vinyl booths, a checkerboard floor, a chrome counter with stools, neon signage inside, a window to a night street, warm nostalgic atmosphere,
```
🔑 khoá: ghế da đỏ + sàn caro + quầy chrome + neon | ⏱ biến thể: `_day` nắng ban ngày · `_rain` phố mưa ngoài cửa

**Quảng trường Thời đại đêm — hiện đại** · `us_hiendai_times_square_night` · `background/us/hiendai/us_hiendai_times_square_night.png`
```
Premium modern cinematic background art, wide cinematic establishing shot of Times Square at night, towering buildings covered in giant glowing billboards and screens, bright multicolored neon, wet reflective pavement, an electric vibrant atmosphere,
```
🔑 khoá: bảng quảng cáo khổng lồ + neon nhiều màu + đường phản chiếu | ⏱ biến thể: `_rain` mưa bokeh · `_snow` tuyết rơi

**Rừng tối — kinh dị** · `us_horror_dark_forest` · `background/us/horror/us_horror_dark_forest.png`
```
Premium dark eerie cinematic background art, wide cinematic establishing shot of a dark misty American pine forest at night, tall twisted bare trees, thick ground fog, faint cold moonlight through branches, a barely-visible dirt trail, tense frightening atmosphere,
```
🔑 khoá: thông xoắn trơ + sương dày + trăng lạnh + lối mòn mờ | ⏱ biến thể: `_fog` sương đặc hơn · `_bloodmoon` trăng đỏ
