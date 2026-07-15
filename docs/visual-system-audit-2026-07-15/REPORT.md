# Review hệ thống nhân vật, hình ảnh và background

Ngày review: 2026-07-15  
Phạm vi: Story Mode, asset library, character resolver, background selection, visual compositor, Review UI, dữ liệu runtime và test liên quan.

## 1. Kết luận điều hành

Hệ thống hiện **chưa đạt điều kiện để mở rộng kho hình ảnh chất lượng cao một cách an toàn**. Vấn đề không chỉ là bộ asset hiện tại chưa đẹp. Ba lỗi nền tảng đang làm cho asset tốt cũng có thể bị chọn sai hoặc không được sử dụng:

1. Index trong database lệch rất xa filesystem: 875 bản ghi nhưng chỉ 66 đường dẫn còn tồn tại; 0 character hiện có trên disk được index thành công.
2. Character resolver bỏ qua `region`, và compositor có thể đổi một character thư viện thành character procedural khác khi beat có cả emotion và pose.
3. Kiến trúc visual v2 có identity model và style registry tốt hơn nhưng Story runtime vẫn chạy visual v1; Shot Grammar mới cũng chưa điều khiển bố cục hình.

Đánh giá tổng quan:

| Trục | Điểm hiện tại | Nhận xét |
|---|---:|---|
| Đúng asset / đúng identity | 2/10 | Index chết, region bị bỏ qua, identity có thể đổi theo beat |
| Chất lượng mỹ thuật | 3/10 | Chủ yếu vector/procedural đơn giản; upscale không tạo thêm chi tiết |
| Đa dạng thật | 3/10 | Nhiều file nhưng lặp hình; coverage region lệch mạnh |
| Nhất quán style | 3/10 | Alias UI/runtime không nối; cho phép fallback sang style khác |
| Khả năng nâng cấp | 4/10 | Có visual v2 đáng dùng, nhưng đang tồn tại song song và chưa là runtime chuẩn |
| Vận hành và QA | 3/10 | Scan thủ công, thiếu health check, metrics và visual regression |

**Khuyến nghị:** chưa chi tiền tạo thêm hàng loạt asset. Làm P0 để sửa index, identity và style routing trước; sau đó mới xây một quality pack nhỏ làm chuẩn và đo bằng A/B hoặc review thủ công.

## 2. Dữ liệu thực tế

### 2.1 Database và filesystem không đồng bộ

Kết quả đọc trực tiếp `data/app.db`:

| Chỉ số | Số lượng |
|---|---:|
| Bản ghi `story_assets` | 875 |
| Đường dẫn còn tồn tại | 66 |
| Đường dẫn đã chết | 809 |
| Character còn tồn tại trong index | 0 |
| Background còn tồn tại trong index | 66 |

Filesystem `data/asset_library` hiện có:

| Kind | Số lượng |
|---|---:|
| Character | 172 |
| Background | 102 |
| Tổng | 274 |

Coverage character chỉ có JP 72 và US 100; CN, KO, VI, EU đều bằng 0. Coverage background là CN 22, EU 12, JP 42, KO 9, US 10, VI 7.

Hệ quả runtime hiện tại:

- UI có thể hiển thị thumbnail chết vì `list_assets()` không kiểm tra file tồn tại.
- Catalog gửi vào model có thể chứa slug chết vì `build_library_catalog()` dùng thẳng `list_assets()`.
- Model chọn slug chết; `get_by_slug()` trả `None`; renderer rơi về procedural.
- `STORY_CHAR_RESOLVER=1` nhưng resolver không có character khả dụng trong index, nên character mới thường có trạng thái `missing` và bị sinh chibi procedural.

### 2.2 Đa dạng background bị phóng đại bởi file trùng

Trong 102 background:

- 27 nhóm có SHA-256 trùng tuyệt đối.
- 62 file nằm trong các nhóm trùng.
- 35 file là bản sao dư thừa, tương đương khoảng 34% kho background.

