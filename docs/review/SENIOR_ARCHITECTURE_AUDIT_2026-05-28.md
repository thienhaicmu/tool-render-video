# SENIOR ARCHITECTURE AUDIT — AI Video Render Studio

**Ngày audit**: 2026-05-28  
**Branch**: `restructure/output-timeline-architecture`  
**Người review**: Senior Architecture Agent (full codebase pass)  
**Phạm vi**: Backend, Frontend, AI pipeline, Business logic, Development roadmap  
**Mục tiêu đặc biệt**: AI trong render — thực trạng và hướng phát triển  

---

## TÓM TẮT ĐIỀU HÀNH

| Chiều | Đánh giá | Ghi chú |
|---|---|---|
| Backend stability | **HEALTHY** | Core render stack solid, WAL DB, QA gate intact |
| AI layer thực chất | **MISLEADING** | 306 file Python nhưng ZERO LLM call trong production path |
| Frontend architecture | **REBUILDING** | React 18 app trong quá trình xây, build pipeline gap tồn tại |
| Business logic | **SOLID** | Partial success, resume/retry, ranking, market scoring đầy đủ |
| Test coverage | **STRONG** | 7,551 tests / 184 test files — ấn tượng |
| Rủi ro cao nhất | **MONOLITH** | render_pipeline.py 5817 dòng + ai_director.py 4620 dòng |

**Verdict**: Nền tảng kỹ thuật đủ tốt để đẩy AI thực sự vào render. Điểm tắc nghẽn lớn nhất không phải là kỹ thuật — là **AI danh nghĩa vs AI thực tế**. Cần activate lớp cloud AI đã xây sẵn để biến system này từ heuristic scorer thành intelligent render platform.

---

## 1. KIẾN TRÚC BACKEND — SENIOR REVIEW

### 1.1 Stack và Runtime

```
Electron shell
  ↓
FastAPI (Uvicorn) — main.py
  ↓
Routes: render / jobs / download / voice / upload / channels
  ↓
SQLite WAL (data/app.db) — sole state store
  ↓
render_pipeline.py (5817 dòng — MONOLITH)
  ↓
FFmpeg subprocess — execution backend
```

**Điểm mạnh**:
- **Single-process architecture** đúng cho desktop offline-first. Không cần Redis, không cần cloud queue.
- **SQLite WAL mode** — reader không bị block bởi writer. Quyết định tốt cho render pipeline write-heavy.
- **ThreadPoolExecutor in-process** — đủ cho desktop, tránh IPC overhead.
- **QA gate** (`qa_pipeline.py`) không thể bypass — kiến trúc defensive đúng đắn.
- **Startup recovery** — jobs bị interrupt được mark là `interrupted`, không silently resume.

**Điểm yếu / Technical Debt**:

| Vấn đề | Mức độ | File |
|---|---|---|
| render_pipeline.py — 5817 dòng monolith | CRITICAL | render_pipeline.py |
| ai_director.py — 4620 dòng monolith | CRITICAL | ai_director.py |
| Mixed DB connection model (2 strategies trong 1 module) | MEDIUM | db.py / jobs_repo.py |
| Cache location bug: tempfile.gettempdir() vs APP_DATA_DIR | MEDIUM | scene_detector, transcription |
| settings.json + settings.local.json tracked in git với bypassPermissions | HIGH-SECURITY | .claude/ |

### 1.2 Pipeline Layers — Business Logic Flow

```
Layer 1-2: Validation + User setup
Layer 3: Source load (yt-dlp / local / editor session)
Layer 4: Scene detection → VisualAnalysisResult
Layer 4.5: ContentAnalyzer (Pass 1) — SINGLE PASS, shared by all consumers
Layer 5: Segment generation + viral/hook/market scoring
Layer 6: AI Director planning (Pass 2 consumers)
Layer 6.5: CameraStrategy
Layer 7: Per-part assets (subtitles, overlays) → PartAssets
Layer 8: FFmpeg encode → RenderOutputResult
Layer 9: QA validation gate (KHÔNG THỂ bypass)
Layer 10: Output ranking + best clip selection
Layer 11: result_json + report
```

**Nhận xét kiến trúc Layer 4.5**:  
ContentAnalyzer chạy một lần duy nhất — đây là quyết định **đúng**. Trước đây mỗi AI consumer tự chạy phân tích riêng gây duplicate compute. Two-pass design (Pass 1: content understanding, Pass 2: technical decisions) là pattern mature.

