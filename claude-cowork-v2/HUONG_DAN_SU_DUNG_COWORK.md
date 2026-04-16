# HƯỚNG DẪN SỬ DỤNG COWORK
**Phiên bản**: 2.0 | **Ngôn ngữ**: Tiếng Việt | **Dự án**: Render Studio

---

## 1. Giới thiệu Cowork

**Cowork** là một hệ thống quy trình chuẩn hóa giữa kỹ sư và Claude Code.

Thay vì gửi yêu cầu thô cho AI và nhận về kết quả không kiểm soát được, Cowork buộc mọi task phải đi qua:

1. **Chuẩn hóa** — yêu cầu được làm rõ scope, điều kiện chấp nhận, rủi ro
2. **Thực thi có giới hạn** — AI chỉ được làm đúng những gì khai báo trong task
3. **Đánh giá** — kết quả được chấm điểm theo tiêu chí cụ thể
4. **Lưu trữ** — toàn bộ quá trình được lưu thành artifact bundle có thể kiểm tra lại

**Tại sao cần Cowork?**
- AI không tự giới hạn scope nếu không được khai báo rõ ràng
- Kết quả không thể audit nếu không có log cấu trúc
- Bug phát sinh khi AI improvise ngoài phạm vi được giao

---

## 2. Cowork Gồm Gì

```
COWORK = CORE + BUSINESS PROFILE + ADAPTER
```

### Core (bất biến, không sửa)
- **Pipeline 10 stage** (`scripts/pipeline.ts`)
- **Schema validation** tại mọi boundary (Ajv, JSON Schema)
- **Logger cấu trúc** NDJSON với 13 loại event
- **Template engine** với `{{VARIABLE}}` và guard chống placeholder chưa render
- **Retry + timeout** cho mọi LLM call (3 lần, backoff 0/1/2s, timeout 60s)

### Business Profile (clone và chỉnh theo dự án)
- `docs/` — tài liệu dự án được inject vào prompt normalization
- `prompts/system/prompt-normalizer-system.md` — cách LLM hiểu task
- `prompts/system/reviewer-system.md` — tiêu chí đánh giá
- `prompts/fewshots/normalize-examples.md` — ví dụ calibration
- `business-profile.md` — định nghĩa domain, entity, rule

### Adapter (config theo môi trường)
- `.env` — API keys, executor mode, đường dẫn
- `.claude-cowork/config.json` — override runtime

---

## 3. Cách Dùng Cơ Bản (Step-by-Step)

### Bước 1: Setup môi trường

```bash
cd claude-cowork-v2
npm install
cp .env.example .env
# Chỉnh .env theo môi trường của bạn
```

### Bước 2: Chọn chế độ chạy

Chỉnh trong `.env`:

```bash
# Development — không gọi AI thật, không thực thi thật
CLAUDE_EXECUTOR_MODE=simulated
NORMALIZER_PROVIDER=mock
REVIEWER_PROVIDER=mock

# Production — gọi AI thật, thực thi thật
CLAUDE_EXECUTOR_MODE=claude_cli
NORMALIZER_PROVIDER=openai_compat
REVIEWER_PROVIDER=openai_compat
NORMALIZER_API_KEY=sk-ant-...
REVIEWER_API_KEY=sk-ant-...
NORMALIZER_BASE_URL=https://api.anthropic.com/v1
REVIEWER_BASE_URL=https://api.anthropic.com/v1
```

### Bước 3: Tạo task

**Option A — Từ file JSON:**
```bash
npm run pipeline -- --file tasks/incoming/sample-task.json
```

**Option B — Từ dòng lệnh (dev nhanh):**
```bash
npm run pipeline -- --prompt "Fix the login bug causing 500 errors" --by "alice"
```

**Option C — Resume task đã intake:**
```bash
npm run pipeline -- --task-id task_abc123def456
```

### Bước 4: Xem kết quả

Pipeline in ra console:
```
════════════════════════════════════════════
Task ID:    task_mo0v4hb3bd930a772281d8a2
Run ID:     run_mo0v4hb916253dfe5d81b527
Status:     completed
Verdict:    accepted_with_followup
Score:      7.3/10
Artifacts:  artifacts/task_mo0v4hb3.../run_mo0v4hb9.../
════════════════════════════════════════════
```

