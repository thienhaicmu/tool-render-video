# Story Asset Library — Generation Prompts

Bộ **danh mục + prompt** để tự sinh (AI) một kho asset offline cho Story Mode:
**nhân vật · nền · đồ vật · frame**, theo **vùng thị trường** (CN/JP/KO/VI/EU/US) ×
**thể loại** (wuxia · ngôn tình · kinh dị · fantasy · cổ đại · hiện đại).

> **Vì sao tự sinh thay vì tải?** Nhân vật stylized (wuxia/anime/ngôn tình) theo vùng +
> thể loại **không có nguồn free/CC0 hợp pháp** để tải hàng loạt; tải bừa (Canva, các
> site "free PNG") **vi phạm license** khi asset đi vào video xuất ra. Tự sinh 1 lần →
> **khoá lại** → tái dùng **miễn phí + nhất quán tuyệt đối** (cùng 1 file). Nền/đồ vật có
> thể bổ sung từ nguồn CC0 (Openverse / The Met / Kenney / OpenGameArt — xem cuối file).

> **Danh mục chi tiết (prompt copy-ready):**
> [nhân vật](asset_library_characters.md) · [nền/khung cảnh](asset_library_backgrounds.md) ·
> [frame/khung hình](asset_library_frames.md). Kế hoạch sản xuất: [backlog](asset_library_backlog.md).

---

## 0. Quy ước lưu (nơi chỉ định)

```
APP_DATA_DIR/asset_library/
  character/{region}/{genre}/{slug}.png     ← PNG NỀN TRONG SUỐT (full-body master)
  background/{region}/{genre}/{slug}.png     ← ảnh ĐẶC, wide 16:9, KHÔNG người
  object/{region}/{slug}.png                 ← PNG trong suốt, 1 vật
  frame/{style}/{slug}.png                    ← PNG trong suốt (khung/hoạ tiết)
```

- `region` = `cn | jp | ko | vi | eu | us`
- `genre` = `wuxia | ngontinh | horror | fantasy | codai | hiendai`
- slug ví dụ: `cn_wuxia_swordsman_male_young`
- Kho sẽ được index theo `kind / region / genre` (feature AL0 sau này — khi có, app tự nhận thư mục này).

---

## 1. Prompt TEMPLATE (điền biến — sinh vô hạn)

### Nhân vật (transparent master)
```
Full-body {ROLE}, {GENDER}, {AGE}, {ETHNIC/REGION cues}, wearing {ATTIRE},
{DISTINCT FEATURES/PROPS}, {EXPRESSION}, {STYLE} style.
Standing, front-facing, entire body head-to-toe, centered, isolated subject,
transparent background, no scene, no floor, no cast shadow, even lighting.
Clean character art, no text, no watermark.
```
**Negative:** `text, watermark, multiple people, cropped, extra limbs, blurry, background scenery, frame`

**STYLE theo genre:**
| genre | STYLE token |
|---|---|
| wuxia / tiên hiệp | `cinematic ink-wash wuxia/xianxia` |
| ngontinh | `soft romantic anime` |
| horror | `dark eerie cinematic` |
| fantasy | `epic fantasy concept art` |
| codai (cổ đại) | `historical painting, realistic` |
| hiendai | `modern semi-realistic` |

**gpt-image-1:** đặt `background="transparent"`, `output_format="png"`, portrait **1024×1536**.
Cùng một nhân vật → giữ NGUYÊN prompt + `seed` cố định để các lần sinh gần giống → chọn 1 bản khoá.

---

## 2. NHÂN VẬT — danh sách sẵn (copy prompt)

> Mỗi archetype có thể nhân thêm **cảm xúc** (bình thản / vui / giận / buồn / chiến đấu) và
> **tuổi** (young / adult / elder) bằng cách đổi `{EXPRESSION}` / `{AGE}` trong template.

### 🇨🇳 CN — wuxia / tiên hiệp / cổ đại