**Nhận xét Partial Success**:  
Business logic partial success (`is_partial_success`, `completed_with_errors`) được implement đầy đủ. Đây là feature quan trọng cho desktop render 20-60 phút — nếu 8/10 clips render xong mà 2 clip fail, user vẫn có output.

---

## 2. AI PIPELINE — SENIOR REVIEW (CRITICAL SECTION)

### 2.1 Thực Trạng AI — "AI Danh Nghĩa vs AI Thực Tế"

**Con số quan trọng**: 306 Python files trong `backend/app/ai/` — nhưng **ZERO LLM API call** đang chạy trong production path mặc định.

Toàn bộ lớp "AI" hiện tại là:

| Loại | Ví dụ | Thực chất |
|---|---|---|
| Rule-based scoring | viral_scorer.py, hook_analyzer.py | Heuristic formula + regex |
| Keyword detection | emotion_analyzer.py | Dictionary lookup |
| Beat analysis | beat_analyzer.py | Librosa/numpy signal processing |
| Narrative arc | content_analyzer.py | Time-window classification |
| Market scoring | viral_scoring.py | Multi-factor weighted sum |
| RAG system | knowledge_index.py + FAISS | Built nhưng inactive trong render path |
| ML fallback | viral_scorer.py Ridge regression | Chỉ activate khi có ≥30 feedback records |

**Đây không phải defect**. Đây là **thiết kế đúng đắn** cho offline-first desktop: không phụ thuộc internet, không phụ thuộc GPU khi không có. Nhưng naming rất misleading — user và developer đều nghĩ AI đang "thinking" trong khi thực chất là heuristic.

### 2.2 Kiến Trúc AI Thực Sự — HybridAnalyzer

**File**: `backend/app/ai/analysis/hybrid_analyzer.py`

```
HybridAnalyzer.analyze(chunks, context)
  ├── LocalAnalyzer  (ALWAYS runs)
  │     ├── hook_analyzer.py    — regex-based, 9 hook types
  │     └── emotion_analyzer.py — keyword emotion detection
  │
  ├── CloudAnalyzer (OPTIONAL — gated by ai_cloud_enabled=False)
  │     ├── OpenAIProvider   — gpt-4o-mini (~$0.0003/video)
  │     └── GroqProvider     — llama-3.1-8b-instant (FREE TIER)
  │
  └── MergeStrategy
        — cloud 70% / local 30% for semantic signals
        → AnalysisSignals (unified output)
```

**Nhận xét**: Kiến trúc này **đúng hướng**. LocalAnalyzer đảm bảo offline-first. CloudAnalyzer là opt-in upgrade path. Merge strategy thông minh: cloud wins semantic signals (70%) nhưng local vẫn đóng góp (30%).

**Vấn đề**: `ai_cloud_enabled=False` là default. Không có UI flow nào guide user activate nó. Groq là FREE — user không cần trả tiền nhưng feature này invisible.

### 2.3 Render Influence — AI→FFmpeg Gateway

**File**: `backend/app/ai/director/render_influence.py`

AI influence vào render chỉ qua 4 surface này:

| Payload field | Effect | Safety gate |
|---|---|---|
| `motion_aware_crop` | Enable MediaPipe subject tracking | camera_plan behavior check |
| `reframe_mode` | Change crop strategy | camera_plan mode + cloud hint |
| `highlight_per_word` | Per-word ASS emphasis markers | subtitle_plan check |
| `subtitle_style` | Font/color/position preset | confidence ≥ 0.80 |

**Nhận xét**: Bounded influence design là đúng. AI không thể rewrite FFmpeg commands trực tiếp — chỉ influence 4 payload fields qua safety gate. Đây là defensive AI architecture tốt.

### 2.4 Knowledge System — RAG và Patterns

```
backend/app/ai/knowledge/
backend/app/ai/rag/
backend/knowledge/processed/    ← knowledge packs
backend/knowledge/index/        ← FAISS index (nếu FAISS available)
```

**KnowledgeIndex** (rag/knowledge_index.py):
- FAISS-backed nếu available; fallback là filter-rank in-memory
- Hỗ trợ `query(filters, top_k=10)` — có thể query theo platform, content type, etc.
- Knowledge packs đã built nhưng chưa wired vào cloud prompt builder

**Pattern**: Có `pattern_extractor.py`, `pattern_registry.py`, `pattern_schema.py` — infrastructure để learn từ creator output nhưng chưa có feedback loop đóng.

### 2.5 Creator Intelligence System

