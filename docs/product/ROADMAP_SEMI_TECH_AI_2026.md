# Roadmap: Semi-Tech & AI Render Platform — 2026

**Ngày**: 2026-05-28  
**Nguồn**: Senior Architecture Audit (docs/review/SENIOR_ARCHITECTURE_AUDIT_2026-05-28.md)  
**Triết lý**: Activate what's built. Connect what's isolated. Close the creator feedback loop.

---

## Vấn Đề Cốt Lõi

Hệ thống hiện tại có **306 AI Python modules** nhưng không có một LLM call nào trong production render path. Đây không phải lỗi kỹ thuật — là **activation gap**: infrastructure đã sẵn sàng, nhưng chưa được bật cho user.

Ba gap lớn nhất:

| Gap | Mô tả | Infrastructure đã có |
|---|---|---|
| **AI Gap** | ZERO LLM calls dù có HybridAnalyzer + cloud providers | HybridAnalyzer, GroqProvider, OpenAIProvider |
| **Feedback Gap** | Creator không thể dạy AI sở thích của họ | creator_dna, viral_scorer ML, adaptive_learning |
| **Explainability Gap** | User không biết tại sao AI chọn clip nào | explainability/, reason_builder, confidence.py |

---

## Định Nghĩa "Semi-tech & AI"

**Semi-tech** = Creator không cần config kỹ thuật:
- Không nhập bitrate, CRF, codec
- Không chọn FFmpeg filter strings
- AI đề xuất, user approve hoặc chọn

**AI thực sự** = Không phải heuristic scoring được gọi là AI:
- LLM hiểu ngữ nghĩa transcript
- Model học từ creator feedback thực tế
- Explanations bằng ngôn ngữ creator hiểu

---

## PHASE A — Real AI Activation (Tuần 1-3)

**Objective**: Bật Groq cloud analysis. Miễn phí, instant value.

### A.1 — Settings UI: API Key Onboarding

```
Settings → AI Intelligence
  [●] Enable Cloud AI Analysis
  
  Provider: ○ Groq (Free)  ○ OpenAI ($)
  API Key:  [________________________]
            [Test Connection]
  
  Cloud AI enriches clip selection with semantic understanding
  of your transcript. Works offline without an API key.
```

### A.2 — Verify RenderRequest Mapping

Trong RenderWorkflow, `cfg.aiCloudApiKey` đã tồn tại trong ConfigState. Cần verify:
```typescript
// RenderRequest phải include:
ai_cloud_enabled: cfg.aiAnalysisMode === 'hybrid' && cfg.aiCloudApiKey !== ''
ai_cloud_provider: cfg.aiCloudProvider  // 'groq' | 'openai'
ai_cloud_api_key: cfg.aiCloudApiKey
ai_cloud_model: cfg.aiCloudModel || null
```

### A.3 — Progress Indicator: "AI is thinking"

Trong Rendering step, khi cloud AI chạy, show:
```
[Scene Detection ✓] → [AI Analysis ◌ "Understanding transcript..."] → [Clip Selection]
```

### A.4 — Quality Metrics

- Log `AnalysisSignals.confidence` vào result_json
- So sánh clip scores: cloud ON vs local-only
- Target: confidence ≥ 0.65 cho 80% videos với Groq

**Effort**: 1-2 tuần  
**Risk**: LOW — ai_cloud_enabled=False default bảo vệ existing users  
**Impact**: HIGH — first real AI in production render

---

## PHASE B — Knowledge-Powered AI (Tuần 4-7)

**Objective**: AI "biết" platform best practices, không chỉ đọc transcript.

### B.1 — Wire KnowledgeIndex vào Cloud Prompts

```python
# backend/app/ai/analysis/cloud/prompt_builder.py — HIỆN TẠI:
def build_system_prompt(context: dict) -> str:
    return STATIC_SYSTEM_PROMPT

# TARGET:
def build_system_prompt(context: dict) -> str:
    platform = context.get("platform", "tiktok")
    knowledge = KnowledgeIndex()
    rules = knowledge.query(
        filters={"platform": platform},
        top_k=5
    )
    platform_rules = "\n".join(f"- {r['rule']}" for r in rules)
    return SYSTEM_PROMPT_TEMPLATE.format(platform_rules=platform_rules)
```

### B.2 — Platform-Specific Prompt Profiles

```
TikTok:  Hook in first 1.5s, max 3 words per subtitle line, fast cut pace
YouTube: Hook in first 5s, longer segments OK, storytelling arc preferred
Reels:   Visual-first, trending audio patterns, trending hashtag hooks
```

Knowledge packs ở `backend/knowledge/processed/` — cần build/verify nội dung cho từng platform.

### B.3 — Automatic Knowledge Update

Khi creator rate clip cao (Phase C), extract patterns:
```python
# Clip với high rating → extract: hook type, duration, pacing, subtitle style
# → add to creator knowledge pack
# → next render uses this knowledge
```