Xem báo cáo đầy đủ:
```bash
cat artifacts/<task_id>/<run_id>/final-summary.md
```

---

## 4. Form Gọi Claude Code (QUAN TRỌNG)

Khi gọi Claude Code trực tiếp (ngoài pipeline), dùng cấu trúc sau:

---

```
[TASK]
<Mô tả ngắn gọn task cần làm — 1-2 câu>

[PROJECT GOAL]
<Mục tiêu tổng thể của dự án này là gì>

[BUSINESS CONTEXT]
<Tại sao task này quan trọng với người dùng hoặc business>

[COWORK CONTEXT]
<Cowork profile của dự án này là gì, executor mode đang dùng là gì, version>

[INPUT]
<Dữ liệu đầu vào cụ thể: file nào, function nào, error message gì, schema nào>

[EXPECTED OUTPUT]
<Kết quả mong đợi sau khi hoàn thành: file nào được sửa, behavior nào thay đổi>

[CONSTRAINTS]
- Chỉ sửa các file được liệt kê
- Không thêm dependency mới
- Không thay đổi schema nếu không được khai báo
- Không gold-plate: chỉ làm đúng yêu cầu
- Phải satisfy acceptance criteria được liệt kê
```

---

### Ví dụ: Gọi Claude sửa bug

```
[TASK]
Sửa bug trong endpoint /api/render/process: job bị stuck ở trạng thái "running"
khi worker thread crash mà không có cleanup.

[PROJECT GOAL]
Render Studio là nền tảng xử lý video tự động — render, phụ đề, viral scoring,
upload lên TikTok/YouTube. Cần pipeline ổn định để người dùng không mất job khi lỗi.

[BUSINESS CONTEXT]
Khi job bị stuck, người dùng phải restart server để chạy lại. Với batch lớn
(100+ video), một crash có thể làm mất hàng giờ công việc. Cần recovery tự động.

[COWORK CONTEXT]
Dự án: Render Studio. Cowork V2. Executor mode: simulated (dev).
Business profile: backend/app/services/job_manager.py là core service.
Coding standard: FastAPI, async/await, structured logging với logger.info.

[INPUT]
- File liên quan: backend/app/services/job_manager.py
- Hàm lỗi: ThreadPoolExecutor submit callback không xử lý exception
- Schema bị ảnh hưởng: bảng jobs (SQLite) — field status
- Error pattern: job chuyển sang "running" nhưng không bao giờ về "failed"

[EXPECTED OUTPUT]
- job_manager.py được sửa để catch exception từ worker thread
- Job status được set về "interrupted" khi thread crash
- Log event structured: logger.error với job_id và error message
- Không có job nào bị stuck ở "running" sau khi server restart

[CONSTRAINTS]
- Chỉ sửa backend/app/services/job_manager.py
- Không thay đổi database schema
- Không thêm dependency mới
- Phải có unit test coverage cho recovery path (nếu tests đã tồn tại)
- Logging phải dùng structured logger hiện tại của project
```

---

### Ví dụ: Gọi Claude thêm feature