| slug | prompt |
|---|---|
| cn_wuxia_swordsman_male_young | `Full-body young male wuxia swordsman, early 20s, long black hair in topknot, white flowing hanfu robe, jade belt, holding a slender jian sword, calm determined face, cinematic ink-wash wuxia style. Standing front-facing, full body head-to-toe, isolated, transparent background, no scene, no floor, even lighting, no text, no watermark.` |
| cn_wuxia_heroine_female_young | `Full-body young female wuxia heroine, early 20s, elegant long hair with hairpin, pale blue silk hanfu, sword at hip, graceful confident pose, cinematic ink-wash wuxia style. Full body front-facing, isolated, transparent background, no scene, no text, no watermark.` |
| cn_xianxia_immortal_male_elder | `Full-body elderly xianxia immortal master, long white beard and hair, ornate daoist robe with cloud patterns, wooden staff, serene wise expression, ethereal glow, cinematic xianxia fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_wuxia_villain_male | `Full-body sinister wuxia villain, 40s, sharp features, black-and-red robe, dark aura, holding a curved blade, menacing smirk, cinematic ink-wash style. Full body front-facing, isolated, transparent background, no scene, no text, no watermark.` |
| cn_xianxia_demoness_female | `Full-body xianxia demoness, flowing dark-red robes, elaborate hair ornaments, pale skin, seductive dangerous expression, dark fantasy ink style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_codai_princess_female | `Full-body ancient Chinese princess, ornate imperial hanfu with phoenix embroidery, elaborate hairpiece, refined gentle expression, historical painting realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_codai_emperor_male | `Full-body ancient Chinese emperor, imperial yellow dragon robe, crown with beaded curtains, dignified authoritative expression, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_codai_general_male | `Full-body ancient Chinese general, heavy lamellar armor, red cape, stern face, holding a guandao polearm, historical cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_codai_scholar_male | `Full-body Chinese scholar (shusheng), blue changshan robe, holding a scroll, gentle scholarly look, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_wuxia_maidservant_female | `Full-body young maidservant, simple green hanfu, hair in twin buns, shy demure expression, ink-wash style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_wuxia_monk_male | `Full-body Shaolin monk, saffron-and-grey robes, shaved head, prayer beads, calm resolute expression, ink-wash style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🇯🇵 JP — samurai / anime / cổ đại

| slug | prompt |
|---|---|
| jp_samurai_male | `Full-body Japanese samurai, traditional o-yoroi armor, katana at side, stern honorable expression, cinematic feudal Japan style. Full body front-facing, isolated, transparent background, no scene, no text, no watermark.` |
| jp_ronin_male | `Full-body wandering ronin, worn kimono and hakama, straw hat on back, katana, weary rugged look, cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_ninja_male | `Full-body ninja/shinobi, dark navy garb, face partly covered, tanto blade, agile ready stance, cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_geisha_female | `Full-body geisha, elaborate silk kimono, white makeup, ornate hair with kanzashi, elegant poised expression, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_anime_schoolgirl_female | `Full-body anime high-school girl, sailor uniform, cheerful expression, clean modern anime style. Full body front-facing, isolated, transparent background, no scene, no text, no watermark.` |
| jp_anime_hero_male | `Full-body anime young male hero, spiky hair, casual jacket, confident smile, vibrant anime style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_yokai_kitsune_female | `Full-body kitsune yokai woman, fox ears and multiple tails, flowing kimono, mysterious alluring expression, dark fantasy anime style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_daimyo_male | `Full-body Japanese daimyo lord, luxurious kimono and haori, fan in hand, commanding calm expression, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🇰🇷 KO — cổ trang (hanbok) / hiện đại

