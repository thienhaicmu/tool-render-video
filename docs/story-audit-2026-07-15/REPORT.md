# REVIEW TOÀN DIỆN STORY MODEL VÀ STORY MODE SAU NÂNG CẤP AI PLAN 3-CALL

Ngày audit: 2026-07-15
Phạm vi: code, prompt, schema, API, UI, render, test, database/log và output thực tế có sẵn.
Nguyên tắc: code là sự thật về triển khai; output thực tế là sự thật về chất lượng sản phẩm.

## 1. Executive Summary

**Kết luận:** kiến trúc Story Compiler mới là một bước tiến đúng hướng về phân tách trách nhiệm, nhưng chưa đủ bằng chứng để kết luận chất lượng video sau nâng cấp đã tăng. Commit 3-call `43ee6001` được tạo ngày 2026-07-15, trong khi toàn bộ Story job/video thực tế tìm thấy đều từ ngày 2026-07-13/14.

Các điểm chính:

- Tên “3-call” chỉ đúng với nhánh `paste`, compiler bật, không có base video, đủ callback và không phát sinh repair/fallback.
- Nhánh `idea` bỏ qua Understanding, nên happy path chỉ có 2 call: Writer và Structure.
- Repair JSON, repair script, idea expansion và provider fallback có thể đẩy số call lên 4 hoặc nhiều hơn.
- Call 1 có fact/quote validation, nhưng kết quả fail chỉ log; không chặn Call 2.
- Context bị mất đáng kể giữa Call 1 → Call 2 → Call 3, đặc biệt relationship, location detail, event time/location/character/quote.
- Không persist output từng call, không checkpoint, không resume từ pass giữa, không rerun riêng Writer/Structure, không cancel.
- Frontend hiển thị tiến độ giả bằng timer; không phản ánh pass backend. Warning/readiness/cost từ backend phần lớn không được UI dùng ở AI-plan flow.
- Story render có voice cast, emotion-aware TTS, bounded parallel TTS, BGM ducking và QA kỹ thuật cơ bản; nhưng visual vẫn là procedural SVG/chibi, ít shot grammar và có xu hướng slideshow lặp.
- Focused backend tests đạt `95/95`; frontend production build thành công.
- Baseline video trước nâng cấp đạt kỹ thuật container/audio ổn, nhưng story/visual/dialogue/retention còn yếu. Baseline này không được dùng để chấm chất lượng 3-call hậu nâng cấp.

**Quyết định khuyến nghị:** chưa rollout rộng dựa trên tuyên bố “3-call improves quality”. Chỉ nên rollout có kiểm soát sau khi có persistence/observability theo pass, hard quality gates tối thiểu và bộ A/B evaluation với output thật.

## 2. Story Model Architecture

Mô hình chính nằm tại `backend/app/domain/story_plan_v2.py` và gồm:

- `StoryPlan`: metadata, story bible, visuals, timeline và render state.
- `CharacterDef`: id, name, canonical description, age, gender, voice metadata, archetype, asset.
- `SettingDef`: id, name, canonical description, scene kind, asset, scene spec.
- `Visual`: setting/character references và các field prompt cũ.
- `Beat`/`Line`: spoken content, speaker, visual, emotion, pose, pacing, hook, BGM và overlay behavior.
- `RenderState`: voices, masters, beat audio, cues, duration và asset paths.

Điểm tốt là ID/ref được chuẩn hóa và cơ khí render được derive bằng code. Điểm yếu là AI contract, editorial model và mutable render state vẫn nằm trong cùng root object; facts, relationships và event chronology từ Call 1 không trở thành first-class domain entities.

## 3. Story Workflow

Luồng thực tế:

1. Frontend nhận paste/idea/paste_json.
2. AI plan chạy async và frontend poll.
3. Backend chọn provider chain và gọi `run_super_plan`.
4. Compiler hoặc legacy single-call tạo `StoryPlan`.
5. Plan được normalize, cap visuals, repair refs, derive styling và lint.
6. Người dùng review/edit plan, preview SVG, chọn voice/assets.
7. Frontend render bằng `story_plan_override`.
8. Backend cast voice, synthesize TTS, tạo visual/overlay, cue render, assemble, mix BGM, QA và finalize.

