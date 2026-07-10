# STORY_MODE_V2 — Implementation Plan (KHOÁ, chờ duyệt)

> Kế thừa Story v1 (P0–P8, merged `a30ac6c1`). v2 thay lõi planning+render, giữ
> `render_format="story"` + Sacred Contracts. Baseline pytest **2723**. Docs↔code: tin code.

---

## 0. QUYẾT ĐỊNH ĐÃ KHOÁ

| # | Quyết định |
|---|-----------|
| K1 | **2 nguồn vào**, cả hai = **1 super call**, **CÙNG output StoryPlan v2**: A=adapt truyện có sẵn · B=sáng tác từ ý tưởng+thời lượng |
| K2 | Chi phí AI = `1 super + N ảnh(≤ceiling) + ~1 TTS` — **phẳng theo độ dài** |
| K3 | Ảnh: **1 ảnh 16:9 rộng/bối cảnh (Visual)**, camera quét vùng `focus`; **không** multi-panel, **không** /shot; **1 beat = 1 focus** (bỏ focus_track) |
| K4 | Nhân vật: `canonical_desc` inject + reference sheet (tùy chọn) |
| K5 | **Bỏ phụ đề** trừ `hook` (cố định `hook_only`; AI chọn beat hook) |
| K6 | TTS batch theo `voice_runs`; **timed transcript (words)**; VI=Gemini · EN/JA=ElevenLabs · fallback edge |
| K7 | `est_sec`=RULE (không AI đoán giây); `dur`=TTS thật; **CUE SHEET tuyệt đối** (`build_cues`, seed) trước render |
| K8 | 14 INVARIANTS toàn vẹn (FK/enum/cap/tất định) |
| K9 | **Input tối giản** — AI/default quyết: `tone`(AI suy) · số ảnh(AI, ≤ceiling) · `aspect`=16:9(default) · `art_style`(AI nếu trống) |
| K10 | FE Story RIÊNG **kế thừa design-system project** (tầng base `components/studio/`); không coupling mode khác, không copy trùng |
| K11 | `render_format="story"`+wire không đổi; StoryPlan v2 additive (blob v1 load được) |

---

## 1. INPUT SOURCES (2 nguồn, 1 pipeline)

```
A · Dán truyện ──────────────→ Super-A → StoryPlan v2 → 🖐Storyboard → images+TTS → render
B · Ý tưởng+thời lượng+thể loại → Super-B (sáng tác gộp) → StoryPlan v2 → 🖐Storyboard → …
```
- Cả hai xuất **cùng schema** → cùng parser/director/pipeline/FE-review. Truyện của B nằm trong `timeline.narration` (review ở Storyboard, không draft riêng).
- **Input tối giản:**
  - Chung: ngôn ngữ (vi/en/ja) · art_style (tùy chọn) · thư mục lưu.
  - A: **Nội dung truyện** (text, bắt buộc — ngắn/dài đều được).
  - B: **Ý tưởng** (bắt buộc) · **thời lượng** (phút) · **thể loại**.
  - Ẩn/AI-lo: tone · số ảnh · aspect(16:9) · subtitle(hook_only).

---

## 2. DATA MODEL (locked — `domain/story_plan.py` schema_version=2)

### 2.1 Enum & hằng
```python
FOCUS=("wide","left","center","right","top","bottom","close")
MOTION=("zoom_in","zoom_out","pan_left","pan_right","pan_up","pan_down","static")
TRANSITION=("cut","fade","slide","zoom","flash","to_black"); TIER=("low","medium","high"); GENDER=("male","female","")
SUBTITLE_MODE=("hook_only","full","off")
ASPECT_SIZE={"16:9":(1536,1024),"9:16":(1024,1536),"1:1":(1024,1024)}
CPS={"vi":15.0,"en":14.0,"ja":8.0}; TRANSITION_SEC=0.4; MIN_BEAT_SEC=1.5
CROP_RECT={"wide":(0,0,1,1),"center":(.15,.10,.70,.80),"left":(0,.05,.62,.90),
           "right":(.38,.05,.62,.90),"top":(.05,0,.90,.62),"bottom":(.05,.38,.90,.62),"close":(.28,.22,.44,.44)}
```

### 2.2 CONTRACT AI (bất biến — super prompt sinh)
```python
CharacterDef{id,name,canonical_desc,age="",gender="",voice_gender="",voice_style=""}
SettingDef  {id,name,canonical_desc}
Visual      {id,setting_id="",prompt="",negative_prompt="",character_ids=[],tier="medium"}   # đơn vị SINH ẢNH
Beat        {id,narration="",speaker_id="",visual_id="",focus="center",motion="zoom_in",
             emotion="normal",reading_speed=1.0,pause_after=0.0,hold_sec=0.0,
             transition_in="cut",hook=False,hook_text=""}   # 1 beat=1 focus; KHÔNG est_sec/focus_track
```

