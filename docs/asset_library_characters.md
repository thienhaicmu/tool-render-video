# Story Asset Library — TẤT CẢ nhân vật (prompt chi tiết, copy-ready)

Mỗi nhân vật có **1 prompt tự chứa** — copy dán thẳng vào gpt-image-1.

## ⚙️ Thiết lập máy
- gpt-image-1: `background="transparent"`, `output_format="png"`, **1024×1536 (dọc)**
- Path lưu suy từ slug: `character/{region}/{genre}/{slug}.png`
- Lặp nhiều cảnh cùng 1 nhân vật → giữ NGUYÊN prompt + **seed cố định** → chọn 1 bản khoá.

## 🧩 Cấu trúc prompt (đã gộp sẵn vào từng nhân vật)
```
Premium {STYLE}, semi-realistic facial anatomy, mature proportions, consistent
clean character-design style, of {MÔ TẢ NHÂN VẬT}.
Single character only, standing naturally, front-facing neutral reference pose,
entire body visible from the top of the hair to the soles of the shoes, centered
with generous transparent padding. Transparent background with clean alpha edges,
no environment, no floor, no ground shadow, even studio lighting.
No text, logo, watermark, border, frame, duplicate character, cropped feet,
cropped hair, extra fingers, extra limbs, malformed hands.
```
**{STYLE} theo genre:** wuxia→`cinematic ink-wash wuxia/xianxia illustration` · ngontinh→`soft romantic anime illustration` · horror→`dark eerie cinematic illustration` · fantasy→`epic fantasy concept illustration` · codai→`historical realistic painting` · hiendai→`Japanese cinematic anime illustration`

---

## 🇯🇵 NHẬT — HIỆN ĐẠI (slice-of-life)

**Haruto — nam, 35, nhân viên văn phòng, nội tâm**
Slug `jp_hiendai_haruto_office_worker_male` · `character/jp/hiendai/jp_hiendai_haruto_office_worker_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 35-year-old Japanese office worker man, slim build, short neat black hair, tired dark-brown eyes, reserved quiet demeanor, wearing a slightly wrinkled navy business suit, white shirt, loosened dark tie, black leather shoes, carrying a simple work bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Yuki — nữ, 28, nhân viên quán cà phê, dịu dàng**
Slug `jp_hiendai_yuki_cafe_staff_female` · `character/jp/hiendai/jp_hiendai_yuki_cafe_staff_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 28-year-old Japanese cafe worker woman, slender build, shoulder-length soft brown hair, warm hazel eyes, gentle kind smile, wearing a brown apron over a cream blouse and beige skirt, small hoop earrings, comfortable flats. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Tanaka — nam, 62, chủ tập đoàn, nghiêm khắc**
Slug `jp_hiendai_tanaka_ceo_male` · `character/jp/hiendai/jp_hiendai_tanaka_ceo_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 62-year-old Japanese corporate chairman, upright posture, grey slicked-back hair, sharp stern eyes, deep facial lines, wearing an expensive charcoal three-piece suit, silk pocket square, polished oxford shoes, gold wristwatch. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Emi — bé gái, 8, vui vẻ, đáng yêu**
Slug `jp_hiendai_emi_child_girl` · `character/jp/hiendai/jp_hiendai_emi_child_girl.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, child proportions, consistent clean character-design style, of an 8-year-old Japanese girl, small build, short black bob hair with a yellow hairclip, big cheerful brown eyes, bright happy smile, wearing a yellow sundress, white socks and red shoes, holding a small plush toy. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Sato — nữ, 24, OL năng động**
Slug `jp_hiendai_sato_office_lady_female` · `character/jp/hiendai/jp_hiendai_sato_office_lady_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 24-year-old Japanese office lady, slim build, long straight black hair, lively dark eyes, bright energetic expression, wearing a fitted light-grey blazer and pencil skirt, white blouse, low heels, small shoulder bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Kenji — nam, 45, salaryman mệt mỏi**
Slug `jp_hiendai_kenji_salaryman_male` · `character/jp/hiendai/jp_hiendai_kenji_salaryman_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 45-year-old Japanese salaryman, average build, thinning short black hair, weary eyes with slight bags, resigned tired expression, wearing a rumpled grey suit, loose tie, worn dress shoes, holding a briefcase. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Aoi — nữ, 20, sinh viên đại học**
Slug `jp_hiendai_aoi_university_student_female` · `character/jp/hiendai/jp_hiendai_aoi_university_student_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 20-year-old Japanese university student girl, slender build, medium brown wavy hair, bright curious eyes, friendly relaxed expression, wearing a soft knit sweater, high-waist jeans, canvas sneakers, a tote bag over one shoulder. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Ren — nam, 17, học sinh cấp 3**
Slug `jp_hiendai_ren_highschool_boy` · `character/jp/hiendai/jp_hiendai_ren_highschool_boy.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, teen proportions, consistent clean character-design style, of a 17-year-old Japanese high-school boy, lean build, tidy short black hair, calm cool dark eyes, composed expression, wearing a black gakuran uniform with brass buttons, black shoes, a school bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Mei — nữ, 16, học sinh cấp 3**
Slug `jp_hiendai_mei_highschool_girl` · `character/jp/hiendai/jp_hiendai_mei_highschool_girl.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, teen proportions, consistent clean character-design style, of a 16-year-old Japanese high-school girl, petite build, black hair in twin braids, gentle shy brown eyes, sweet timid expression, wearing a navy sailor uniform with a red scarf, knee socks, brown loafers, a satchel. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Hiroshi — nam, 70, ông lão hiền hậu**
Slug `jp_hiendai_hiroshi_grandpa_male` · `character/jp/hiendai/jp_hiendai_hiroshi_grandpa_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, elderly proportions, consistent clean character-design style, of a 70-year-old Japanese grandfather, slightly stooped, thin grey hair, kind gentle eyes, warm wrinkled smile, wearing a beige cardigan over a checked shirt, brown slacks, comfortable loafers, round glasses. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Kimiko — nữ, 68, bà lão hiền hậu**
Slug `jp_hiendai_kimiko_grandma_female` · `character/jp/hiendai/jp_hiendai_kimiko_grandma_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, elderly proportions, consistent clean character-design style, of a 68-year-old Japanese grandmother, small gentle build, grey hair in a neat bun, soft caring eyes, warm smile, wearing a lavender cardigan over a modest blouse, a long grey skirt, flat shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Nakamura — nam, 50, bác sĩ**
Slug `jp_hiendai_nakamura_doctor_male` · `character/jp/hiendai/jp_hiendai_nakamura_doctor_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 50-year-old Japanese doctor, calm composed build, short greying hair, steady reassuring eyes, wearing an open white medical coat over a shirt and tie, a stethoscope around the neck, dark trousers, formal shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Yui — nữ, 30, y tá**
Slug `jp_hiendai_yui_nurse_female` · `character/jp/hiendai/jp_hiendai_yui_nurse_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 30-year-old Japanese nurse, slim build, dark hair tied back neatly, caring gentle eyes, soft smile, wearing light-blue scrubs, a small watch, white nursing shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Mori — nam, 40, giáo viên**
Slug `jp_hiendai_mori_teacher_male` · `character/jp/hiendai/jp_hiendai_mori_teacher_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 40-year-old Japanese teacher, average build, short neat hair, thin-framed glasses, patient friendly expression, wearing a sweater vest over a collared shirt, slacks, loafers, holding a hardcover book. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Keiko — nữ, 38, nội trợ**
Slug `jp_hiendai_keiko_housewife_female` · `character/jp/hiendai/jp_hiendai_keiko_housewife_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 38-year-old Japanese housewife, gentle build, shoulder-length brown hair, warm caring eyes, soft smile, wearing a simple apron over a casual blouse and long skirt, house slippers. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Taro — nam, 55, chủ tiệm tạp hoá**
Slug `jp_hiendai_taro_shopkeeper_male` · `character/jp/hiendai/jp_hiendai_taro_shopkeeper_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 55-year-old Japanese shopkeeper, sturdy build, short greying hair, friendly hardworking face, wearing a navy work apron over a rolled-sleeve shirt, a cloth cap, work trousers, sturdy shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

