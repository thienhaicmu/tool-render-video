"""
story_director_v2.py — provider-agnostic Super-Prompt orchestration for Story v2.

ONE super call → StoryPlan v2 (mode A adapt / mode B create-from-idea, same schema),
+ a bounded repair pass, + a chunk-and-merge path for very long chapters, + the
deterministic post-passes (inject character canon, cap/validate/reindex, seed).

Parameterised by ``call_fn(system, user) -> str | None`` so every provider binds its
own raw model call (key rotation / retry / cache inside call_fn) — mirrors v1
content_director. Sacred Contract #3: never raises; returns None on total failure.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Callable, Optional

from app.domain.story_plan_v2 import RelationshipDef, StoryPlan
from app.features.render.ai.llm.story_prompts_v2 import (
    build_super_story_prompt, build_super_video_prompt, build_super_idea_prompt,
    build_super_repair_prompt, SUPER_PROMPT_VERSION, compiler_enabled,
    build_understanding_prompt, build_writer_adapt_prompt, build_writer_idea_prompt,
    build_writer_repair_prompt, build_structure_prompt,
    MAX_SOURCE_CHARS,
)
from app.features.render.ai.llm.story_parser_v2 import parse_super_plan_response

logger = logging.getLogger("app.render.story_director_v2")

SuperCall = Callable[[str, str], Optional[str]]
StoryObserver = Callable[[dict[str, Any]], None]


def _emit(observer: "Optional[StoryObserver]", event: str, **data) -> None:
    if observer is None:
        return
    try:
        observer({"event": event, "ts": time.time(), **data})
    except Exception:
        pass


def _observed_call(call_fn: SuperCall, system: str, user: str, *, stage: str,
                   provider_label: str = "", model_label: str = "",
                   observer: "Optional[StoryObserver]" = None) -> Optional[str]:
    """Invoke one physical LLM request and publish an auditable start/end pair."""
    started = time.perf_counter()
    _emit(observer, "call_started", stage=stage, provider=provider_label, model=model_label,
          input_chars=len(system or "") + len(user or ""), system=system, user=user)
    status = "empty"
    raw: Optional[str] = None
    error = ""
    try:
        raw = call_fn(system, user)
        status = "success" if raw else "empty"
        return raw
    except Exception as exc:
        status = "error"
        error = str(exc)[:500]
        raise
    finally:
        _emit(observer, "call_completed", stage=stage, provider=provider_label, model=model_label,
              status=status, latency_ms=round((time.perf_counter() - started) * 1000, 1),
              output_chars=len(raw or ""), output=raw or "", error=error)


def estimate_super_plan_cost(*, source_chars: int, ceiling: int, model: str = "gpt-4o",
                             source: str = "paste", has_base_video: bool = False) -> dict:
    """Rough $ estimate for the Story planning LLM cost (F-08 — Story audit).

    Story imagery is procedural SVG ($0), but the planning LLM is NOT free — the
    pre-flight previously reported $0 total, hiding the only real cost. Returns
    ``{input_tokens, output_tokens, cost_usd, llm_calls}`` as an ESTIMATE (not
    billed usage). Under the GĐ1 compiler the pipeline is 3 calls (Understanding →
    Writer → Structure): the source is read ~2×, and the output includes the prose
    script besides the JSON plan. Per-1M rates env-tunable
    (``OPENAI_STORY_PRICE_IN_PER_M`` / ``OPENAI_STORY_PRICE_OUT_PER_M``, default
    gpt-4o). Never raises."""
    try:
        src = max(0, int(source_chars))
        plan_out = int(max(1, int(ceiling)) * 300)      # ~1 visual + its beats per slot
        use_compiler = compiler_enabled() and not has_base_video and source in ("paste", "idea")
        if use_compiler:
            calls = 2 if source == "idea" else 3
            # understanding(src) + writer(src+facts) + structure(script≈plan-size prose)
            source_factor = 1.2 if source == "idea" else 2.2
            fixed_prompt_chars = 6500 if source == "idea" else 9000
            in_tok = int((src * source_factor + fixed_prompt_chars) / 4)
            out_tok = plan_out * 2 + 800                 # script ≈ plan text + facts JSON
        else:
            calls = 1
            in_tok = int((src + 3500) / 4)
            out_tok = plan_out
        price_in = float(os.getenv("OPENAI_STORY_PRICE_IN_PER_M", "2.5"))
        price_out = float(os.getenv("OPENAI_STORY_PRICE_OUT_PER_M", "10.0"))
        cost = in_tok / 1_000_000 * price_in + out_tok / 1_000_000 * price_out
        return {"input_tokens": in_tok, "output_tokens": out_tok,
                "cost_usd": round(cost, 4), "llm_calls": calls}
    except Exception:
        return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "llm_calls": 0}


def shot_grammar_report(plan) -> dict:
    """Deterministic scene/shot coverage and diversity instrument (0-100)."""
    try:
        timeline = list(getattr(plan, "timeline", []) or [])
        scenes = list(getattr(plan, "scenes", []) or [])
        shots = list(getattr(plan, "shots", []) or [])
        by_id = {shot.id: shot for shot in shots}
        mapped = [by_id.get(getattr(beat, "shot_id", "")) for beat in timeline]
        mapped_count = sum(1 for shot in mapped if shot is not None)
        sizes = [shot.shot_size for shot in mapped if shot is not None]
        angles = [shot.angle for shot in mapped if shot is not None]
        motions = [shot.motion_intent for shot in mapped if shot is not None]
        max_repeat = 0
        run = 0
        previous = None
        for signature in zip(sizes, angles, motions):
            run = run + 1 if signature == previous else 1
            max_repeat = max(max_repeat, run)
            previous = signature
        scene_first = []
        beats_by_id = {getattr(beat, "id", ""): beat for beat in timeline}
        for scene in scenes:
            first = by_id.get(scene.shot_ids[0]) if scene.shot_ids else None
            first_beat = beats_by_id.get(scene.beat_ids[0]) if scene.beat_ids else None
            cold_open = bool(first_beat and (getattr(first_beat, "hook", False) or
                                             (getattr(first_beat, "hook_text", "") or "").strip()))
            scene_first.append(bool(first and (first.shot_size in ("extreme_wide", "wide")
                                               or cold_open)))
        hook_shots = [by_id.get(getattr(beat, "shot_id", "")) for beat in timeline
                      if bool(getattr(beat, "hook", False)) or
                      bool((getattr(beat, "hook_text", "") or "").strip())]
        hook_close = sum(1 for shot in hook_shots
                         if shot and shot.shot_size in ("close", "extreme_close"))
        coverage = mapped_count / len(timeline) if timeline else 0.0
        establishing = sum(scene_first) / len(scene_first) if scene_first else 0.0
        size_target = min(3, len(timeline)) if timeline else 1
        angle_target = min(3, len(timeline)) if timeline else 1
        size_diversity = min(1.0, len(set(sizes)) / max(1, size_target))
        angle_diversity = min(1.0, len(set(angles)) / max(1, angle_target))
        hook_rate = hook_close / len(hook_shots) if hook_shots else 1.0
        repeat_score = 1.0 if max_repeat <= 2 else max(0.0, 1.0 - (max_repeat - 2) / 4)
        score = 100.0 * (0.30 * coverage + 0.20 * establishing + 0.15 * size_diversity +
                         0.15 * angle_diversity + 0.10 * hook_rate + 0.10 * repeat_score)
        return {
            "scenes": len(scenes), "shots": len(shots), "mapped_beats": mapped_count,
            "beat_coverage": round(coverage, 3), "establishing_rate": round(establishing, 3),
            "unique_sizes": len(set(sizes)), "unique_angles": len(set(angles)),
            "unique_motions": len(set(motions)), "max_repeated_setup": max_repeat,
            "hook_close_rate": round(hook_rate, 3), "shot_score": round(score, 1),
        }
    except Exception:
        return {"scenes": 0, "shots": 0, "beat_coverage": 0.0, "shot_score": 0.0,
                "error": "unreadable_plan"}


def shot_grammar_gate(plan) -> list[str]:
    """Hard reasons for compiler output; legacy/imported plans remain soft-linted."""
    report = shot_grammar_report(plan)
    reasons: list[str] = []
    if report.get("beat_coverage", 0.0) < 1.0:
        reasons.append("not every beat maps to a valid shot")
    if report.get("scenes", 0) and report.get("establishing_rate", 0.0) < 0.75:
        reasons.append("fewer than 75% of scenes start with an establishing shot")
    if report.get("shots", 0) >= 4 and report.get("unique_sizes", 0) < 2:
        reasons.append("shot-size vocabulary is too repetitive")
    if report.get("max_repeated_setup", 0) > 4:
        reasons.append("the same camera setup repeats for more than four shots")
    return reasons


def lint_story_plan(plan) -> list:
    """Best-effort SEMANTIC lint of a BUILT StoryPlan (P3). Returns a list of
    human-readable warnings for a reviewer/monitor. NEVER mutates the plan and
    never raises — structural integrity is already enforced by
    StoryPlan.validate_refs; this only surfaces SOFT quality signals (weak plan)
    and does NOT gate the render (Sacred Contract #3 spirit)."""
    warnings: list = []
    try:
        chars = list(getattr(plan, "characters", []) or [])
        visuals = list(getattr(plan, "visuals", []) or [])
        timeline = list(getattr(plan, "timeline", []) or [])
        by_id = {c.id: c for c in chars}
        # multiline-aware: the on-screen speaker is the beat's legacy speaker_id OR the
        # first line's speaker (primary_speaker); the beat text is narration OR joined lines.
        def _primary(b) -> str:
            try:
                return b.primary_speaker() or ""
            except Exception:
                return (getattr(b, "speaker_id", "") or "")

        def _beat_text(b) -> str:
            t = (getattr(b, "narration", "") or "").strip()
            if t:
                return t
            try:
                return " ".join((ln.text or "").strip() for ln in b.effective_lines()).strip()
            except Exception:
                return ""
        spoken = {_primary(b) for b in timeline if _primary(b)}
        # 0. Characters defined but NONE ever speaks/anchors → the render overlays a
        #    character only for a beat with a speaking character, so the video comes out
        #    BACKGROUND-ONLY (no character on screen). Directly predicts that failure.
        if chars and timeline and not spoken:
            warnings.append(
                f"{len(chars)} character(s) defined but none speaks on any beat — the video "
                "will render background-only (no character on screen)")
        # 1. A speaking character with no canonical look → generic overlay/voice.
        for cid in sorted(spoken):
            c = by_id.get(cid)
            if c is not None and not (c.canonical_desc or "").strip():
                warnings.append(f"character '{cid}' speaks but has no canonical_desc (generic look)")
        # 2. Orphan visuals (composed but no beat uses them → wasted work).
        used_vis = {(b.visual_id or "") for b in timeline}
        for v in visuals:
            if v.id and v.id not in used_vis:
                warnings.append(f"visual '{v.id}' is never used by any beat")
        # 3. Unused cast (defined but never speaks and never in a visual).
        in_visual = {cid for v in visuals for cid in (v.character_ids or [])}
        for c in chars:
            if c.id and c.id not in spoken and c.id not in in_visual:
                warnings.append(f"character '{c.id}' is defined but never speaks or appears")
        # 4. Degenerate repeated narration (possible looping output).
        from collections import Counter
        counts = Counter(_beat_text(b) for b in timeline if _beat_text(b))
        for txt, n in counts.items():
            if n >= 3:
                warnings.append(f"narration repeated {n}× (possible loop): {txt[:40]!r}")
        # 5. No narration at all → a silent video.
        if timeline and not any(_beat_text(b) for b in timeline):
            warnings.append("no beat has narration (silent video)")
        # 6. Retention basics: an explicit opening hook and enough visual variation.
        opening = timeline[:3]
        if opening and not any(bool(getattr(b, "hook", False)) or
                               bool((getattr(b, "hook_text", "") or "").strip())
                               for b in opening):
            warnings.append("none of the first three beats is marked as the story hook")
        if len(timeline) >= 6:
            visual_counts = Counter((getattr(b, "visual_id", "") or "") for b in timeline)
            most_used, count = visual_counts.most_common(1)[0]
            if most_used and count / len(timeline) > 0.65:
                warnings.append(
                    f"visual '{most_used}' is reused by {count}/{len(timeline)} beats "
                    "(low shot diversity)")
        shot_report = shot_grammar_report(plan)
        if shot_report.get("shots", 0):
            for reason in shot_grammar_gate(plan):
                warnings.append(f"shot grammar: {reason}")
            if shot_report.get("unique_angles", 0) < 2 and len(timeline) >= 4:
                warnings.append("shot grammar: camera angle does not vary across the story")
    except Exception:
        return warnings
    return warnings[:20]


def _stable_seed(text: str) -> int:
    try:
        return int(hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()[:8], 16)
    except Exception:
        return 0


def inject_character_canon(plan: StoryPlan) -> StoryPlan:
    """Append each present character's canonical_desc to a visual's prompt (idempotent)
    so image gen keeps the character consistent. No-op without characters. Never raises."""
    try:
        canon = {c.id: (c.canonical_desc or "").strip() for c in plan.characters if (c.canonical_desc or "").strip()}
        if not canon:
            return plan
        for v in plan.visuals:
            frags = []
            for cid in v.character_ids:
                d = canon.get(cid)
                if d and d not in frags:
                    frags.append(d)
            if not frags:
                continue
            inject = "; ".join(frags)
            base = (v.prompt or "").strip()
            if inject in base:
                continue
            v.prompt = f"{base}. {inject}" if base else inject
        return plan
    except Exception as exc:
        logger.info("story_director_v2: inject canon skipped: %s", exc)
        return plan


def _call_and_parse(call_fn: SuperCall, system: str, user: str, ceiling: int, *,
                    stage: str = "structure", provider_label: str = "",
                    model_label: str = "",
                    observer: "Optional[StoryObserver]" = None) -> Optional[StoryPlan]:
    """One call + parse; on parse-failure, one bounded repair pass (CM-8)."""
    try:
        raw = _observed_call(call_fn, system, user, stage=stage,
                             provider_label=provider_label, model_label=model_label,
                             observer=observer)
    except Exception as exc:
        logger.info("story_director_v2: call raised %s", exc)
        return None
    if not raw:
        return None
    plan = parse_super_plan_response(raw, ceiling)
    if plan is None and os.getenv("STORY_PLAN_REPAIR", "1") == "1":
        try:
            rsys, ruser = build_super_repair_prompt(raw)
            fixed = _observed_call(call_fn, rsys, ruser, stage=f"{stage}_repair",
                                   provider_label=provider_label, model_label=model_label,
                                   observer=observer)
            if fixed:
                plan = parse_super_plan_response(fixed, ceiling)
                if plan is not None:
                    logger.info("story_director_v2: plan recovered via repair pass")
        except Exception as exc:
            logger.info("story_director_v2: repair pass failed %s", exc)
    return plan


def _merge_plans(a: StoryPlan, b: StoryPlan) -> StoryPlan:
    """Concatenate plan b after a: dedupe characters/settings by id, re-id b's visuals
    to avoid collision (remapping its beats), concat timelines. Never raises."""
    try:
        a_char = {c.id for c in a.characters}
        a.characters += [c for c in b.characters if c.id not in a_char]
        a_set = {s.id for s in a.settings}
        a.settings += [s for s in b.settings if s.id not in a_set]
        a_vis = {v.id for v in a.visuals}
        remap: dict = {}
        for v in b.visuals:
            new_id = v.id
            n = 2
            while new_id in a_vis:
                new_id = f"{v.id}_{n}"; n += 1
            remap[v.id] = new_id
            v.id = new_id
            a_vis.add(new_id)
            a.visuals.append(v)
        for beat in b.timeline:
            beat.visual_id = remap.get(beat.visual_id, beat.visual_id)
            a.timeline.append(beat)
        return a
    except Exception as exc:
        logger.info("story_director_v2: merge failed %s", exc)
        return a


def _build_paste_prompt(chapter, language, art_style, aspect_ratio, subtitle_mode, ceiling,
                        prior_context, library_catalog, has_base_video, base_video_dur):
    """Pick the right PASTE-mode builder: P2 (narrate over a base video) when a base
    video is present, else P1 (adapt → SVG)."""
    if has_base_video:
        return build_super_video_prompt(chapter, language, art_style, aspect_ratio, subtitle_mode,
                                        ceiling, prior_context, library_catalog, base_video_dur)
    return build_super_story_prompt(chapter, language, art_style, aspect_ratio, subtitle_mode,
                                    ceiling, prior_context, library_catalog)


def _split_source_chunks(text: str, limit: int = MAX_SOURCE_CHARS) -> "list[str]":
    """Split without dropping the tail, preferring paragraph and line boundaries."""
    source = (text or "").strip()
    if not source:
        return []
    limit = max(32, int(limit or MAX_SOURCE_CHARS))
    parts: list[str] = []
    while len(source) > limit:
        floor = int(limit * 0.60)
        cut = source.rfind("\n\n", floor, limit + 1)
        if cut < floor:
            cut = source.rfind("\n", floor, limit + 1)
        if cut < floor:
            cut = source.rfind(" ", floor, limit + 1)
        if cut < floor:
            cut = limit
        parts.append(source[:cut].strip())
        source = source[cut:].strip()
    if source:
        parts.append(source)
    return [part for part in parts if part]


def _plan_long_chapter(call_fn, chapter, language, art_style, aspect_ratio, subtitle_mode,
                       ceiling, threshold, prior_context="", library_catalog="",
                       has_base_video=False, base_video_dur=0.0,
                       provider_label="", observer=None) -> Optional[StoryPlan]:
    """Split an over-long chapter without dropping its tail, plan each chunk, merge."""
    parts = _split_source_chunks(chapter, threshold)
    if not parts:
        return None
    # Budget the ceiling ACROSS chunks (ceil division) so the merged plan
    # stays ~ceiling — otherwise each half planned at the FULL ceiling and the outer
    # cap_visuals dropped a whole half (the back of the story) after merge.
    per_half = max(1, -(-int(ceiling) // len(parts)))
    plans = []
    for part_no, part in enumerate(parts, 1):
        sysm, user = _build_paste_prompt(part, language, art_style, aspect_ratio, subtitle_mode,
                                         per_half, prior_context, library_catalog,
                                         has_base_video, base_video_dur)
        p = _call_and_parse(call_fn, sysm, user, per_half,
                            stage=f"legacy_chunk_{part_no}",
                            provider_label=provider_label, observer=observer)
        if p is not None:
            plans.append(p)
    if not plans:
        return None
    merged = plans[0]
    for p in plans[1:]:
        merged = _merge_plans(merged, p)
    return merged


def _idea_expand_env() -> "tuple[int, float, float, float]":
    """(tries, floor_ratio, factor_step, base_factor) for the idea length-expand loop.
    Env-tunable; STORY_IDEA_EXPAND_TRIES=0 disables the loop (pre-s21 behaviour)."""
    def _f(name, default):
        try:
            return float(os.getenv(name, str(default)) or default)
        except (TypeError, ValueError):
            return default
    try:
        tries = max(0, int(os.getenv("STORY_IDEA_EXPAND_TRIES", "1") or 1))
    except (TypeError, ValueError):
        tries = 1
    return (tries, _f("STORY_IDEA_EXPAND_FLOOR", 0.7),
            max(1.0, _f("STORY_IDEA_EXPAND_FACTOR_STEP", 1.7)),
            max(1.0, _f("STORY_IDEA_LENGTH_FACTOR", 1.8)))


def _plan_idea_with_expand(call_fn: SuperCall, idea: str, duration_sec: int, genre: str,
                           language: str, art_style: str, aspect_ratio: str, subtitle_mode: str,
                           ceiling: int, prior_context: str, library_catalog: str,
                           provider_label: str,
                           observer: "Optional[StoryObserver]" = None) -> Optional[StoryPlan]:
    """Idea→StoryPlan with a bounded 'too short → regenerate at a higher length factor'
    loop (escalate-and-regenerate). Keeps the plan CLOSEST to the target (short is a
    failure, mild overshoot is fine). Never raises — falls back to the first/best plan."""
    call_no = 0

    def _make(factor: float) -> Optional[StoryPlan]:
        nonlocal call_no
        call_no += 1
        sysm, user = build_super_idea_prompt(
            idea, duration_sec, genre, language, art_style, aspect_ratio,
            subtitle_mode, ceiling, prior_context, library_catalog, length_factor=factor)
        if observer is None:
            # Preserve the long-standing helper seam used by tests and local plugins
            # that monkeypatch _call_and_parse with its original 4-argument shape.
            p = _call_and_parse(call_fn, sysm, user, ceiling)
        else:
            p = _call_and_parse(call_fn, sysm, user, ceiling,
                                stage=("legacy_plan" if call_no == 1 else "legacy_idea_expand"),
                                provider_label=provider_label, observer=observer)
        if p is not None and language:
            p.language = language  # accurate cps for estimated_total_sec() below
        return p

    best = _make(0.0)  # 0.0 → build_super_idea_prompt uses the env/default factor
    if best is None or not duration_sec or duration_sec <= 0:
        return best
    tries, floor, step, base = _idea_expand_env()
    if tries <= 0:
        return best
    floor_sec = duration_sec * floor
    best_est = best.estimated_total_sec()
    if best_est >= floor_sec:
        return best  # first plan already long enough — no extra LLM calls

    def _better(cand_est: float, cur_est: float) -> bool:
        cand_ok, cur_ok = cand_est >= floor_sec, cur_est >= floor_sec
        if cand_ok != cur_ok:
            return cand_ok  # reaching the floor beats a short plan
        if cand_ok:  # both acceptable → closest to target (mild overshoot ok)
            return abs(cand_est - duration_sec) < abs(cur_est - duration_sec)
        return cand_est > cur_est  # both short → the longer one wins

    factor = base
    for i in range(tries):
        factor *= step
        cand = _make(factor)
        if cand is None:
            continue
        cand_est = cand.estimated_total_sec()
        logger.info("story_director_v2[%s]: idea-expand try=%d factor=%.2f est=%.0fs (target=%ds best=%.0fs)",
                    provider_label, i + 1, factor, cand_est, duration_sec, best_est)
        if _better(cand_est, best_est):
            best, best_est = cand, cand_est
        if best_est >= floor_sec:
            break
    return best


def _run_compiler(*, call_fn: SuperCall, writer_call_fn: SuperCall,
                  json_call_fn: Optional[SuperCall], source: str, chapter: str, idea: str,
                  duration_sec: int, genre: str, language: str, art_style: str,
                  aspect_ratio: str, subtitle_mode: str, ceiling: int,
                  prior_context: str, library_catalog: str,
                  provider_label: str, model_label: str = "",
                  writer_provider_label: str = "", writer_model_label: str = "",
                  json_provider_label: str = "", json_model_label: str = "",
                  observer: "Optional[StoryObserver]" = None) -> Optional[StoryPlan]:
    """GĐ1 Story Compiler — 3 calls, deterministic validators between them:

      1. UNDERSTANDING (paste only; ``json_call_fn``) → facts + quote-verified events.
      2. WRITER (``writer_call_fn``, prose) → screenplay-lite script; validated
         (speakers / event coverage / tail / length); ONE targeted repair round for
         missing MAJOR events; idea mode length-loop measured by len(script).
      3. STRUCTURE (``call_fn`` — the existing strict-schema plan call) → StoryPlan.

    Returns the parsed plan or None (caller falls back to the legacy single-pass).
    Never raises (Sacred Contract #3)."""
    from app.features.render.ai.llm.story_understanding import (
        parse_understanding, validate_understanding, understanding_block, validate_script,
        script_spoken_chars, understanding_gate, script_gate, validate_plan_coverage,
    )
    _p = provider_label or "?"
    src = (source or "paste").strip().lower()

    # ── Pass 1 — Understanding (paste only; an idea has no source to cover) ──
    u = None
    if src == "paste" and json_call_fn is not None:
        try:
            usys, uusr = build_understanding_prompt(chapter, language)
            u = parse_understanding(_observed_call(
                json_call_fn, usys, uusr, stage="understanding",
                provider_label=(json_provider_label or _p), model_label=json_model_label,
                observer=observer))
        except Exception as exc:
            logger.info("story_compiler[%s]: understanding call failed %s", _p, exc)
            u = None
        if u is not None:
            urep = validate_understanding(u, chapter)
            logger.info("story_compiler[%s]: understanding events=%d verified=%d majors=%d/%d "
                        "tail=%s order=%s", _p, urep["total"], urep["verified"],
                        urep["majors_verified"], urep["majors_total"],
                        urep["tail_covered"], urep["order_ok"])
            try:
                min_verified = float(os.getenv("STORY_UNDERSTANDING_MIN_VERIFIED", "0.70") or 0.70)
            except (TypeError, ValueError):
                min_verified = 0.70
            gate_reasons = understanding_gate(urep, min_verified_ratio=min_verified)
            _emit(observer, "validation", stage="understanding", report=urep,
                  passed=not gate_reasons, reasons=gate_reasons)
            if gate_reasons:
                logger.warning("story_compiler[%s]: understanding gate failed: %s",
                               _p, "; ".join(gate_reasons))
                return None
        else:
            logger.info("story_compiler[%s]: no usable understanding — writing without facts", _p)

    # ── Pass 2 — Writer (prose script) ────────────────────────────────────────
    if src == "paste" and u is None:
        _emit(observer, "validation", stage="understanding", passed=False,
              reasons=["understanding output is missing or malformed"])
        return None

    writer_calls = 0

    def _write(factor: float = 0.0) -> Optional[str]:
        nonlocal writer_calls
        try:
            if src == "idea":
                wsys, wusr = build_writer_idea_prompt(
                    idea, duration_sec, genre, language, prior_context, length_factor=factor)
            else:
                wsys, wusr = build_writer_adapt_prompt(
                    chapter, language, genre,
                    understanding_block(u) if u is not None else "", prior_context)
            writer_calls += 1
            return _observed_call(
                writer_call_fn, wsys, wusr,
                stage=("writer" if writer_calls == 1 else "writer_expand"),
                provider_label=(writer_provider_label or _p), model_label=writer_model_label,
                observer=observer)
        except Exception as exc:
            logger.info("story_compiler[%s]: writer call failed %s", _p, exc)
            return None

    script = _write()
    if not (script or "").strip():
        logger.warning("story_compiler[%s]: writer produced no script", _p)
        return None

    target_chars = 0
    if src == "idea" and duration_sec and duration_sec > 0:
        from app.domain.story_plan_v2 import cps_for
        target_chars = int(duration_sec * cps_for(language))

    rep = validate_script(script, u, language=language, target_chars=target_chars)

    # Idea length-loop: reuse the STORY_IDEA_EXPAND_* knobs, but measure the SCRIPT
    # directly (len — no JSON parse, so a retry costs one writer call only).
    if src == "idea" and target_chars > 0:
        tries, floor, step, base = _idea_expand_env()
        best, best_len = script, rep["spoken_chars"]
        factor = base
        for i in range(tries):
            if best_len >= target_chars * max(floor, 0.9):
                break
            factor *= step
            cand = _write(factor)
            if not (cand or "").strip():
                continue
            cand_len = script_spoken_chars(cand)
            logger.info("story_compiler[%s]: idea-expand try=%d factor=%.2f len=%d (target=%d)",
                        _p, i + 1, factor, cand_len, target_chars)
            if cand_len > best_len:
                best, best_len = cand, cand_len
        if best is not script:
            script = best
            rep = validate_script(script, u, language=language, target_chars=target_chars)

    # Targeted repair (ONE round): missing MAJOR events are named; the writer weaves
    # them in and returns the full corrected script.
    if rep["missing_events"] and os.getenv("STORY_SCRIPT_REPAIR", "1") == "1":
        try:
            rsys, rusr = build_writer_repair_prompt(script, rep["missing_events"], language)
            fixed = _observed_call(writer_call_fn, rsys, rusr, stage="writer_repair",
                                   provider_label=(writer_provider_label or _p),
                                   model_label=writer_model_label, observer=observer)
            if (fixed or "").strip() and "[SCENE" in fixed.upper():
                script = fixed
                rep = validate_script(script, u, language=language, target_chars=target_chars)
                logger.info("story_compiler[%s]: script repaired — missing majors now %d",
                            _p, len(rep["missing_events"]))
        except Exception as exc:
            logger.info("story_compiler[%s]: script repair failed %s", _p, exc)
    if rep["warnings"]:
        logger.info("story_compiler[%s]: script notes: %s", _p, "; ".join(rep["warnings"][:6]))
    try:
        min_script_ratio = float(os.getenv("STORY_SCRIPT_MIN_TARGET_RATIO", "0.70") or 0.70)
    except (TypeError, ValueError):
        min_script_ratio = 0.70
    script_reasons = script_gate(rep, target_chars=target_chars,
                                 min_target_ratio=min_script_ratio)
    _emit(observer, "validation", stage="writer", report=rep,
          passed=not script_reasons, reasons=script_reasons)
    if script_reasons:
        logger.warning("story_compiler[%s]: writer gate failed: %s",
                       _p, "; ".join(script_reasons))
        return None

    # ── Pass 3 — Structure (existing strict-schema plan call + repair pass) ──
    ssys, susr = build_structure_prompt(
        script, language, art_style, aspect_ratio, subtitle_mode, ceiling, genre,
        characters=(u.characters if u is not None else []),
        prior_context=prior_context, library_catalog=library_catalog,
        fact_context=(understanding_block(u) if u is not None else ""))
    plan = _call_and_parse(call_fn, ssys, susr, ceiling, stage="structure",
                           provider_label=_p, model_label=model_label, observer=observer)
    if plan is None:
        logger.warning("story_compiler[%s]: structure pass produced no plan", _p)
        return None
    coverage = validate_plan_coverage(script, plan)
    try:
        min_coverage = float(os.getenv("STORY_STRUCTURE_MIN_COVERAGE", "0.75") or 0.75)
    except (TypeError, ValueError):
        min_coverage = 0.75
    coverage_reasons = ([] if coverage["coverage"] >= min_coverage else [
        f"StoryPlan preserves {coverage['coverage'] * 100:.0f}% of approved script tokens; "
        f"minimum is {min_coverage * 100:.0f}%"])
    if coverage.get("order_coverage", 0.0) < 0.70:
        coverage_reasons.append(
            f"StoryPlan preserves only {coverage.get('order_coverage', 0.0) * 100:.0f}% "
            "of ordered script anchors")
    opening = list(getattr(plan, "timeline", None) or [])[:3]
    if opening and not any(bool(getattr(beat, "hook", False)) or
                           bool((getattr(beat, "hook_text", "") or "").strip())
                           for beat in opening):
        coverage_reasons.append("none of the first three beats is marked as the story hook")
    _emit(observer, "validation", stage="structure", report=coverage,
          passed=not coverage_reasons, reasons=coverage_reasons)
    if coverage_reasons:
        logger.warning("story_compiler[%s]: structure gate failed: %s",
                       _p, "; ".join(coverage_reasons))
        return None
    if u is not None:
        plan.relationships = [RelationshipDef(
            source_id=str(item.get("a") or ""), target_id=str(item.get("b") or ""),
            kind=str(item.get("type") or ""), status=str(item.get("status") or ""),
        ) for item in (u.relationships or []) if isinstance(item, dict)]
    return plan


def run_super_plan(
    *,
    call_fn: SuperCall,
    source: str = "paste",
    chapter: Optional[str] = None,
    idea: Optional[str] = None,
    duration_sec: int = 0,
    genre: str = "",
    language: str = "vi",
    art_style: str = "",
    aspect_ratio: str = "16:9",
    subtitle_mode: str = "hook_only",
    ceiling: int = 15,
    series_id: str = "",
    chapter_no: int = 0,
    seed: int = 0,
    prior_context: str = "",
    library_catalog: str = "",
    has_base_video: bool = False,
    base_video_dur: float = 0.0,
    provider_label: str = "",
    model_label: str = "",
    writer_provider_label: str = "",
    writer_model_label: str = "",
    json_provider_label: str = "",
    json_model_label: str = "",
    writer_call_fn: Optional[SuperCall] = None,
    json_call_fn: Optional[SuperCall] = None,
    observer: "Optional[StoryObserver]" = None,
) -> Optional[StoryPlan]:
    """Turn a source (chapter text OR idea) into a StoryPlan v2. ``prior_context`` (G1)
    grounds a later series chapter on earlier ones. ``has_base_video`` routes a PASTE
    source to the over-video prompt (P2) instead of the SVG prompt (P1).

    GĐ1: when the Story Compiler is enabled AND a ``writer_call_fn`` (prose) is
    available, the plan is produced by the 3-call pipeline (Understanding → Writer →
    Structure) — any failure inside it falls back to the legacy single-call path, so
    a compiler hiccup never loses a render. Returns None on total failure (Sacred
    Contract #3 — never raises)."""
    try:
        src = (source or "paste").strip().lower()
        _p = provider_label or "?"
        _emit(observer, "authoring_started", source=src, provider=_p)

        # ── GĐ1 Story Compiler path (SVG sources only; P2 over-video stays legacy) ──
        if (compiler_enabled() and writer_call_fn is not None and not has_base_video
                and src in ("paste", "idea")
                and ((src == "idea" and (idea or "").strip())
                     or (src == "paste" and (chapter or "").strip()))):
            try:
                chunks = (_split_source_chunks((chapter or "").strip())
                          if src == "paste" and len((chapter or "").strip()) > MAX_SOURCE_CHARS
                          else [])
                if len(chunks) > 1:
                    _emit(observer, "source_chunked", chunks=len(chunks),
                          source_chars=len((chapter or "").strip()),
                          max_chunk_chars=MAX_SOURCE_CHARS)
                    per_chunk = max(1, -(-int(ceiling) // len(chunks)))
                    plans = []
                    for chunk_no, chunk in enumerate(chunks, 1):
                        _emit(observer, "chunk_started", chunk=chunk_no,
                              chunks=len(chunks), chunk_chars=len(chunk))
                        chunk_plan = _run_compiler(
                            call_fn=call_fn, writer_call_fn=writer_call_fn,
                            json_call_fn=json_call_fn, source=src, chapter=chunk, idea="",
                            duration_sec=duration_sec, genre=genre, language=language,
                            art_style=art_style, aspect_ratio=aspect_ratio,
                            subtitle_mode=subtitle_mode, ceiling=per_chunk,
                            prior_context=prior_context, library_catalog=library_catalog,
                            provider_label=_p, model_label=model_label,
                            writer_provider_label=writer_provider_label,
                            writer_model_label=writer_model_label,
                            json_provider_label=json_provider_label,
                            json_model_label=json_model_label, observer=observer)
                        if chunk_plan is None:
                            plans = []
                            break
                        plans.append(chunk_plan)
                    plan = plans[0] if plans else None
                    for chunk_plan in plans[1:]:
                        plan = _merge_plans(plan, chunk_plan)
                else:
                    plan = _run_compiler(
                        call_fn=call_fn, writer_call_fn=writer_call_fn, json_call_fn=json_call_fn,
                        source=src, chapter=(chapter or "").strip(), idea=(idea or "").strip(),
                        duration_sec=duration_sec, genre=genre, language=language,
                        art_style=art_style, aspect_ratio=aspect_ratio, subtitle_mode=subtitle_mode,
                        ceiling=ceiling, prior_context=prior_context,
                        library_catalog=library_catalog, provider_label=_p,
                        model_label=model_label,
                        writer_provider_label=writer_provider_label,
                        writer_model_label=writer_model_label,
                        json_provider_label=json_provider_label,
                        json_model_label=json_model_label,
                        observer=observer)
            except Exception as exc:
                logger.warning("story_compiler[%s]: unexpected %s — falling back to legacy",
                               _p, exc, exc_info=True)
                plan = None
            if plan is not None:
                plan.cap_visuals(ceiling)
                plan.validate_refs()
                plan.reindex()
                _seed_src = (chapter if src == "paste" else idea) or ""
                plan.seed = int(seed) if seed else _stable_seed(_seed_src)
                if series_id:
                    plan.series_id = series_id
                if chapter_no:
                    plan.chapter_no = chapter_no
                if language:
                    plan.language = language
                if not plan.art_style and art_style:
                    plan.art_style = art_style
                if aspect_ratio:
                    plan.aspect_ratio = aspect_ratio
                plan.derive_scene_shot_grammar()
                plan.validate_refs()
                shot_reasons = shot_grammar_gate(plan)
                _emit(observer, "validation", stage="shot_grammar",
                      report=shot_grammar_report(plan), passed=not shot_reasons,
                      reasons=shot_reasons)
                if shot_reasons and os.getenv("STORY_SHOT_GRAMMAR_HARD_GATE", "1") != "0":
                    plan = None
                if plan is None or plan.is_empty() or not plan.visuals:
                    plan = None
                else:
                    logger.info("story_compiler[%s]: OK chars=%d visuals=%d beats=%d topic=%r",
                                _p, len(plan.characters), plan.image_count(),
                                plan.beat_count(), plan.topic)
                    _emit(observer, "authoring_selected", mode="compiler", provider=_p)
                    return plan
            logger.info("story_compiler[%s]: falling back to legacy single-pass", _p)
            _emit(observer, "compiler_fallback", provider=_p,
                  reason="compiler failed a call, parse, or quality gate")

        if src == "idea":
            idea = (idea or "").strip()
            if not idea:
                return None
            logger.info("story_director_v2[%s]: super=%s IDEA len=%d dur=%ds ceiling=%d",
                        _p, SUPER_PROMPT_VERSION, len(idea), duration_sec, ceiling)
            plan = _plan_idea_with_expand(call_fn, idea, duration_sec, genre, language, art_style,
                                          aspect_ratio, subtitle_mode, ceiling, prior_context,
                                          library_catalog, _p, observer=observer)
            _seed_src = idea
        else:
            chapter = (chapter or "").strip()
            if not chapter:
                return None
            threshold = int(os.getenv("STORY_MAX_CHAPTER_CHARS_SINGLE", "18000") or 18000)
            logger.info("story_director_v2[%s]: super=%s PASTE len=%d ceiling=%d",
                        _p, SUPER_PROMPT_VERSION, len(chapter), ceiling)
            if len(chapter) > int(threshold * 1.2):
                plan = _plan_long_chapter(call_fn, chapter, language, art_style, aspect_ratio,
                                          subtitle_mode, ceiling, threshold, prior_context,
                                          library_catalog, has_base_video, base_video_dur,
                                          provider_label=_p, observer=observer)
            else:
                sysm, user = _build_paste_prompt(chapter, language, art_style, aspect_ratio,
                                                 subtitle_mode, ceiling, prior_context,
                                                 library_catalog, has_base_video, base_video_dur)
                plan = _call_and_parse(call_fn, sysm, user, ceiling, stage="legacy_plan",
                                       provider_label=_p, observer=observer)
            _seed_src = chapter
        if plan is None:
            logger.warning("story_director_v2[%s]: no usable plan", _p)
            return None

        # ── Deterministic post-passes ────────────────────────────────────────
        # (No inject_character_canon: it appended a character's look to visual.prompt
        # for an IMAGE-GEN provider. Story is SVG-only — visual.prompt was removed
        # from the schema (s11) and the render composes from setting/archetype/asset —
        # so there is nothing to inject into. Character continuity lives in
        # canonical_desc via the series-memory block, not the visual prompt.)
        plan.cap_visuals(ceiling)
        plan.validate_refs()
        plan.reindex()
        plan.seed = int(seed) if seed else _stable_seed(_seed_src)
        if series_id:
            plan.series_id = series_id
        if chapter_no:
            plan.chapter_no = chapter_no
        if language:
            plan.language = language
        if not plan.art_style and art_style:
            plan.art_style = art_style
        if aspect_ratio:
            plan.aspect_ratio = aspect_ratio
        plan.derive_scene_shot_grammar()
        plan.validate_refs()

        if plan.is_empty() or not plan.visuals:
            return None
        logger.info("story_director_v2[%s]: OK chars=%d visuals=%d beats=%d topic=%r",
                    _p, len(plan.characters), plan.image_count(), plan.beat_count(), plan.topic)
        _emit(observer, "authoring_selected",
              mode=("compiler_fallback_single_pass" if compiler_enabled() else "single_pass"),
              provider=_p)
        return plan
    except Exception as exc:
        logger.warning("story_director_v2[%s]: unexpected %s", provider_label or "?", exc, exc_info=True)
        return None


__all__ = ["run_super_plan", "inject_character_canon", "estimate_super_plan_cost",
           "lint_story_plan", "shot_grammar_report", "shot_grammar_gate",
           "SuperCall", "StoryObserver"]