```
creator_dna/        — creator style fingerprint
creator_archetype/  — archetype classification
creator_style/      — camera + subtitle + render strategy
creator_fusion/     — merge multiple creator signals
preset_evolution/   — preset auto-evolve từ performance
feedback/           — feedback learning infrastructure
adaptive/           — adaptive memory + safety
outcome_tracking/   — render success patterns
```

**Nhận xét**: Infrastructure đầy đủ nhưng chưa có **user-facing feedback loop**. Creator không có cách nào mark clip nào tốt để train model. Đây là gap lớn nhất giữa infrastructure và product value.

### 2.6 Viral Scorer — ML Path Hidden

**File**: `backend/app/services/viral_scorer.py`

```python
# Scoring modes:
# 1. Heuristic (default) — multi-factor formula
# 2. ML (optional) — sklearn Ridge regression
#    Activates when data/viral_model.pkl exists
#    Built from data/viral_feedback.jsonl
#    Requires ≥30 feedback records to train
```

**Nhận xét quan trọng**: Có một ML scoring model ẩn trong viral_scorer. Nếu creator record feedback + view counts sau khi đăng video, model tự train. Nhưng không có UI để làm điều này. Đây là **feature hoàn toàn invisible với user**.

---

## 3. FRONTEND ARCHITECTURE — SENIOR REVIEW

### 3.1 Stack

```
React 18 + TypeScript + Vite
Zustand (state management — uiStore + renderStore)
WebSocket (RenderSocketClient) + HTTP polling fallback
No React Router — activePanel string controls navigation
```

### 3.2 Component Architecture

```
App.tsx → ClipStudio (fullscreen, 4-step workflow)
       → HistoryScreen (jobs/history)
       → DownloaderScreen
       → StudioScreen (source hero → ClipStudio redirect)
       → SettingsScreen

ClipStudio steps:
  Step 1: Source selection
  Step 2: Configure (StepConfigure — AI tabs, presets, subtitles)
  Step 3: Rendering (StepRendering — live WebSocket progress)
  Step 4: Results (StepResults — output gallery, ranking, quality)
```

**Điểm mạnh sau restructure**:
- RenderWorkflow.tsx split từ 2983 dòng → 8 files: clean separation của concerns
- useRenderSocket hook với fingerprint-based dedup — không re-render nếu data không đổi
- WebSocket + HTTP polling dual track — đúng per offline-first contract
- Error boundary, empty/loading/error states cho mọi feature

### 3.3 Technical Debt — Frontend

**Debt 1 — renderStore không nhận WebSocket updates**:
```typescript
// renderStore chỉ được write khi submit, không cập nhật từ WS
// Components cần live state phải dùng useRenderSocket trực tiếp
// Mọi component muốn stage/progress phải re-subscribe hook
```
*Impact*: Không thể share live job state qua store — duplicate subscriptions nếu nhiều component cần cùng state.

**Debt 2 — Build pipeline gap (Issue 1)**:
```
vite.config.ts builds to: backend/static-new/   (gitignored)
ui_gate.py serves from:   backend/static-v2/
```
*Impact*: `npm run build` không update served UI. Developer phải manually copy. Rất dễ deploy stale UI.

**Debt 3 — AI UI exposure gap**:
```typescript
// cfg state có đầy đủ AI fields:
aiAnalysisMode: 'hybrid'
aiCloudProvider: 'groq'
aiCloudApiKey: ''
aiCloudModel: ''
```
*Impact*: UI fields cho AI cloud tồn tại trong ConfigState nhưng cần verify chúng được submit trong RenderRequest payload đúng cách.

### 3.4 WebSocket Event Shape — Đang Hoạt Động Đúng

```typescript
// WS event shape frozen:
{ job: {...}, parts: [...], summary: {...} }

// useRenderSocket xử lý đúng:
client.onProgress((summary, parts) => { ... })
client.onComplete((event) => { const status = event.job.status })
client.onError((err) => { ... })
```

---

## 4. BUSINESS LOGIC — SENIOR REVIEW

### 4.1 Core Render Workflow — Solid

| Business rule | Implementation | Status |
|---|---|---|
| Partial success | `is_partial_success`, `completed_with_errors` | SOLID |
| Resume/retry interrupted jobs | `resume_mode` in pipeline | SOLID |
| Startup recovery | `interrupted` status, không auto-resume | SOLID |
| Output validation gate | qa_pipeline.py — không thể bypass | SOLID |
| Market-aware scoring | US/EU/JP profiles, hook patterns | SOLID |
| Multi-variant rendering | Infrastructure exists | PARTIAL — no UI confirmation |
| Creator DNA personalization | Infrastructure exists | PARTIAL — no feedback UI |