> **Hiện đại các vùng khác:** đổi `Japanese` → dân tộc (`Korean/Vietnamese/American/…`) và lưu vào `character/{region}/hiendai/`, giữ nguyên phần còn lại.

---

## 🇨🇳 TRUNG — wuxia / tiên hiệp / cổ đại

**Kiếm khách trẻ (nam)** · Slug `cn_wuxia_swordsman_male_young` · `character/cn/wuxia/cn_wuxia_swordsman_male_young.png`
`Premium cinematic ink-wash wuxia illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a male wuxia swordsman in his early 20s, lean athletic build, long black hair in a topknot, sharp calm dark eyes, determined expression, wearing a white flowing hanfu robe, a jade belt, cloth boots, holding a slender jian sword at his side. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Nữ hiệp trẻ** · Slug `cn_wuxia_heroine_female_young` · `character/cn/wuxia/cn_wuxia_heroine_female_young.png`
`Premium cinematic ink-wash wuxia illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a female wuxia heroine in her early 20s, slender graceful build, long black hair with a jade hairpin, bright confident eyes, wearing a pale-blue silk hanfu, a slim sword sheathed at the hip, cloth shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Tiên nhân lão** · Slug `cn_xianxia_immortal_male_elder` · `character/cn/wuxia/cn_xianxia_immortal_male_elder.png`
`Premium cinematic ink-wash xianxia illustration, semi-realistic facial anatomy, elderly proportions, consistent clean character-design style, of an elderly immortal daoist master, tall thin build, long white beard and flowing white hair, serene wise eyes, wearing an ornate daoist robe with cloud patterns, holding a wooden staff, a faint ethereal glow. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Phản diện ma đầu (nam)** · Slug `cn_wuxia_villain_male` · `character/cn/wuxia/cn_wuxia_villain_male.png`
`Premium cinematic ink-wash wuxia illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a sinister wuxia villain in his 40s, tall imposing build, sharp gaunt features, cold cruel eyes, a thin cruel smirk, wearing a black-and-red robe with dark motifs, holding a curved blade, a faint dark aura. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Công chúa cổ đại** · Slug `cn_codai_princess_female` · `character/cn/codai/cn_codai_princess_female.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Chinese princess, elegant slender build, elaborate coiled hair with gold hairpieces, refined gentle face, wearing an ornate imperial hanfu with phoenix embroidery, silk sleeves, embroidered shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Hoàng đế** · Slug `cn_codai_emperor_male` · `character/cn/codai/cn_codai_emperor_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Chinese emperor, dignified build, groomed black beard, authoritative eyes, wearing an imperial yellow dragon robe, a crown with beaded curtains (mianguan), embroidered boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Tướng quân** · Slug `cn_codai_general_male` · `character/cn/codai/cn_codai_general_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Chinese general, powerful build, stern bearded face, wearing heavy lamellar armor, a red cape, a helmet, holding a guandao polearm, armored boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Thư sinh** · Slug `cn_codai_scholar_male` · `character/cn/codai/cn_codai_scholar_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a young Chinese scholar, slim build, hair in a neat topknot with a headband, gentle scholarly face, wearing a blue changshan robe, holding a rolled scroll, cloth shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 🇯🇵 NHẬT — samurai / anime / cổ đại

**Samurai** · Slug `jp_samurai_male` · `character/jp/codai/jp_samurai_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Japanese samurai, strong build, hair in a topknot, stern honorable face, wearing traditional o-yoroi lamellar armor, a katana at the side, armored sandals. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Ronin** · Slug `jp_ronin_male` · `character/jp/codai/jp_ronin_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a wandering ronin, lean rugged build, loose messy hair, weary sharp eyes, wearing a worn grey kimono and hakama, a straw hat on the back, a katana at the hip, straw sandals. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Geisha** · Slug `jp_geisha_female` · `character/jp/codai/jp_geisha_female.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a geisha, graceful build, elaborate black hair with kanzashi ornaments, white face makeup with red lips, wearing an elaborate silk kimono with a wide obi, holding a folding fan, geta sandals. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Anh hùng anime (nam)** · Slug `jp_anime_hero_male` · `character/jp/fantasy/jp_anime_hero_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a young anime male hero, athletic build, spiky dark hair, bright determined eyes, confident smile, wearing a fitted jacket over a shirt, cargo pants, sturdy boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 🇰🇷 HÀN — cổ trang (hanbok)

**Quý bà hanbok** · Slug `ko_hanbok_noblewoman_female` · `character/ko/codai/ko_hanbok_noblewoman_female.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Korean noblewoman, elegant build, hair in a refined updo with a binyeo pin, graceful gentle face, wearing an ornate hanbok (short jeogori jacket and full chima skirt) in soft colors, embroidered shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Học giả seonbi** · Slug `ko_seonbi_scholar_male` · `character/ko/codai/ko_seonbi_scholar_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Korean seonbi scholar, calm build, dignified face, wearing a white hanbok robe (dopo) and a black gat horsehair hat, cloth shoes, hands clasped. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Vua** · Slug `ko_king_male` · `character/ko/codai/ko_king_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Korean king, majestic build, groomed beard, authoritative face, wearing a royal red gonryongpo dragon robe and an ornate crown (ikseongwan), embroidered boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 🇻🇳 VIỆT — cổ trang / kiếm hiệp Việt

**Thiếu nữ áo dài** · Slug `vi_aodai_lady_female` · `character/vi/codai/vi_aodai_lady_female.png`
`Premium cinematic realistic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Vietnamese young woman, slender graceful build, long straight black hair, gentle warm eyes, soft smile, wearing a traditional white áo dài with silk trousers, holding a nón lá conical hat, delicate sandals. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Thầy đồ** · Slug `vi_codai_scholar_male` · `character/vi/codai/vi_codai_scholar_male.png`
`Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Vietnamese old scholar (thầy đồ), calm build, thin grey beard, wise gentle face, wearing a black áo the long robe and a khăn đóng turban, holding a writing brush, cloth shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Kiếm khách** · Slug `vi_kiemkhach_male` · `character/vi/wuxia/vi_kiemkhach_male.png`
`Premium cinematic ink-wash illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Vietnamese swordsman, lean build, hair tied back, resolute face, wearing a traditional dark robe with a sash, holding a straight sword, cloth boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 🇪🇺 CHÂU ÂU — fantasy / trung cổ / kinh dị