Do render luôn dùng plan override sau review, metadata final thường ghi `plan_source=override`; provenance của provider/model tạo plan có thể bị mất.

## 4. AI 3-Call Architecture

Dispatcher ở `backend/app/features/render/ai/llm/__init__.py:314` chọn provider, model và ba callback. Compiler ở `story_director_v2.py:326` điều phối các pass.

Ma trận call thực tế:

| Nhánh | Base calls | Có thể tăng bởi |
|---|---:|---|
| paste + compiler | 3 | writer repair, JSON repair, provider fallback, compiler→legacy fallback |
| idea + compiler | 2 | idea expansion, JSON repair, provider fallback, compiler→legacy fallback |
| base video | 1 legacy | JSON repair/provider fallback |
| compiler off/thiếu writer | 1 legacy | JSON repair/provider fallback |

Vì vậy “3-call” nên được xem là một strategy có nhánh, không phải invariant.

## 5. Call 1 Review — Understanding

Chỉ chạy với source `paste`. Prompt yêu cầu topic, genre, tone, characters, locations, relationships, goals/conflicts và 8–25 ordered events có verbatim quote.

Điểm tốt:

- Có JSON contract riêng.
- Có quote matching, tail coverage và event-order check trong `story_understanding.py:152`.
- Tách fact extraction khỏi creative writing.

Rủi ro:

- Validation report chỉ được log ở `story_director_v2.py:359`; quote verification thấp, mất ending hoặc sai order vẫn đi tiếp.
- Event anchor matching tương đối mềm, dễ coi một event là covered qua token chung.
- Source dài hơn `STORY_MAX_SOURCE_CHARS=60000` bị cắt đầu vào; compiler không chunk.

## 6. Call 2 Review — Writer

Writer nhận source/idea, một understanding block nén và craft/style rules. Output là screenplay-lite text, không phải JSON.

Điểm tốt:

- Prompt tập trung hook, arc, show-don’t-tell, dialogue đọc thành tiếng và genre voice.
- Có script validator và một vòng targeted repair cho missing major events.
- Idea có bounded expansion khi quá ngắn.

Rủi ro:

- Unknown speaker, tail failure và script ngắn chủ yếu là warning.
- Repair chỉ tập trung missing events, không chữa relationship drift, voice drift, cliché, dialogue ratio hoặc emotional arc.
- Script chưa được persist nên không thể review, diff hoặc approve độc lập.

## 7. Call 3 Review — Structure

Structure chuyển screenplay thành strict `StoryPlan` JSON, pin character IDs và yêu cầu giữ wording verbatim.

Điểm tốt:

- Schema chặt hơn, lean contract giảm token cơ khí.
- Normalize/validate refs sau parse giúp plan renderable.
- Multiline beats cho phép dialogue nhiều giọng trong cùng shot.

Rủi ro:

- Call 3 chỉ nhận script và character table; không nhận full facts/relationships/locations/events/quotes.
- Không có deterministic round-trip validator chứng minh toàn bộ script đã được map đủ và đúng thứ tự.
- Prompt vừa nói “verbatim” vừa cho phép trim filler, tạo vùng mơ hồ.
- Parse repair có thể thêm một LLM call nhưng không được phản ánh trong `authoring_mode` hay cost UI.

## 8. Context Passing Review

Call 1 → Call 2 giữ character basics, location names, goals và event summaries, nhưng làm mất topic/genre/tone đã extract, relationship edges, location descriptions, event timestamps, event locations, event character IDs, quotes và verification flags.

Call 2 → Call 3 chỉ giữ screenplay và character table. Mọi provenance từ source gần như mất tại boundary cuối. Đây là gap lớn nhất về fidelity: pass cuối có quyền tái cấu trúc nhưng không có fact ledger để tự kiểm.