### 4.2 Ranking Logic

Output ranking combines:
- `viral_score` — heuristic + optional ML
- `hook_score` — proximity to hook positions  
- `retention_score` — dropoff prediction
- `motion_score` — scene density + tracking quality
- `market_score` — platform/market fit
- `quality_penalty` — QA gate deductions

**Nhận xét**: Multi-signal ranking tốt. Nhưng user không thể thấy **tại sao** một clip được rank cao hơn — thiếu explainability UI (infrastructure đã có trong `explainability/`).

### 4.3 Creator-perceived Quality Gap

Từ ARCHITECTURE.md — được document là known gap:
> *Technical quality can pass while creator-perceived quality still feels less premium. Premium perception depends on hook visuals, typography, motion rhythm, audio polish, intro/outro treatment, branding, and visual consistency.*

**Phân tích**: System có thể produce technically valid video nhưng thiếu:
- Hook visual treatment (text animation on first 3 seconds)
- Subtitle typography premium (bounce/karaoke là đúng hướng nhưng cần refinement)
- Audio polish (loudness normalization, music bed)
- Intro/outro branding (remotion_adapter exist nhưng experimental)

---

## 5. PHÂN TÍCH RỦI RO KỸ THUẬT

### 5.1 Risk Matrix

| Risk | Severity | Probability | Mitigated? |
|---|---|---|---|
| render_pipeline.py monolith gây change regression | HIGH | HIGH | Partial — pytest suite |
| AI labeling misleads về actual capabilities | MEDIUM | HIGH | No |
| renderStore WebSocket sync gap | MEDIUM | MEDIUM | No |
| Build pipeline deploys stale frontend | MEDIUM | HIGH | No |
| settings.json bypassPermissions in git | SECURITY | HIGH | No |
| Cache accumulation (tempfile bug) | LOW-MEDIUM | HIGH | No |
| NVENC session overflow on concurrent renders | HIGH | LOW | Yes — semaphore |

### 5.2 Điều Không Được Sờ Không Có Plan

```
render_pipeline.py    5817 dòng  — CRITICAL: full pytest required
ai_director.py        4620 dòng  — CRITICAL: same as above
qa_pipeline.py        ~500 dòng  — CRITICAL: never bypass
schemas.py                       — HIGH: additive-only
data/app.db                      — HIGH: sole state, no backup
```

---

## 6. HƯỚNG PHÁT TRIỂN — AI MẠNH MẼ CHO RENDER

### Tầm nhìn: Semi-tech & AI Platform

**"Semi-tech"** = Creator không cần hiểu kỹ thuật, AI đưa ra quyết định thay họ  
**"AI"** = Không phải heuristic scoring — là real intelligence từ LLM + learned preferences

---

### PHASE A — Activate AI Thực Sự (2-3 tuần) — QUICK WIN

**Mục tiêu**: Bật Groq cloud analyzer cho user. Miễn phí, không cần GPU.

**A.1 — UI: Thêm Groq API Key onboarding**
```
Settings → AI Configuration
  [  ] Enable AI Cloud Analysis
  Provider: [Groq (Free)] [OpenAI]
  API Key: [______________]
  → "Test connection" button
```

**A.2 — Backend: Wire ai_cloud_enabled vào RenderRequest submission**
```python
# RenderWorkflow.tsx ConfigState đã có:
aiAnalysisMode: 'hybrid'
aiCloudProvider: 'groq' 
aiCloudApiKey: ''
# → Verify chúng được map sang RenderRequest đúng
```

**A.3 — Đo lường**: So sánh clip selection quality khi cloud ON vs OFF
- Dùng `AnalysisSignals.confidence` như metric
- Log kết quả trong `result_json.ai_director`

**Impact**: User thấy AI "thinking" thực sự. Clip selection tốt hơn vì LLM hiểu ngữ nghĩa transcript, không chỉ regex hook patterns.

---

### PHASE B — Activate RAG Knowledge System (3-4 tuần) — STRATEGIC

**Mục tiêu**: Feed knowledge packs vào cloud AI prompts để AI "biết" về platform best practices.