```
[TASK]
Thêm hỗ trợ upload lên YouTube Shorts từ giao diện upload hiện tại.

[PROJECT GOAL]
Render Studio tự động hóa toàn bộ quy trình từ render → upload.
Hiện tại hỗ trợ TikTok. YouTube Shorts cần được thêm để tăng reach cho người dùng.

[BUSINESS CONTEXT]
Content creator muốn publish cùng một video lên nhiều nền tảng. Việc phải upload
thủ công lên YouTube sau khi TikTok đã được tự động hóa là điểm ma sát lớn.

[COWORK CONTEXT]
Dự án: Render Studio. Cowork V2. Executor mode: simulated (dev).
Business profile: upload flow qua /api/upload/schedule/start.
Coding standard: FastAPI, Playwright cho browser automation, async.

[INPUT]
- Upload adapter hiện tại: backend/app/services/upload_service.py
- Channel config: backend/app/models/channel.py
- Route: backend/app/routes/upload.py
- Frontend: desktop-shell (Electron, không thuộc scope)

[EXPECTED OUTPUT]
- Channel type "youtube_shorts" được thêm vào channel model
- Upload adapter cho YouTube Shorts (sử dụng YouTube Data API hoặc Playwright)
- Route /api/upload/schedule/start hỗ trợ youtube_shorts channel type
- Logging event: upload.youtube_shorts.started, upload.youtube_shorts.completed

[CONSTRAINTS]
- Chỉ sửa các file trong scope: upload_service.py, channel.py, upload.py
- Không sửa TikTok adapter đang hoạt động
- Không thay đổi database schema nếu chưa có migration plan
- Frontend nằm ngoài scope của task này
- API keys YouTube phải đọc từ environment variable, không hardcode
```

---

## 5. Ví Dụ Thực Tế

### Ví dụ 1: Bug Fix — Job bị stuck

**Input task JSON** (`tasks/incoming/my-task.json`):
```json
{
  "raw_prompt": "Job render bị stuck ở trạng thái running khi thread crash. Cần auto-recovery.",
  "submitted_by": "alice",
  "priority": "high"
}
```

**Chạy:**
```bash
npm run pipeline -- --file tasks/incoming/my-task.json
```

**Output artifacts:**
```
artifacts/task_xyz/run_abc/
├── raw-prompt.json           ← Task gốc
├── normalized-prompt.json    ← Đã chuẩn hóa: scope, criteria, risks
├── task-pack.md              ← Hướng dẫn chi tiết cho Claude
├── execution-result.json     ← Claude đã làm gì
├── review-report.json        ← Điểm: scope_fit=8, safety=9, overall=8.2
└── final-summary.md          ← Báo cáo đọc được
```

---

### Ví dụ 2: Feature — Upload YouTube Shorts

**Chạy nhanh:**
```bash
npm run pipeline -- \
  --prompt "Thêm YouTube Shorts upload support vào upload_service.py" \
  --by "bob"
```

**Sau khi xem final-summary.md, quyết định:**
- Verdict: `accepted_with_followup` → accept nhưng cần verify manual
- Follow-up: "Run integration test với YouTube API credentials thật"

---

## 6. Các Loại Task

| Task Type | Khi nào dùng | Ví dụ trong Render Studio |
|---|---|---|
| `bugfix` | Fix lỗi behavior hiện tại | Job stuck, API trả 500, subtitle sai |
| `feature` | Thêm chức năng mới | YouTube upload, new render preset |
| `refactor` | Cải thiện cấu trúc, không đổi behavior | Tách service, cải thiện types |
| `performance` | Tối ưu tốc độ/memory | Render pipeline bottleneck |
| `infra` | Config, Docker, DB migration | Thêm index, thay đổi Docker compose |
| `security` | Bảo mật | Input validation, auth, secrets |
| `test` | Thêm/sửa test | Unit test cho job_manager |
| `docs` | Tài liệu | Cập nhật README, API docs |

---

## 7. Cách Dùng Template

### Template task (execution-task.md)

Template được render tự động từ NormalizedPrompt. Bạn không cần sửa template trực tiếp.

Nếu muốn thêm thông tin vào task pack, thêm vào các field của NormalizedPrompt:
- `scope_in` — thêm file cần AI đọc/sửa
- `scope_out` — thêm file AI tuyệt đối không được động vào
- `acceptance_criteria` — thêm điều kiện cụ thể phải được satisfy
- `review_checkpoints` — thêm điểm reviewer cần check

### Kiểm tra template

Nếu output có `{{VARIABLE}}` chưa render:
```bash
# Chạy lại với dry_run để debug
CLAUDE_EXECUTOR_MODE=dry_run npm run pipeline -- --prompt "test"
# Xem log lỗi
cat logs/events/$(date +%Y-%m-%d).ndjson | grep "unresolved"
```

### Thêm biến vào template