| slug | prompt |
|---|---|
| ko_hanbok_noblewoman_female | `Full-body Korean noblewoman in ornate hanbok (jeogori + chima), elegant updo hair, graceful refined expression, historical drama style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_seonbi_scholar_male | `Full-body Korean seonbi scholar, white hanbok robe and gat (black hat), calm dignified look, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_king_male | `Full-body Korean king in royal gonryongpo (dragon robe), imperial crown, majestic expression, historical drama style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_warrior_male | `Full-body Korean warrior, leather-and-cloth armor, sword, determined face, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_gisaeng_female | `Full-body gisaeng entertainer, colorful hanbok, delicate makeup, graceful pose, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_modern_woman_female | `Full-body modern Korean young woman, trendy streetwear, stylish, bright confident expression, semi-realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_modern_man_male | `Full-body modern Korean young man, smart-casual outfit, calm charismatic expression, semi-realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🇻🇳 VI — cổ trang / kiếm hiệp Việt / hiện đại

| slug | prompt |
|---|---|
| vi_aodai_lady_female | `Full-body Vietnamese woman in traditional áo dài, long black hair, nón lá conical hat in hand, gentle graceful expression, soft cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_codai_scholar_male | `Full-body Vietnamese scholar (thầy đồ), áo the black robe and khăn đóng turban, holding a brush, scholarly calm look, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_kiemkhach_male | `Full-body Vietnamese swordsman, traditional robe, straight sword, resolute expression, ink-wash cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_general_male | `Full-body ancient Vietnamese general, traditional lamellar armor, sword, commanding stance, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_farmer_female | `Full-body Vietnamese peasant woman, brown áo bà ba, nón lá, warm kind expression, historical rural style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_princess_female | `Full-body ancient Vietnamese princess, ornate royal áo tấc robe, elaborate headdress, refined expression, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_modern_youth_male | `Full-body modern Vietnamese young man, casual shirt and jeans, friendly expression, semi-realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🇪🇺 EU — fantasy / trung cổ / kinh dị

| slug | prompt |
|---|---|
| eu_knight_male | `Full-body medieval knight, full plate armor, sword and shield, heroic stance, epic fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_mage_male | `Full-body wizard/mage, long robe with arcane runes, wooden staff with glowing crystal, wise mysterious look, epic fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_princess_female | `Full-body medieval princess, ornate gown, tiara, gentle regal expression, fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_rogue_female | `Full-body rogue/thief woman, dark leather armor, hood, twin daggers, sly confident look, fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_vampire_male | `Full-body aristocratic vampire, elegant Victorian coat, pale skin, red eyes, sinister charm, dark gothic horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_witch_female | `Full-body witch, dark tattered robe, pointed hat, glowing eyes, eerie expression, dark fantasy horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_king_male | `Full-body medieval king, royal robe and crown, scepter, authoritative expression, fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_priest_male | `Full-body medieval priest/cleric, white-and-gold vestments, holy symbol, serene benevolent expression, fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🇺🇸 US — hiện đại / miền tây / kinh dị

| slug | prompt |
|---|---|
| us_cowboy_male | `Full-body American cowboy, hat, leather vest, revolver at hip, rugged squint, western cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_detective_male | `Full-body noir detective, trench coat and fedora, serious look, 1940s cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_modern_woman_female | `Full-body modern American woman, business-casual outfit, confident expression, semi-realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_teen_male | `Full-body American teenage boy, hoodie and sneakers, casual friendly look, semi-realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_soldier_male | `Full-body modern soldier, tactical gear, serious focused expression, cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_ghost_female | `Full-body ghostly woman, pale translucent white dress, hollow eyes, eerie floating pose, horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_businessman_male | `Full-body American businessman, sharp suit, briefcase, confident expression, semi-realistic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

---

## 2B. NHÂN VẬT MỞ RỘNG (phản diện · phụ · trẻ em · người già · quái vật)

> Cùng template mục 1 (isolated, transparent background, no scene, no text). Đường dẫn:
> `character/{region}/{genre}/{slug}.png` — quái vật để `genre = horror` hoặc `fantasy`.

### 👿 Phản diện (villains)

| slug | prompt |
|---|---|
| cn_wuxia_sect_leader_evil_male | `Full-body evil wuxia sect leader, 50s, long grey hair, black robe with silver serpent motifs, cold cruel eyes, dark qi aura, cinematic ink-wash style. Full body front-facing, isolated, transparent background, no scene, no text, no watermark.` |
| cn_xianxia_sorceress_evil_female | `Full-body evil xianxia sorceress, blood-red robes, sharp painted nails, floating dark energy, malevolent smile, dark fantasy ink style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_codai_corrupt_minister_male | `Full-body corrupt imperial minister, ornate dark official robe and hat, sly greedy expression, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_evil_warlord_male | `Full-body cruel Japanese warlord, dark ornate armor, oni-mask helmet under arm, ruthless glare, cinematic style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| ko_traitor_general_male | `Full-body treacherous Korean general, dark lacquered armor, scheming expression, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| vi_banditchief_male | `Full-body Vietnamese bandit chief (sơn tặc), rough tunic, broad saber, fierce scarred face, historical style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_dark_lord_male | `Full-body dark lord, black spiked armor, glowing red eyes, tattered cape, menacing aura, epic dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_necromancer_male | `Full-body necromancer, tattered black-purple robes, skull staff, sickly pale face, sinister grin, dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_evil_queen_female | `Full-body evil queen, dark ornate gown, spiked crown, cold arrogant expression, dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| us_gangster_male | `Full-body 1930s American gangster, pinstripe suit, fedora, tommy gun, cold ruthless expression, noir style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🧑‍🤝‍🧑 Phụ / quần chúng (supporting)