**B.1 — Wire KnowledgeIndex vào prompt_builder**
```python
# backend/app/ai/analysis/cloud/prompt_builder.py
# Hiện tại: static prompts
# Target: dynamic prompts enriched với relevant knowledge items

knowledge = KnowledgeIndex()
relevant_rules = knowledge.query(
    filters={"platform": "tiktok", "content_type": "entertainment"},
    top_k=5
)
# Inject rules into system prompt
```

**B.2 — Platform-aware Knowledge Retrieval**
```python
# backend/app/ai/knowledge/platform_knowledge_retriever.py (đã có)
# Retrieve TikTok-specific rules cho TikTok platform
# Retrieve YouTube Shorts-specific rules cho YouTube
```

**Impact**: AI không chỉ "đọc transcript" mà còn "biết" rằng TikTok cần hook trong 1.5s đầu, YouTube Shorts cần khác. Clip selection trở nên platform-aware thực sự.

---

### PHASE C — Creator Feedback Loop (4-6 tuần) — HIGH VALUE

**Mục tiêu**: Creator đánh dấu clip nào tốt → AI học preference → preset auto-evolve.

**C.1 — UI: Feedback surface trong Results step**
```
Results Gallery:
  [Clip 1] ★★★★★  ← Rate this clip
           👍 Post    ← Track engagement later
           🎯 Good hook  🎯 Good visuals  (tags)
```

**C.2 — Backend: Wire feedback vào viral_scorer ML path**
```python
# viral_scorer.record_feedback() đã có
# Cần gọi khi user rate clip:
viral_scorer.record_feedback(
    segment_features=clip.features,
    actual_views=0,  # update later from upload result
    actual_likes=0,
)
# Sau 30+ records: viral_scorer.train_model() 
# → sklearn Ridge regression thay thế heuristic
```

**C.3 — Creator DNA auto-update**
```python
# creator_dna/dna_engine.py đã có infrastructure
# Cần: khi user rate clip cao → extract style DNA
# → update creator profile → influence next render
```

**Impact**: Mỗi lần render, AI hiểu creator muốn gì hơn. System personalizes theo thời gian. Đây là killer differentiator so với generic video tools.

---

### PHASE D — Explainability UI (2-3 tuần) — TRUST BUILDER

**Mục tiêu**: User hiểu TẠI SAO AI chọn clip này, rank cao clip kia.

**D.1 — AI Decision Panel trong Results**
```
Clip 1 (Rank #1, Score 87)
  "Được chọn vì: Hook mạnh ở 0:03, emotion peak 'excitement',
   camera motion pattern phù hợp TikTok, subtitle density tối ưu"
  
  📊 Score breakdown:
  ╠ Viral:   82  ████████░░
  ╠ Hook:    91  █████████░
  ╠ Market:  78  ███████░░░
  ╠ Quality: 90  █████████░
```

**D.2 — Backend**: `explainability/` module đã có
```python
# explainability/reason_builder.py
# explainability/summary.py  
# explainability/confidence.py
# → Already built, cần expose qua API và render trong UI
```

**D.3 — API endpoint**:
```
GET /api/jobs/{id}/ai-explain
→ { clip_reasons: [...], ranking_factors: {...}, confidence_breakdown: {...} }
```

**Impact**: User trust tăng khi họ thấy AI không "black box". Creator có thể học từ AI decisions để cải thiện workflow.

---

### PHASE E — Intelligent Segment Override (6-8 tuần) — POWER USER

**Mục tiêu**: AI không chỉ score — AI chọn segments thay user khi họ opt-in.

**E.1 — Enable ai_content_driven_selection**
```python
# render_pipeline.py đã có:
# ai_content_driven_selection=True → AI Director segments override heuristic
# Hiện tại: default False
# Target: enable với safety gate — chỉ khi cloud confidence ≥ 0.75
```

**E.2 — Multi-variant Planning UI**
```
"AI creates 3 versions of your video:
  Version A: Hook-optimized (hook at 0:02)
  Version B: Story-driven (build to climax)  
  Version C: Market-optimized (US/TikTok best practices)
  
  → Preview thumbnails → Pick favorite → Render"
```

**E.3 — Strategy Variants**
```python
# backend/app/ai/strategy_variants/ đã có:
# variant_generator.py, variant_evaluator.py, strategy_reasoner.py
# → Wire multivariant planning vào UI flow
```

**Impact**: Power users không cần configure — AI proposes strategies, user picks. True "semi-tech" UX.

---

### PHASE F — Real-time Quality Intelligence (8-12 tuần) — PREMIUM

**Mục tiêu**: AI evaluate output quality post-render và suggest improvements.