**Effort**: 2-3 tuần  
**Risk**: LOW — chỉ ảnh hưởng khi cloud enabled  
**Impact**: HIGH — AI trở nên platform-aware thực sự

---

## PHASE C — Creator Feedback Loop (Tuần 6-12)

**Objective**: Mỗi video creator post → AI học → render tiếp theo tốt hơn.

### C.1 — Feedback UI trong Results Step

```
╔═══════════════════════════════════════╗
║  Clip 1  [▶ Preview]  [📋 Open]       ║
║                                       ║
║  Rate this clip:                      ║
║  [🤙 Great] [👍 Good] [👎 Skip]       ║
║                                       ║
║  What makes it work?                  ║
║  [✓ Strong hook] [✓ Good pacing]      ║
║  [  Natural cut] [  Clear audio]      ║
╚═══════════════════════════════════════╝
```

### C.2 — Backend: Record Feedback

```python
# POST /api/jobs/{id}/parts/{no}/feedback
{
    "rating": "great" | "good" | "skip",
    "tags": ["strong_hook", "good_pacing"],
    "platform": "tiktok"
}

# Handler:
viral_scorer.record_feedback(
    segment_features=extract_features(part),
    actual_views=0,   # updated later from upload
    actual_likes=0,
)
creator_dna.record_preference(
    style_signals=extract_style_signals(part),
    rating=rating,
)
```

### C.3 — ML Model Auto-Train

```python
# viral_scorer.py đã có:
_MIN_SAMPLES_TO_TRAIN = 30  # Ridge regression activates sau 30 samples

# Sau 30 ratings: auto-train → viral_model.pkl
# Render tiếp theo dùng ML score thay heuristic formula
# User thấy: "AI has learned from 32 of your ratings ✨"
```

### C.4 — Upload Performance Tracking (Optional)

```
After upload to TikTok/YouTube:
  24h later → pull view/like count
  → viral_scorer.record_feedback(views=1240, likes=89)
  → model retrains với real engagement signal
```

**Effort**: 4-6 tuần (UI + backend)  
**Risk**: MEDIUM — cần design UI tốt để không friction creator workflow  
**Impact**: VERY HIGH — closed learning loop, long-term differentiator

---

## PHASE D — Explainability (Tuần 4-6)

**Objective**: AI không còn black box. Creator học từ AI decisions.

### D.1 — AI Insight Card trong Results

```
╔═══════════════════════════════════════════╗
║  🤖 Why AI ranked this #1                 ║
║                                           ║
║  "Strong hook at 0:03 — 'You won't       ║
║  believe what happened...' (curiosity)    ║
║  Clip peaks at emotional high point.      ║
║  Fast scene pace matches TikTok norm."    ║
║                                           ║
║  Score breakdown:                         ║
║  Hook      ████████░░  82                 ║
║  Viral     ███████░░░  74                 ║
║  Market    █████████░  91                 ║
║  Quality   ████████░░  85                 ║
╚═══════════════════════════════════════════╝
```

### D.2 — API Endpoint

```
GET /api/jobs/{id}/ranking
→ {
    output_ranking: [...],
    ranking_reasons: {
        "1": "Strong hook at 0:03, curiosity pattern, TikTok-optimal pacing",
        "2": "Good visual variety, solid hook, below-average market score"
    }
  }
```

Infrastructure:
- `explainability/reason_builder.py` — đã có
- `explainability/summary.py` — đã có
- `explainability/confidence.py` — đã có
- `ai_output_ranking` trong result_json — đã có

### D.3 — "Learn from AI" Mode

```
After viewing AI explanation:
  "Apply these settings to next render:
  [✓] Prioritize curiosity hooks
  [✓] Prefer fast-paced segments  
  [  ] Add hook overlay text
  → [Save as my preference]"
```

**Effort**: 2-3 tuần  
**Risk**: LOW — chỉ đọc existing data  
**Impact**: HIGH — trust, retention, learning loop

---

## PHASE E — Strategy Variants + One-Click AI (Tuần 10-16)

**Objective**: AI proposes, creator picks. True semi-tech UX.

### E.1 — "AI Suggests 3 Strategies" UI

```
After source upload:

  🤖 AI analyzed your video (3:47)
  
  Strategy A — Hook-Optimized
  "Focus on your strongest opening hooks.
  Best for: TikTok, first-time viewers"
  [Preview thumbnails...]  [Select →]
  
  Strategy B — Story Arc
  "Build tension → climax → resolution.
  Best for: engaged followers, longer retention"
  [Preview thumbnails...]  [Select →]
  
  Strategy C — Market-Fit (US/TikTok)
  "Optimized for current trends and platform algorithm"
  [Preview thumbnails...]  [Select →]
  
  [Or configure manually →]
```

### E.2 — Backend: strategy_variants activation