## 9. Failure Handling Review

- Compiler exception fallback về legacy single-call toàn phần.
- Provider failure chuyển sang provider kế tiếp và rerun từ đầu.
- JSON malformed có một repair call.
- Missing events có một Writer repair.
- TTS/render/BGM nhiều nơi fail-open để vẫn giao video.

Thiết kế ưu tiên availability, nhưng có thể giao output “technically complete, semantically degraded”. Không có error budget theo pass, quality state machine hay degraded-mode label cho người dùng.

## 10. Cost & Latency Review

Estimator ở `story_director_v2.py:33` dùng phép ước lượng chars/4 và rate môi trường, không phải usage thật.

Ví dụ theo default gpt-4o, source 10.000 ký tự, ceiling 10:

- Legacy estimate: khoảng `$0.0384`.
- Compiler estimate: khoảng `$0.0874`.
- Tỷ lệ ước lượng: khoảng `2.27x`.

Estimator bỏ sót repair, idea expansion, provider fallback, compiler→legacy fallback và cache hit. Latency pass là tuần tự; chưa có metric per-pass nên không thể xác nhận P50/P95. Suy luận kỹ thuật hợp lý là happy-path latency tăng gần tổng latency của 2–3 request, nhưng chưa có số đo production.

## 11. Story Input Review

- `paste`: giữ text thô nhưng `_fit` cắt ở 60.000 ký tự.
- `idea`: dùng duration/genre/language/art style làm creative brief.
- `paste_json`: bỏ qua AI, validate rồi review.
- base video: rơi về legacy path.

Không có chunk/merge compiler cho chapter dài. UI có warning tail cut, nhưng đây vẫn là fidelity loss nghiêm trọng và không nên chỉ xử lý bằng hướng dẫn người dùng tự tách chương.

## 12. Story Understanding Review

Schema Understanding có nền tảng tốt để trở thành fact ledger, nhưng hiện mới là transient prompt payload. Chưa có:

- stable entity aliases;
- confidence/uncertainty per fact;
- contradiction detection;
- source span offsets;
- persistence và human review;
- downstream enforcement.

Kết luận: tốt về ý tưởng, chưa đủ mạnh như một contract xuyên pipeline.

## 13. Adaptation Fidelity Review

Đánh giá implementation: **5/10**. Có quote/event checks nhưng fail-open và context loss mạnh trước Structure.

Đánh giá output hậu nâng cấp: **N/A** vì không có artifact 3-call thật. Không được dùng baseline idea trước nâng cấp để khẳng định fidelity.

## 14. Adaptation Creativity Review

Writer prompt có craft rules và genre packs, giúp tăng không gian sáng tạo so với “one giant JSON call”. Tuy nhiên hệ thống chưa đo:

- novelty;
- cliché density;
- adaptation distance;
- dialogue/narration balance;
- emotional payoff;
- source-preserving invention.

Đánh giá implementation potential: **7/10**; output hậu nâng cấp: **N/A**.

## 15. Story Quality Review

Baseline trước nâng cấp có arc hiểu được nhưng generic, hook yếu, xung đột và payoff mỏng. 30 beats/231.6s tạo cảm giác dàn đều hơn là tăng tiến.

3-call có khả năng cải thiện prose vì Writer được tách khỏi JSON, nhưng chưa có post-upgrade render/script để xác nhận.

## 16. Beat Design Review

Beat là đơn vị vừa editorial vừa render. “One beat = one shot” giúp pipeline đơn giản, nhưng một beat multiline có thể chứa nhiều lượt thoại mà vẫn chỉ một visual/camera state. Không có beat role bắt buộc như setup/escalation/reversal/payoff và không có coverage validator cho five-act quota sau Structure.

## 17. Pacing Review

Compiler thêm reading speed, pause và hold labels; code derive timing từ TTS. Đây là cải thiện kỹ thuật thật.

Gap:

- không có pacing curve cấp story;
- không đo shot-duration variance;
- không gate duration drift theo target ở AI plan;
- baseline thực tế có target 180s nhưng ra 231.6s;
- UI chỉ cảnh báo idea drift trên 30%.

## 18. Narration Review

Writer prompt yêu cầu spoken prose và show-don’t-tell. Structure phải giữ wording. Tuy nhiên baseline trước nâng cấp chứa nhiều câu kể ngôi ba được gán cho character speaker, cho thấy boundary giữa narrator và character voice từng yếu.

Không có validator về POV consistency, sentence speakability, repetition semantic hoặc pronunciation risk.

## 19. Dialogue Review

Multiline contract và per-character TTS là nền tảng tốt. Nhưng chưa có quality gates cho:

- tỷ lệ dialogue;
- character voice distinctness;
- alternating-speaker coherence;
- dialogue tag leakage;
- monologue length;
- subtext/cliché.

Baseline trước nâng cấp gần như không có dialogue thật: score tham khảo **1/10**, không đại diện 3-call.

## 20. Character System Review

Character ID, canonical description, gender, archetype, asset và voice cast được nối xuyên model → render. Series memory có thể khóa voice giữa chapter.

Thiếu relationship graph và character-state timeline trong StoryPlan. Call 1 có relationships/goals nhưng chúng biến mất trước output domain.

## 21. Character Quality Review

Prompt yêu cầu canonical look nhưng visual resolver có thể map nhân vật Việt sang library asset không phù hợp vùng văn hóa. Khi asset không có, procedural preset tạo identity nhất quán tương đối nhưng thẩm mỹ generic.

Beauty/appeal hậu nâng cấp: **N/A**. Baseline visual tham khảo: **3/10** về độ đẹp, **5/10** về nhận diện nhất quán.

## 22. Character Continuity Review

Điểm tốt:

- character IDs được pin ở Structure;
- voice mapping deterministic;
- master images theo speaker/emotion/pose;
- refs được normalize.

Điểm yếu:

- appearance không có structured attributes/version;
- relationship/state continuity không persisted;
- non-speaking character trong scene có thể biến mất vì overlay chủ yếu driven bởi speaker.

## 23. Scene System Review

`Setting` + `Visual` xấp xỉ scene system. Scene kind vocabulary giúp procedural backgrounds render chắc chắn. Nhưng không có first-class Scene với purpose, participants, time, location continuity, entry/exit state và coverage.

## 24. Shot System Review

Không có Shot model đúng nghĩa. Beat có focus/motion/anchor/scale/transition nhưng thiếu shot size, angle, lens, camera position, blocking, eyeline, axis và composition intent. “One beat = one shot” hiện là mapping kỹ thuật, chưa phải shot grammar điện ảnh.

## 25. Frame Composition Review

Character overlay có left/center/right, scale và motion. Đây là composition primitives tối thiểu. Baseline contact sheet cho thấy nhiều frame dùng cùng background, nhân vật đổi vị trí đơn giản, negative space lớn và ít depth.

Artifact: `docs/story-audit-2026-07-15/artifacts/baseline-contact-sheet.png`.

## 26. Visual Prompt Review

Story Mode ép provider SVG ở `story_pipeline_v2.py:424`. AI strict schema lean không yêu cầu image prompt; `Visual.prompt`, `negative_prompt` và `tier` vẫn còn trong type/UI nhưng render SVG không dùng chúng.

Đây là contract drift: UI/type tạo cảm giác visual prompt có tác dụng, trong khi runtime truth là scene kind + asset/procedural composition.

## 27. Visual Quality Review

Ưu điểm: offline, deterministic, chi phí `$0`, không phụ thuộc image provider, identity có thể ổn định.

Giới hạn: procedural SVG/chibi, ít scene variation, ít camera grammar, background reuse cao, khó đạt cinematic realism. Baseline score tham khảo **3/10**; hậu nâng cấp **N/A** vì Call architecture không thay đổi năng lực render cốt lõi.

## 28. Voice System Review