### 2.3 RENDER STATE (pipeline điền, keyed-by-id, persist resume)
```python
Word{text,start,end}
BeatAudio{path,dur,words:[Word]}                                  # timed transcript
Cue{beat_id,visual_id,start_sec,end_sec,crop_from,crop_to,transition,transition_sec,
    hook,hook_text,audio_path,subtitle=""}                        # đã RESOLVE HẾT
RenderState{visual_assets:{vid→path}, voices:{cid→(engine,vid)}, refs:{cid→path},
            beat_audio:{bid→BeatAudio}, cues:[Cue], total_sec:0.0}
```

### 2.4 StoryPlan
```python
StoryPlan{schema_version=2, seed=0, series_id="",chapter_no=0,
          language="",art_style="",aspect_ratio="16:9",reading_pace="normal",topic="",tone="",
          characters:[CharacterDef], settings:[SettingDef], visuals:[Visual](≤ceiling),
          timeline:[Beat], render:RenderState}
          # legacy v1 (scenes/story_bible): parser bỏ qua, chỉ để load blob cũ
```

### 2.5 INVARIANTS (`validate_refs()` enforce, tất định, never raise)
INV1 beat.visual_id∈visuals(drop dangling) · INV2 speaker_id∈chars∪"" · INV3 setting_id∈settings∪"" ·
INV4 char_ids⊆chars · INV5 focus/motion/transition/tier/gender∈enum(default) · INV6 len(visuals)≤ceiling ·
INV7 id unique(slug+_2) · INV8 beat: narration≠"" ∨ hold_sec>0(else drop); timeline≠[] ·
INV9 render.* KHÔNG do AI set(parser drop) · INV10 cues=f(contract,dur,seed) tất định ·
INV11 transition"random"resolve tại build_cues(seed) · INV12 total_sec trừ overlap(khớp QA#8) ·
INV13 cùng visual: cue[k+1].crop_from==cue[k].crop_to · INV14 ∀cue start<end, chuỗi liên tục.

### 2.6 Timing rules
```
beat_est_sec(beat,lang)= len(narration)/CPS[lang]/reading_speed  if narration else hold_sec   # FE preview
build_cues(plan): t=0;prev=None;prevcrop=None;rng=seed  → mỗi beat: dur=beat_audio.dur|hold_sec;
   same=visual_id==prev; trans=cut if same else resolve_random(transition_in,rng); tsec=0|TRANSITION_SEC;
   target=CROP_RECT[focus]; crop_from=prevcrop if same else motion_from(target,motion); crop_to=motion_to(...);
   start=t-(0|tsec); end=start+dur+pause_after; append Cue; t=end;prev=vid;prevcrop=crop_to
   → render.cues, render.total_sec=t
image_timeline()=[(c.visual_id,c.start,c.end)…]   # "hình nào ở giây nào"
voice_runs(plan)= gom beat liên tiếp cùng speaker_id → mỗi run 1 TTS call
```

---

## 3. SUPER PROMPT (kiến trúc khoa học — 2 builder, 1 schema)

Cấu trúc mỗi prompt (system+user), suy luận theo **thứ tự phụ thuộc** trong 1 call:
`[ROLE]→[INPUT]→[METHOD: (a)characters→(b)settings→(c)visuals≤ceiling→(d)timeline]→[SCHEMA JSON contract 2.2]→[HARD RULES=INV]→[SELF-CHECK refs]`.

- **A** `build_super_story_prompt(chapter,language,art_style,aspect,subtitle_mode,ceiling)` — "ADAPT truyện này".
- **B** `build_super_idea_prompt(idea,duration_sec,genre,language,art_style,aspect,subtitle_mode,ceiling)` — "SÁNG TÁC truyện theo ý tưởng, tổng narration ~ `duration_sec×CPS` ký tự, RỒI dàn dựng".
- **Chung:** cùng SCHEMA + HARD RULES + SELF-CHECK. AI tự xuất `topic/tone`; tự chọn số visual ≤ ceiling; hook thưa; subtitle=off→hook=false. `SUPER_PROMPT_VERSION="s1"`.
- Nguyên tắc: grounding tầng (d⊂c⊂a,b) · constraint=INV(defense-in-depth với parser) · determinism (temp thấp+json_object+seed) · repair bounded (CM-8) · `STORY_PLAN_MODE=quality`(env) tách 2-call chỉ khi ai_eval chứng minh lợi.

---

## 4. BACKEND — phases (mỗi phase: py_compile + unit + full pytest=2723)

### B0 · Models/wire — HIGH (Sacred #2)
`models/render.py`: thêm field inert (additive) — `story_source:str=""`(paste|idea), `story_idea:str=""`,
`story_duration_sec:int=0`, `story_genre:str=""`. (Đã có: story_series_id/chapter_no/art_style/
reading_pace/plan_override; `content_script`=text mode A.) `render_public.FE_FACING_FIELDS`+4;
`render_field_groups` group "story"+4; `api.ts` interface+4. Cập nhật 3 count-pin test (+4).
**Tests** `test_story_v2_fields.py` (default inert, FE-facing, count-pin).

### B1 · Domain v2 — LOW (additive)
`domain/story_plan.py`: dataclass 2.2–2.4 + enum/hằng 2.1 + helpers 2.6 + `validate_refs`/`cap_visuals`/
`reindex`/`build_cues`/`image_timeline`/`voice_runs`/`beat_est_sec`; GIỮ v1 fields.
**Tests** `test_story_plan_v2.py`: roundtrip; blob v1 load(timeline=[]); INV1/5/6/7/8; est_sec;
build_cues tất định(seed→cues, INV13/14); image_timeline.

### B2 · Super prompt + parser — HIGH (Sacred #3)
`ai/llm/story_prompts.py`: `build_super_story_prompt`(A) + `build_super_idea_prompt`(B) + `build_super_repair_prompt`
(§3, format-safe, `SUPER_PROMPT_VERSION`). `ai/llm/story_parser.py`: `parse_super_plan_response(raw,ceiling)→StoryPlan|None`
(extract JSON fence/salvage → contract → validate_refs → cap_visuals → None nếu 0 beat/visual; drop render.* — INV9).
**Xoá** prompt/parser v1. **Tests** `test_super_prompt.py`, `test_super_parser.py`.

### B3 · Super director — HIGH
`ai/llm/story_director.py`: `run_super_plan(*,call_fn,source,chapter=None,idea=None,duration_sec=0,genre="",
language,art_style,aspect_ratio,subtitle_mode,ceiling,series_id,chapter_no,provider_label)→StoryPlan|None`
— source→chọn builder A/B; call→parse; None→repair→parse; nguồn quá dài→2 super-call nối timeline
(re-map id/offset); post: inject canonical_desc vào visual.prompt(char_ids), cap_visuals, validate_refs,
reindex, gán seed. `ai/llm/__init__.py`: `generate_story_plan(...,source,...)→run_super_plan`;
`STORY_AI_PROVIDER`(có)+`STORY_SUPER_MODEL`. **Tests** `test_super_director.py` (A & B, repair, nối, inject).

### B4 · Voice cast — LOW
`story_voice_cast.py`: `apply_voice_cast(plan,language)` đọc characters.voice_gender/style →
`render.voices[cid]=(engine,voice_id)` (language→engine + pool gender); narrator ""→default.
**Tests** cập nhật shape v2.

### B5 · Image gen theo visual + cap — HIGH
`engine/visual/story_image.py`: `generate_visual_image(visual,characters,art_style,w,h,out,seed)` —
prompt+style; refs theo char_ids(render.refs); tier=clamp(visual.tier,`STORY_IMAGE_MAX_TIER`);
size=ASPECT_SIZE; cache; gpt-image-1(có). None→fallback. `story_decision.clamp_tier`+budget.
**Tests** `test_story_visual_image.py`(mock SDK).

### B6 · TTS batch + timed transcript — MEDIUM/HIGH
`engine/audio/story_narration.py`(MỚI): `synthesize_timeline(plan,ctx)` theo `voice_runs`: mỗi run 1 synth.
ElevenLabs`convert_with_timestamps`→Word; Gemini/edge→Whisper-align 1 lần(W5-6)→Word. Cắt theo beat →
`render.beat_audio[bid]=BeatAudio(path,dur,words)`. Fallback per-beat. **Tests** `test_story_narration.py`.

### B7 · Render engine (cue sheet) — CRITICAL (Render Edit Protocol đầy đủ)
- `engine/stages/story/cue_builder.py`(MỚI): `build_cues(plan)`(2.6) sau images+TTS.
- `engine/stages/story/beat_stage.py`(thay shot_stage): `render_one_cue(ctx,plan,part_no,cue)` — nền=
  visual_assets[cue.visual_id]; ffmpeg `zoompan` crop_from→crop_to suốt [start,end]; mux cue.audio_path;
  cue.hook→overlay hook_text(text_overlay); cue.subtitle(full)→burn else KHÔNG phụ đề. Part=cue(Sacred#5).
- `engine/stages/story/assembly_stage.py`: concat theo cues; cue.transition/transition_sec (cùng visual→cut nối liền). Tái dùng content_assembler.
- `engine/pipeline/story_pipeline.py` `run_story` v2: `run_super_plan(source…) → update_story_plan →
  apply_voice_cast → gen images(visuals)→visual_assets → synthesize_timeline → build_cues → seed part=cue →
  render_one_cue loop → assemble → finalize`. Bất biến: stage seq/part enum/result_json#1/QA#8/partial/close_thread_conn.
- **Tests** `test_run_story_v2_e2e.py`(ffmpeg thật, mock super+TTS+image), `test_focus_crop.py`,
  `test_run_story_v2_partial/cancel/resume`. **Render Edit Protocol: baseline→edit→full pytest=baseline.**

### B8 · API — MEDIUM
`features/story/router.py`: `POST /api/story/plan` body{source,chapter|idea,duration_sec,genre,language,
art_style,series_id,chapter_no} → StoryPlan v2 dict(+image_count,estimated_total_sec). GIỮ
`/character/reference-sheet`; MỚI `/visual/preview`(1 Visual→ảnh); `/narration/preview`(1 beat).
`/jobs/{id}/story-plan`→v2. **Tests** `test_story_v2_endpoint.py`.

### Env
`STORY_MAX_IMAGES`(ceiling 20) · `STORY_IMAGE_MAX_TIER`(medium) · `STORY_SUBTITLE_MODE`(hook_only) ·
`STORY_SUPER_MODEL`(gpt-4o) · `STORY_MAX_CHAPTER_CHARS_SINGLE`(18000) · `STORY_AI_PROVIDER`(openai) ·
`STORY_PLAN_MODE`(fast).

---

## 5. FRONTEND — Story Studio RIÊNG, **kế thừa base project**

### 5.1 Tầng BASE (mới, mode-agnostic) — `components/studio/`
`StudioScreen·StudioCard·StudioField·StudioStepper·SegRow·RatioPicker` + `studio.css`(class `.st-*`
CHỈ dùng `var(--surface-1/2,--border,--text-*,--space-*,--ok,--fail,--accent)`). Đây là design-system
base cả 2 studio kế thừa. Content-studio migrate sau (tùy chọn, không chặn).

### 5.2 `story-studio/` (screens riêng, import base + `components/ui/*` — KHÔNG import content-studio)
```
StoryStudio.tsx     orchestrator (source A/B; phase input|review|monitor; /api/story/plan; submitRender)
types.ts            StoryConfig + StoryPlan v2 types
InputScreen.tsx     tab [Truyện có sẵn | Sáng tác ý tưởng]:
                      A: textarea "Nội dung truyện"
                      B: textarea "Ý tưởng" + slider thời lượng(phút) + select thể loại
                      chung: ngôn ngữ · art style(optional) · thư mục(picker+validate)
PlanReview/
  CharactersPanel.tsx  name·canonical_desc(sửa)·voice·nút "Ảnh chuẩn"(tùy chọn)
  VisualsPanel.tsx     grid ≤N: prompt(sửa)·negative·chip char_ids·"Xem thử"(previewVisual)·"Tạo lại"
  TimelineEditor.tsx   ⭐ list beat: narration(sửa)·visual_id(+thumb)·focus·motion·transition·hook+hook_text·
                       ▲▼·✕·＋; badge màu theo visual; est_sec/beat + tổng
  StoryMonitor.tsx     progress theo cue (reuse socket/polling)
api/story.ts        planStory·previewVisual·previewNarration·generateReferenceSheet
```
- **F0** base `components/studio/*`+`studio.css`. **F1** story-studio scaffold+types. **F2** InputScreen(A/B).
  **F3** PlanReview(CharactersPanel+VisualsPanel+TimelineEditor). **F4** StoryMonitor+wiring(nav/i18n có).
- Guard test: grep `story-studio/` không có `from '../content-studio`.
- Submit: `{render_format:'story',story_source,content_script|story_idea,story_duration_sec,story_genre,
  story_*:cfg,voice_language,aspect_ratio:'16:9',add_subtitle:false,output_dir}`.

---

### 5.3 · LIVE UX — rendering sinh động (tham khảo Content/Recap)

Story phải cho user thấy **AI đang làm gì theo thời gian thực**, không phải progress bar khô. Kế thừa 3 mẫu đã có:
- Content `ScriptPhase.AiDirectorConsole` — overlay "AI Director" đi từng bước lúc PLAN.
- Content `ContentMonitor` — thẻ per-scene sống động lúc RENDER (sub-step Narration→Visual→Compose).
- Recap `RecapLiveView` — live stage view + StoryModel.

**(a) Planning console** (khi `/api/story/plan` chạy) — `StoryDirectorConsole.tsx`:
overlay "AI Story Director" đi các bước THẬT theo dependency: `Đọc & hiểu truyện → Định nghĩa nhân vật →
Dựng bối cảnh → Thiết kế N key-visual → Viết timeline (beat)`. Mode B thêm bước đầu `Sáng tác truyện từ ý tưởng`.
(1 call đồng bộ → đi bước theo timer + giữ bước cuối; honest, không % giả — như AiDirectorConsole).

**(b) Render live** (trong lúc render) — `StoryMonitor.tsx` bám WS stream (`story_pipeline` đã emit
`_emit_render_event` job/parts/summary + per-cue message):
- **Header stage:** ANALYZING/RENDERING/WRITING_REPORT/DONE + % tổng + total_sec.
- **Visuals grid:** ô ≤N ảnh — **hiện dần thumbnail khi mỗi Visual sinh xong** (spinner→ảnh), thấy tiền tiến.
- **Timeline sống:** con trỏ chạy dọc cue; cue hiện tại show `visual thumbnail + narration đang đọc + sub-step`
  (🎙 TTS → 🖼 ảnh → 🎬 compose) — giống sub-step per-scene của ContentMonitor.
- **Activity feed:** dòng sự kiện ("Sinh ảnh 3/8", "TTS batch xong 40 beat", "Ghép cue 12/40",
  fallback/warning) — như feed của Content.
- **Partial/hook badge:** đánh dấu beat hook, cue fail (partial success).
Reuse: render socket hook + polling fallback `/jobs/{id}/story-plan` (đã có v2). Dùng base
`components/studio/*` (không copy). **F4** = `StoryDirectorConsole` + `StoryMonitor` (2 phần trên).

## 6. MIGRATION
`render_format="story"`+wire ổn định (override mang JSON v2). StoryPlan v2 additive→blob/job v1 load;
không timeline→nhánh legacy đọc scenes(giữ). FE v1(P7) thay bởi v2 cùng thư mục(gỡ import content-studio).
Prompt/parser/director/pipeline v1 nội bộ thay bằng v2; test v1→v2.

## 7. RỦI RO & GUARD
Super prompt tràn token→model context lớn+repair+chunk-nối · 1 call nông→HARD RULES;quality 2-call env ·
focus→crop enum cố định deterministic · TTS thiếu timestamp→Whisper-align+fallback per-beat · ảnh vượt
ceiling→parser cap+gen enforce+budget · B7 state machine→Render Edit Protocol · FE lẫn mode→grep guard.

## 8. TEST & DoD
Mỗi phase unit+full pytest=2723(0 regression). B7: e2e ffmpeg + **runtime verify(.env)** đo **số call AI
(mode A:1+N+1, B:1+N+1) + ai_cost** — so ngắn vs dài → PHẲNG. FE: tsc -b+build+grep guard.
**DoD:** A & B đều 1 super+N ảnh(≤ceiling)+~1 TTS; video 16:9 không phụ đề(trừ hook); nhân vật nhất quán;
cue tất định(seed); TimelineEditor sửa được; chi phí không tuyến tính theo độ dài(đo được).

## 9. THỨ TỰ & CHECKPOINT
B0→B1→B2→B3→**[duyệt: JSON plan v2 thật, cả A&B]**→B4→B5→B6→**B7 CRITICAL**→**[duyệt: render thật+đo
call/chi phí]**→B8→F0→F1→F2→**F3[duyệt UI timeline]**→F4→**[verify tổng A&B]**.

## 10. TRẠNG THÁI
| Phase | TT | Ngày | Ghi chú |
|-------|----|------|---------|
| B0 | ✅ DONE | 2026-07-10 | models/wire +4 field (`story_source/idea/duration_sec/genre`) inert Sacred #2 + validator `story_source`→(paste\|idea\|""); `render_public` FE_FACING +4, `render_field_groups` story +4, `api.ts` +4; count-pin FE 90→94 total 170→174. Baseline **2723→2728** (0 regression), tsc -b sạch. Chưa wire vào pipeline (đúng scope B0). |
| B1 | ✅ DONE | 2026-07-10 | Domain v2 **`domain/story_plan_v2.py`** (file mới — v1 `story_plan.py` giữ nguyên để pipeline v1 không vỡ; cutover xoá v1 ở B7). Enums (FOCUS/MOTION/TRANSITION/TIER/GENDER) + hằng (ASPECT_SIZE/CPS/CROP_RECT/TRANSITION_SEC/MIN_BEAT_SEC) + contract (CharacterDef/SettingDef/Visual/Beat) + RenderState (Word/BeatAudio/Cue) + StoryPlan v2 (defensive from/to_json) + helpers (`validate_refs` INV1-8, `cap_visuals` INV6, `reindex`, `beat_est_sec`, `estimated_total_sec`, `build_cues` INV10-14 tất định + motion/crop + resolve_random, `image_timeline`, `voice_runs`). Baseline **2728→2740** (0 regression); 12 test: roundtrip ổn định, INV enforce, cap, cue tất định (seed→cues, INV13/14), random-transition deterministic, image_timeline, voice_runs. **Deviation ghi:** v2 ở file riêng (không phải ghi đè story_plan.py) để mỗi phase pytest xanh. |
| B2 | ✅ DONE | 2026-07-10 | Super prompt + parser (file mới, v1 giữ tới cutover B7). `ai/llm/story_prompts_v2.py`: `build_super_story_prompt`(A adapt) + `build_super_idea_prompt`(B create, budget=duration×cps) + `build_super_repair_prompt`, cùng SCHEMA + RULES(=INV) + SELF-CHECK, kiến trúc dependency-order (characters→settings→visuals→timeline). Format-safe (text NỐI chuỗi, schema raw). `ai/llm/story_parser_v2.py`: `parse_super_plan_response(raw,ceiling)` extract JSON(fence/salvage) → drop `render`(INV9) → StoryPlan._from_dict → validate_refs → cap_visuals → None nếu rỗng/no-visual. Baseline **2740→2756** (0 regression); 16 test: prompt shape/ceiling/budget/off-hook/format-safe · parser garbage→None/valid/fence/salvage/dangling-drop/INV9-render-drop/cap/no-visual→None. |
| B3 | ✅ DONE | 2026-07-10 | Super director (file mới). `ai/llm/story_director_v2.py`: `run_super_plan` (chọn builder A/B → `_call_and_parse` + repair CM-8 → chunk-nối `_plan_long_chapter`/`_merge_plans` khi >ngưỡng → post: `inject_character_canon`, cap/validate/reindex, seed hash) + `inject_character_canon`. `ai/llm/__init__.py`: `generate_story_plan_v2` dispatcher (bind `_call_<p>_content` với `STORY_SUPER_MODEL`=gpt-4o, ceiling từ `STORY_MAX_IMAGES`, fallback chain). Baseline **2756→2765** (0 regression); 9 test: A/B builder, canon inject, None/empty, repair recover, long-chunk-merge (2 call), call-raise nuốt, dispatch no-key→None. |
| B3-verify | 🔎 checkpoint | 2026-07-10 | runtime real super call (A & B) — xem JSON plan trước B4 |
| B4 | ✅ DONE | 2026-07-10 | Voice cast v2 — `story_voice_cast.py` +`apply_voice_cast_v2(plan,language)` (additive, tái dùng `cast_voices`): điền `plan.render.voices[cid]=[engine,voice_id]` (+"" narrator), engine theo ngôn ngữ (vi→gemini, en/ja→elevenlabs), ưu tiên `voice_gender`, rotate pool theo gender. Baseline **2765→2770** (0 regression); 5 test: vi→gemini, en→elevenlabs, distinct-per-gender, prefer voice_gender, never-raise. |
| B5 | ✅ DONE | 2026-07-10 | Image gen theo Visual + cap. `story_decision.py` +`clamp_tier(tier)` (cap `STORY_IMAGE_MAX_TIER`, default medium). `story_image.py` +`generate_visual_image(visual,refs,art_style,w,h,out,seed)` (additive): prompt+style, tier clamp, ref theo `character_ids` (refs dict → images.edit) else generate, size=ASPECT_SIZE, cache (prompt,size,tier,refs,seed). Baseline **2770→2777** (0 regression); 7 test: clamp_tier, no-key→None, generate/edit endpoint, tier-clamped, cache, empty→None. |
| B6 | ✅ DONE | 2026-07-10 | TTS timeline. MỚI `engine/audio/story_narration.py` `synthesize_timeline(plan,job_id,audio_dir,subtitle_mode)` — điền `render.beat_audio[bid]=BeatAudio(path,dur,words)` mỗi beat: engine/voice từ `render.voices[speaker_id]` (B4), locale map, `_reading_speed_to_rate`+`probe_audio_duration`; beat câm→hold_sec; TTS fail→empty audio; never raise. **Deviation có chủ đích:** synth PER-BEAT (theo voice_runs) thay vì batch-concat — TTS tính theo ký tự nên batch KHÔNG giảm $; split batch chính xác mong manh VI/JA (như focus_track đã bỏ). `words` để dành full-subtitle (mặc định hook_only không cần). Baseline **2777→2781** (0 regression); 4 test: fill dur/silent-hold, cast voice/engine, TTS-fail→empty, never-raise. |
| B7 | ✅ DONE | 2026-07-10 | Render engine cue-sheet (CRITICAL, Render Edit Protocol). MỚI `stages/story/beat_render.py` `render_one_cue(ctx,plan,part_no,cue)` — Ken Burns qua `zoompan` (cover-crop ảnh 3:2→canvas rồi pan/zoom crop_from→crop_to) + mux giọng apad→đúng dài cue, libx264 CPU (không đụng NVENC), never raise. MỚI `pipeline/story_pipeline_v2.py` `run_story_v2` — super plan → cast → images(≤ceiling) → `synthesize_timeline` → `build_cues` → seed part (Sacred #5 QUEUED→RENDERING→DONE/FAILED) → render loop → `assemble_shots` (tái dùng xfade) → `_finalize_story_v2` (QA #8 + result_json Sacred #1 + DONE). Sửa `CROP_RECT` domain → giữ tỉ lệ (w==h, không méo). Đổi dispatch `_common.py` story→`run_story_v2` (điểm chạm CRITICAL duy nhất, 1 dòng). Baseline **2781→2785** (0 regression); 4 e2e ffmpeg thật (video+audio, DONE, Sacred #1, plan v2 + cue sheet persist, override, cancel, no-plan-fail) + cập nhật 12 dispatch test. **Hoãn B7.1:** burn hook_text/full-subtitle (cần font pipeline text_overlay). **v1 story giờ dead** (dispatch không tới) — xoá = cutover-cleanup riêng. |
| B7.1 | ✅ DONE | 2026-07-10 | Overlay burn — `beat_render.py` +`_drawtext`/`_overlay_suffix`: hook_text→title upper-third (Anton bold), `subtitle`(full)→caption lower (Oswald); qua `textfile=` (không escape inline, an toàn tiếng Việt), tái dùng `_fontfile_for_family`/`_wrap_text_for_drawtext`/`get_text_overlay_temp_dir`/`safe_filter_path`; nối vào `vf` cả nhánh ảnh & màu; never raise→"". Baseline **2790→2796** (0 regression; 1 flake ordering `test_content_tempo_fit` đã xác nhận qua run cố định thứ tự); 6 unit + e2e b1 hook=True burn ffmpeg thật. |
| Cutover-1 | ✅ DONE | 2026-07-10 | Xoá **v1 render path** (dead sau dispatch→v2): `git rm` `pipeline/story_pipeline.py`, `stages/story/shot_stage.py`, `stages/story/finalize_stage.py`, `tests/test_story_qa_regen.py`. Repoint `routes/jobs.py:api_get_job_story_plan` v1→**v2** (`story_plan_v2`, `.timeline`). Cập nhật test: `test_story_wire_surface` (persisted plan→v2), `test_story_dispatch` (bỏ 2 `_build_transitions`). GIỮ `stages/story/{context(safe_filename),assembly_stage(assemble_shots)}` (v2 dùng). Baseline **2796→2791** (−5 test xoá, 0 regression). **Còn v1 (retire ở F-phase khi xoá v1 FE):** endpoint `/analyze` + `/character/reference-sheet` + stack Story-Intelligence (`analyze_story`,`story_director/prompts/parser`, domain `story_plan.py`) + leaf `generate_shot_image`/`apply_voice_cast`/`generate_story_plan` — vẫn còn consumer active. |
| B8 | ✅ DONE | 2026-07-10 | API v2 — `features/story/router.py`: viết lại `POST /api/story/plan` sang super plan v2 (body{source,chapter_text\|idea,duration_sec,genre,language,art_style,aspect_ratio,subtitle_mode,ceiling,series_id,chapter_no}→`generate_story_plan_v2`→{plan v2,image_count,beat_count,estimated_total_sec}; 422 text rỗng theo source, 502 None Sacred #3; GPT-centric provider STORY_AI_PROVIDER). MỚI `POST /visual/preview` (1 prompt→1 key-visual, token+url) + `GET /visual/image/{token}`. GIỮ `/analyze`,`/character/reference-sheet`,`/narration/preview`. Baseline **2785→2790** (0 regression); viết lại `test_story_plan_endpoint.py` v2 (paste/idea 422, 502, A&B trả plan+counts, visual 422/502/success). **Cutover:** `/plan` v1 (scenes/shots) đã thay — v1 `generate_story_plan` import gỡ khỏi router. |
| Commit-v2 | ✅ DONE | 2026-07-10 | Nhánh `feat/story-mode-v2` `762ded2b` — 38 file (B0–B8 + cutover), stage path tường minh (không `.env`/artifact). Chưa push/merge. |
| F0 | ✅ DONE | 2026-07-10 | Tầng BASE mode-agnostic `components/studio/`: `StudioScreen`·`StudioCard`·`StudioField`·`StudioStepper`·`SegRow`(generic)·`RatioPicker`(generic, default 16:9) + `index.ts` barrel + `studio.css` (class `.st-*`, CHỈ token `styles/tokens.css`: `--bg-*`,`--border*`,`--text-1/2/3`,`--space-*`,`--radius-*`,`--ok/--fail/--accent`,`--brand-gradient`). `tsc -b` sạch (exit 0); guard: 0 import content-studio. Cả 2 studio kế thừa; content-studio migrate sau (không chặn). Commit `5c359558`. |
| F3 | ✅ DONE | 2026-07-10 | PlanReview đầy đủ (sửa plan trước render): `index.tsx` orchestrator (edit immutable: character/visual/beat + move▲▼/add＋/delete✕ beat, review-bar counts + tổng est live) + `helpers.ts` (`beatEstSec` mirror backend, `visualColorMap`). `CharactersPanel` (sửa name/canonical_desc, tag giọng auto, nút "Ảnh chuẩn"→generateReferenceSheet). `VisualsPanel` (grid ≤N: sửa prompt/negative, chip char_ids toggle, tier, **"Xem thử/Tạo lại"**→previewVisual hiện thumbnail theo aspect). ⭐`TimelineEditor` (list beat: narration·speaker·visual(badge màu+thumb)·focus·motion·transition·hook+hook_text, est_sec/beat + tổng, reorder/add/delete). Story css đầy đủ (review/char/visual/timeline/chip/icon-btn). `tsc -b` exit 0; guard OK. |
| F2 | ✅ DONE | 2026-07-10 | InputScreen đầy đủ (A/B): char-count live + cảnh báo chương ngắn (<200), **template mẫu** (chèn/xoá, VI+EN theo ngôn ngữ), B: slider thời lượng(phút) + **gợi ý ngân sách chữ** (duration×CPS) + select thể loại, config (ngôn ngữ+hint engine TTS · aspect RatioPicker · art datalist · output dir validate+picker), nút Tạo báo rõ **điều kiện còn thiếu** ("Cần: …"), `st-input--invalid`. Thêm base css utils (field-foot/link/warn/invalid/actions--col/btn--lg). `tsc -b` exit 0; guard OK. |
| F1 | ✅ DONE | 2026-07-10 | Scaffold **story-studio v2 (cutover FE shell, cùng thư mục)**: rewrite `api/story.ts` v2 (types mirror `story_plan_v2` + `planStory`/`previewVisual`/`previewNarration`/`generateReferenceSheet`/`fetchJobStoryPlan`), `types.ts` v2 (`StoryConfig`/`StoryPhase input\|review\|monitor`/enums FOCUS/MOTION/TRANSITION/TIER/GENRE/ART/ASPECT/VOICE_LOCALE), orchestrator `StoryStudio.tsx` v2 (state+handlers `onGenerate`→planStory, `onRender`→submitRender payload story_source/idea/duration/genre/plan_override, reset), `InputScreen.tsx` (functional-minimal: source A/B tabs·textarea·duration·genre·ngôn ngữ·aspect·art·output), `PlanReview/index.tsx` + `StoryMonitor.tsx` (stub cho F3/F4). Mở rộng base `studio.css` (btn/actions/grid/range/alert/stat/muted/code). **Xoá v1** `InputPhase/BiblePhase/StoryboardPhase.tsx` + rewrite `StoryStudio.css`. `App.tsx` mount không đổi (named export giữ). `tsc -b` exit 0; guard: 0 import content-studio thật. |