```python
# backend/app/ai/strategy_variants/ đã có:
# variant_generator.py — tạo N strategy variants
# variant_evaluator.py — evaluate mỗi variant
# strategy_reasoner.py — explain each strategy

# Wire vào:
# POST /api/render/suggest-strategies
# Body: { source_path, platform, duration }
# Response: { strategies: [{name, description, config, preview_thumbnails}] }
```

### E.3 — Multi-variant Parallel Render

```
Creator picks 2 strategies → render both in parallel
→ Results show side-by-side comparison
→ Creator picks winner → feed rating back to model
```

Infrastructure:
- `multivariant/multivariant_planner.py` — đã có
- `multivariant/multivariant_execution.py` — đã có
- Cần: UI side-by-side comparison view

**Effort**: 6-8 tuần  
**Risk**: MEDIUM — touches render_pipeline.py  
**Impact**: VERY HIGH — defines the product as AI-first

---

## PHASE F — Vision Quality Intelligence (Tuần 16-24)

**Objective**: AI xem output video và đánh giá quality như một creator.

### F.1 — Thumbnail Visual Quality Check

```python
# extract_thumbnail_frame() đã có trong render_engine

# Add: Claude Haiku vision API
def evaluate_thumbnail_visual(frame_path: str) -> dict:
    """Use Claude Haiku vision to evaluate thumbnail appeal."""
    # Is there a clear subject?
    # Is there text visible for silent viewing?
    # Does it trigger curiosity?
    # What's the dominant emotion?
    return {
        "visual_score": 0-100,
        "improvements": ["Add text overlay", "Crop tighter on subject"],
        "hook_potential": "medium"
    }
```

### F.2 — Post-render AI Quality Report

```
╔═══════════════════════════════════════════╗
║  🎯 AI Quality Report — Clip 1            ║
║                                           ║
║  Technical: ✓ Pass                        ║
║  Creator Quality: 78/100                  ║
║                                           ║
║  Opportunities:                           ║
║  ⚡ Add hook text overlay (0:00-0:03)     ║
║  📝 Reduce subtitle density (too dense)   ║
║  🎵 Background music would improve pace   ║
║                                           ║
║  [Apply suggestions →]  [Ignore]          ║
╚═══════════════════════════════════════════╝
```

### F.3 — Model Selection Strategy

| Model | Use case | Cost per video |
|---|---|---|
| Groq llama-3.1-8b | Transcript analysis, hook detection | $0 (free tier) |
| Groq llama-3.3-70b | Strategy reasoning | $0 (free tier) |
| Claude Haiku 4.5 | Vision quality check, thumbnail eval | ~$0.001 |
| Claude Sonnet 4.6 | Deep creative analysis (opt-in) | ~$0.01 |

**Start with Groq for all text analysis** (free, fast, sufficient quality).  
**Add Claude Haiku for vision** when creator wants quality insights.  
**Claude Sonnet optional premium tier** for serious creators.

---

## KẾT QUẢ KỲ VỌNG

| Phase | Tính năng thấy được | AI thực sự làm gì |
|---|---|---|
| A | "AI analyzed your video" | LLM reads transcript, detects semantic hooks |
| B | "Platform-optimized clips" | AI applies TikTok/YouTube best practice rules |
| C | "AI learned from 32 of your clips" | Ridge regression + Creator DNA personalization |
| D | "Why this clip ranked #1" | Explainability reasons from AI decision chain |
| E | "3 strategies suggested by AI" | Multi-variant planning with strategy reasoning |
| F | "AI quality score: 82/100" | Vision model evaluates thumbnail + visual quality |

---

## DEPENDENCIES VÀ RISKS

| Dependency | Phased A | Phase B | Phase C | Phase D | Phase E | Phase F |
|---|---|---|---|---|---|---|
| Groq API key từ user | Required | Required | - | - | Optional | - |
| Claude API key | - | - | - | - | - | Optional |
| render_pipeline.py changes | - | - | - | - | MEDIUM | - |
| ai_director.py changes | - | LOW | LOW | - | MEDIUM | - |
| New API endpoints | LOW | LOW | MEDIUM | LOW | MEDIUM | LOW |
| Frontend new UI | MEDIUM | - | HIGH | MEDIUM | HIGH | MEDIUM |

**Lowest risk path**: A → D → B → C → E → F  
(Start với activation + explainability trước khi build learning loop)

---

## METRICS ĐO LƯỜNG THÀNH CÔNG

| Metric | Baseline | Target sau 12 tuần |
|---|---|---|
| % users với cloud AI enabled | 0% | 40% |
| AI confidence score (avg) | N/A | ≥0.65 |
| Creator feedback ratings collected | 0 | ≥500 |
| Clip reuse rate (same creator re-renders same source) | Unknown | +20% |
| "I understand why this clip was chosen" (NPS signal) | Unknown | Positive |

---

*Tài liệu này là roadmap. Update file này khi priorities thay đổi. Không phải append-only.*