`story_voice_cast.py` chọn engine theo language, pool theo gender, tránh trùng voice đến khi pool hết, giữ user override và có series lock. Đây là subsystem rõ ràng và deterministic.

Rủi ro: gender normalization mặc định mọi giá trị không phải male thành female; `voice_style` trong model chưa tham gia casting; provider fallback có thể đổi chất giọng.

## 29. Audio Review

`story_narration.py` synthesize theo beat/line, emotion đi vào TTS, dialogue nhiều speaker được concat và có line spans; mặc định 4 workers. BGM dùng per-beat mood/intensity và sidechain ducking.

Baseline thực tế: integrated loudness khoảng `-16.98 LUFS`, true peak `-4.01 dBTP`, LRA `6.70`, có nhiều pause 0.5–0.9s. Chỉ có thể kết luận audio kỹ thuật ổn; không đủ công cụ nghe để chấm tự nhiên, phát âm, diễn cảm hay voice fit.

## 30. Timeline Review

Timeline có beat ordering, per-line spans, TTS-derived duration, pauses, transitions và BGM cues. Người dùng có thể reorder/add/delete/edit.

Thiếu timeline-level constraints cho continuity, target duration, scene grouping, shot diversity và emotional curve. Normalize ưu tiên renderability hơn editorial correctness.

## 31. Final Video Review

Video baseline: 1920×1080, H.264, 60fps, AAC stereo 48kHz, 231.642s, khoảng 23.95MB/827kbps. Container và audio technically valid.

Product impression từ frame sampling: slideshow/chibi, visual repetition cao, ít shot variation, khó giữ retention dài. Đây là output trước 3-call và chỉ dùng làm baseline.

## 32. Frontend Review

Story Studio có input, async planning, project autosave, versioning, undo/redo, review/edit, SVG preview, asset/voice selection, monitor và render.

Gap chính:

- `StoryPlanResponse` không khai báo `authoring_mode`, `readiness`, `cost_preflight` dù backend trả về.
- `onGenerate` không hiển thị AI-plan warnings/asset resolution; chỉ xử lý truncation/duration drift.
- không có pass outputs, pass timing, provider/model thật, token/cost thật hoặc rerun riêng pass.

## 33. UI/UX Review

`StoryDirectorConsole.tsx:25` tăng step mỗi 1.2s bằng timer. Các label như “Reading & understanding” vẫn xuất hiện cho idea dù Call 1 không chạy. Đây là progress theater, không phải observability.

UX review/edit khá giàu tính năng, nhưng người dùng không biết plan đang degraded, fallback provider nào đã chạy, facts nào chưa verified hay warning nào cần xử lý trước render.

## 34. Backend Review

Backend chia module tương đối tốt: prompts, parser/schema, compiler, router, domain và render stages. Defensive normalization/test coverage khá.

Rủi ro backend lớn nhất:

- transient in-memory plan job registry, TTL 30 phút;
- không checkpoint;
- status không theo pass;
- fail-open semantic gates;
- metadata provider/model có thể ghi primary thay vì provider fallback thực tế;
- override render làm mất AI provenance.

## 35. Provider Review

Provider chain hỗ trợ OpenAI, Gemini, Claude và fallback. Cache/retry/key rotation tồn tại ở provider layer.

Nhưng fallback rerun toàn compiler theo provider mới; cache là provider-specific. Chất lượng có thể thay đổi âm thầm. Result không reliably phản ánh provider thực sự thành công, ảnh hưởng reproducibility và cost attribution.

## 36. Model Review

Default Story model là `gpt-4o` qua `STORY_SUPER_MODEL`; Gemini default `gemini-2.5-flash`; Claude default Haiku. Cùng một model được dùng cho Understanding, Writer và Structure trong một provider attempt.

Không có role-based routing. Writer cần model mạnh về prose; Structure cần model mạnh về constrained JSON; Understanding cần extraction/grounding. Dùng một model cho cả ba đơn giản vận hành nhưng không tối ưu quality/cost.

## 37. Prompt 1 Review

