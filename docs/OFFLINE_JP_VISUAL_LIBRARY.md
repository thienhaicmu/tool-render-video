# Offline Japanese Visual Library v1

## Mục tiêu

Bộ nền tảng này tạo nhân vật và background Nhật hoàn toàn offline bằng SVG thủ tục.
Không gọi dịch vụ tạo ảnh, không cần mạng và không phát sinh chi phí theo ảnh.

## Ba style dùng chung identity

| Style ID | Hướng hình ảnh | Nội dung phù hợp |
|---|---|---|
| `jp_anime_clean_v1` | Nét sạch, màu rõ, cel-shading cân bằng | giải thích, học đường, đời thường |
| `jp_anime_cinematic_v1` | tương phản sâu, bóng và vignette mạnh | drama, bí ẩn, cao trào |
| `jp_anime_soft_drama_v1` | màu ấm/pastel, tương phản mềm | gia đình, tình cảm, chữa lành |

Style chỉ thay màu, ánh sáng và bóng. `CharacterLook` không đổi, nên đổi style không
được phép đổi khuôn mặt, tóc, tuổi, giới tính hoặc trang phục của nhân vật.

## Kho khởi đầu

- 24 identity: 16 vai hiện đại và 8 vai cổ đại.
- Nghề hiện đại: cảnh sát, bác sĩ, kỹ sư, học sinh, CEO/giám đốc, mẹ chồng,
  nàng dâu, giáo viên, chủ quán cà phê và nhân viên cửa hàng tiện lợi.
- Vai cổ đại: samurai, nữ võ sĩ, daimyo, miko, geisha, thương nhân, chủ quán trọ,
  ninja.
- 12 background curated: đường phố, đồn cảnh sát, bệnh viện, phòng thí nghiệm,
  lớp học, phòng khách, văn phòng tổng giám đốc, ga tàu, cửa hàng tiện lợi, quán
  cà phê, đền Thần đạo và nhà truyền thống.
- Factory vẫn có thêm các scene chung như rừng, lâu đài, rooftop và bãi biển.

Kho curated mặc định dùng tóc đen/nâu và mắt nâu/đen để hợp nội dung Nhật đời
thường. Nhân vật tạo tùy chỉnh vẫn có thể dùng màu tóc anime.

## Luồng matching offline

```text
Chapter / StoryPlan
  -> role + era + profession + location tags (JA/EN/ZH)
  -> jp_catalog.search_roles()
  -> stable role_id
  -> CharacterLook (identity lock)
  -> outfit / pose / emotion
  -> background_for_role()
  -> selected Japanese StylePack
  -> transparent character SVG + opaque scene SVG
```

Thứ tự fallback bắt buộc:

```text
đúng identity + đúng pose
  -> đúng identity + pose gần nhất
  -> đúng identity + neutral
  -> block render và yêu cầu bổ sung/tạo asset đúng identity
```

Không được thay nhân vật bằng một identity khác chỉ vì mô tả gần giống.

## Vị trí code và dữ liệu sinh ra

- Theme: `backend/app/features/render/engine/visual/v2/theme_pack.py`
- Identity/look: `backend/app/features/render/engine/visual/v2/look_spec.py`
- Character factory: `backend/app/features/render/engine/visual/v2/anime_char.py`
- Background factory: `backend/app/features/render/engine/visual/v2/anime_scene.py`
- Role/background catalog: `backend/app/features/render/engine/visual/v2/jp_catalog.py`
- Builder: `backend/scripts/build_jp_three_style_library.py`
- Generated library/manifest: `artifacts/visual_v2_jp/`

## Trạng thái tích hợp

Đây là Visual Foundation và chưa được nối vào render pipeline chính. Gate tiếp theo:

1. Duyệt contact sheet nhân vật và background.
2. Chốt style mặc định theo project/series.
3. Nối resolver vào StoryPlan và thêm Asset Coverage/Readiness gate.
4. Chỉ render khi identity, pose và background đã qua validation.

Quyết định giữ factory chưa nối pipeline giúp việc duyệt hình không ảnh hưởng luồng
render hiện tại và không làm thay đổi project của người dùng đang có.
