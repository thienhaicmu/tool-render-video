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

## ➕ Thêm nhân vật
Gửi: `Tên – giới tính, tuổi, vai trò, tính cách` (+ mô tả ngoại hình nếu có).
Tôi trả về **1 khối prompt tự chứa** đúng cấu trúc trên (tự thiết kế ngoại hình nếu bạn chỉ cho tên + vai trò).