Prompt Understanding rõ trách nhiệm, schema đủ rộng và có quote grounding. Cần nâng từ “prompt request + soft log” thành “verified fact contract + hard threshold”. Nên thêm source offsets, aliases, confidence và contradictions.

## 38. Prompt 2 Review

Prompt Writer là phần mạnh nhất của nâng cấp: tách prose khỏi JSON, có craft rules, hook, five-stage arc, genre packs và banned cliché guidance.

Điểm cần sửa trong plan tương lai: truyền full fact ledger có provenance, relationship/setting details, explicit adaptation budget và self-check summary; không chỉ nén event summaries.

## 39. Prompt 3 Review

Prompt Structure nên thuần compiler, nhưng hiện vẫn trao quyền editorial nhỏ (“trim fillers”) và thiếu full fact ledger. Cần deterministic constraints: exact line coverage, order coverage, speaker mapping, event coverage, no invented entity/location và shot diversity budget.

## 40. AI Output Review

Parser/normalizer làm output renderable nhưng có thể che lỗi AI bằng remap/drop/default. Raw output, repaired output và normalization diff không được lưu. Vì vậy không thể trả lời đầy đủ “AI sai ở đâu” sau khi chỉ còn final plan.

## 41. Performance Review

TTS có bounded parallelism và reuse, visual SVG offline, phù hợp performance. AI compiler lại tuần tự và thiếu per-pass telemetry. Long chapter không chunk nên giảm token bằng truncation, đổi performance lấy mất nội dung.

Chưa có benchmark post-upgrade cho P50/P95 plan latency, render latency, memory hoặc concurrency.

## 42. Reliability Review

Reliability kỹ thuật khá nhờ fallback và normalize. Reliability sản phẩm thấp hơn vì nhiều failure semantic không block. Async registry mất khi process restart, không idempotency key/checkpoint/cancel và không durable job state.

## 43. Cost Review

Chi phí visual SVG gần như bằng 0; chi phí chính là LLM + TTS. Compiler làm LLM cost tăng khoảng 2.27x trong ví dụ chuẩn, chưa tính retry/fallback. TTS per-character nên per-line không giảm giá nhưng tăng số request và failure surface.

Cần usage ledger thực tế theo pass/provider/model/cache/retry và show preflight range thay vì một số estimate giả định đúng 3 calls.

## 44. Test Review

Đã chạy:

```text
95 passed in 1.52s
```

Các test tập trung compiler, multiline, plan, endpoint, GD4, narration và BGM. Frontend production build thành công.

Thiếu:

- real-provider integration test;
- golden story set đa ngôn ngữ/genre/độ dài;
- A/B legacy vs compiler;
- hallucination/fidelity scoring;
- UI tests cho Story Studio;
- post-upgrade end-to-end render artifact;
- measured token/cost/latency;
- restart/resume/fallback provenance tests.

## 45. Findings

| ID | Mức | Finding | Ảnh hưởng |
|---|---|---|---|
| F-01 | Critical | Không có output thật hậu commit 3-call | Không thể xác nhận chất lượng/cost/latency production |
| F-02 | High | Understanding/script semantic checks fail-open | Fact drift hoặc mất ending vẫn đi tiếp |
| F-03 | High | Context loss qua hai boundary | Structure không còn fact/relationship/location provenance |
| F-04 | High | Không persist/checkpoint từng call | Không audit, resume, rerun riêng pass hoặc debug chính xác |
| F-05 | High | Compiler truncate source >60k, không chunk | Mất phần cuối chapter |
| F-06 | High | UI progress giả và không hiện quality signals | Người dùng hiểu sai trạng thái/chất lượng |
| F-07 | High | Visual engine thiếu shot grammar, reuse cao | Video tĩnh, lặp, retention thấp |
| F-08 | High | Provider/model provenance có thể sai/mất | Không reproducible, cost attribution sai |
| F-09 | Medium | `authoring_mode`/cost giả định theo feature flag | Báo “3-call” cho idea/base-video/repair không đúng |
| F-10 | Medium | Cùng model cho mọi role | Không tối ưu prose/grounding/JSON/cost |
| F-11 | Medium | Visual prompt fields/UI không có runtime effect | Contract và kỳ vọng người dùng lệch nhau |
| F-12 | Medium | Async registry volatile, không cancel | Restart mất job; UX timeout khó kiểm soát |
| F-13 | Medium | Không có quality eval/golden/A-B suite | Regression chất lượng không được bắt |
| F-14 | Medium | Không round-trip validate script→plan | Có thể rơi/méo/reorder content ở Call 3 |
| F-15 | Medium | Hook không được hard validate | Plan có thể không có hook |
| F-16 | Medium | QA final không hard-fail missing audio | Video im lặng vẫn có thể completed |
| F-17 | Low | Comment/log còn ghi “super plan (1 call)” | Quan sát và bảo trì gây nhầm |