**F.1 — Post-render AI quality report**
```
After render:
  "Your clip passes technical QA but here's how to improve:
  - First frame is a cut instead of a strong visual (score: 61/100)  
  - Subtitle density is too high for this platform (score: 72/100)
  - No hook overlay applied — consider adding text callout
  Suggested next render: apply hook overlay + reduce subtitle density"
```

**F.2 — Vision-based thumbnail analysis**
```python
# extract_thumbnail_frame() đã có trong render_engine
# Add: Claude Haiku vision API call để evaluate:
# - Is the first frame visually compelling?
# - Does it have a clear subject?
# - Is there text visible for silent viewing?
```

**F.3 — Upload performance loop**
```
Upload to TikTok → 24h later → pull view count
  → feed into viral_scorer.record_feedback()
  → creator DNA updates
  → next render uses learned preferences
```

**Impact**: Closed feedback loop. AI improves with every video posted. Long-term competitive advantage.

---

### PHASE G — Upgrade AI Model (Ongoing)

**Model progression** (không cần thay đổi kiến trúc — chỉ cần wire):

| Phase | Model | Use case | Cost |
|---|---|---|---|
| Now (PHASE A) | Groq llama-3.1-8b | Hook/emotion classification | Free |
| PHASE E | Groq llama-3.3-70b | Strategy reasoning | Free tier |
| PHASE F | Claude Haiku 4.5 | Vision + quality analysis | ~$0.001/video |
| Long-term | Claude Sonnet 4.6 | Deep creative analysis | ~$0.01/video |

**Key insight**: HybridAnalyzer architecture supports provider swap without changing downstream code. Wire `anthropic` SDK vào `CloudAnalyzerBase._call_api()` là một new provider file.

---

## 7. QUICK WINS — CÓ THỂ LÀM NGAY

| Item | Effort | Impact | Risk |
|---|---|---|---|
| Fix build pipeline gap (vite → static-v2) | LOW | HIGH | LOW |
| Expose Groq API key trong Settings UI | LOW | HIGH | LOW |
| Explainability endpoint + UI card | MEDIUM | HIGH | LOW |
| viral_scorer feedback recording khi user rate clip | MEDIUM | HIGH | LOW |
| Fix cache location bug (tempfile → APP_DATA_DIR/cache) | MEDIUM | MEDIUM | MEDIUM |
| Remove settings.local.json từ git tracking | LOW | SECURITY | LOW |

---

## 8. KẾT LUẬN

### Điểm Mạnh Cốt Lõi

1. **Defensive architecture** — QA gate, partial success, resume/retry, WAL database. Production-grade.
2. **Two-pass AI design** — ContentAnalyzer single-pass + consumer reuse. Đúng kiến trúc.
3. **HybridAnalyzer** — local-first + cloud-optional. Đúng hướng cho offline desktop.
4. **306 AI module files** — infrastructure đồ sộ. Không thiếu building blocks, chỉ thiếu activation.
5. **7551 tests** — coverage đáng tin cậy cho CRITICAL/HIGH tier changes.

### Khoảng Cách Lớn Nhất

**Gap 1 — AI danh nghĩa vs thực tế**: 306 files, 0 LLM calls. User không nhận được AI intelligence mà chỉ nhận heuristic scoring được đặt tên là AI.

**Gap 2 — Creator feedback loop không tồn tại**: Infrastructure học từ user preferences đã xây (creator DNA, preset evolution, adaptive learning) nhưng không có entry point từ UI.

**Gap 3 — Explainability invisible**: AI đưa ra decisions về clip selection và ranking nhưng user không thể thấy lý do. Black-box AI không build trust.

**Gap 4 — Knowledge system chưa wired**: KnowledgeIndex + platform knowledge retriever được build kỹ nhưng không inject vào AI prompts.

### Kết Luận

Hệ thống này **không cần rebuild** — cần **activate và connect** những gì đã xây. Lộ trình A→B→C→D là investment ít nhất nhưng impact lớn nhất:

- **A** (Groq): Biến AI từ heuristic thành LLM-powered — 2-3 tuần
- **B** (RAG): Biến AI từ generic thành platform-aware — 3-4 tuần  
- **C** (Feedback): Biến AI từ static thành learning — 4-6 tuần
- **D** (Explainability): Biến AI từ black-box thành trustworthy — 2-3 tuần

**Total**: 11-16 tuần để có một AI render platform thực sự differentiated.

---

*Tài liệu này là audit snapshot tại 2026-05-28. Không edit file này — tạo file mới nếu có findings mới.*