**Hiệp sĩ** · Slug `eu_knight_male` · `character/eu/fantasy/eu_knight_male.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a medieval knight, strong build, short hair, resolute face, wearing full polished plate armor, a sword sheathed at the hip and a heater shield, armored sabatons. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Pháp sư** · Slug `eu_mage_male` · `character/eu/fantasy/eu_mage_male.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a wizard mage, tall thin build, long grey beard, wise mysterious eyes, wearing a deep-blue robe with arcane runes and a pointed hood, holding a wooden staff topped with a glowing crystal, leather boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Công chúa** · Slug `eu_princess_female` · `character/eu/fantasy/eu_princess_female.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a medieval princess, elegant build, long flowing hair, a small tiara, gentle regal face, wearing an ornate ball gown with fine embroidery, delicate slippers. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Ma cà rồng** · Slug `eu_vampire_male` · `character/eu/horror/eu_vampire_male.png`
`Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an aristocratic vampire, tall slender build, slicked-back dark hair, pale skin, piercing red eyes, a sinister charming smile, wearing an elegant Victorian tailcoat with a high collar and cape, polished boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Phù thuỷ** · Slug `eu_witch_female` · `character/eu/horror/eu_witch_female.png`
`Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a witch, slender build, long dark hair, glowing eyes, an eerie expression, wearing a tattered black robe and a wide pointed hat, holding a gnarled staff, worn boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 🇺🇸 MỸ — hiện đại / miền tây / kinh dị

**Cao bồi** · Slug `us_cowboy_male` · `character/us/codai/us_cowboy_male.png`
`Premium western cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an American cowboy, rugged build, stubble, squinting eyes, wearing a wide-brim hat, a leather vest over a shirt, a bandana, jeans, a revolver in a holster, leather boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Thám tử noir** · Slug `us_detective_male` · `character/us/hiendai/us_detective_male.png`
`Premium 1940s noir cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a noir detective, average build, tired serious face, wearing a beige trench coat, a fedora, a shirt and tie, dark trousers, leather shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Nữ hồn ma** · Slug `us_ghost_female` · `character/us/horror/us_ghost_female.png`
`Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a ghostly woman, slender build, long pale hair, hollow sorrowful eyes, translucent skin, wearing a tattered flowing white dress, bare feet, faint drifting mist around her. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 🐉 QUÁI VẬT (genre horror/fantasy) — dùng chung template, đổi loài

**Rồng Trung Hoa** · Slug `cn_dragon` · `character/cn/fantasy/cn_dragon.png`
`Premium cinematic ink-wash fantasy illustration, consistent clean creature-design style, of a majestic Chinese dragon, long serpentine body, golden scales, whiskers, a flowing mane, sharp claws. Single subject only, full body from head to tail-tip, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate, malformed anatomy.`

**Quỷ Oni (JP)** · Slug `jp_oni` · `character/jp/fantasy/jp_oni.png`
`Premium dark fantasy illustration, consistent clean creature-design style, of an oni demon, muscular red-skinned body, horns, fangs, a loincloth, holding an iron kanabo club, a fierce roaring face. Single subject only, full body from the top of the horns to the soles of the feet, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate, extra limbs, malformed anatomy.`

**Rồng châu Âu** · Slug `eu_dragon` · `character/eu/fantasy/eu_dragon.png`
`Premium epic fantasy illustration, consistent clean creature-design style, of a European dragon, massive scaled body, spread leathery wings, a horned head, sharp claws, a fierce expression. Single subject only, full body, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate, malformed anatomy.`

---

## ➕ MỞ RỘNG — JP hiện đại (nghề nghiệp · gia đình · giới trẻ)

**Ayumi — nữ, 48, nữ giám đốc cấp cao, quyết đoán** · `jp_hiendai_ayumi_senior_exec_female` · `character/jp/hiendai/jp_hiendai_ayumi_senior_exec_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 48-year-old Japanese senior female executive, poised build, shoulder-length black hair with subtle grey, sharp confident eyes, composed expression, wearing a tailored dark blazer and pencil skirt, a silk blouse, minimal jewelry, elegant heels. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Sora — nam, 26, nhạc sĩ đường phố, phóng khoáng** · `jp_hiendai_sora_musician_male` · `character/jp/hiendai/jp_hiendai_sora_musician_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 26-year-old Japanese street musician, slim build, messy dyed-ash hair, easygoing warm eyes, relaxed smile, wearing a loose graphic tee, an open flannel shirt, ripped jeans, sneakers, an acoustic guitar strapped on the back. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Naoko — nữ, 34, mẹ đơn thân, kiên cường** · `jp_hiendai_naoko_single_mother_female` · `character/jp/hiendai/jp_hiendai_naoko_single_mother_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 34-year-old Japanese single mother, gentle tired build, hair in a practical low ponytail, kind but weary eyes, a soft resilient smile, wearing a simple cardigan over a blouse, comfortable slacks, flat shoes, a shoulder bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Daichi — nam, 30, đầu bếp, tận tụy** · `jp_hiendai_daichi_chef_male` · `character/jp/hiendai/jp_hiendai_daichi_chef_male.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 30-year-old Japanese chef, fit build, short cropped hair, a headband, focused proud expression, wearing a white double-breasted chef's jacket, an apron, checkered trousers, kitchen clogs. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Riku — nam, 6, bé trai mẫu giáo, tinh nghịch** · `jp_hiendai_riku_toddler_boy` · `character/jp/hiendai/jp_hiendai_riku_toddler_boy.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, small child proportions, consistent clean character-design style, of a 6-year-old Japanese boy, tiny build, short messy black hair, big playful eyes, a mischievous grin, wearing a striped t-shirt, denim overalls, light-up sneakers, a small backpack. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Miku — nữ, 19, gyaru cá tính** · `jp_hiendai_miku_gyaru_female` · `character/jp/hiendai/jp_hiendai_miku_gyaru_female.png`
`Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 19-year-old Japanese gyaru girl, slim build, long dyed-blonde wavy hair, bold makeup, confident playful expression, wearing a trendy crop top, a pleated mini skirt, a cardigan, platform boots, chunky accessories. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## ➕ MỞ RỘNG — Hàn hiện đại (K-drama)

**Ji-woo — nam, 29, thái tử tập đoàn (bá đạo), lạnh lùng** · `ko_hiendai_jiwoo_chaebol_heir_male` · `character/ko/hiendai/ko_hiendai_jiwoo_chaebol_heir_male.png`
`Premium Korean drama cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 29-year-old Korean chaebol heir, tall slim build, styled dark hair, sharp cold handsome features, an aloof confident expression, wearing an immaculate charcoal designer suit, a luxury watch, polished dress shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Ha-eun — nữ, 25, nữ chính hiền lành, dịu dàng** · `ko_hiendai_haeun_lead_female` · `character/ko/hiendai/ko_hiendai_haeun_lead_female.png`
`Premium Korean drama cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 25-year-old Korean woman, slender build, long soft brown hair, warm gentle eyes, a bright sincere smile, wearing a pastel knit sweater, a pleated skirt, a light coat, ankle boots, a small crossbody bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Sun-ok — nữ, 58, bà thím (ajumma), tháo vát** · `ko_hiendai_sunok_ajumma_female` · `character/ko/hiendai/ko_hiendai_sunok_ajumma_female.png`
`Premium Korean drama cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 58-year-old Korean ajumma, sturdy build, tightly permed short hair, lively expressive face, wearing a colorful patterned blouse, comfortable slacks, a light vest, practical shoes, carrying a market bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## ➕ MỞ RỘNG — Trung hiện đại (đô thị / tổng tài)