## 46. Technical Score

| Hạng mục | Điểm /10 |
|---|---:|
| Architecture | 6.0 |
| Backend | 7.0 |
| Frontend | 5.5 |
| AI workflow correctness | 5.5 |
| Reliability | 5.5 |
| Performance | 6.5 |
| Observability | 3.5 |
| Test coverage | 6.0 |
| Security/safety surface | 7.0 |
| **Tổng hợp** | **5.8** |

Điểm phản ánh implementation hiện tại, không phải chất lượng content hậu nâng cấp.

## 47. Product Quality Score

**3-call post-upgrade:** `N/A — chưa đủ bằng chứng output thật`.

Baseline trước nâng cấp, chỉ để định vị khoảng cách:

| Hạng mục | Điểm /10 |
|---|---:|
| Story coherence | 4 |
| Hook | 1 |
| Pacing | 4 |
| Narration | 4 |
| Dialogue | 1 |
| Character appeal | 3 |
| Character continuity | 5 |
| Scene design | 4 |
| Shot design | 2 |
| Frame composition | 3 |
| Visual quality | 3 |
| Audio technical | 7 |
| Voice naturalness | N/A |
| Editing/retention | 3 / 2 |
| **Final product baseline** | **3.3** |

## 48. Gap Analysis

Khoảng cách từ hiện tại đến một Story product đáng tin cậy:

- Từ “3 prompts” đến “durable compiler pipeline”.
- Từ soft validation đến enforceable quality gates.
- Từ transient understanding đến persisted fact/relationship ledger.
- Từ beat-as-shot đến scene/sequence/shot grammar.
- Từ procedural asset placement đến composition-aware visual direction.
- Từ timer progress đến real pass telemetry.
- Từ estimated cost đến actual usage ledger.
- Từ unit tests đến output-based quality evaluation.

## 49. Architecture Upgrade Plan

Đề xuất target architecture:

```text
Input
  -> Source normalizer/chunker
  -> Pass 1 UnderstandingArtifact (persisted + validated)
  -> Quality Gate U
  -> Pass 2 ScriptArtifact (persisted + diffable)
  -> Quality Gate W
  -> Pass 3 StoryPlanArtifact (persisted)
  -> Deterministic round-trip + refs + duration + diversity gates
  -> Human Review
  -> RenderPlan snapshot with full provenance
  -> Render/QA/Evaluation
```

Mỗi artifact cần `run_id`, pass, provider, model, prompt version/hash, input/output hash, token usage, latency, cache/retry/fallback, validation report và parent artifact ID.

## 50. AI Upgrade Plan

1. Biến pass count thành runtime trace, không hard-code “3”.
2. Persist raw/parsed/validated artifacts theo pass.
3. Hard-gate Understanding theo quote coverage, tail, order và major events.
4. Truyền full compact fact ledger vào Writer và Structure.
5. Thêm deterministic script→plan line/event/order coverage validator.
6. Chunk long sources theo semantic boundaries rồi merge fact ledger.
7. Route model theo role và benchmark: extraction, creative writer, constrained compiler.
8. Ghi provider/model thực sự thắng fallback.
9. Cho phép rerun riêng Writer hoặc Structure từ artifact đã duyệt.
10. Xây golden eval và A/B harness trước khi đổi default.