Một hình giống hệt đang được gắn cho nhiều region/genre khác nhau, ví dụ courtyard CN/KO, market CN/EU/VI, office JP/US. Đây là **đa dạng nhãn**, không phải đa dạng hình ảnh, đồng thời làm giảm độ tin cậy văn hóa.

### 2.3 Variant coverage gần như chưa tồn tại

- 172 character tạo thành 172 family; không có family nào có emotion/pose variant thật.
- 72 file JP thực chất là 24 role nhân ba style.
- 100 file US là bộ GEE!ME đánh số, metadata role khó dùng cho semantic selection.
- 102 background tạo thành 76 family; 26 family có day/night variant.

## 3. Findings theo mức độ

### P0.1 - Asset catalog đang cung cấp dữ liệu chết cho UI và model

**Bằng chứng code**

- `backend/app/db/story_asset_repo.py:93-125`: `list_assets()` trả row mà không kiểm tra `_exists(path)`.
- `backend/app/db/story_asset_repo.py:296-317`: `build_library_catalog()` gom family từ các row đó mà không xác thực file.
- `backend/app/features/story/router.py:918-927`: scan chỉ được gọi qua endpoint thủ công.
- `backend/app/db/story_asset_repo.py:469-525`: scan và prune chỉ chạy khi endpoint/script gọi; upsert từng file rồi commit riêng.

**Tác động**

- Broken thumbnail, slug chết trong prompt, fallback ngoài dự kiến.
- Thêm asset mới không đồng nghĩa asset được runtime nhìn thấy.
- Chất lượng output không phản ánh chất lượng kho hiện có.

**Sửa bắt buộc**

- Lọc asset không tồn tại ở mọi read path ngay lập tức.
- Chạy reconcile lúc startup hoặc khi manifest/version thay đổi.
- Scan theo transaction/batch; trả health summary `indexed/stale/quarantined/error`.
- Không cho catalog hoặc picker dùng row `status != active`.

### P0.2 - Identity nhân vật bị thay giữa các beat

**Bằng chứng code**

- `backend/app/features/render/engine/stages/story/visuals_stage.py:286-301`: nếu emotion và pose đều khác mặc định, code bỏ library asset và sinh procedural chibi.
- `backend/tests/test_story_char_overlay.py:75-92`: test hiện còn yêu cầu chính hành vi đổi renderer này.

**Tác động**

Một nhân vật có thể đổi khuôn mặt, tóc, quần áo, tỷ lệ và art style chỉ vì beat chuyển sang `angry + point`. Đây là lỗi continuity nghiêm trọng hơn việc thiếu một pose.

**Nguyên tắc sửa**

- Identity lock phải mạnh hơn emotion/pose fidelity.
- Khi thiếu variant kết hợp, giữ base identity và áp transform/layer gần đúng; không được đổi sang renderer khác.
- Mỗi master phải mang `identity_id`, `pack_id`, `pack_version`, `content_hash` và variant axes.

### P0.3 - Character resolver nhận `region` nhưng không dùng

**Bằng chứng code**

- `backend/app/features/render/engine/visual/character_resolver.py:102-112`: `_candidates(region, ...)` gọi `list_assets()` chỉ với genre/style, không truyền region.

**Tác động**

Nhân vật có thể được chọn sai văn hóa/thời đại. Khi kho mở rộng, xác suất lỗi sẽ tăng chứ không giảm.

**Sửa bắt buộc**

- Region/era/style/license/status là hard filter, không phải soft score.
- Chỉ fallback cross-region khi plan cho phép rõ ràng và phải ghi telemetry.
- Thêm test region isolation và fallback policy.

### P1.1 - Story runtime chưa dùng visual v2

**Bằng chứng code**

- Runtime vẫn import `svg_char` và `svg_scene` v1 tại `visual/svg_compose.py:17-19`, `visual/story_reference_sheet.py:21` và `stages/story/visuals_stage.py:258`.
- `visual/v2/look_spec.py`, `visual/v2/styles.py`, `visual/v2/anime_char.py` và `visual/v2/anime_scene.py` có identity/style model tốt hơn nhưng chủ yếu phục vụ script tạo library.

**Tác động**