| slug | prompt |
|---|---|
| _guard_soldier_male | `Full-body common guard soldier, simple {REGION} armor, spear, neutral alert expression, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _merchant_male | `Full-body {REGION} merchant, modest traditional clothes, friendly shrewd expression, holding a coin pouch, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _innkeeper_female | `Full-body {REGION} innkeeper woman, apron over traditional dress, warm welcoming smile, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _servant_male | `Full-body humble {REGION} servant, plain clothes, deferential posture, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _monk_priest_male | `Full-body {REGION} monk/holy man, simple religious robes, calm serene expression, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _physician_male | `Full-body traditional {REGION} physician, scholarly robe, medicine box, kindly focused expression, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

> Thay `{REGION}`/`{STYLE}` theo vùng (Chinese/Japanese/Korean/Vietnamese/medieval European/American) và lưu vào đúng thư mục vùng.

### 🧒 Trẻ em (children)

| slug | prompt |
|---|---|
| cn_child_disciple_boy | `Full-body young Chinese boy disciple, ~10 years old, small grey training robe, curious bright eyes, ink-wash style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_anime_child_girl | `Full-body anime child girl, ~8 years old, cute casual dress, cheerful innocent expression, anime style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_child_prince_boy | `Full-body young medieval prince, ~10 years old, small royal outfit, curious expression, fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _child_villager_girl | `Full-body {REGION} village girl, ~9 years old, simple traditional clothes, shy smile, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 👵 Người già (elders)

