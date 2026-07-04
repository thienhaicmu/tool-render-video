# Content Studio — Redesign V2 (Bold / Vibrant Creator Tool)

> Design plan (chưa code). Phạm vi: **chỉ Content Studio**. Hướng: **Bold /
> năng lượng** — cảm giác "creator tool" (CapCut / Canva): gradient, màu mạnh,
> card nổi có bóng + glow, icon lớn, typography đậm, motion vui mắt.
>
> Bản V1 (token-hoá, P0–P6) đã đưa UI về design-system nhưng vẫn "phẳng / hiền".
> V2 KHÔNG phải vá — đây là một **ngôn ngữ thị giác mới** đắp lên nền token sẵn
> có, để Content Studio trông sống động và "đã mắt".
>
> File thật: `frontend/src/features/content-studio/` (ContentStudio.tsx + .css).
> Không đụng backend. Reuse token (`--brand-gradient`, `--brand-pink`,
> `--accent-*`, `--ai-*`) + `motion.css`; thêm một lớp "bold" mới.

---

## 1. Ngôn ngữ thị giác Bold (design language)

| Yếu tố | V1 (hiện tại) | V2 Bold |
|--------|---------------|---------|
| **Header** | h1 chữ + phụ đề xám | **Hero gradient**: dải nền gradient mờ, icon lớn ✨, tiêu đề đậm 28–32px, phụ đề sáng |
| **Nút chính** | Button gradient phẳng | **Nút gradient lớn** + **glow** khi hover + hiệu ứng nhấn (scale) + icon |
| **Card** | viền mảnh, nền phẳng | **Card nổi**: shadow mềm + hover **nâng lên (translateY)** + viền accent glow khi active |
| **Section** | label chữ nhỏ | **Section có icon + màu**: mỗi nhóm 1 icon tròn gradient nhỏ (🎨 Định dạng · 🖼 Hình · 🎙 Giọng) |
| **Chip / badge** | pill viền | **Pill đặc màu / gradient**, chữ trắng, bo tròn to |
| **Màu** | accent tím nhạt | Đẩy mạnh `--brand-gradient` (tím→indigo) + `--brand-pink` cho điểm nhấn + `--ai-active` cho khoảnh khắc AI |
| **Typography** | 700 tối đa | Tiêu đề **800**, số liệu **900**, phân cấp rõ (hero → section → body) |
| **Bo góc** | `--radius-lg` | `--radius-xl / 2xl` cho card lớn → mềm, hiện đại |
| **Motion** | fade/slide nhẹ | Hero entrance, **card hover lift**, button press, gradient shimmer trên phần active, orb glow |

**Nguyên tắc:** dùng gradient/màu mạnh **có chủ đích** ở điểm nhấn (CTA, hero,
khoảnh khắc AI), giữ vùng nhập liệu (textarea/input) trung tính để không rối. Tôn
trọng `prefers-reduced-motion`. Light/dark đều đẹp (token tự lo).

### Token bổ sung (thêm vào ContentStudio.css, không sửa tokens.css)
```
--cs-glow-accent : 0 0 24px rgba(var(--accent-rgb), .35);
--cs-glow-pink   : 0 0 24px rgba(var(--brand-pink-rgb), .30);
--cs-card-shadow : 0 8px 28px rgba(0,0,0,.28);
--cs-hero-grad   : linear-gradient(135deg, rgba(var(--accent-rgb),.18), rgba(var(--brand-pink-rgb),.12));
--cs-lift        : translateY(-3px);
```

---

## 1B. ⭐ BẮT BUỘC: Dark + Light theme và VI/EN (như tool đang có)

> Yêu cầu cứng của bạn. Cả hai đã là cơ chế sẵn có của app — V2 phải **giữ nguyên
> và chạy đẹp ở CẢ HAI** chế độ và CẢ HAI ngôn ngữ. Không được hardcode.

