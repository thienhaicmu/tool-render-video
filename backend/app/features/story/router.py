"""
Story Studio API — Story-to-Video v2 pre-render review endpoints.

The render itself goes through the shared render API (render_format="story"); this
router covers the review flow the FE Story Studio drives before render:

    POST /api/story/plan                      — ONE super call → StoryPlan v2
    POST /api/story/visual/svg-preview        — compose procedural SVG key-visual(s)
    POST /api/story/character/reference-sheet — transparent SVG character master
    POST /api/story/narration/preview         — one beat's narration to audio

Story Mode is SVG-only: all imagery is procedural (offline, $0). AI is used ONLY for
the super plan. All calls are defensive (Sacred Contract #3): a None/empty result
surfaces as a clean 4xx/502 — no unhandled raise reaches the client.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import APP_DATA_DIR, CACHE_DIR
from app.db import story_repo, story_project_repo, story_asset_repo
from app.features.render.ai.llm import generate_story_plan_v2

logger = logging.getLogger("app.story.api")

router = APIRouter(prefix="/api/story", tags=["story"])

# Per-beat narration + key-visual PREVIEW assets live under the cache root
# (pruneable). Keyed by an opaque 32-hex token; the GET validates the token shape.
_PREVIEW_DIR = CACHE_DIR / "story_preview"
_VISUAL_DIR = CACHE_DIR / "story_preview_visual"
_MASTER_DIR = CACHE_DIR / "story_master"          # transparent character-master previews
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")
_PLAN_RUN_DIR = APP_DATA_DIR / "story_plan_runs"
_PLAN_RUN_CONTEXT = threading.local()


class _PlanRunObserver:
    """Persist pass artifacts and expose a compact, thread-safe planning trace."""

    _PHASE_LABELS = {
        "understanding": "Reading and verifying source facts",
        "writer": "Writing the narration script",
        "writer_expand": "Expanding the narration script",
        "writer_repair": "Repairing missing story events",
        "structure": "Structuring the production plan",
        "structure_repair": "Repairing the production plan JSON",
        "legacy_plan": "Building the legacy production plan",
    }

    def __init__(self, run_id: str, job_id: str = "") -> None:
        self.run_id = run_id
        self.job_id = job_id
        self.run_dir = _PLAN_RUN_DIR / run_id
        self.lock = threading.Lock()
        self.sequence = 0
        self.active: dict[str, list[int]] = {}
        self.trace: dict = {
            "run_id": run_id,
            "status": "running",
            "phase": "queued",
            "message": "Planning queued",
            "actual_llm_calls": 0,
            "authoring_mode": "",
            "selected_provider": "",
            "selected_model": "",
            "compiler_fallback": False,
            "events": [],
            "artifacts_available": True,
        }

    @staticmethod
    def _safe_stage(stage: str) -> str:
        return re.sub(r"[^a-z0-9_-]+", "_", (stage or "call").lower())[:64] or "call"

    def _write_text(self, path: Path, value: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(value or "", encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:
            logger.info("story plan artifact write skipped: %s", exc)
            self.trace["artifacts_available"] = False

    def _persist_manifest(self) -> None:
        self._write_text(
            self.run_dir / "manifest.json",
            json.dumps(self.trace, ensure_ascii=False, indent=2, default=str),
        )

    def _update_job(self) -> None:
        if not self.job_id:
            return
        try:
            with _PLAN_JOBS_LOCK:
                job = _PLAN_JOBS.get(self.job_id)
                if job is not None:
                    job["progress"] = self.public_trace()
        except Exception:
            pass

    def public_trace(self) -> dict:
        return {k: v for k, v in self.trace.items() if k != "events"} | {
            "events": list(self.trace.get("events", []))[-30:]
        }

    def __call__(self, event: dict) -> None:
        with self.lock:
            raw = dict(event or {})
            kind = str(raw.get("event") or "event")
            stage = str(raw.get("stage") or "")
            system = str(raw.pop("system", "") or "")
            user = str(raw.pop("user", "") or "")
            output = str(raw.pop("output", "") or "")

            if kind == "call_started":
                self.sequence += 1
                seq = self.sequence
                self.active.setdefault(stage, []).append(seq)
                self.trace["actual_llm_calls"] += 1
                self.trace["phase"] = stage
                self.trace["message"] = self._PHASE_LABELS.get(stage, stage.replace("_", " ").title())
                safe = self._safe_stage(stage)
                self._write_text(
                    self.run_dir / f"{seq:02d}_{safe}_input.json",
                    json.dumps({"provider": raw.get("provider", ""),
                                "model": raw.get("model", ""),
                                "system": system, "user": user},
                               ensure_ascii=False, indent=2),
                )
                raw["call_no"] = seq
            elif kind == "call_completed":
                queue = self.active.get(stage) or []
                seq = queue.pop(0) if queue else self.sequence
                safe = self._safe_stage(stage)
                self._write_text(self.run_dir / f"{seq:02d}_{safe}_output.txt", output)
                raw["call_no"] = seq
            elif kind == "authoring_selected":
                self.trace["authoring_mode"] = raw.get("mode", "")
            elif kind == "compiler_fallback":
                self.trace["compiler_fallback"] = True
            elif kind == "source_chunked":
                self.trace["source_chunked"] = True
                self.trace["chunk_count"] = int(raw.get("chunks") or 0)
            elif kind == "provider_selected":
                self.trace["selected_provider"] = raw.get("provider", "")
                self.trace["selected_model"] = raw.get("model", "")
                self.trace["role_routes"] = raw.get("role_routes", {})
            elif kind == "provider_attempt":
                self.trace["role_routes"] = raw.get("role_routes", {})
            elif kind == "run_completed":
                self.trace["status"] = "done"
                self.trace["phase"] = "done"
                self.trace["message"] = "Story plan ready"
            elif kind == "run_failed":
                self.trace["status"] = "error"
                self.trace["phase"] = "error"
                self.trace["message"] = str(raw.get("error") or "Planning failed")

            self.trace["events"].append(raw)
            self.trace["events"] = self.trace["events"][-120:]
            self._persist_manifest()
            self._update_job()


class StoryPlanRequest(BaseModel):
    source: str = "paste"              # paste (source A) | idea (source B)
    chapter_text: str = Field(default="", description="Raw chapter text (source=paste)")
    idea: str = ""                     # short idea (source=idea)
    duration_sec: int = 0              # target length (source=idea)
    genre: str = ""
    language: str = "vi"
    art_style: str = ""
    aspect_ratio: str = "16:9"
    subtitle_mode: str = "hook_only"   # hook_only | full | off
    ceiling: Optional[int] = None      # max key-visuals (default env STORY_MAX_IMAGES)
    series_id: str = ""
    chapter_no: int = 0
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None
    use_video: bool = False            # paste + base video → P2 (narrate over video) prompt


@router.post("/plan")
def plan_storyboard(req: StoryPlanRequest) -> dict:
    """Story v2 — ONE super call → StoryPlan v2 (characters/settings/visuals/timeline).
    source=paste (A) adapts a whole chapter; source=idea (B) authors from a short idea
    + target duration — SAME output schema. Returns the plan + counts for the FE
    review screen. 422 when the chosen source's text is empty; 502 when the AI
    produced no usable plan (Sacred Contract #3 — generate_story_plan_v2 returned
    None)."""
    import os as _os

    source = (req.source or "paste").strip().lower()
    if source not in ("paste", "idea"):
        source = "paste"
    chapter = (req.chapter_text or "").strip()
    idea = (req.idea or "").strip()
    if source == "idea":
        if not idea:
            raise HTTPException(status_code=422, detail="idea is required for source=idea")
    elif not chapter:
        raise HTTPException(status_code=422, detail="chapter_text is required")

    observer = getattr(_PLAN_RUN_CONTEXT, "observer", None)
    if observer is None:
        observer = _PlanRunObserver(uuid.uuid4().hex)
    observer({"event": "request_started", "ts": time.time(), "source": source,
              "source_chars": len(idea if source == "idea" else chapter)})

    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key

    # GPT-centric like the render pipeline: provider from payload else STORY_AI_PROVIDER
    # (.env, default "openai") — NOT the global AI_PROVIDER_DEFAULT.
    provider = (req.ai_provider or "").strip().lower() or (
        _os.getenv("STORY_AI_PROVIDER", "openai") or "openai").strip().lower()
    api_key, _ = _resolve_api_key(req, provider)

    # G1: ground a later series chapter on earlier ones (no-op when series_id empty).
    from app.features.render.engine.pipeline.story_series_memory import build_prior_context
    _sid = (req.series_id or "")
    _cno = int(req.chapter_no or 0)
    prior_context = build_prior_context(_sid, before_chapter=(_cno or None))

    # Library-pick: give the Review plan the SAME asset-library catalog the render
    # pipeline injects (STORY_LIBRARY_PICK, scoped by genre group) so the AI can pick
    # `asset` slugs here too. Without this the reviewed/approved plan (rendered verbatim
    # via story_plan_override) carried no asset picks — library matching was bypassed
    # for the FE review flow. Empty catalog → prompt byte-identical (Sacred #2 rollback).
    library_catalog = ""
    if _os.getenv("STORY_LIBRARY_PICK", "1") == "1":
        try:
            from app.db import story_asset_repo
            from app.features.render.engine.pipeline.story_pipeline_v2 import _genre_group
            from app.features.render.engine.visual.character_resolver import resolver_enabled
            # GĐ3: resolver on → the engine assigns characters; prompt carries only
            # the BACKGROUNDS section.
            _kinds = ("background",) if resolver_enabled() else ("character", "background")
            library_catalog = story_asset_repo.build_library_catalog(
                genres=_genre_group(req.genre or ""), kinds=_kinds,
                style=(story_asset_repo.active_library_style(req.art_style or "") or None))
        except Exception:
            library_catalog = ""

    plan = generate_story_plan_v2(
        provider=provider, source=source, chapter=chapter, idea=idea,
        duration_sec=int(req.duration_sec or 0), genre=(req.genre or ""),
        language=(req.language or "vi"), art_style=(req.art_style or ""),
        aspect_ratio=(req.aspect_ratio or "16:9"),
        subtitle_mode=(req.subtitle_mode or "hook_only"), ceiling=req.ceiling,
        series_id=_sid, chapter_no=_cno, prior_context=prior_context,
        library_catalog=library_catalog,
        has_base_video=bool(req.use_video and source == "paste"),
        api_key=api_key, model=req.llm_model,
        # F-11: the generic ai_cloud_api_key is the ACTIVE provider's key — a
        # cross-provider fallback resolves only from its own per-provider/env key.
        resolve_key=lambda _p: _resolve_api_key(req, _p, allow_generic=(_p == provider))[0],
        observer=observer,
    )
    if plan is None or plan.is_empty() or plan.image_count() == 0:
        observer({"event": "run_failed", "ts": time.time(),
                  "error": "Story planning returned no usable plan"})
        raise HTTPException(status_code=502, detail="Story planning returned no usable plan")

    _visual_count = plan.image_count()
    # Source-truncation transparency: the super-prompt fits the chapter/idea to its cap —
    # surface when we cut so the FE can warn the user to split a very long chapter instead
    # of silently dropping the tail. (Idea cap is now env-tunable, no longer a hard 8000.)
    from app.features.render.ai.llm.story_prompts_v2 import MAX_SOURCE_CHARS, MAX_IDEA_CHARS
    _src_len = len(chapter) if source == "paste" else len(idea)
    _src_limit = MAX_SOURCE_CHARS if source == "paste" else MAX_IDEA_CHARS
    # F-08: Story imagery is procedural SVG ($0), but the planning LLM is NOT free.
    # Surface an ESTIMATE so the pre-flight no longer reports a misleading $0 total.
    from app.features.render.ai.llm.story_director_v2 import (
        estimate_super_plan_cost, lint_story_plan, shot_grammar_report,
    )
    _llm_cost = estimate_super_plan_cost(
        source_chars=_src_len, ceiling=_visual_count, model=(req.llm_model or "gpt-4o"),
        source=source, has_base_video=bool(req.use_video and source == "paste"))
    # P3: soft semantic lint (non-mutating) so the FE Review can flag weak-plan
    # signals (orphan visuals, generic-look speakers, looping narration).
    _lint = lint_story_plan(plan)
    # Length-shortfall visibility: when the user set a target and the AI's plan lands well
    # under it, surface it in warnings too (the FE already compares — this makes the
    # backend/monitor honest as well). 0.7 mirrors the escalate-and-regenerate floor.
    _tgt = int(req.duration_sec or 0)
    if _tgt > 0:
        _est = plan.estimated_total_sec()
        if _est < _tgt * 0.7:
            _lint = list(_lint) + [
                f"length is ~{_est:.0f}s vs target ~{_tgt}s ({_est / _tgt * 100:.0f}% of "
                "requested) — edit the timeline or regenerate to reach the length"]
    # GĐ3: deterministic character→asset resolution (identity lock + unique) so the
    # Review opens with real assignments + per-character states.
    _asset_res = _resolve_plan_assets(plan, series_id=_sid, genre=(req.genre or ""))
    # GĐ4b: readiness preview (no output_dir at plan time) — warns merge into the
    # review warnings so the user sees them BEFORE spending a render.
    _ready = None
    try:
        from app.features.render.engine.pipeline.story_readiness import evaluate_readiness
        _ready = evaluate_readiness(plan, target_sec=int(req.duration_sec or 0))
        _lint = list(_lint) + list(_ready["warns"]) + list(_ready["fails"])
    except Exception:
        _ready = None
    observer({"event": "run_completed", "ts": time.time()})
    _trace = observer.public_trace()
    _mode = _trace.get("authoring_mode") or _authoring_mode(
        source=source, has_base_video=bool(req.use_video and source == "paste"))
    return {
        "plan": json.loads(plan.to_json()),
        "image_count": _visual_count,
        "beat_count": plan.beat_count(),
        "estimated_total_sec": round(plan.estimated_total_sec(), 1),
        "character_count": len(plan.characters),
        "source_truncated": bool(_src_len > _src_limit and not _trace.get("source_chunked")),
        "source_chunked": bool(_trace.get("source_chunked")),
        "source_chunk_count": int(_trace.get("chunk_count") or 0),
        "source_chars": _src_len,
        "source_char_limit": _src_limit,
        "warnings": _lint,
        # GĐ3: per-character asset assignment + state (matched_exact | matched |
        # needs_approval | missing). Additive; None when the resolver is off.
        "asset_resolution": _asset_res,
        # GĐ4b: readiness preview (storage checks run at render time, not here).
        "readiness": _ready,
        "quality_signals": {"scene_shot": shot_grammar_report(plan)},
        # GĐ1: how this plan was authored — "compiler" (Understanding → Writer →
        # Structure, 3 calls) vs "single_pass" (legacy 1 call). Additive.
        "authoring_mode": _mode,
        "planning_trace": _trace,
        # Story imagery is procedural SVG + offline ($0); the super-plan LLM is not.
        "cost_preflight": {
            "visual_count": _visual_count,
            "character_count": len(plan.characters),
            "premium_image_count": 0,
            "image_cost_usd": 0.0,
            "estimated_llm_calls": _llm_cost.get("llm_calls", 1),
            "actual_llm_calls": int(_trace.get("actual_llm_calls") or 0),
            "estimated_llm_input_tokens": _llm_cost["input_tokens"],
            "estimated_llm_output_tokens": _llm_cost["output_tokens"],
            "estimated_llm_cost_usd": _llm_cost["cost_usd"],
            "estimated_cost_usd": _llm_cost["cost_usd"],   # total = image($0) + LLM
        },
    }


def _authoring_mode(*, source: str = "paste", has_base_video: bool = False) -> str:
    try:
        from app.features.render.ai.llm.story_prompts_v2 import compiler_enabled
        if has_base_video or source not in ("paste", "idea"):
            return "single_pass"
        return "compiler" if compiler_enabled() else "single_pass"
    except Exception:
        return "single_pass"


def _resolve_plan_assets(plan, *, series_id: str = "", genre: str = "") -> "Optional[dict]":
    """GĐ3 — run the deterministic character resolver on a freshly-built/validated
    plan (mutates ``characters[].asset`` + ``render.asset_status``). Returns the
    report dict for the API response, or None when the resolver is off / fails."""
    try:
        from app.features.render.engine.visual.character_resolver import (
            resolve_characters, resolver_enabled,
        )
        if not resolver_enabled():
            return None
        from app.features.render.engine.pipeline.story_pipeline_v2 import _genre_group
        from app.features.render.engine.pipeline.story_series_memory import locked_assets
        rep = resolve_characters(
            plan, locked=locked_assets((series_id or "").strip()),
            region=(getattr(plan, "region", "") or ""), genres=_genre_group(genre))
        by_id = {c.id: c for c in plan.characters}
        return {
            "statuses": rep["statuses"],
            "needs_approval": rep["needs_approval"],
            "missing": rep["missing"],
            "characters": [
                {"id": cid, "name": (getattr(by_id.get(cid), "name", "") or cid),
                 "asset": rep["assigned"].get(cid, ""), "status": st}
                for cid, st in rep["statuses"].items()
            ],
        }
    except Exception as exc:
        logger.info("story: asset resolution skipped: %s", exc)
        return None


# ── GĐ1f: async plan (the compiler is 3 sequential LLM calls — a long chapter can
# take minutes, past typical HTTP client timeouts). Minimal in-process job registry:
# POST /plan/async → {plan_job_id}; GET /plan/async/{id} → {status, result|error}.
# The sync POST /plan stays untouched (backward compat). Registry is bounded and
# self-pruning; jobs live in memory only (a restart loses them — the FE just retries).
_PLAN_JOBS: "dict[str, dict]" = {}
_PLAN_JOBS_LOCK = threading.Lock()
_PLAN_JOBS_MAX = 40
_PLAN_JOB_TTL_SEC = 30 * 60


def _prune_plan_jobs_locked() -> None:
    now = time.time()
    dead = [k for k, v in _PLAN_JOBS.items()
            if now - v.get("created", now) > _PLAN_JOB_TTL_SEC]
    for k in dead:
        _PLAN_JOBS.pop(k, None)
    while len(_PLAN_JOBS) > _PLAN_JOBS_MAX:
        oldest = min(_PLAN_JOBS, key=lambda k: _PLAN_JOBS[k].get("created", 0))
        _PLAN_JOBS.pop(oldest, None)


def _run_plan_job(job_id: str, req: "StoryPlanRequest") -> None:
    observer = _PlanRunObserver(job_id, job_id=job_id)
    _PLAN_RUN_CONTEXT.observer = observer
    try:
        result = plan_storyboard(req)          # reuse the sync logic verbatim
        with _PLAN_JOBS_LOCK:
            if job_id in _PLAN_JOBS:
                _PLAN_JOBS[job_id].update(status="done", result=result)
    except HTTPException as he:
        observer({"event": "run_failed", "ts": time.time(), "error": str(he.detail)})
        with _PLAN_JOBS_LOCK:
            if job_id in _PLAN_JOBS:
                _PLAN_JOBS[job_id].update(status="error", error=str(he.detail),
                                          status_code=int(he.status_code))
    except Exception as exc:                   # defensive — never let the thread die silently
        observer({"event": "run_failed", "ts": time.time(), "error": "planning failed"})
        logger.warning("story plan job %s failed: %s", job_id, exc)
        with _PLAN_JOBS_LOCK:
            if job_id in _PLAN_JOBS:
                _PLAN_JOBS[job_id].update(status="error", error="planning failed",
                                          status_code=502)
    finally:
        try:
            delattr(_PLAN_RUN_CONTEXT, "observer")
        except AttributeError:
            pass


@router.post("/plan/async")
def plan_storyboard_async(req: StoryPlanRequest) -> dict:
    """Start a plan job in the background → ``{plan_job_id}``. Poll GET
    /plan/async/{id}. Same validation/semantics as POST /plan (it runs the same
    function); 422s surface at poll time as status=error."""
    job_id = uuid.uuid4().hex
    with _PLAN_JOBS_LOCK:
        _prune_plan_jobs_locked()
        _PLAN_JOBS[job_id] = {
            "status": "running", "created": time.time(),
            "progress": {"run_id": job_id, "status": "running", "phase": "queued",
                         "message": "Planning queued", "actual_llm_calls": 0, "events": []},
        }
    threading.Thread(target=_run_plan_job, args=(job_id, req),
                     name=f"story-plan-{job_id[:8]}", daemon=True).start()
    return {"plan_job_id": job_id, "status": "running"}


@router.get("/plan/async/{job_id}")
def plan_storyboard_async_status(job_id: str) -> dict:
    """Poll a plan job: ``{status: running|done|error, result?, error?}``.
    404 on a malformed/unknown/expired id."""
    if not _TOKEN_RE.match(job_id or ""):
        raise HTTPException(status_code=404, detail="not found")
    with _PLAN_JOBS_LOCK:
        job = _PLAN_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="not found")
        out = {"status": job.get("status", "running"),
               "progress": job.get("progress", {})}
        if job.get("status") == "done":
            out["result"] = job.get("result")
        elif job.get("status") == "error":
            out["error"] = job.get("error", "")
            out["status_code"] = job.get("status_code", 502)
    return out


# ── Paste-JSON validate (feature: paste a StoryPlan → render, no AI) ──────────

class StoryValidateRequest(BaseModel):
    plan: object = Field(default="", description="StoryPlan JSON (object or string)")
    has_base_video: bool = Field(default=False, description="True if a base video will be attached (Template-2 over-video)")


@router.post("/validate")
def validate_story_plan(req: StoryValidateRequest) -> dict:
    """Preflight a HAND-PASTED StoryPlan (paste-JSON feature) BEFORE render. Parses +
    normalizes (validate_refs / cap / drop stale render state), then returns hard
    ``errors`` (block render) + soft ``warnings`` (lint) + the length/counts + the
    normalized plan. Never raises (Sacred Contract #3) — a bad paste is a clean 200
    with ``ok=false`` + reasons, not a 500."""
    from app.domain.story_plan_v2 import StoryPlan
    from app.features.render.ai.llm.story_director_v2 import lint_story_plan

    raw = req.plan if isinstance(req.plan, str) else json.dumps(req.plan or {}, ensure_ascii=False)
    plan = StoryPlan.from_json(raw)
    errors: list = []
    warnings: list = []
    if plan is None:
        return {"ok": False, "errors": ["JSON không đọc được — không phải StoryPlan hợp lệ"],
                "warnings": [], "estimated_total_sec": 0.0, "beat_count": 0,
                "character_count": 0, "image_count": 0, "plan_normalized": None}

    # Dangling refs are AUTO-scrubbed by normalize — collect them as warnings BEFORE that.
    try:
        char_ids = {c.id for c in plan.characters}
        vis_ids = {v.id for v in plan.visuals}
        for b in plan.timeline:
            if b.visual_id and b.visual_id not in vis_ids:
                warnings.append(f"beat {b.id}: visual_id '{b.visual_id}' không tồn tại (sẽ được remap)")
            for ln in b.effective_lines():
                if ln.speaker_id and ln.speaker_id not in char_ids:
                    warnings.append(f"beat {b.id}: speaker '{ln.speaker_id}' không có trong characters (→ narrator)")
        for v in plan.visuals:
            for cid in (v.character_ids or []):
                if cid not in char_ids:
                    warnings.append(f"visual {v.id}: character '{cid}' không tồn tại (bỏ qua)")
    except Exception:
        pass

    # Template-2 (over-video) fields present but no base video attached → they're ignored.
    try:
        has_t2 = any((getattr(b, "source_audio", "mute") or "mute") != "mute"
                     or (getattr(b, "char_anchor", "none") or "none") != "none"
                     for b in plan.timeline)
        if has_t2 and not req.has_base_video:
            warnings.append("plan có source_audio/char_anchor (Template-2) nhưng KHÔNG đính video nền — "
                            "các field đó sẽ bị bỏ qua (render như storyboard)")
    except Exception:
        pass

    # Normalize + derive so the estimate / lint reflect what will actually render.
    plan.normalize_for_render(max(15, plan.image_count()))
    try:
        plan.derive_beat_styling()
    except Exception:
        pass

    # Hard errors — mirror the pipeline's own acceptance gate.
    if plan.schema_version != 2:
        errors.append("schema_version phải = 2")
    if plan.image_count() <= 0:
        errors.append("cần ít nhất 1 visual")
    if plan.is_empty():
        errors.append("timeline rỗng — cần ít nhất 1 beat có lời (lines[].text hoặc narration)")

    try:
        warnings += list(lint_story_plan(plan))
    except Exception:
        pass

    # GĐ3: resolve characters on the pasted plan too (hand-authored picks are honored;
    # empty ones get a unique library assignment + state for the Review chips).
    _asset_res = _resolve_plan_assets(plan)

    ok = not errors
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings[:30],
        "estimated_total_sec": round(plan.estimated_total_sec(), 1),
        "beat_count": plan.beat_count(),
        "character_count": len(plan.characters),
        "image_count": plan.image_count(),
        "asset_resolution": _asset_res,
        "plan_normalized": (json.loads(plan.to_json()) if ok else None),
    }


# ── SVG key-visual preview (Storyboard review — WYSIWYG, offline $0) ──────────

class SvgPreviewRequest(BaseModel):
    plan: dict = Field(default_factory=dict, description="The StoryPlan v2 being reviewed")
    visual_ids: list = Field(default_factory=list, description="Subset to compose ([] = all)")


@router.post("/visual/svg-preview")
def svg_visual_preview(req: SvgPreviewRequest) -> dict:
    """Compose the procedural SVG key-visual(s) for a StoryPlan so the FE Review shows
    exactly what the render will produce (WYSIWYG, offline, $0). Returns
    ``{items: [{visual_id, token, url}]}`` for every visual that composed. 422 on an
    empty/invalid plan; 502 when the SVG rasteriser is unavailable (resvg-py). Composes
    with characters placed so the reviewer sees who is in each scene (the render itself
    overlays the speaker per-beat). Never raises past a clean HTTP error."""
    from app.domain.story_plan_v2 import StoryPlan, ASPECT_SIZE
    from app.features.render.engine.visual import svg_raster
    from app.features.render.engine.visual.svg_compose import compose_visual

    try:
        plan = StoryPlan.from_json(json.dumps(req.plan or {}, ensure_ascii=False))
    except Exception:
        plan = None
    if plan is None or not plan.visuals:
        raise HTTPException(status_code=422, detail="a StoryPlan with visuals is required")
    if not svg_raster.available():
        raise HTTPException(status_code=502, detail="SVG rasteriser unavailable (install resvg-py)")
    w, h = ASPECT_SIZE.get((plan.aspect_ratio or "16:9"), ASPECT_SIZE["16:9"])
    wanted = {str(v) for v in (req.visual_ids or []) if v}
    _VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    items: list = []
    for v in plan.visuals:
        if wanted and v.id not in wanted:
            continue
        try:
            svg = compose_visual(plan, v, w, h, chars=True)
            if not svg:
                continue
            token = uuid.uuid4().hex
            out = _VISUAL_DIR / f"{token}.png"
            if svg_raster.save_svg_png(svg, str(out), w, h, opaque_bg="#101820"):
                items.append({"visual_id": v.id, "token": token,
                              "url": f"/api/story/visual/image/{token}"})
        except Exception as exc:
            logger.info("story svg-preview: visual %s failed: %s", v.id, exc)
    return {"items": items}


@router.get("/visual/image/{token}")
def visual_image(token: str):
    """Stream a key-visual preview png by token. 404 on a malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _VISUAL_DIR / f"{token}.png"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="image/png")