1. Thêm `{{MY_VAR}}` vào `prompts/templates/execution-task.md`
2. Thêm `.replace('{{MY_VAR}}', value)` vào `scripts/build-task-pack.ts`
3. Thêm source field vào `NormalizedPrompt` nếu cần
4. Chạy lại pipeline — guard tự động báo lỗi nếu placeholder còn sót

---

## 8. Khi Project Chưa Có Cowork

Nếu bạn cần clone Cowork sang dự án mới:

### Bước 1: Copy core

```bash
cp -r claude-cowork-v2/ /path/to/new-project/claude-cowork-v2/
```

### Bước 2: Xóa runtime data (KHÔNG copy data cũ)

```bash
cd /path/to/new-project/claude-cowork-v2/
rm -rf tasks/incoming/* tasks/normalized/* tasks/taskpacks/*
rm -rf tasks/execution-results/* tasks/reviews/*
rm -rf logs/ artifacts/
```

### Bước 3: Viết lại Business Profile

Cập nhật các file sau cho dự án mới:
```
docs/project-overview.md      ← Mô tả dự án mới
docs/architecture.md           ← Architecture mới
docs/coding-standards.md       ← Coding standards mới
business-profile.md            ← Viết lại hoàn toàn
prompts/fewshots/normalize-examples.md  ← Ví dụ mới theo domain
```

### Bước 4: Config môi trường

```bash
cp .env.example .env
# Chỉnh PROJECT_NAME, API keys, paths
```

### Bước 5: Verify

```bash
npm install
CLAUDE_EXECUTOR_MODE=dry_run npm run pipeline -- \
  --prompt "Test normalization" --by "setup-test"
```

Nếu ra `Status: completed` là thành công.

---

## 9. Debug Khi Lỗi

### Pipeline dừng ở normalization

```bash
# Xem prompt đã gửi cho LLM
cat logs/prompts/<task_id>-normalize.json

# Xem event log
cat logs/events/<date>.ndjson | grep task_id

# Chạy lại với mock provider để tách biệt LLM issue
NORMALIZER_PROVIDER=mock npm run pipeline -- --task-id <task_id>
```

### Execution failed

```bash
# Xem stdout/stderr của Claude CLI
cat logs/executions/<run_id>-stdout.txt
cat logs/executions/<run_id>-stderr.txt

# Kiểm tra Claude CLI có hoạt động không
claude --version

# Chạy với simulated để confirm pipeline OK
CLAUDE_EXECUTOR_MODE=simulated npm run pipeline -- --task-id <task_id>
```

### Template có placeholder chưa render

```bash
# Xem lỗi cụ thể trong event log
cat logs/events/<date>.ndjson | grep unresolved

# Lỗi sẽ cho biết variable nào bị thiếu, ví dụ:
# "Unresolved placeholders: {{MY_VAR}}"
# → Tìm {{MY_VAR}} trong execution-task.md
# → Thêm .replace('{{MY_VAR}}', value) vào build-task-pack.ts
```

### Review luôn cho verdict changes_requested

```bash
# Deterministic reviewer chỉ cho accepted_with_followup khi simulated
# Chuyển sang LLM reviewer để có intelligent review
REVIEWER_PROVIDER=openai_compat \
REVIEWER_API_KEY=sk-ant-... \
REVIEWER_BASE_URL=https://api.anthropic.com/v1 \
npm run pipeline -- --task-id <task_id>
```

### Schema validation failed

```bash
# Xem error detail trong log
cat logs/events/<date>.ndjson | grep "validation"

# Lỗi thường gặp:
# - estimated_complexity: "epic" → phải là "xl"
# - acceptance_criteria_results[].notes → phải là "evidence"
# - scores.overall → phải là flat field overall_score
```

---