## 51. Product Quality Upgrade Plan

1. Thêm first-class `Sequence`, `Scene`, `Shot`, `CharacterState` và relationship graph.
2. Bắt buộc hook/reversal/payoff coverage theo genre/target duration.
3. Đo dialogue ratio, POV consistency, cliché/repetition và emotional curve.
4. Thêm shot grammar: size, angle, blocking, eyeline, composition, motion intent.
5. Thêm visual diversity budget và background reuse threshold.
6. Hiển thị missing/unverified facts trong Review.
7. Hard-fail spoken beats có TTS rỗng; kiểm tra silence/loudness/clipping.
8. Tạo post-render contact sheet, perceptual checks và human rating form.
9. Đánh giá voice naturalness/phát âm bằng mẫu nghe có rubric.
10. Chỉ tuyên bố quality uplift khi A/B đạt ngưỡng thống kê và reviewer agreement.

## 52. Roadmap

**Phase 0 — Evidence (1–2 ngày):** tạo 10–20 output 3-call thật, lưu scripts/plans/videos, đo tokens/latency/cost, A/B với legacy.

**Phase 1 — Trust (3–5 ngày):** pass telemetry, persistence, provenance, real progress, cancel/resume, hard gates và long-source chunking.

**Phase 2 — Editorial Quality (1–2 tuần):** fact ledger xuyên pass, round-trip validator, scene/shot model, duration/arc/dialogue evaluators.

**Phase 3 — Visual/Audio Quality (1–2 tuần):** composition grammar, diversity controls, asset-region fit, audio hard QA và listening tests.

**Phase 4 — Controlled Rollout:** feature cohort, quality dashboard, rollback threshold, weekly golden-set regression.

## 53. Priorities

| Ưu tiên | Việc | Lý do |
|---|---|---|
| P0 | Tạo và đánh giá output thật hậu nâng cấp | Hiện không có bằng chứng sản phẩm |
| P0 | Persist + telemetry từng pass | Nền tảng audit/reliability/cost |
| P0 | Hard gates + script→plan coverage | Chặn semantic degradation |
| P0 | Long-source chunking | Ngăn mất ending |
| P1 | Provenance provider/model/prompt | Reproducibility |
| P1 | Real UI progress + warning/cost/readiness | Trust và quyết định trước render |
| P1 | Golden A/B quality suite | Chống regression |
| P1 | Scene/shot grammar + diversity | Nâng chất lượng hình/retention |
| P2 | Role-based model routing | Tối ưu quality/cost sau khi có benchmark |
| P2 | Voice listening eval + perceptual video QA | Hoàn thiện product score |

## 54. Final Recommendation

**Go có điều kiện cho engineering validation; No-Go cho tuyên bố product-quality uplift hoặc rollout rộng.**

Giữ compiler dưới feature flag/cohort. Trước khi duyệt triển khai tiếp, yêu cầu tối thiểu:

- ít nhất 10 case đa dạng có output thật post-upgrade;
- A/B legacy vs compiler với rubric và blind review;
- actual pass trace/token/cost/latency;
- persisted intermediate artifacts;
- hard gates cho fidelity/tail/script coverage;
- UI hiển thị đúng pass/fallback/warnings;
- provenance end-to-end đến final result.

Không có code sản phẩm, prompt, schema, migration, package hay feature flag nào được thay đổi trong audit này.

REVIEW TOÀN DIỆN STORY MODEL, AI 3-CALL WORKFLOW VÀ CHẤT LƯỢNG SẢN PHẨM ĐÃ HOÀN THÀNH. CHƯA THỰC HIỆN THAY ĐỔI CODE. ĐANG CHỜ NGƯỜI DÙNG DUYỆT AI UPGRADE PLAN VÀ PRODUCT QUALITY ROADMAP.