# ── Character master (transparent SVG chibi — Review preview + overlay asset) ─

class CharacterMasterRequest(BaseModel):
    character_id: str = ""
    name: str = ""
    description: str = ""       # kept for FE compatibility (unused by the SVG builder)
    archetype: str = ""        # drives the chibi look (e.g. "swordsman")
    gender: str = ""
    region: str = ""
    genre: str = ""
    art_style: str = ""        # accepted for compatibility (the chibi style is fixed)
    # 0 = canonical stand pose; >0 rotates the pose so "regenerate" yields a different look.
    variant: int = 0


@router.post("/character/reference-sheet")
def character_master(req: CharacterMasterRequest) -> dict:
    """Compose a cutout-ready transparent CHARACTER MASTER (procedural SVG chibi, offline
    $0) for the Review character panel — the SAME asset the render overlays. Returns
    ``{path, url}``. 422 without any character signal; 502 on compose failure / resvg-py
    unavailable (Sacred Contract #3)."""
    from types import SimpleNamespace
    from app.features.render.engine.visual.story_reference_sheet import generate_character_master

    name = (req.name or "").strip()
    arch = (req.archetype or "").strip()
    cid = (req.character_id or "").strip()
    if not (name or arch or cid):
        raise HTTPException(status_code=422, detail="a character (name/archetype) is required")
    character = SimpleNamespace(id=(cid or name), name=name, archetype=arch,
                                gender=(req.gender or ""))
    path = generate_character_master(
        character, art_style=(req.art_style or ""), variant=int(req.variant or 0),
        region=(req.region or ""), genre=(req.genre or ""))
    if not path:
        raise HTTPException(status_code=502, detail="character master generation failed")
    url = ""
    try:
        import shutil
        _MASTER_DIR.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        shutil.copyfile(path, _MASTER_DIR / f"{token}.png")
        url = f"/api/story/character/master/{token}"
    except Exception as exc:
        logger.warning("story: master preview copy failed: %s", exc)
    return {"path": path, "url": url}