### Theme (Dark + Light) — dùng đúng cơ chế `data-theme` sẵn có
- **Mọi màu/gradient/glow build từ TOKEN**, tuyệt đối không hardcode hex. Dùng
  `--surface-*`, `--text-*`, `--accent-rgb`, `--brand-pink-rgb`, `--brand-gradient`
  → tự đổi theo dark/light qua `<html data-theme>`.
- **Hiệu ứng bold phải "tự giảm" ở light-mode** để không chói/bẩn:
  ```
  /* mặc định (dark) */
  --cs-card-shadow: 0 8px 28px rgba(0,0,0,.28);
  --cs-glow-accent: 0 0 24px rgba(var(--accent-rgb), .35);
  /* light: bóng nhạt hơn, glow dịu hơn, hero gradient mờ hơn */
  [data-theme="light"] {
    --cs-card-shadow: 0 6px 20px rgba(0,0,0,.10);
    --cs-glow-accent: 0 0 18px rgba(var(--accent-rgb), .22);
    --cs-hero-grad: linear-gradient(135deg, rgba(var(--accent-rgb),.10), rgba(var(--brand-pink-rgb),.07));
  }
  ```
- Textarea/input/preview video giữ `--surface-input` (đã đúng cả 2 theme).
- **B5 verify PHẢI chụp cả dark lẫn light** cho mỗi màn.

### Ngôn ngữ (VI + EN) — dùng đúng `useI18n().lang` sẵn có
- ContentStudio hiện đã dùng pattern `vi ? '…' : '…'` cho MỌI chuỗi — **giữ nguyên**.
- Mọi chuỗi MỚI trong V2 (nhãn section, hero, tooltip, nút, mô tả tier…) đều phải
  có **cả VI lẫn EN**, không được để 1 ngôn ngữ.
- Text co giãn được: EN thường dài hơn VI → layout (card/nút/section) phải không
  vỡ khi đổi ngôn ngữ. B5 verify chụp cả VI lẫn EN.

→ Ma trận kiểm tra ở B5: **{dark, light} × {VI, EN}** cho mỗi màn (Compose /
Planning / Review / Render / Publish) + `prefers-reduced-motion`.

---

## 2. Compose (Script + Config) — màn chính, redesign mạnh nhất

```
╔═══════════════════════════════════════════════════════════════╗
║  ✨  CONTENT STUDIO                          [1 Viết ▸ 2 ▸ 3]  ║ ← hero gradient
║  Biến kịch bản thành video — AI lo cảnh, lời kể & hình ảnh      ║
╚═══════════════════════════════════════════════════════════════╝

┌──────────────── Script (2/3) ────────────┐ ┌──── Config (1/3) ────┐
│ 📝 Kịch bản                    921 ký tự  │ │ 🎨 Định dạng          │
│ ┌───────────────────────────────────────┐│ │ [9:16][1:1][16:9]     │← segmented
│ │ (textarea lớn, nền input trung tính)  ││ │ ▭ preview khung 9:16  │← MỚI: ô xem tỉ lệ
│ │                                       ││ │ Thời lượng ●───── 90s │← slider
│ └───────────────────────────────────────┘│ │                       │
│ [📁 Nhập .txt] [✕ Xoá] [＋ Mẫu ▾]         │ │ 🖼 Hình ảnh           │
│                                           │ │ Nguồn [Local ▾]       │
│ 🕘 Bản nháp: [A ·4c][B ·6c ✓] …           │ │ (nếu AI) Imagen tier  │
└───────────────────────────────────────────┘ │  [Nhanh][Chuẩn][Ultra]│
                                               │ Nền [Màu][Ảnh][Video] │
                                               │                       │
                                               │ 🎙 Giọng & Phụ đề     │
                                               │ [VI][Nữ][edge] 🔊     │
                                               │ Phụ đề [Bật] capcut   │
                                               │                       │
                                               │ ⚙ Khác  Nhạc · Lưu    │
                                               └───────────────────────┘

              ┌─────────────────────────────────────┐
              │   ✨  TẠO KẾ HOẠCH (AI)   →          │ ← nút gradient lớn + glow
              └─────────────────────────────────────┘
```
**Điểm mới bold:**
- **Hero gradient** đầu màn (nền `--cs-hero-grad`, icon ✨ trong vòng tròn gradient).
- Config **gom nhóm có icon tròn màu** (🎨/🖼/🎙/⚙) thay vì label chữ khô.
- **Ô preview tỉ lệ khung** (vẽ khung 9:16/1:1/16:9 thật) — trực quan hơn 3 nút chữ.
- **Slider thời lượng** thay ô số.
- CTA "Tạo kế hoạch" **to, gradient, có mũi tên + glow**, đặt giữa nổi bật.
- Draft chips bo tròn to, hover glow.

