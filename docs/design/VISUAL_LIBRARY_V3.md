# Visual Library V3

## Legacy character migration map

The legacy character library is inventoried before any Planner matching work:

- `172` legacy PNG artifacts are preserved as `legacy_artifacts`.
- `124` logical identities are created from stable region/genre/slug groups.
- `7` declared style ids are retained, including `legacy_default_v1` and three US art-direction packs.
- Bare slug aliases are emitted only when a slug maps to one identity; path aliases remain unique.
- Migrated identities start as `draft`; only the selected remaster batch moves to `review`.

Generate the inventory map:

```powershell
cd backend
.\\.venv\\Scripts\\python.exe scripts/build_visual_library_v3_legacy_character_map.py
```

Generate a review batch without changing matching or resolver behavior:

```powershell
.\\.venv\\Scripts\\python.exe scripts/remaster_visual_library_v3_legacy_characters.py --region jp --limit 24
```

The current JP batch contains `24` identities and `120` native SVG masters across five framings. The contact sheet supports `--region`, `--quality`, and `--limit` for small visual QA batches.

Each remastered `CharacterMasterSpec` may keep an SVG source in `artifact` and a transparent PNG delivery/preview in `preview_artifact`. The preview is optional for old draft inventory, but its hash and dimensions are validated whenever present.

Run the non-matching coverage audit:

```powershell
.\\.venv\\Scripts\\python.exe scripts/audit_visual_library_v3_legacy_characters.py
```

The audit is a gate for inventory integrity only. It does not approve artwork as `active` and does not call the AI Planner, matcher, or resolver.

Build the artwork upgrade queue:

```powershell
.\\.venv\\Scripts\\python.exe scripts/build_visual_library_v3_artwork_queue.py
```

The current queue classifies `100` US identities as `P0` because their new style ids still point to structured proof artwork and need a high-end artwork pack. The `24` JP identities are `P2` structured masters for art-direction QA. This priority is intentionally separate from identity matching.

## Legacy scene migration

The legacy background inventory is now represented as `78` logical scene identities with `102` preserved source artifacts across `jp`, `cn`, `eu`, `us`, `ko`, and `vi`. Scene identities keep:

- `layers.background` for the current authored master.
- `variants` for style/time/recipe outputs.
- `safe_zones` for subject, focal point, and subtitle placement.
- `legacy_artifacts` for every source PNG and its provenance.

Build the map and remaster the first JP batch:

```powershell
.\\.venv\\Scripts\\python.exe scripts/build_visual_library_v3_legacy_scene_map.py
.\\.venv\\Scripts\\python.exe scripts/remaster_visual_library_v3_legacy_scenes.py --region jp
.\\.venv\\Scripts\\python.exe scripts/audit_visual_library_v3_legacy_scenes.py
```

The first scene batch has now expanded to all `78` identities with `190` layered SVG/PNG style variants. Every scene has a safe-zone contract and remains `review`, not `active`; high-end art-direction approval is still a separate gate.

Scene recipe QA is tracked separately:

```powershell
.\\.venv\\Scripts\\python.exe scripts/build_visual_library_v3_scene_artwork_queue.py
```

The queue now reports `0` P0 family aliases, `0` P1 overused recipes, and `78` scenes ready for normal visual QA. Native recipes were added for courtyard, market, library, cave, ruins, waterfall, desert, graveyard, park, garden, snow, temple, battlefield, and inn so regional scenes do not silently reuse one generic composition.

Run the final gate before any Planner integration:

```powershell
.\\.venv\\Scripts\\python.exe scripts/audit_visual_library_v3_release_gate.py
```

The current gate passes `124` character identities / `620` masters and `78` scene identities / `190` variants. It verifies full character framing, 100% preview coverage, scene safe-zones, legacy preservation and manifest integrity while explicitly asserting that matching remains untouched.

Trạng thái: Pha 1 - contract và pilot  
Phạm vi hiện tại: character/scene template, identity, master, version và quality gate.  
Ngoài phạm vi: AI Planner matching, resolver, scoring và runtime selection.

## Mục tiêu

Visual Library V3 lấy **identity có định danh** làm trung tâm. File PNG/SVG/Lottie chỉ là artifact của một identity và có thể được thay thế bằng bản remaster mà không đổi `character_id` hoặc `scene_id`.

Thứ tự triển khai đã chốt:

1. Registry và schema.
2. Character Template V3.
3. Scene Template V3.
4. Remaster kho cũ.
5. Xây thêm character và scene theo coverage matrix.
6. Visual QA và duyệt pack.
7. Matching với AI Planner.

## Ownership boundary

Package:

```text
backend/app/features/render/engine/visual/library_v3/
  contracts.py    # dữ liệu có version
  registry.py     # load/write/validate manifest
```

Package không được import `character_resolver`, Story prompt hoặc Planner. Chiều phụ thuộc sau này là:

```text
Planner output -> matcher -> Visual Library V3 registry -> renderer
```

Registry không gọi ngược Planner và không tự đoán identity.