## 10. Lỗi Thường Gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `NORMALIZER_API_KEY not set` | Chưa set API key trong .env | Thêm `NORMALIZER_API_KEY=sk-ant-...` |
| `claude: command not found` | Claude CLI chưa cài | `npm install -g @anthropic-ai/claude-code` |
| `Unresolved placeholders: {{RUN_ID}}` | Template/renderer không khớp | Thêm `.replace('{{RUN_ID}}', run_id)` vào renderer |
| `Schema validation failed: must have required property 'schema_version'` | Thiếu field bắt buộc | Thêm `schema_version: "2.0"` vào output |
| `estimated_complexity must be equal to one of the allowed values` | Dùng "epic" thay vì "xl" | Thay "epic" → "xl" trong normalizer prompt |
| `LLM call timed out after 60000ms` | API chậm hoặc mạng chậm | Retry tự động; tăng `TIMEOUT_SECONDS` nếu cần |
| `Task pack build returned no result` | Tất cả docs paths không tồn tại | Kiểm tra `doc_paths` trong config và đường dẫn docs |
| `Reviewer LLM returned invalid JSON` | LLM trả về JSON không hợp lệ | Retry tự động; xem log để kiểm tra response raw |
| `Pipeline failed: Critical stage "normalize" failed` | Normalization lỗi | Xem `logs/prompts/<task_id>-normalize.json` |
| `additionalProperties must NOT have additional properties` | Schema thêm field không khai báo | Xem `schemas/*.json` để biết field nào được phép |

---

## 11. Mẹo Sử Dụng

### Mẹo 1: Chạy dry_run trước khi production

```bash
# Xác nhận pipeline config đúng mà không tốn API call
CLAUDE_EXECUTOR_MODE=dry_run \
NORMALIZER_PROVIDER=mock \
npm run pipeline -- --prompt "Test" --by "you"
```

### Mẹo 2: Dùng simulated cho dev loop nhanh

Khi đang phát triển feature cho Cowork:
```bash
# Toàn bộ pipeline chạy trong < 1s, không tốn API
CLAUDE_EXECUTOR_MODE=simulated NORMALIZER_PROVIDER=mock npm run pipeline -- --prompt "..."
```

### Mẹo 3: Xem prompt sẽ gửi cho AI trước khi gửi

```bash
# Normalize xong nhưng KHÔNG execute
npm run normalize -- tasks/incoming/sample-task.json
cat tasks/normalized/<task_id>.json   # xem normalized prompt
# Sau đó mới build pack và execute
```

### Mẹo 4: Luôn khai báo scope_out rõ ràng

Khi viết task prompt, luôn nêu rõ những gì KHÔNG được đụng vào:
> "Chỉ sửa job_manager.py. Không đụng vào upload_service.py, database schema, hay frontend."

Điều này được inject vào `scope_out[]` và reviewer sẽ check nếu AI vi phạm.

### Mẹo 5: Dùng labels để filter artifacts sau

```json
{
  "raw_prompt": "...",
  "submitted_by": "alice",
  "labels": ["backend", "critical", "sprint-23"],
  "priority": "high"
}
```

Labels được lưu vào manifest và có thể dùng để search artifact sau này.

### Mẹo 6: Đặt acceptance criteria testable

**Xấu:**
> "Code phải sạch hơn"

**Tốt:**
> "Khi worker thread crash, job status phải chuyển sang 'interrupted' trong vòng 5 giây"

Reviewer LLM dùng acceptance criteria để chấm điểm. Criteria không testable sẽ cho `not_verifiable`.

### Mẹo 7: Xem full pipeline trace khi debug

```bash
LOG_LEVEL=debug npm run pipeline -- --prompt "..." 2>&1 | tee debug.log
```

---

## 12. Kết Luận

Cowork không phải là overhead — nó là contract giữa bạn và AI.

Khi bạn đầu tư 5 phút viết task rõ ràng với scope, criteria, và constraints, AI sẽ:
- Không improvise ngoài phạm vi
- Không thêm dependency không cần thiết
- Không sửa code không liên quan
- Trả về kết quả có thể audit và rollback

Khi bạn gửi yêu cầu mơ hồ, AI sẽ đoán — và bạn sẽ mất thời gian review và fix nhiều hơn là tiết kiệm được.

**Quy tắc vàng:** Task càng rõ ràng → AI execution càng chính xác → Review score càng cao → Ít thời gian sửa hơn.

---

*Tài liệu này là một phần của Claude Cowork V2 — hệ thống workflow AI-assisted engineering cho Render Studio.*