@router.get("/character/master/{token}")
def character_master_image(token: str):
    """Stream a character-master preview png (transparent) by token. 404 on a
    malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _MASTER_DIR / f"{token}.png"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="image/png")


# ── P4: per-shot narration preview (cast voice + language-routed engine) ──────

class NarrationPreviewRequest(BaseModel):
    text: str = Field(default="", description="The shot narration to voice")
    language: str = "vi"
    gender: str = "female"
    voice_id: str = ""          # from Voice Casting (engine-specific)
    reading_speed: float = 1.0


@router.post("/narration/preview")
def narration_preview(req: NarrationPreviewRequest) -> dict:
    """Synthesize ONE shot's narration to previewable audio, routing the engine by
    language (Gemini VI / ElevenLabs EN-JP; edge fallback). Returns
    ``{token, url, engine, duration_sec}``. 422 empty text; 502 when TTS produced
    nothing (Sacred Contract #3 — no unhandled raise reaches the client)."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")

    from app.features.render.engine.audio.tts import (
        generate_narration_audio, resolve_story_tts_engine,
    )
    from app.features.render.engine.stages.content_scene_render import (
        _reading_speed_to_rate, probe_audio_duration,
    )

    engine = resolve_story_tts_engine(req.language)
    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    out = _PREVIEW_DIR / f"{token}.mp3"
    try:
        path = generate_narration_audio(
            text=text, language=(req.language or "vi"), gender=(req.gender or "female"),
            rate=_reading_speed_to_rate(req.reading_speed),
            job_id=f"story-preview-{token}", voice_id=(req.voice_id or None),
            output_path=str(out), content_type="vlog", tts_engine=engine,
        )
    except Exception as exc:
        logger.warning("story narration preview: TTS raised %s", exc)
        raise HTTPException(status_code=502, detail="TTS failed")

    final = Path(path) if path else out
    if final != out and final.exists():
        try:
            import shutil
            shutil.move(str(final), str(out))
        except Exception:
            out = final
    if not out.exists() or out.stat().st_size <= 0:
        raise HTTPException(status_code=502, detail="TTS produced no audio")

    return {
        "token": token, "url": f"/api/story/narration/audio/{token}",
        "engine": engine, "duration_sec": probe_audio_duration(str(out)),
    }


@router.get("/narration/audio/{token}")
def narration_audio(token: str):
    """Stream a narration-preview mp3 by token. 404 on a malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _PREVIEW_DIR / f"{token}.mp3"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="audio/mpeg")


# ── Phase 4: voice picker — available voices for the language's TTS engine ────

@router.get("/voices")
def story_voices(language: str = "vi") -> dict:
    """Return the available Story voices for a language's TTS engine, split by gender:
    ``{engine, female[], male[]}``. Lets the FE offer a per-character voice override
    (written into the plan's render.voices, preserved at render). Never raises."""
    from app.features.render.ai.llm.story_voice_cast import list_voices
    return list_voices(language or "vi")


# ── SP1: Story project persistence (save / list / open / delete) ──────────────

class StoryProjectSaveRequest(BaseModel):
    id: str = ""                       # "" → create a new project
    name: str = ""
    language: str = ""
    source: str = ""                   # paste | idea
    config: dict = Field(default_factory=dict)   # the FE StoryConfig
    plan: Optional[dict] = None         # the edited StoryPlan v2 (None → not planned yet)
    status: str = "draft"              # draft | ready


@router.post("/projects")
def save_story_project(req: StoryProjectSaveRequest) -> dict:
    """Create (id="") or update a Story project (config + edited plan). Powers the FE
    autosave + manual Save. Returns ``{id}``. Never persists render state — this is a
    pre-render authoring store only."""
    pid = (req.id or "").strip() or uuid.uuid4().hex
    ok = story_project_repo.upsert_project(
        pid, name=(req.name or ""), language=(req.language or ""),
        source=(req.source or ""),
        config_json=json.dumps(req.config or {}, ensure_ascii=False),
        plan_json=(json.dumps(req.plan, ensure_ascii=False) if req.plan else ""),
        status=(req.status or "draft"),
    )
    if not ok:
        raise HTTPException(status_code=500, detail="failed to save project")
    return {"id": pid}


@router.get("/projects")
def list_story_projects() -> dict:
    """List recent LIVE Story projects (newest first, without the heavy config/plan blobs)."""
    return {"projects": story_project_repo.list_projects()}


@router.get("/projects/trash")
def list_trashed_story_projects() -> dict:
    """List soft-deleted (trashed) Story projects. Defined BEFORE /projects/{id} so
    'trash' is never captured as a project id."""
    return {"projects": story_project_repo.list_trashed_projects()}


@router.get("/projects/{project_id}")
def get_story_project(project_id: str) -> dict:
    """Return one project with ``config`` + ``plan`` parsed back to objects. 404 missing."""
    row = story_project_repo.get_project(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        row["config"] = json.loads(row.get("config_json") or "") if row.get("config_json") else {}
    except Exception:
        row["config"] = {}
    try:
        row["plan"] = json.loads(row.get("plan_json") or "") if row.get("plan_json") else None
    except Exception:
        row["plan"] = None
    row.pop("config_json", None)
    row.pop("plan_json", None)
    return row


@router.delete("/projects/{project_id}")
def delete_story_project(project_id: str) -> dict:
    """SOFT-delete a Story project (move to trash). Idempotent — always reports success.
    Restore via /projects/{id}/restore; hard-remove via /projects/{id}/purge."""
    story_project_repo.delete_project(project_id)
    return {"deleted": True, "id": project_id}


@router.post("/projects/{project_id}/restore")
def restore_story_project(project_id: str) -> dict:
    """Restore a trashed Story project (clear deleted_at)."""
    story_project_repo.restore_project(project_id)
    return {"restored": True, "id": project_id}


@router.delete("/projects/{project_id}/purge")
def purge_story_project(project_id: str) -> dict:
    """HARD-delete a Story project + all its versions (empty-trash). Irreversible."""
    story_project_repo.purge_project(project_id)
    return {"purged": True, "id": project_id}


# ── SP3+: project version history (snapshot / list / restore) ─────────────────

class SaveVersionRequest(BaseModel):
    label: str = ""


@router.post("/projects/{project_id}/versions")
def snapshot_story_project_version(project_id: str, req: SaveVersionRequest) -> dict:
    """Snapshot the project's CURRENT stored plan+config as a version. 404 when the
    project doesn't exist. Returns ``{version_id}``."""
    row = story_project_repo.get_project(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    vid = story_project_repo.save_version(
        project_id, label=(req.label or ""),
        plan_json=(row.get("plan_json") or ""), config_json=(row.get("config_json") or ""),
    )
    if not vid:
        raise HTTPException(status_code=500, detail="failed to snapshot version")
    return {"version_id": vid}


@router.get("/projects/{project_id}/versions")
def list_story_project_versions(project_id: str) -> dict:
    """List a project's version snapshots (newest first, without the heavy blobs)."""
    return {"versions": story_project_repo.list_versions(project_id)}


@router.post("/projects/{project_id}/restore-version/{version_id}")
def restore_story_project_version(project_id: str, version_id: str) -> dict:
    """Restore a version's plan+config back INTO the project (overwrites current) and
    return the restored ``{config, plan}`` for the FE to reload. 404 on a missing version."""
    ver = story_project_repo.get_version(version_id)
    if ver is None or (ver.get("project_id") or "") != project_id:
        raise HTTPException(status_code=404, detail="version not found")
    proj = story_project_repo.get_project(project_id) or {}
    story_project_repo.upsert_project(
        project_id, name=(proj.get("name") or ""), language=(proj.get("language") or ""),
        source=(proj.get("source") or ""),
        config_json=(ver.get("config_json") or ""), plan_json=(ver.get("plan_json") or ""),
        status=(proj.get("status") or "draft"),
    )
    try:
        config = json.loads(ver.get("config_json") or "") if ver.get("config_json") else {}
    except Exception:
        config = {}
    try:
        plan = json.loads(ver.get("plan_json") or "") if ver.get("plan_json") else None
    except Exception:
        plan = None
    return {"restored": True, "config": config, "plan": plan}


# ── AL2: offline asset library (list / get / thumb / scan / delete) ───────────

@router.get("/assets")
def list_story_assets(kind: str = "", region: str = "", genre: str = "", q: str = "") -> dict:
    """List indexed library assets, filtered by kind/region/genre + free-text q."""
    return {"assets": story_asset_repo.list_assets(kind=kind, region=region, genre=genre, q=q)}


@router.post("/assets/scan")
def scan_story_assets() -> dict:
    """(Re)index the asset library folder → story_assets. Returns {indexed, pruned, root}."""
    return story_asset_repo.scan_library()


@router.get("/assets/{asset_id}")
def get_story_asset(asset_id: str) -> dict:
    """Return one asset's metadata. 404 when missing."""
    row = story_asset_repo.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return row


@router.get("/assets/{asset_id}/image")
def get_story_asset_image(asset_id: str):
    """Stream the asset's image file. 404 when the asset / file is missing."""
    row = story_asset_repo.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    p = Path(row.get("path") or "")
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="asset file not found")
    _media = "image/webp" if p.suffix.lower() == ".webp" else "image/png"
    return FileResponse(str(p), media_type=_media)


@router.delete("/assets/{asset_id}")
def delete_story_asset(asset_id: str) -> dict:
    """Remove an asset's DB row (does NOT delete the file on disk). Idempotent."""
    story_asset_repo.delete_asset(asset_id)
    return {"deleted": True, "id": asset_id}