- Hai kiến trúc cùng tồn tại, logic style và identity bị phân tán.
- Nâng chất lượng ở v2 không tự cải thiện Story output.
- Chi phí bảo trì tăng và test không bảo vệ đường runtime mong muốn.

**Khuyến nghị**

Tạo một `VisualRenderer` contract duy nhất và đưa v2 thành implementation chuẩn. V1 chỉ là compatibility adapter trong giai đoạn chuyển đổi, sau đó loại bỏ.

### P1.2 - Shot Grammar chưa điều khiển hình ảnh

`StoryPlan` đã có `shot_size`, `angle`, `lens`, `camera_position`, `composition`, `motion_intent`, nhưng tìm kiếm usage trong visual renderer không có kết quả. Các field chủ yếu được normalize và hiển thị trong UI.

**Tác động**

- Shot khác nhau vẫn dùng cùng background, cùng framing và cùng scale nhân vật.
- Model có thể viết shot đa dạng nhưng output nhìn lặp lại.

**Khuyến nghị**

Biên dịch Shot thành `CompositionSpec`: crop anchor, subject scale, screen position, foreground/midground/background layer, camera height, depth, motion preset và safe zone.

### P1.3 - Style UI và style pack không cùng taxonomy

- UI dùng các giá trị như `anime`, `realistic`, `wuxia`, `ink wash`.
- Kho JP dùng `jp_anime_clean_v1`, `jp_anime_cinematic_v1`, `jp_anime_soft_drama_v1`.
- `visual/v2/theme_pack.py:35-47` có alias resolver, nhưng `story_asset_repo.active_library_style()` tại dòng 214-218 chỉ exact-match `known_styles()`.
- `get_by_slug()` tại dòng 261-275 vẫn cho foreign style là candidate cuối.

**Tác động**

Chọn `anime` có thể không kích hoạt pack JP nào, rồi query mở rộng sang mọi style. Một video có thể trộn clean, cinematic, soft drama và styleless.

**Khuyến nghị**

- Một taxonomy duy nhất: `art_direction_id -> compatible pack ids`.
- Không fallback foreign style âm thầm.
- Fallback phải có policy, reason code và cảnh báo trước render.

### P1.4 - StoryPlan chưa lưu visual identity đủ mạnh

`CharacterDef` tại `story_plan_v2.py:117-126` chỉ có mô tả, tuổi, giới tính, archetype và slug. `SettingDef` tại dòng 130-140 chỉ có mô tả, scene kind, slug và optional scene spec. `RenderState` tại dòng 331-336 lưu đường dẫn tuyệt đối.

Thiếu các khái niệm first-class:

- `VisualIdentity` / `CharacterLook` bất biến.
- Asset pack và version.
- Outfit state, hair/face/palette/accessories.
- Variant family và axes emotion/pose/outfit.
- Content hash, dimensions, safe zones, status và quality tier.
- Lighting, time, weather, season và camera anchors cho setting.

Đường dẫn tuyệt đối trong plan cũng dễ chết sau cleanup, di chuyển data directory hoặc restore job.

### P1.5 - Chất lượng asset hiện tại thấp và style khác biệt chủ yếu bằng màu

Kiểm tra trực quan trên asset thật và cache render cho thấy:

- Character procedural dùng cùng anatomy/face template, khác chủ yếu tóc, màu và phụ kiện.
- Background ít lớp chiều sâu, ít vật thể kể chuyện, nhiều khoảng trống và gradient đơn giản.
- JP clean/cinematic/soft drama dùng gần như cùng geometry; cinematic chủ yếu thêm tint/shadow.
- File `asset_library_enhanced_2x.zip` là upscale hình đơn giản, tăng pixel nhưng không tăng chi tiết, anatomy hay art direction.

Vì vậy không nên lấy độ phân giải làm quality gate. Cần đánh giá composition, silhouette, anatomy, identity distinctness, material/detail, lighting, cultural specificity và consistency theo pack.

### P2.1 - Asset registry thiếu schema để quản trị kho lớn

Hiện tại:

- ID là SHA-1 của absolute path (`story_asset_repo.py:42-43`), nên thay root là đổi identity.
- Không có unique constraint rõ ràng cho `(kind, slug, style)`.
- Tags là text tự do, search bằng SQL `LIKE`.
- Không có pack/version/content hash/parent variant/quality/status/dimensions.
- Sidecar lỗi được bỏ qua mềm; delete DB có thể bị rescan phục hồi.

Đây là schema phù hợp cho prototype, chưa phù hợp cho kho nhiều pack và nhiều phiên bản.

### P2.2 - Asset Picker chưa hỗ trợ quản trị chất lượng

`AssetPicker.tsx:12-37` hard-code region/genre, search mỗi keystroke, không style filter và không pagination. Card tại dòng 77-87 chỉ hiển thị name, region, genre. Character picker tại `CharactersPanel.tsx:196-203` không truyền region/genre mặc định của plan.

Thiếu các tín hiệu cần cho người duyệt:

- Pack/style/version/quality/status.
- Variant coverage.
- Broken/missing indicator.
- Compare side-by-side và identity sheet.
- Usage count/repetition warning.
- Health status và last scan.

### P2.3 - Readiness và telemetry mô tả sai fallback thực tế

`story_readiness.py:71-82` cảnh báo character missing sẽ “không overlay”, trong khi `visuals_stage.py:297-301` sinh procedural overlay. Người dùng không biết output đã đổi nguồn/style.

Chưa thấy metric cho:

- Library hit rate và dead-slug rate.
- Procedural fallback rate.
- Cross-region/cross-style fallback.
- Identity switch.
- Duplicate usage trong cùng video.
- Pack/version distribution và render failure theo asset.

### P2.4 - Hợp đồng aspect ratio gây rủi ro bố cục

`ASPECT_SIZE` tại `story_plan_v2.py:84` gắn `16:9` với 1536x1024 và `9:16` với 1024x1536, thực chất là 3:2 và 2:3. Encoder sau đó cover-crop về kích thước output.

Pipeline vẫn render được, nhưng tác giả asset và compositor đang bố cục trên canvas khác tỷ lệ cuối. Subject gần biên có thể bị cắt; preview và output có thể lệch. Cần hoặc dùng canvas đúng aspect, hoặc khai báo rõ source canvas + crop-safe zones theo từng target.

## 4. Kiến trúc đích đề xuất

### 4.1 Asset pack có version và manifest

```text
asset_packs/
  jp_anime_clean/
    1.0.0/
      manifest.json
      characters/
        ceo_woman/
          identity.webp
          variants/
            neutral_stand.webp
            angry_point.webp
          identity.json
      backgrounds/
        cafe_modern/
          day_wide.webp
          night_medium.webp
          setting.json
```

Database lưu logical ID và content hash; filesystem/object store chỉ là blob location. Plan lưu `pack_id`, `version`, `asset_id`, `variant_id`, không lưu absolute path làm identity.

### 4.2 Tách identity khỏi variant

```text
CharacterIdentity
  -> immutable look: face, hair, body, palette, outfit baseline, style pack
  -> VariantSpec: emotion, pose, outfit state, camera-facing
  -> RenderedMaster: content hash + source provenance
```

Khi thiếu variant, degrade theo thứ tự:

1. Cùng identity, cùng outfit, gần nhất emotion/pose.
2. Cùng identity, base image + transform/layer.
3. Cùng identity, neutral pose.
4. Cảnh báo cần duyệt.

Không bao giờ tự động chuyển sang identity/renderer khác.

### 4.3 Selection hai pha, deterministic

**Pha 1 - hard compatibility filter**

`kind`, `status=active`, region, era, art direction, aspect compatibility, license, pack version, transparency.

**Pha 2 - weighted ranking**

Role/semantic similarity, setting match, visual palette, shot compatibility, variant coverage, quality tier; trừ điểm asset đã dùng gần đây để tăng đa dạng. Tie-break bằng stable seed để rerender không đổi ngẫu nhiên.

LLM chỉ nên đề xuất semantic intent hoặc logical family; resolver là nơi quyết định asset cụ thể theo policy.

### 4.4 Quality gate cho mỗi pack

