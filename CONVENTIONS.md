# CONVENTIONS.md — Code & Comment Standards

> Status: **DRAFT for review** (2026-06-19). This document defines the
> target standard for turning the codebase into a professional product.
> It is the contract every cleanup batch must follow. Nothing is applied
> to source files until this draft is approved.
>
> Read `CLAUDE.md` first — this document **never** overrides the Sacred
> Contracts, Frozen API Contracts, Blast Radius tiers, or the append-only
> audit rule. Where they conflict, CLAUDE.md wins.

---

## 1. Goals

1. Comments describe **what the code does and why**, organised by
   **feature/behaviour** — not by the historical phase/sprint/batch that
   introduced them.
2. No dead code: every symbol has a caller, a test, or a documented
   reason to exist.
3. One naming style, applied consistently.
4. **Zero behaviour change.** This is a readability/maintainability
   programme, not a refactor. No logic, no signatures, no public names
   change under this banner.

---

## 2. Comment policy

### 2.1 The three classes of marker

Every `Phase` / `Sprint` / `Batch` / `UP2x` / `MT-x` / `T2.x` reference
falls into exactly one class. Treat them differently.

| Class | Definition | Action |
|-------|-----------|--------|
| **A — Load-bearing rationale** | Explains *why* code looks the way it does, or documents a Sacred Contract / backward-compat shim / non-obvious workaround. | **KEEP the explanation.** Rewrite to feature-oriented prose. The provenance label (e.g. "Sprint 4.H —") may be dropped, but the *reason* must survive verbatim in meaning. |
| **B — Audit anchor** | A marker referenced by name in `docs/audit-*/` or paired with a `FINDING-xx` / audit id. | **KEEP AS-IS.** These are append-only audit anchors. Do not reword, do not drop the label. |
| **C — Pure provenance noise** | A bare timestamp/label with no surviving explanatory value, e.g. build-string log lines, `# Phase 45 hoist`, `(build=2026-06-04.sprint4c-...)`. | **REMOVE** (comment) or **simplify** (log line — keep the event, drop the build tag). |

**When unsure, treat it as Class A and keep the meaning.** Deleting a
comment is irreversible context loss; keeping one is harmless.

### 2.2 Rewrite examples

```python
# BEFORE (Class A — provenance label + rationale)
# Sprint 4.H — persistence runs only when AI emission succeeded.
# Flag-OFF / AI-failed jobs leave the render_plan_json column NULL.
if _render_plan is not None:

# AFTER (theo tính năng, giữ nguyên lý do, viết tiếng Việt)
# Chỉ lưu RenderPlan khi AI emit thành công; job thất bại/tắt cờ để cột
# render_plan_json = NULL (an toàn với schema additive-only).
if _render_plan is not None:
```

```python
# BEFORE (Class C — build-string noise)
logger.info("llm: dispatcher loaded (build=2026-06-04.sprint4c-render-plan-dual)")
# AFTER
logger.info("llm: dispatcher loaded")
```

```python
# KEEP UNCHANGED (Class B — audit anchor, giữ nguyên si tiếng Anh)
# Batch 10H (audit FINDING-API05): channels surface removed.
```

### 2.3 Never touch

- Any comment containing the literal `Sacred Contract` — keep verbatim.
- Any `# FORBIDDEN` / security warning (`devtools.py`, NVENC, qa_pipeline).
- Docstrings that state a frozen contract (stage names, event shape,
  `result_json` aliases, API field lists).

### 2.4 Style for new/edited comments

- **Code comment viết bằng tiếng Việt** — câu đầy đủ, mô tả hành vi: *"Giữ
  NVENC semaphore trước khi encode để số phiên render đồng thời không vượt
  giới hạn phần cứng."*
- Không ghi ngày tháng, không nhãn sprint/batch trong comment viết mới.
- Giải thích *tại sao*, không lặp lại *cái gì* khi code đã tự rõ.
- **Ngoại lệ giữ tiếng Anh:** audit anchor (Class B), tên trong Sacred
  Contract, các marker `# FORBIDDEN`/cảnh báo bảo mật — giữ nguyên si.
  Identifier (tên hàm/biến/hằng) luôn tiếng Anh theo §4.

---

## 3. Dead-code policy — chế độ GẮT

Mặc định: **code không có lý do tồn tại thì phải đi.** Nhưng "phải đi"
vẫn cần bằng chứng — gắt nghĩa là chủ động truy quét rộng và không khoan
nhượng với rác, KHÔNG phải xóa theo cảm tính.

### 3.1 Phạm vi truy quét (rộng hơn mặc định)

Mỗi đợt dọn phải soi tất cả các dạng sau, không chỉ "hàm không ai gọi":
- Import không dùng, biến gán rồi không đọc.
- Code bị comment-out (khối code chết treo trong comment) → xóa thẳng.
- Nhánh không thể tới (`if False`, sau `return`, cờ đã chết vĩnh viễn).
- Tham số hàm không bao giờ dùng; giá trị trả về không ai đọc.
- Log/build-string gắn với tính năng đã gỡ.
- Hàm/lớp/hằng zero call-site trong toàn repo.