## 3. AI Planning — "AI Director" sân khấu hơn

Giữ overlay console (V1) nhưng **bold hơn**: orb lớn hơn + **halo glow nhấp nháy**,
nền overlay gradient tối, các bước hiện với **thanh tiến trình gradient chạy**,
chữ đậm. Cảm giác "AI đang thực sự sáng tạo".

## 4. Review — plan như "thẻ bài" sống động

```
╔═══════════════════════════════════════════════════════════╗
║ <topic>  ·  storytelling  ·  4 cảnh  ·  ~90s   [✨ AI đã lo]║ ← hero nhỏ
╚═══════════════════════════════════════════════════════════╝
┌── ✨ AI đã làm gì ─────────────────────────────────────────┐
│ [applied] Chỉnh nhịp đọc 120s→90s   ████▸░░ (thanh mini)   │← chip gradient + bar
│ [applied] Hiểu: <topic> · Nhân vật ⬤A ⬤B                   │
│ [advisory] 1 cảnh quá tải, 1 thưa  → nhảy tới              │
└───────────────────────────────────────────────────────────┘
[Lọc: Tất cả | ⚠ Cảnh yếu]                    [＋ Thêm cảnh]

┌─ Cảnh 1 ───────────────────────── hook ──── [ok]─┐ ← card nổi, viền theo trạng thái
│ [tiêu đề]                       🔊 ↑ ↓ ✕         │
│ [lời kể…]                                        │
│ 😊 Cảm xúc  ⏩ Tốc độ  ⏱ Dur   🖼 visual prompt   │← control có icon
└──────────────────────────────────────[⚠ Quá tải]┘
```
- **AI Insights = hàng thẻ gradient** (chip `applied`/`advisory` màu rõ, có mini-bar).
- Scene card **nổi + viền màu theo audit** (ok=xanh mờ / quá tải=đỏ mờ / thưa=xám),
  **hover lift**. Control có icon nhỏ.
- Badge "⚠ Quá tải" pill đỏ đặc góc phải.

## 5. Live Render — "phòng điều khiển" năng lượng

```
┌── ✨ AI đang làm ────────────┐ ┌── Cảnh (4) ─────────────────┐
│ ● Hiểu kịch bản              │ │ ┌───┐ ┌───┐ ┌───┐ ┌───┐     │
│ ● Lập kế hoạch 4 cảnh        │ │ │✓ 1│ │◐ 2│ │⏳3│ │⏳4│     │← tile nổi, glow khi chạy
│ ◐ Sinh ảnh Imagen — cảnh 3   │◀│ │███│ │▓▓░│ │░░░│ │░░░│     │
│ · Ghép video                 │ │ └───┘ └───┘ └───┘ └───┘     │
│ ▓▓▓▓▓▓▓░░ 68%  (gradient)    │ └─────────────────────────────┘
└──────────────────────────────┘
```
- Vòng % **ConicRing gradient** to ở đầu + feed item **slide-in + glow** ở bước active.
- Scene tile đang chạy **viền accent glow + shimmer**; xong = ✓ xanh.
- Xong: **preview video** trong khung bo lớn + confetti nhẹ (score-xl-appear) + nút gradient "Tạo video mới".

## 6. Publish — khoảnh khắc "hoàn thành"