**Gu Yan — nam, 32, tổng tài bá đạo, quyền lực** · `cn_hiendai_guyan_ceo_male` · `character/cn/hiendai/cn_hiendai_guyan_ceo_male.png`
`Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 32-year-old Chinese domineering CEO, tall commanding build, neatly styled black hair, sharp intense eyes, a cool authoritative expression, wearing a sleek black tailored suit, a crisp white shirt, a luxury watch, polished shoes. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Xia Tian — nữ, 24, nữ chính ngôn tình, trong sáng** · `cn_ngontinh_xiatian_lead_female` · `character/cn/ngontinh/cn_ngontinh_xiatian_lead_female.png`
`Premium soft romantic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 24-year-old Chinese woman, slender delicate build, long silky black hair, large gentle bright eyes, a sweet innocent smile, wearing a floral summer dress, a light cardigan, flat sandals, a small handbag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## ➕ MỞ RỘNG — Việt (hiện đại + bổ sung)

**Lan — nữ, 27, nhân viên văn phòng, dịu dàng** · `vi_hiendai_lan_office_female` · `character/vi/hiendai/vi_hiendai_lan_office_female.png`
`Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 27-year-old Vietnamese office woman, slim build, long straight black hair, gentle warm eyes, a soft smile, wearing a modern white blouse and dark slacks, a blazer, low heels, a slim shoulder bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Bà Tư — nữ, 65, bà lão quê, hiền hậu** · `vi_hiendai_batu_grandmother_female` · `character/vi/hiendai/vi_hiendai_batu_grandmother_female.png`
`Premium cinematic realistic illustration, semi-realistic facial anatomy, elderly proportions, consistent clean character-design style, of a 65-year-old Vietnamese rural grandmother, small gentle build, grey hair in a bun, kind wrinkled face, a warm smile, wearing a brown áo bà ba, loose trousers, a checkered scarf, simple sandals, holding a betel-nut tray. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## ➕ MỞ RỘNG — Nhóm phiêu lưu fantasy (EU)

**Cung thủ tiên tộc (nữ)** · `eu_elf_archer_female` · `character/eu/fantasy/eu_elf_archer_female.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a female elf archer, slender agile build, long silver hair, pointed ears, keen calm eyes, wearing light green leather armor, a hooded cloak, holding a longbow with a quiver on the back, soft boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Chiến binh lùn (nam)** · `eu_dwarf_warrior_male` · `character/eu/fantasy/eu_dwarf_warrior_male.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, dwarf proportions, consistent clean character-design style, of a dwarf warrior, short stocky powerful build, a thick braided red beard, fierce proud eyes, wearing heavy chainmail and plate, holding a large battle-axe, sturdy iron boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Barbarian (nam)** · `eu_barbarian_male` · `character/eu/fantasy/eu_barbarian_male.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a barbarian warrior, huge muscular build, long wild hair, war paint, a fierce expression, wearing fur-and-leather armor, holding a massive two-handed sword, fur boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Tu sĩ chữa thương (nữ)** · `eu_cleric_female` · `character/eu/fantasy/eu_cleric_female.png`
`Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a female cleric, gentle build, hair tucked under a hood, serene compassionate eyes, wearing white-and-gold robes with a holy emblem, holding a glowing staff, modest shoes, a soft radiant aura. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## ➕ MỞ RỘNG — Mỹ hiện đại (bổ sung)