Công cụ hỗ trợ (chạy để lập bằng chứng, không tự tin tay):
`python -m pyflakes <file>` cho import/biến thừa; `Grep` toàn repo cho
call-site; `python -m py_compile` sau mỗi file.

### 3.2 Điều kiện xóa (tất cả phải đúng — đây là phanh an toàn, KHÔNG nới)

1. `Grep` cho thấy **zero call-site** ngoài chính định nghĩa của nó —
   soi cả `tests/`, `frontend/`, và ref động dạng chuỗi (getattr, string
   dispatch, entrypoint, route đăng ký).
2. Không phải shim backward-compat được tài liệu hóa là cố ý giữ.
3. Không thuộc bề mặt Frozen API / Sacred Contract.
4. Test tier tương ứng pass cả trước và sau khi xóa.

→ "Gắt" áp dụng cho **độ rộng truy quét và mức zero-khoan-nhượng với rác
đã chứng minh là chết** (xóa luôn, không để lại "phòng khi cần"). Bốn
điều kiện trên là phanh an toàn — **không bao giờ nới** để xóa nhanh hơn.

### 3.3 Looks-dead-but-isn't — TUYỆT ĐỐI không xóa

- `output_rank_score`, `is_best_output`, `is_best_clip` (Sacred Contract #1)
- `JobStage.DOWNLOADING` (giữ cho backward compat)
- `backend/app/models/schemas.py` re-export shim
- Guard optional-dep `try/except ImportError` trong `ai/**`
- Mô hình kép `_thread_conn` vs `db_conn` (hoãn vô thời hạn)

LOW-tier: xóa thẳng khi đủ 4 điều kiện. MEDIUM trở lên: xuất **danh sách
đề xuất kèm bằng chứng**, duyệt từng mục rồi mới xóa.

---

## 4. Naming conventions

Codify the **dominant existing pattern** — do not invent a new one, and
**never rename a frozen identifier** (stage/part names, API fields,
`result_json` keys, REST paths).

| Kind | Rule | Example |
|------|------|---------|
| Modules / files | `snake_case.py` | `render_pipeline.py` |
| Classes | `PascalCase` | `RenderRequestPublic` |
| Functions / methods | `snake_case` | `select_render_plan` |
| Constants | `UPPER_SNAKE` | `NVENC_SEMAPHORE` |
| Module-private | leading underscore | `_resolve_api_key` |
| Local temporaries | leading underscore is **tolerated** but not required; prefer plain names in new code | `render_plan` over `_render_plan` |
| Feature flags | `_FEATURE_<NAME>` module const reading an env var | `_FEATURE_LLM_EMIT_RENDER_PLAN` |
| Env vars | `UPPER_SNAKE` | `LLM_FALLBACK_ENABLED` |

**Renaming is out of scope for the comment/dead-code passes.** Any
rename, even a local variable, is a separate reviewed change because
local-var churn produces large diffs that hide real edits. Only rename
when a symbol is provably non-public and the rename is the point of the
task.

---

## 5. Process (tiered, per CLAUDE.md Blast Radius)

| Tier | What's allowed under this programme | Gate |
|------|-------------------------------------|------|
| **LOW** | Comment rewrite, Class C removal, evidence-backed dead-code removal | Edit freely; `py_compile` after each file |
| **MEDIUM** | Comment rewrite only; dead code only with focused pytest | Planner + focused pytest |
| **HIGH** | **Comment rewrite only.** No dead-code removal, no rename, no logic. | Planner + explicit approval + full pytest |
| **CRITICAL** | **Comment rewrite only**, one file per approved plan, surgical `Edit`. | Render Edit Protocol (full, in order) |

Each batch:
1. Targets one tier and a small file set.
2. Produces a diff for review.
3. Runs `py_compile` (LOW) up to full `pytest` (HIGH/CRITICAL).
4. Touches nothing outside the approved file list — no "while I'm here".

---

## 6. Out of scope (explicitly)

- Renaming stage/part enum values, API fields, `result_json` keys, REST
  paths — **frozen forever**.
- Restructuring modules, moving files, changing imports for aesthetics.
- Editing files under `docs/audit-*/` (append-only).
- Touching `data/app.db`, `devtools.py` enablement, NVENC constants.
- Changing default values of feature flags or env vars.

---

## 7. Definition of done (per file)

- [ ] All Class C noise removed; Class A rationale preserved in
      feature-oriented prose; Class B anchors untouched.
- [ ] No frozen identifier renamed.
- [ ] Any dead code removed has documented zero-caller evidence.
- [ ] `py_compile` passes; required test tier passes.
- [ ] Diff reviewed; no behaviour change.