Mỗi asset phải qua:

- Schema + license + provenance.
- Decode, dimensions, alpha và color profile.
- Safe-zone check cho 16:9, 9:16, 1:1.
- Exact hash + perceptual hash duplicate detection.
- Contact sheet kiểm tra consistency.
- Character identity sheet nhiều pose/emotion.
- Background sheet nhiều time/weather/shot size.
- Trạng thái `draft -> review -> active`; có `deprecated/quarantined` và rollback.

## 5. Roadmap ưu tiên

### Pha A - Làm runtime dùng đúng asset (ước lượng 1-2 ngày)

1. Reconcile index tự động, lọc row chết và thêm health endpoint.
2. Sửa region filter, style alias và cấm foreign-style fallback âm thầm.
3. Giữ identity khi thiếu emotion+pose variant; thay test đang khóa hành vi sai.
4. Ghi provenance/fallback reason vào plan và readiness.
5. Bổ sung test chạy trên manifest/filesystem mẫu, không chỉ DB mock.

**Điều kiện pass:** 100% catalog slug resolve được; 0 cross-region không khai báo; 0 identity switch; fallback được hiển thị.

### Pha B - Hợp nhất kiến trúc visual (ước lượng 3-5 ngày)

1. Đưa visual v2 qua `VisualRenderer` contract và nối vào Story runtime.
2. Thêm `VisualIdentity`, `AssetRef`, `AssetPackRef`, `VariantSpec` vào domain model.
3. Biên dịch Shot Grammar thành `CompositionSpec` và dùng trong compositor.
4. Chuyển path tuyệt đối thành logical ID/content-addressed resolution.

**Điều kiện pass:** cùng plan + seed + pack version cho output identity ổn định; shot size/camera/composition tạo khác biệt đo được.

### Pha C - Xây quality pack chuẩn (ước lượng theo nguồn ảnh)

Không làm toàn bộ region ngay. Chọn một market/genre có nhu cầu cao và tạo vertical slice:

- 8-12 character identity khác biệt rõ.
- Mỗi identity có neutral + 4 emotion + 4 pose quan trọng, ưu tiên variant kết hợp thường dùng.
- 12-20 setting family, mỗi family có day/night và ít nhất wide/medium.
- 1 art direction duy nhất, có style bible và contact sheet.
- A/B với kho cũ trên cùng 10 StoryPlan cố định.

Chỉ nhân rộng khi pack đạt quality gate và giảm fallback/repetition rõ ràng.

### Pha D - Công cụ vận hành và mở rộng

1. Asset Manager có pack/style/status/version/filter và compare.
2. Import pipeline tạo sidecar/manifest, pHash, thumbnail, safe-zone preview tự động.
3. Dashboard library hit, fallback, duplicate use, identity continuity.
4. Versioned rollout và rollback theo project/channel.

## 6. Test đã chạy và khoảng trống

Đã chạy:

```text
tests/test_story_asset_library.py
tests/test_character_resolver.py
tests/test_story_library_match.py
tests/test_asset_library_styles.py
tests/test_story_char_overlay.py

44 passed in 2.22s
```

Test xanh nhưng chưa bao phủ health của kho thật. Cần thêm:

- DB/filesystem parity và stale catalog exclusion.
- Region isolation.
- Art-style alias từ preset UI đến pack ID.
- Identity continuity qua emotion + pose.
- Pack manifest validation và duplicate detection.
- Golden/contact-sheet visual regression.
- Shot Grammar có tác động thực đến bố cục.

## 7. Quyết định đề xuất

**Duyệt Pha A trước.** Đây là phần ít tốn chi phí AI nhất và có lợi tức cao nhất: làm cho hệ thống dùng đúng những gì đã có, đồng thời tạo nền đo lường đáng tin trước khi đầu tư vào ảnh mới.

Sau Pha A, chọn một quality pack nhỏ ở Pha C để chứng minh chuẩn mỹ thuật. Không nên “generate thật nhiều rồi scan vào kho”; cách đó sẽ tăng file count nhưng tiếp tục làm taxonomy, duplicate và style inconsistency tệ hơn.