## Character contract

### CharacterTemplateSpec

Template mô tả khả năng dựng hình, không phải một nhân vật cụ thể:

- `anatomy_model`
- `layer_slots`
- `supported_framings`
- `supported_poses`
- `supported_emotions`
- `renderer_id`
- `style_id` và `version`

Layer contract ban đầu:

```text
anatomy
skin
face
eyes
hair_back
hair_front
outfit_base
outfit_detail
accessories
effects
```

### CharacterIdentitySpec

Identity là nhân vật hình ảnh ổn định:

- `id`, `version`, `template_id`, `style_id`
- `region`, `era`, `role`
- `look`
- `signature_features`
- `immutable_fields`
- `masters`
- `provenance`
- `quality_state`

`immutable_fields` là phần renderer và variant builder không được tự đổi giữa các cảnh, ví dụ khuôn mặt, màu mắt, màu tóc, silhouette và đặc điểm nhận diện.

### CharacterMasterSpec

Mỗi master gắn với một framing cụ thể:

- `full_body`
- `three_quarter`
- `waist_up`
- `bust`
- `close_up`
- `profile`
- `back_three_quarter`

Một identity muốn chuyển sang `review` hoặc `active` phải có tối thiểu `full_body`, `waist_up` và `bust`. Close-up sẽ được thêm vào quality gate khi Character Template V3 sinh được face detail riêng, thay vì crop full-body.

## Scene contract

Scene cũng có template và identity riêng. Scene template khai báo:

- Layer `background`, `midground`, `foreground`, `lighting`, `atmosphere`.
- Aspect native `16:9`, `9:16`, `1:1`.
- Shot size, time và weather được hỗ trợ.

Scene ở trạng thái `review` hoặc `active` phải có safe zone để compositor biết vùng đặt nhân vật, focal point và vùng subtitle.

## Quality states

```text
draft -> review -> active -> deprecated
                  \-> quarantined
```

- `draft`: được phép thiếu framing/variant trong lúc remaster.
- `review`: đủ master tối thiểu, content hash, nguồn và license.
- `active`: đã được duyệt mỹ thuật và có thể dùng ở runtime sau khi matching được xây.
- `deprecated`: giữ alias tương thích nhưng không dùng cho sản phẩm mới.
- `quarantined`: lỗi license, file, identity hoặc chất lượng.

Registry hiện thực thi các gate cấu trúc. Gate mỹ thuật như anatomy, identity consistency và cultural specificity sẽ được thực hiện bằng contact sheet ở pha remaster.

## Legacy migration

`legacy_aliases` chỉ ánh xạ slug cũ sang ID mới để giữ lịch sử:

```json
{
  "jp_ceo_woman": "jp_modern_ceo_woman_01"
}
```

Đây không phải matching. Alias là ánh xạ tĩnh, được duyệt khi remaster. AI Planner không nhìn thấy hoặc chọn alias trong Pha 1.

## Pilot hiện tại

Chạy:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/build_visual_library_v3_pilot.py
```

Output cục bộ:

```text
data/visual_library_v3_pilot.json
```

Pilot chuyển ba mẫu có định danh rõ:

- `jp_ceo_woman` -> `jp_modern_ceo_woman_01`
- `jp_samurai` -> `jp_historical_samurai_man_01`
- `jp_cafe` -> `jp_modern_cafe_01`

Cả ba vẫn là `draft`. Pilot chứng minh schema, content hash, dimensions, provenance và alias; nó không tuyên bố artwork cũ đã đạt chuẩn.

## Pha tiếp theo

1. Mở rộng `CharacterLook` thành anatomy/face/hair/outfit layer spec đầy đủ.
2. Nâng `anime_char` thành renderer theo framing thay vì một canvas full-body cố định.
3. Sinh contact sheet cho hai identity pilot ở các framing.
4. Đặt tiêu chí duyệt anatomy, silhouette, face diversity, outfit và shading.
5. Remaster pilot tới `review`, rồi mới lập kế hoạch chuyển đổi hàng loạt.

## Remaster pilot đã chạy

Chạy:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts/remaster_visual_library_v3_pilot.py
.\.venv\Scripts\python.exe scripts/build_visual_library_v3_contact_sheet.py `
  --manifest ..\data\visual_library_v3_pilot_remastered.json `
  --output-dir ..\artifacts\visual_library_v3\pilot_remastered
```

Kết quả cục bộ:

- `data/visual_library_v3_pilot_remastered.json` - manifest `0.2.0`, identity ở trạng thái `review`.
- `data/visual_library_v3/characters/` - 10 PNG + 10 SVG master cho 2 identity.
- `artifacts/visual_library_v3/pilot_remastered/character_masters.png` - contact sheet duyệt mắt.

Pilot chưa được đánh dấu `active`. Các artifact hiện chứng minh được identity continuity, native framing, hash, dimensions và provenance; chất lượng mỹ thuật high-end vẫn cần vòng remaster/duyệt tiếp theo.