Reveal panel gradient: video preview lớn, **3 thẻ meta** (Tiêu đề/Mô tả/Thẻ) mỗi
thẻ có nút **Copy** bo tròn màu, gợi ý ảnh bìa. Cảm giác "xong rồi, chia sẻ thôi".

---

## 7. Component mới / nâng cấp (nội bộ content-studio)

| Component | Vai trò |
|-----------|---------|
| `HeroHeader` | Dải gradient + icon tròn + tiêu đề đậm (dùng lại 4 màn) |
| `SectionCard` | Card nhóm config có icon tròn màu + tiêu đề |
| `GradientButton` (hoặc dùng `Button variant=primary` + class bold) | CTA lớn glow |
| `RatioPreview` | Vẽ khung tỉ lệ 9:16/1:1/16:9 chọn được |
| `DurationSlider` | Slider thời lượng |
| `InsightChip` | Chip gradient applied/advisory + mini-bar (nâng từ AIChip) |
| `SceneCard` (bold) | Nổi + viền trạng thái + hover lift |
| `LiveSceneTile` (bold) | Glow khi chạy + shimmer |
| `animations.css` | Thêm: hero-in, card-lift, btn-press, glow-pulse |

---

## 8. Motion spec (bold, tái dùng motion.css + thêm ít)

| Nơi | Hiệu ứng | Nguồn |
|-----|----------|-------|
| Hero xuất hiện | fade + rise nhẹ | `panel-slide-up` |
| Card hover | nâng `translateY(-3px)` + shadow đậm | **mới** `.cs-card:hover` transition |
| Nút nhấn | scale 0.97 | **mới** `:active` transform |
| CTA hover | glow (box-shadow accent) | **mới** transition |
| Bước AI active | shimmer / glow-pulse | `progress-shimmer` + **mới** `glow-pulse` |
| Orb planning | halo nhấp nháy | `status-pulse` |
| Scene tile chạy | viền glow + shimmer | `clip-card-appear` + glow |
| Xong render | bung nảy % | `score-xl-appear` |

Chỉ thêm ~2–3 keyframe (`glow-pulse`, `hero-in`), còn lại transition thuần. Tất cả
bọc `prefers-reduced-motion`.

---

## 9. Lộ trình triển khai

| Phase | Nội dung | Ghi chú |
|-------|----------|---------|
| B0 | Thêm token bold (`--cs-*`) + `HeroHeader` + `SectionCard` + nút gradient lớn + card-lift/glow toàn cục | Nền tảng — đổi cảm giác ngay |
| B1 | Compose: hero + config nhóm-icon + RatioPreview + DurationSlider + CTA bold | Màn chính |
| B2 | Review: InsightChip gradient + SceneCard bold (viền trạng thái, hover) | |
| B3 | Render: ConicRing gradient + feed glow + scene tile glow/shimmer | |
| B4 | Planning orb bold + Publish reveal + preview khung lớn | |
| B5 | Verify: `tsc -b` + `npm run build` + **chạy app chụp từng màn ở {dark,light}×{VI,EN}** để tự kiểm | Không giao mù |

---

## 10. Không phá vỡ
- Giữ 100% chức năng + logic (chỉ đổi lớp trình bày).
- Không đổi backend / payload / WS shape.
- Reuse `components/ui` khi hợp; class bold nằm gọn trong `ContentStudio.css`.
- Light/dark + VI/EN + reduced-motion đều chạy.
- **B5 bắt buộc chụp màn hình tự kiểm** trước khi báo xong (rút kinh nghiệm V1).

---

**Tóm tắt:** V2 giữ nguyên bộ khung + chức năng, đắp lên một lớp **Bold/creator-tool**
— hero gradient, section có icon màu, CTA glow, card nổi hover-lift, khoảnh khắc AI
rực rỡ (orb halo, feed glow, insight chip gradient). Mục tiêu: Content Studio nhìn
**đã mắt, có năng lượng**, không còn "phẳng/hiền" như V1.