| slug | prompt |
|---|---|
| _elder_grandmother_female | `Full-body elderly {REGION} grandmother, grey hair in a bun, traditional clothes, kind wrinkled smile, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _elder_sage_male | `Full-body elderly {REGION} sage, long white beard, flowing robe, wise calm expression, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _elder_villager_male | `Full-body old {REGION} villager man, weathered face, simple worn clothes, walking cane, {STYLE} style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

### 🐉 Quái vật / sinh vật (creatures) — genre `horror` / `fantasy`

| slug | prompt |
|---|---|
| cn_dragon | `Full-body majestic Chinese dragon, long serpentine body, golden scales, whiskers, flowing mane, epic ink-wash fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_fox_spirit | `Full-body nine-tailed fox spirit (huli jing), white fur, glowing eyes, ethereal, dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| cn_jiangshi | `Full-body jiangshi (hopping vampire), stiff Qing-era official robe, pale greenish face, talisman on forehead, arms outstretched, horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_oni | `Full-body oni demon, muscular red skin, horns, fangs, loincloth, iron club (kanabo), fierce roar, dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| jp_tengu | `Full-body tengu, long red nose, feathered wings, mountain-ascetic robes, fierce expression, dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_dragon | `Full-body European dragon, massive scaled body, leathery wings spread, horned head, fierce, epic fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_orc | `Full-body orc warrior, green muscular skin, tusks, crude armor, jagged axe, snarling, epic fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_skeleton_warrior | `Full-body skeleton warrior, rusted armor, sword and shield, glowing eye sockets, dark fantasy style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| eu_werewolf | `Full-body werewolf, hulking furry body, sharp claws and fangs, feral glare, dark horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _ghost_spirit | `Full-body pale translucent ghost, tattered flowing garment, hollow glowing eyes, drifting pose, eerie horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |
| _zombie | `Full-body zombie, decaying skin, torn clothes, vacant hungry stare, arms reaching, horror style. Full body, isolated, transparent background, no scene, no text, no watermark.` |

---

## 3. NỀN / KHUNG CẢNH (ảnh ĐẶC, wide 16:9, KHÔNG người)

```
Wide cinematic establishing shot of {PLACE}, {MOOD/LIGHTING}, {STYLE} style,
no people, detailed, atmospheric. 16:9, no text, no watermark.
```

| region | slug → PLACE |
|---|---|
| cn | `cn_palace` ancient Chinese imperial palace · `cn_bamboo` misty bamboo forest · `cn_mountain` immortal cloud-covered mountains · `cn_temple` daoist temple courtyard |
| jp | `jp_shrine` shinto shrine with torii gates · `jp_sakura` cherry-blossom street · `jp_castle` feudal Japanese castle · `jp_street` old Edo street at dusk |
| ko | `ko_hanok` traditional hanok village · `ko_palace` Gyeongbokgung palace · `ko_mountain` mountain temple |
| vi | `vi_dinh` Vietnamese communal house (đình làng) · `vi_ruong` rice terraces · `vi_pho` Hoi An old town lanterns · `vi_song` riverside pier |
| eu | `eu_castle` medieval castle on a hill · `eu_cathedral` gothic cathedral interior · `eu_forest` misty enchanted forest · `eu_village` cobblestone stone village |
| us | `us_city` night city skyline · `us_desert` western desert canyon · `us_diner` neon diner at night · `us_suburb` quiet suburban street |

---

## 4. ĐỒ VẬT / PROP (PNG trong suốt, 1 vật)

```
A single {OBJECT}, isolated, transparent background, no scene, soft studio
lighting, {STYLE} style. Centered, no text, no watermark.
```

| slug | OBJECT |
|---|---|
| cn_sword | a slender Chinese jian sword |
| cn_lantern | a red Chinese paper lantern |
| cn_scroll | an ancient Chinese bamboo scroll |
| cn_guqin | a guqin (Chinese zither) |
| jp_katana | a Japanese katana with black scabbard |
| jp_fan | a folding Japanese fan (sensu) |
| ko_celadon | a Korean celadon vase |
| vi_nonla | a Vietnamese conical hat (nón lá) |
| vi_trongdong | a Dong Son bronze drum |
| eu_goblet | an ornate medieval goblet |
| eu_tome | an ancient spellbook tome |
| us_revolver | a western revolver |
| us_guitar | an acoustic guitar |

### 📚 ĐỒ VẬT — BỘ CHI TIẾT MỞ RỘNG (prompt tự chứa)

> Add-only. Mỗi đồ vật: **ô mô tả** + **🔑 ghi chú**. **Cách dùng:** prompt hoàn chỉnh =
> *nội dung ô* **+ TAIL** bên dưới. PNG **trong suốt, 1024×1024 (vuông) hoặc 1024×1536**,
> **1 vật duy nhất**, không cảnh, không tay/người. Path: `object/{region}/{slug}.png`.

**TAIL (đồ vật — dán vào cuối MỌI prompt bên dưới):**
```
a single isolated object, centered with generous transparent padding, three-quarter product view, transparent background with clean alpha edges, soft even studio lighting, no scene, no floor, no ground shadow, no hands, no people, no text, no logo, no watermark.
```

#### 🌏 Hiện đại / phổ dụng (dùng nhiều nhất cho truyện đời thường)
- **Điện thoại thông minh** · `object/jp/phone.png` · `A modern black smartphone with a glossy screen and thin bezels,` — 🔑 điện thoại đen bóng
- **Tách cà phê bốc khói** · `object/jp/coffee_cup.png` · `A white ceramic coffee cup on a saucer with a gentle wisp of steam,` — 🔑 tách sứ trắng + khói mảnh
- **Cặp sách học sinh** · `object/jp/schoolbag.png` · `A brown leather Japanese student satchel (randoseru-style) with buckles,` — 🔑 cặp da nâu có khoá
- **Laptop mở** · `object/us/laptop.png` · `A slim open silver laptop with a softly glowing blank screen,` — 🔑 laptop bạc mỏng, màn hình sáng trống
- **Chồng sách** · `object/us/book_stack.png` · `A small neat stack of three hardcover books in muted colors,` — 🔑 3 cuốn bìa cứng màu trầm
- **Ô/dù trong suốt** · `object/jp/umbrella.png` · `A clear transparent vinyl umbrella, half open, seen from the side,` — 🔑 ô nhựa trong nửa mở
- **Bó hoa** · `object/eu/bouquet.png` · `A small tied bouquet of pink and white flowers with greenery,` — 🔑 bó hoa hồng-trắng + lá
- **Ly rượu vang** · `object/eu/wine_glass.png` · `A single glass of red wine, elegant stemware, subtle reflection,` — 🔑 ly vang đỏ chân cao
- **Vali kéo** · `object/us/suitcase.png` · `A modern hard-shell carry-on suitcase with a raised handle,` — 🔑 vali cứng có tay kéo
- **Gấu bông** · `object/us/teddy_bear.png` · `A soft brown plush teddy bear sitting, with a small ribbon,` — 🔑 gấu bông nâu + nơ
- **Phong thư** · `object/us/letter.png` · `A cream envelope sealed with a red wax stamp,` — 🔑 phong bì kem + xi đỏ
- **Hộp nhẫn** · `object/us/ring_box.png` · `An open small velvet ring box with a sparkling diamond ring,` — 🔑 hộp nhung mở + nhẫn kim cương

#### 🏮 Cổ trang / văn hoá theo vùng
- **Ấm trà Trung Hoa** · `object/cn/teapot.png` · `An ornate Chinese porcelain teapot with blue floral patterns,` — 🔑 ấm sứ hoa lam
- **Lư hương** · `object/cn/incense_burner.png` · `A bronze Chinese incense burner with thin rising smoke,` — 🔑 lư đồng + khói mảnh
- **Ô giấy dầu Nhật (wagasa)** · `object/jp/wagasa.png` · `A traditional Japanese oil-paper umbrella (wagasa), open, red with spokes,` — 🔑 ô giấy dầu đỏ
- **Mèo may mắn** · `object/jp/maneki_neko.png` · `A white maneki-neko lucky cat figurine with a raised paw and a gold coin,` — 🔑 mèo vẫy trắng + xu vàng
- **Hộp cơm bento** · `object/jp/bento.png` · `A traditional Japanese bento lunch box, lacquered, closed, with a cloth tie,` — 🔑 hộp bento sơn mài + vải buộc
- **Nón lá Việt** · `object/vi/nonla.png` · `A Vietnamese conical leaf hat (nón lá) with a silk chin strap,` — 🔑 nón lá + quai lụa
- **Bánh chưng** · `object/vi/banh_chung.png` · `A square Vietnamese sticky-rice cake (bánh chưng) wrapped in green leaves, tied with string,` — 🔑 bánh chưng lá xanh + lạt
- **Bình gốm celadon Hàn** · `object/ko/celadon_vase.png` · `A Korean celadon vase with a soft jade-green glaze and crane inlay,` — 🔑 bình celadon xanh ngọc + hoạ tiết hạc

#### 🐉 Fantasy / kinh dị (prop kịch tính)
- **Quả cầu phép** · `object/eu/magic_orb.png` · `A glowing crystal magic orb swirling with blue energy, on a small ornate stand,` — 🔑 cầu pha lê phát sáng xanh
- **Rương báu** · `object/eu/treasure_chest.png` · `An old wooden treasure chest open, overflowing with gold coins and gems,` — 🔑 rương gỗ mở + vàng
- **Thanh gươm thần** · `object/eu/holy_sword.png` · `An ornate silver longsword with a glowing blue rune blade and a gemmed hilt,` — 🔑 kiếm bạc lưỡi rune xanh
- **Nến sọ người** · `object/us/skull_candle.png` · `A human skull with a lit dripping candle on top, eerie dark mood,` — 🔑 sọ + nến chảy (kinh dị)
- **Đèn lồng cũ** · `object/us/old_lantern.png` · `A rusty old oil lantern with a faint warm flame inside,` — 🔑 đèn dầu gỉ + lửa mờ

---

## 5. FRAME / HOẠ TIẾT (PNG trong suốt — viền trang trí)

```
Decorative {STYLE} ornamental border frame, symmetrical, transparent center
and background, elegant, PNG with alpha, no text, no watermark.
```

| slug | STYLE |
|---|---|
| frame/wuxia/ink_corner | Chinese ink-wash corner ornament |
| frame/anime/soft_glow | soft glowing anime border |
| frame/gothic/dark_vines | gothic dark vine border |
| frame/royal/gold_baroque | ornate gold baroque frame |

---

## 6. Mẹo sinh để NHẤT QUÁN + rẻ

- **Cùng một nhân vật** dùng lại nhiều cảnh: giữ NGUYÊN prompt + `seed` cố định → các lần
  sinh gần giống → chọn 1 bản, khoá lại, tái dùng.
- **gpt-image-1**: `background="transparent"`, `output_format="png"`, portrait **1024×1536**
  (nhân vật) / **1536×1024** (nền).
- **Batch**: sinh 2–3 biến thể mỗi archetype, chọn bản đẹp nhất lưu kho.
- Đặt tên file đúng **slug** + để đúng **thư mục** (mục 0) → khi có feature index, app tự nhận.
- Biến thể cảm xúc/tư thế: chỉ đổi `{EXPRESSION}` (calm / smiling / angry / sad / fighting)
  và `{AGE}` (young / adult / elderly) trong template — giữ phần còn lại để nhất quán.

---

## 7. Nguồn CC0 bổ sung (nền / đồ vật — hợp pháp để tải)

Dùng cho **nền/đồ vật** (KHÔNG dùng cho nhân vật stylized — không có nguồn free hợp pháp).
Chỉ nhận **CC0 / Public Domain / CC-BY (ghi nguồn)**:

| Nguồn | License | Ghi chú |
|---|---|---|
| Openverse (`api.openverse.org`) | lọc CC0 / CC-BY | 800M+ ảnh, no-key, trả kèm metadata license |
| The Met Open Access | CC0 | Tranh/đồ vật CN/JP/KO cổ, API |
| Smithsonian Open Access | CC0 | Đồ vật, art (key free) |
| Wikimedia Commons | PD / CC (lọc từng file) | Địa danh, đền đài |
| Kenney.nl | CC0 | Prop/đồ vật kiểu game |
| OpenGameArt | lọc CC0 / CC-BY | Prop, tileset |

**TRÁNH cho kho (cấm phát hành lại file rời):** Canva · Pixabay · Pexels · Unsplash · Freepik.

---

## 8. Dùng kho tự động — `STORY_LIBRARY_FIRST` (AL5)

Mặc định **TẮT** → render không đổi (byte-identical). Bật để render **ưu tiên
kho** trước khi gọi AI:

```
STORY_LIBRARY_FIRST=1      # opt-in
```

Khi bật, mỗi **nhân vật** cần overlay được **khớp theo tên** với 1 master trong
kho (transparent) — trùng thì dùng luôn, **không tốn tiền AI** và **nhất quán**
cho nhân vật lặp lại (vd truyện tái dùng "Haruto"/"Yuki"). Khớp theo thứ tự:
tên/slug trùng khít → chuỗi con trong slug/name/tags → trùng token. Không có tín
hiệu tên → **bỏ qua** (không thay bừa 1 nhân vật khác). **Nền** vẫn gán tay qua
picker "🗂️ Kho" (prompt tự do không khớp tên an toàn được).

> Không cần cấu hình picker: gán tay trong màn Review (nút **🗂️ Kho** ở nhân
> vật / key-visual) luôn hoạt động **bất kể** cờ này — nó ghi thẳng
> `render.masters` / `render.visual_assets` (AL4), render tái dùng (AL3).

### Manifest xuất xứ — `asset_sources.json` (tùy chọn)

Đặt tại `ASSET_LIBRARY_DIR/asset_sources.json`. Khi 1 file **không có sidecar**
`{file}.json`, `scan_library` lấy `license`/`source` mặc định theo family khớp:

```json
{
  "families": [
    { "match": { "kind": "background" }, "license": "cc0-openverse", "source": "openverse" },
    { "match": { "kind": "character", "region": "jp" }, "license": "ai-generated", "source": "gpt-image-1" }
  ]
}
```

Ưu tiên: **sidecar `{file}.json` > manifest > mặc định cứng** (`ai-generated`/`local`).
`match` bỏ trống khóa nào thì khóa đó là wildcard; family khớp **đầu tiên** thắng.