**Lính cứu hoả (nam)** · `us_hiendai_firefighter_male` · `character/us/hiendai/us_hiendai_firefighter_male.png`
`Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an American firefighter, strong build, short hair, determined brave face, wearing full turnout gear (bunker jacket and trousers with reflective stripes), a helmet under one arm, heavy boots. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

**Nữ doanh nhân (nữ)** · `us_hiendai_businesswoman_female` · `character/us/hiendai/us_hiendai_businesswoman_female.png`
`Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 35-year-old American businesswoman, confident build, sleek shoulder-length hair, poised assertive expression, wearing a sharp tailored pantsuit, a blouse, minimal jewelry, heels, holding a slim laptop bag. Single character only, standing naturally, front-facing neutral reference pose, entire body from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands.`

---

## 📚 BỘ CHI TIẾT MỞ RỘNG — dàn đều 6 vùng (prompt giàu + thuộc tính khoá)

> Add-only (không sửa entry cũ ở trên). Mỗi nhân vật gồm: **ô prompt mô tả giàu** +
> dòng **🔑 thuộc tính khoá** (giữ cố định khi sinh lại để nhất quán) + **⛔ neg riêng** +
> **seed** gợi ý. **Cách dùng:** prompt hoàn chỉnh = *nội dung trong ô* **+ TAIL** bên dưới
> (dán ô, thêm TAIL). Giữ NGUYÊN prompt + seed → sinh lại gần như giống → chọn 1 bản khoá.

**TAIL (nhân vật — dán vào cuối MỌI prompt bên dưới):**
```
Single character only, standing naturally, front-facing neutral reference pose, entire body visible from the top of the hair to the soles of the shoes, centered with generous transparent padding. Transparent background with clean alpha edges, no environment, no floor, no ground shadow, even studio lighting. No text, logo, watermark, border, frame, duplicate character.
```
**NEG chung (thêm cùng ⛔ neg riêng):** `text, watermark, logo, multiple people, cropped feet, cropped hair, extra fingers, extra limbs, malformed hands, blurry, background scenery`

**{STYLE} theo genre:** wuxia→`cinematic ink-wash wuxia/xianxia illustration` · ngontinh→`soft romantic anime illustration` · horror→`dark eerie cinematic illustration` · fantasy→`epic fantasy concept illustration` · codai→`historical realistic painting` · hiendai→`modern cinematic illustration` (JP hiện đại→`Japanese cinematic anime illustration`).

---

### 🇨🇳 TRUNG — mở rộng

**Lăng Sương — nữ chưởng môn phái, uy nghiêm** · `cn_wuxia_sect_leader_female` · `character/cn/wuxia/cn_wuxia_sect_leader_female.png`
```
Premium cinematic ink-wash wuxia/xianxia illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a female wuxia sect leader in her late 30s, tall commanding graceful build, long jet-black hair in a high coiled bun held by a silver phoenix hairpin, sharp calm almond eyes, pale flawless skin, an aura of quiet authority, wearing layered white-and-violet silk robes with wide sleeves and silver cloud embroidery, a jade pendant sash, a slim longsword strapped to the back, embroidered white boots.
```
🔑 tóc: đen dài búi cao + trâm phượng bạc | mắt: hạnh, sắc lạnh | da: trắng | dáng: cao, uy nghi | trang phục: lụa trắng-tím, thêu mây bạc | phụ kiện: ngọc bội, trường kiếm sau lưng | giày: hài trắng thêu | seed: 21001
⛔ neg: `modern clothing, revealing outfit, cartoon chibi`

**Diệp Vân — đệ tử tiên môn trẻ, nhiệt huyết** · `cn_xianxia_disciple_male_young` · `character/cn/wuxia/cn_xianxia_disciple_male_young.png`
```
Premium cinematic ink-wash wuxia/xianxia illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a young male xianxia cultivator around 18, slim agile build, black hair half-up in a topknot with a blue ribbon, bright hopeful dark eyes, clear youthful face, wearing a light blue-and-white disciple robe with a cloth belt, a wooden sword talisman at the waist, a faint spiritual glow around the hands, cloth boots.
```
🔑 tóc: đen nửa búi + ruy băng xanh | mắt: sáng, nhiệt huyết | dáng: mảnh, nhanh nhẹn | trang phục: đạo bào xanh-trắng | phụ kiện: kiếm gỗ bùa chú, quầng linh khí tay | giày: hài vải | seed: 21002
⛔ neg: `old face, armor, modern clothing`

**Mộ Dung Tuấn — nam phụ ngôn tình, si tình lạnh lùng** · `cn_ngontinh_second_male_lead` · `character/cn/ngontinh/cn_ngontinh_second_male_lead.png`
```
Premium soft romantic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 27-year-old Chinese man, tall elegant slender build, soft dark-brown side-swept hair, gentle melancholic hazel eyes, fair skin, a refined wistful expression, wearing a cream turtleneck under a beige tailored coat, a thin silver watch, slim trousers, polished loafers, holding a single white flower.
```
🔑 tóc: nâu sẫm vuốt lệch | mắt: nâu hạt dẻ, buồn dịu | da: trắng | dáng: cao, thanh thoát | trang phục: áo len kem + măng tô be | phụ kiện: đồng hồ bạc, hoa trắng | giày: giày lười | seed: 21003
⛔ neg: `historical robe, aggressive expression`

**Cương thi — quỷ nhảy cổ trang, rùng rợn** · `cn_horror_jiangshi` · `character/cn/horror/cn_horror_jiangshi.png`
```
Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean creature-design style, of a Chinese hopping vampire (jiangshi), stiff upright posture with arms outstretched forward, greyish-green decayed skin, long black nails, a Qing-dynasty official's dark robe and round hat, a yellow paper talisman stuck to the forehead, hollow pale eyes, an eerie cold aura.
```
🔑 da: xám-xanh mục | tư thế: cứng đờ, hai tay đưa trước | trang phục: quan phục nhà Thanh đen + mũ tròn | phụ kiện: bùa giấy vàng trên trán, móng dài | mắt: trắng đục rỗng | seed: 21004
⛔ neg: `friendly expression, bright colors, modern clothing`

**Thái hậu — mẫu nghi thiên hạ, thâm sâu** · `cn_codai_empress_dowager_female` · `character/cn/codai/cn_codai_empress_dowager_female.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Chinese empress dowager in her 50s, dignified upright build, elaborate coiled black-grey hair crowned with an ornate gold-and-jade headdress, sharp discerning eyes, powdered fair face, a composed powerful expression, wearing a magnificent imperial dragon-phoenix robe in deep red and gold with long embroidered sleeves, gold nail guards, embroidered court shoes.
```
🔑 tóc: đen-xám búi cầu kỳ + mũ vàng-ngọc | mắt: sắc, thâm | dáng: uy nghi | trang phục: long-phượng bào đỏ-vàng | phụ kiện: hộ giáp vàng | giày: hài cung đình | seed: 21005
⛔ neg: `young face, modern clothing, casual pose`

**Tô Nhiên — nữ tổng tài đô thị, tsundere** · `cn_hiendai_ceo_female_tsundere` · `character/cn/hiendai/cn_hiendai_ceo_female_tsundere.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 29-year-old Chinese businesswoman, slim poised build, sleek shoulder-length black hair, sharp confident dark eyes with a faint proud tilt, fair skin, an assertive expression softening at the edges, wearing a fitted burgundy blazer over a white silk blouse, a slim pencil skirt, a designer watch, elegant black heels, holding a slim phone.
```
🔑 tóc: đen ngang vai bóng | mắt: sắc, kiêu | da: trắng | dáng: mảnh, đĩnh đạc | trang phục: blazer đỏ mận + sơ mi trắng | phụ kiện: đồng hồ hiệu, điện thoại | giày: cao gót đen | seed: 21006
⛔ neg: `historical robe, timid posture`

---

### 🇯🇵 NHẬT — mở rộng (lấp thể loại còn thiếu)

**Sakura — nữ chính shoujo, mơ mộng** · `jp_ngontinh_shoujo_lead_female` · `character/jp/ngontinh/jp_ngontinh_shoujo_lead_female.png`
```
Premium soft romantic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 17-year-old Japanese schoolgirl, slim gentle build, long soft pink-tinted brown hair with a small ribbon, large sparkling honey eyes, fair rosy skin, a shy dreamy smile, wearing a pastel sailor school uniform with a pink bow, a beige cardigan, knee socks, brown loafers, holding a love letter to her chest.
```
🔑 tóc: nâu ánh hồng dài + ruy băng | mắt: mật ong to, long lanh | da: trắng hồng | trang phục: đồng phục sailor pastel + nơ hồng | phụ kiện: áo len be, thư tình | giày: giày lười nâu | seed: 22001
⛔ neg: `mature adult, dark palette, armor`

**Yurei — hồn ma nữ Nhật, ám ảnh** · `jp_horror_yurei_female` · `character/jp/horror/jp_horror_yurei_female.png`
```
Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Japanese yurei ghost woman, slender ethereal build, extremely long straight black hair hanging over the face, deathly pale translucent skin, hollow sorrowful dark eyes, wearing a plain white burial kimono (shiroshozoku), no visible feet fading into faint mist, a cold haunting presence.
```
🔑 tóc: đen dài phủ mặt | da: trắng tái, mờ | mắt: đen rỗng, u sầu | trang phục: kimono trắng tang | đặc điểm: chân mờ vào sương | seed: 22002
⛔ neg: `bright colors, happy face, shoes, modern clothing`

**Kage — ninja, lặng lẽ chết chóc** · `jp_ninja_male` · `character/jp/codai/jp_ninja_male.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Japanese shinobi ninja, lean muscular agile build, hidden hair under a black hood, sharp focused dark eyes visible above a face mask, wearing a fitted matte-black shinobi shozoku with wrapped forearms and shins, a short ninjato sword on the back, kunai and shuriken pouches at the belt, split-toe tabi boots.
```
🔑 dáng: gọn, cơ bắp, nhanh | mắt: đen sắc trên khăn che mặt | trang phục: shinobi shozoku đen mờ, quấn tay-chân | phụ kiện: ninjato sau lưng, túi kunai/shuriken | giày: tabi xẻ ngón | seed: 22003
⛔ neg: `bright armor, exposed face, modern clothing`

**Ryūzō — ông trùm yakuza, uy quyền** · `jp_hiendai_yakuza_boss_male` · `character/jp/hiendai/jp_hiendai_yakuza_boss_male.png`
```
Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 50-year-old Japanese yakuza boss, broad imposing build, slicked-back greying black hair, hard scarred face with a stern gaze, wearing an expensive dark pinstripe suit open at the chest revealing partial traditional irezumi tattoos, a silk shirt, gold rings, polished black shoes, one hand in his pocket.
```
🔑 tóc: đen-hoa râm vuốt ngược | mặt: sẹo, lạnh | dáng: bệ vệ | trang phục: suit sọc đen, hé lộ hình xăm irezumi | phụ kiện: nhẫn vàng | giày: da đen bóng | seed: 22004
⛔ neg: `friendly smile, casual clothing, teen`

**Hina — thần tượng nhạc pop, rạng rỡ** · `jp_hiendai_idol_female` · `character/jp/hiendai/jp_hiendai_idol_female.png`
```
Premium Japanese cinematic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 19-year-old Japanese pop idol, slim energetic build, twin-tail bright teal hair with star clips, big shining eyes, fair skin, a dazzling stage smile, wearing a frilly pastel idol stage costume with layered skirt, ribbons and a small cape, thigh-high socks, glittery ankle boots, holding a heart-shaped microphone.
```
🔑 tóc: teal buộc hai bên + kẹp sao | mắt: to, long lanh | trang phục: idol pastel bèo nhún + áo choàng nhỏ | phụ kiện: mic hình tim, tất cao | giày: bốt lấp lánh | seed: 22005
⛔ neg: `dull colors, business suit, mature adult`

**Kotone — pháp sư nữ isekai, điềm tĩnh** · `jp_fantasy_mage_female` · `character/jp/fantasy/jp_fantasy_mage_female.png`
```
Premium epic fantasy concept illustration with anime influence, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a young female mage, slender build, long silver-lavender hair, calm violet eyes, fair skin, a composed intelligent expression, wearing a deep-blue-and-gold mage robe with a short cape and rune trims, a wide-brim witch hat, holding an ornate staff topped with a glowing crystal, knee-high boots, a faint magic circle at her feet.
```
🔑 tóc: bạc-tím dài | mắt: tím, điềm tĩnh | trang phục: pháp bào xanh-vàng + choàng ngắn, viền rune | phụ kiện: mũ rộng vành, trượng pha lê phát sáng | giày: bốt cao | seed: 22006
⛔ neg: `modern clothing, dull staff, elderly`

---

### 🇰🇷 HÀN — mở rộng

**Yeon-hwa — kỹ nữ gisaeng, đài các** · `ko_codai_gisaeng_female` · `character/ko/codai/ko_codai_gisaeng_female.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Joseon-era Korean gisaeng, graceful slender build, glossy black hair in an elaborate braided updo with a norigae ornament, delicate powdered face with soft red lips, refined melancholic eyes, wearing a luxurious silk hanbok with a short jade-green jeogori and a wide crimson chima skirt, a folding fan in hand, embroidered silk shoes.
```
🔑 tóc: đen búi tết cầu kỳ + norigae | mặt: phấn nhẹ, môi đỏ | mắt: sâu, u buồn | trang phục: hanbok lụa jeogori xanh ngọc + chima đỏ | phụ kiện: quạt xếp | giày: hài lụa thêu | seed: 23001
⛔ neg: `modern clothing, casual pose`

**Mu-yeol — tướng quân Joseon, dũng mãnh** · `ko_codai_general_male` · `character/ko/codai/ko_codai_general_male.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Joseon-era Korean general, powerful broad build, topknot under a black-and-red war helmet, a stern bearded weathered face, wearing heavy traditional Korean lamellar armor (durumagi over plates) in dark red and iron, a commander's sash, holding a curved sword, armored boots.
```
🔑 tóc: búi dưới mũ chiến đỏ-đen | mặt: râu, khắc khổ | dáng: to, mạnh | trang phục: giáp lamellar đỏ-sắt | phụ kiện: đai chỉ huy, đao cong | giày: giày giáp | seed: 23002
⛔ neg: `modern clothing, thin build, timid`

**Gwishin — nữ quỷ tóc dài, rùng rợn** · `ko_horror_gwishin_female` · `character/ko/horror/ko_horror_gwishin_female.png`
```
Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Korean gwishin ghost, thin frail build, extremely long tangled black hair covering most of a pale bluish face, hollow dark eyes and faint dark tear streaks, wearing a plain white mourning hanbok (sobok), bare pale feet, a cold sorrowful haunting aura, faint mist below.
```
🔑 tóc: đen rối phủ mặt | da: xanh tái | mắt: đen rỗng, vệt lệ | trang phục: hanbok tang trắng | đặc điểm: chân trần, sương mờ | seed: 23003
⛔ neg: `bright colors, happy face, modern clothing`

**Tae-yang — thần tượng K-pop nam, cuốn hút** · `ko_hiendai_kpop_idol_male` · `character/ko/hiendai/ko_hiendai_kpop_idol_male.png`
```
Premium Korean drama cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 22-year-old Korean male K-pop idol, slim toned build, styled two-tone (black-and-silver) hair, sharp charismatic eyes, flawless fair skin, a confident cool expression, wearing a trendy stage outfit — a cropped studded leather jacket over a mesh top, ripped black jeans, a chain belt, layered necklaces, high-top sneakers, in-ear monitor.
```
🔑 tóc: đen-bạc tạo kiểu | mắt: sắc, hút hồn | da: trắng mịn | trang phục: jacket da đinh tán + áo lưới | phụ kiện: dây chuyền lớp, thắt lưng xích | giày: sneaker cổ cao | seed: 23004
⛔ neg: `business suit, historical robe, dull colors`

**So-ra — nữ thám tử hiện đại, sắc sảo** · `ko_hiendai_detective_female` · `character/ko/hiendai/ko_hiendai_detective_female.png`
```
Premium Korean drama cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 32-year-old Korean female detective, athletic build, dark hair in a practical low ponytail, sharp observant eyes, fair skin, a serious focused expression, wearing a fitted charcoal trench coat over a dark shirt, slim trousers, a badge on the belt, a holstered pistol, ankle boots.
```
🔑 tóc: đen buộc thấp | mắt: sắc, quan sát | dáng: khỏe | trang phục: trench than + áo tối | phụ kiện: phù hiệu, bao súng | giày: bốt cổ ngắn | seed: 23005
⛔ neg: `frilly dress, historical robe, timid`

**Ha-rin — nữ phụ ngôn tình, kiêu kỳ** · `ko_ngontinh_second_female_lead` · `character/ko/ngontinh/ko_ngontinh_second_female_lead.png`
```
Premium soft romantic anime illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 25-year-old Korean woman, elegant slim build, long wavy chestnut hair, striking confident eyes with a proud tilt, fair skin, a cool refined expression, wearing a designer cream coat over a silk blouse, a pleated skirt, a luxury handbag, pearl earrings, elegant heels.
```
🔑 tóc: hạt dẻ dài xoăn nhẹ | mắt: sắc, kiêu | da: trắng | trang phục: măng tô kem + sơ mi lụa | phụ kiện: túi hiệu, khuyên ngọc trai | giày: cao gót | seed: 23006
⛔ neg: `casual sloppy, historical robe`

---

### 🇻🇳 VIỆT — mở rộng

**Vua Lê — quân vương cổ trang, uy nghi** · `vi_codai_king_male` · `character/vi/codai/vi_codai_king_male.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Vietnamese king, dignified upright build, a groomed short beard, authoritative calm eyes, wearing a royal yellow áo long bào with dragon embroidery and a wide belt, a Vietnamese royal crown (mũ bình thiên) with beaded curtains, embroidered court boots, holding a jade tablet.
```
🔑 mặt: râu ngắn, uy nghi | trang phục: long bào vàng thêu rồng | phụ kiện: mũ bình thiên rèm châu, hốt ngọc | giày: hia thêu | seed: 24001
⛔ neg: `modern clothing, Chinese-style robe, young beardless`

**Công chúa Ngọc — cổ trang Việt, đoan trang** · `vi_codai_princess_female` · `character/vi/codai/vi_codai_princess_female.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Vietnamese princess, elegant slender build, long black hair in a refined coil with gold hairpins, a gentle graceful face, wearing a layered Nhật Bình royal robe in deep red and gold with phoenix embroidery and a wide decorative collar, delicate embroidered shoes.
```
🔑 tóc: đen búi + trâm vàng | mặt: đoan trang | trang phục: áo Nhật Bình đỏ-vàng thêu phượng, cổ trang trí rộng | giày: hài thêu | seed: 24002
⛔ neg: `modern clothing, Chinese hanfu, casual`

**Tướng Trần — võ tướng Việt, quả cảm** · `vi_codai_general_male` · `character/vi/codai/vi_codai_general_male.png`
```
Premium historical realistic painting, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an ancient Vietnamese military general, strong sturdy build, a fierce bearded face, wearing traditional Vietnamese lamellar armor in dark bronze and red with a war cloak, a conical-crest helmet, holding a long spear, armored boots.
```
🔑 mặt: râu, quả cảm | dáng: to khỏe | trang phục: giáp lamellar đồng-đỏ + choàng | phụ kiện: mũ trụ, trường thương | giày: giày giáp | seed: 24003
⛔ neg: `modern clothing, Chinese armor, thin build`

**Ma nữ áo trắng — kinh dị Việt, ám ảnh** · `vi_horror_maiden_ghost_female` · `character/vi/horror/vi_horror_maiden_ghost_female.png`
```
Premium dark eerie cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Vietnamese female ghost, slender frail build, very long straight black hair partly hiding a pale bloodless face, hollow dark sorrowful eyes, wearing a plain long white áo dài, bare pale feet, drifting faint mist, a cold mournful haunting presence.
```
🔑 tóc: đen dài che mặt | da: trắng tái | mắt: đen rỗng, u sầu | trang phục: áo dài trắng dài | đặc điểm: chân trần, sương | seed: 24004
⛔ neg: `bright colors, happy face, shoes, modern casual`

**Minh — doanh nhân trẻ Việt, tự tin** · `vi_hiendai_businessman_male` · `character/vi/hiendai/vi_hiendai_businessman_male.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 30-year-old Vietnamese businessman, fit trim build, neat short black hair, confident friendly eyes, warm tan skin, an approachable assured expression, wearing a well-fitted navy suit, a light-blue shirt with no tie, a slim watch, brown leather shoes, holding a smartphone.
```
🔑 tóc: đen ngắn gọn | mắt: tự tin, thân thiện | da: rám nhẹ | trang phục: suit xanh navy + sơ mi xanh nhạt | phụ kiện: đồng hồ mảnh, điện thoại | giày: da nâu | seed: 24005
⛔ neg: `historical robe, sloppy clothing, elderly`

**Hương — nữ sinh viên Việt, năng động** · `vi_hiendai_student_female` · `character/vi/hiendai/vi_hiendai_student_female.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 20-year-old Vietnamese university student, slim build, long straight black hair, bright cheerful eyes, warm skin, a friendly relaxed smile, wearing a casual white tee under an oversized pastel cardigan, high-waist jeans, white sneakers, a canvas tote bag on one shoulder.
```
🔑 tóc: đen thẳng dài | mắt: sáng, vui | da: ấm | trang phục: áo phông trắng + cardigan pastel rộng | phụ kiện: túi tote vải | giày: sneaker trắng | seed: 24006
⛔ neg: `historical robe, formal suit, mature adult`

---

### 🇪🇺 CHÂU ÂU — mở rộng

**Công tước Ashford — romance nhiếp chính, lịch lãm** · `eu_romance_duke_male` · `character/eu/ngontinh/eu_romance_duke_male.png`
```
Premium soft romantic cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a Regency-era English duke around 30, tall elegant build, wavy dark-brown hair, piercing blue eyes, fair skin, a charming aloof expression, wearing a tailored deep-green tailcoat over an ivory cravat and waistcoat, fitted breeches, tall polished riding boots, a signet ring.
```
🔑 tóc: nâu sẫm gợn sóng | mắt: xanh dương, hút hồn | da: trắng | trang phục: tailcoat xanh lục + cravat ngà | phụ kiện: nhẫn ấn | giày: bốt cưỡi ngựa | seed: 25001
⛔ neg: `modern clothing, armor, casual`

**Roland — đạo tặc/thích khách, tinh ranh** · `eu_fantasy_rogue_thief_male` · `character/eu/fantasy/eu_fantasy_rogue_thief_male.png`
```
Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a fantasy rogue thief, lean agile build, messy dark hair, a sly grin, sharp green eyes, light stubble, wearing a hooded dark-leather jerkin with many straps and pouches, fingerless gloves, twin daggers at the belt, a cloak, worn leather boots.
```
🔑 tóc: đen rối | mắt: xanh lá sắc | biểu cảm: cười gian | trang phục: da tối có mũ trùm + nhiều túi/dây | phụ kiện: găng hở ngón, song đao | giày: bốt da cũ | seed: 25002
⛔ neg: `heavy plate armor, modern clothing, clean noble`

**Ser Godfrey — thánh kỵ paladin, chính trực** · `eu_fantasy_paladin_male` · `character/eu/fantasy/eu_fantasy_paladin_male.png`
```
Premium epic fantasy concept illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a holy paladin, tall strong build, short golden hair, a noble resolute face, wearing gleaming silver plate armor with gold trim and a white tabard bearing a sun emblem, a long cape, a large sword and a kite shield, a faint holy glow around the armor, armored boots.
```
🔑 tóc: vàng ngắn | mặt: chính trực | trang phục: giáp bạc viền vàng + áo choàng trắng huy hiệu mặt trời | phụ kiện: đại kiếm, khiên, quầng thánh | giày: giày giáp | seed: 25003
⛔ neg: `dark evil aura, modern clothing, rusty armor`

**Grommash — chiến binh orc, hung tợn** · `eu_fantasy_orc_warrior_male` · `character/eu/fantasy/eu_fantasy_orc_warrior_male.png`
```
Premium epic fantasy concept illustration, semi-realistic anatomy, massive proportions, consistent clean creature-design style, of a hulking orc warrior, huge muscular green-skinned build, protruding lower tusks, a fierce scarred face, a black mohawk, wearing rugged spiked iron-and-leather armor over one shoulder, tribal war paint, holding a massive jagged axe, heavy boots.
```
🔑 da: xanh, cơ bắp | mặt: nanh dưới, sẹo, dữ | tóc: mohawk đen | trang phục: giáp sắt-da gai một vai | phụ kiện: rìu lớn, sơn chiến | giày: bốt nặng | seed: 25004
⛔ neg: `human skin, friendly face, modern clothing`

**Mortis — pháp sư hắc ám/necromancer, tà mị** · `eu_horror_necromancer_male` · `character/eu/horror/eu_horror_necromancer_male.png`
```
Premium dark eerie cinematic illustration, semi-realistic facial anatomy, gaunt proportions, consistent clean character-design style, of a sinister necromancer, tall thin build, long stringy black hair, sunken glowing green eyes, pale corpse-like skin, a cruel thin smile, wearing a tattered black robe with bone ornaments and a high ragged collar, skeletal hand jewelry, holding a staff crowned with a skull, a sickly green aura, worn boots.
```
🔑 tóc: đen bết dài | mắt: xanh lục phát sáng, hõm | da: trắng bệch | trang phục: hắc bào rách + xương trang trí | phụ kiện: trượng sọ, quầng lục bệnh hoạn | giày: bốt cũ | seed: 25005
⛔ neg: `bright holy aura, healthy skin, modern clothing`

**Ava — điệp viên hiện đại, lạnh lùng** · `eu_hiendai_spy_female` · `character/eu/hiendai/eu_hiendai_spy_female.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 30-year-old European female spy, athletic sleek build, sleek dark hair in a low bun, sharp cool grey eyes, fair skin, a composed dangerous expression, wearing a form-fitting black tactical catsuit under a slim leather jacket, a thin utility belt, a concealed holster, low combat boots.
```
🔑 tóc: đen búi thấp | mắt: xám lạnh | dáng: gọn, khỏe | trang phục: catsuit đen + jacket da | phụ kiện: đai công cụ, bao súng giấu | giày: combat boot thấp | seed: 25006
⛔ neg: `fantasy armor, historical clothing, timid`

---

### 🇺🇸 MỸ — mở rộng

**Cmdr. Hale — phi hành gia, can trường** · `us_hiendai_astronaut_male` · `character/us/hiendai/us_hiendai_astronaut_male.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an American astronaut, fit build, short cropped hair visible with helmet held under one arm, a calm brave face, wearing a detailed white EVA spacesuit with blue trim, mission patches, a chest control unit and tubes, thick gloves, heavy space boots.
```
🔑 tóc: cắt ngắn | mặt: điềm tĩnh, can trường | trang phục: bộ đồ EVA trắng viền xanh + patch | phụ kiện: mũ cầm dưới tay, bảng điều khiển ngực | giày: bốt không gian | seed: 26001
⛔ neg: `fantasy armor, historical clothing, casual`

**Sgt. Cole — lính đặc nhiệm, kiên cường** · `us_hiendai_soldier_male` · `character/us/hiendai/us_hiendai_soldier_male.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of an American special-forces soldier, strong build, short hair, a rugged determined face with light face paint, wearing modern multicam combat fatigues and a plate carrier vest with pouches, a helmet with a headset, tactical gloves, holding a rifle at low ready, combat boots.
```
🔑 tóc: ngắn | mặt: rắn rỏi, sơn ngụy trang nhẹ | trang phục: quân phục multicam + áo giáp plate carrier | phụ kiện: mũ tai nghe, súng trường, găng | giày: combat boot | seed: 26002
⛔ neg: `fantasy armor, historical clothing, clean suit`

**Zoe — hacker/tin tặc, tinh nghịch** · `us_hiendai_hacker_female` · `character/us/hiendai/us_hiendai_hacker_female.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 24-year-old American hacker, slim build, short dyed-purple undercut hair, sharp witty eyes behind thin glasses, fair skin with a few tattoos, a smug clever smirk, wearing an oversized graphic hoodie, ripped black jeans, fingerless gloves, chunky sneakers, headphones around the neck.
```
🔑 tóc: tím undercut | mắt: sắc, kính mỏng | da: trắng, vài hình xăm | trang phục: hoodie rộng in hình + jeans rách | phụ kiện: găng hở ngón, tai nghe | giày: sneaker to | seed: 26003
⛔ neg: `formal suit, historical clothing, timid`

**Sentinel — siêu anh hùng, hào hùng** · `us_fantasy_superhero_male` · `character/us/fantasy/us_fantasy_superhero_male.png`
```
Premium modern comic cinematic illustration, semi-realistic anatomy, heroic proportions, consistent clean character-design style, of an American superhero, tall powerful muscular build, short dark hair, a strong confident jaw, wearing a sleek navy-and-silver armored suit with a chest emblem, a flowing cape, gauntlets and boots with subtle glowing lines, a bold heroic stance.
```
🔑 tóc: đen ngắn | dáng: cơ bắp, anh hùng | trang phục: giáp xanh navy-bạc + huy hiệu ngực | phụ kiện: áo choàng, gauntlet phát sáng nhẹ | giày: bốt giáp | seed: 26004
⛔ neg: `historical clothing, casual clothing, dull suit`

**Vincent — trùm gangster 1920s, bảnh bao** · `us_codai_gangster_1920s_male` · `character/us/codai/us_codai_gangster_1920s_male.png`
```
Premium 1920s noir cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 1920s American gangster, lean sharp build, slicked-back dark hair, a cold confident face with a thin moustache, wearing a pinstripe double-breasted suit with a vest and pocket watch chain, a fedora, a silk tie, spats over polished shoes, holding a cigar.
```
🔑 tóc: đen vuốt ngược | mặt: ria mảnh, lạnh | trang phục: suit sọc 2 hàng khuy + gile | phụ kiện: mũ fedora, dây đồng hồ, xì gà | giày: giày bóng có spats | seed: 26005
⛔ neg: `modern clothing, fantasy armor, casual`

**Grace — y tá hiện đại, tận tâm** · `us_hiendai_nurse_female` · `character/us/hiendai/us_hiendai_nurse_female.png`
```
Premium modern cinematic illustration, semi-realistic facial anatomy, mature proportions, consistent clean character-design style, of a 29-year-old American nurse, gentle build, brown hair tied in a neat bun, kind warm eyes, an approachable caring smile, wearing clean teal scrubs, a lanyard ID, a small watch, a stethoscope around the neck, comfortable white sneakers.
```
🔑 tóc: nâu búi gọn | mắt: ấm, tận tâm | trang phục: scrubs xanh teal | phụ kiện: thẻ lanyard, ống nghe, đồng hồ | giày: sneaker trắng | seed: 26006
⛔ neg: `historical clothing, formal gown, stern face`

---

## ➕ Thêm nhân vật
Gửi: `Tên – giới tính, tuổi, vai trò, tính cách` (+ mô tả ngoại hình nếu có).
Tôi trả về **1 khối prompt tự chứa** đúng cấu trúc trên (tự thiết kế ngoại hình nếu bạn chỉ cho tên + vai trò).
