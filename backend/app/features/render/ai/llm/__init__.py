"""
llm — multi-provider LLM dispatch for RenderPlan emission.

Routes select_render_plan() to the right provider implementation by name.
Each provider module exposes select_render_plan(...) returning a RenderPlan.

Supported providers: gemini, openai, claude.
Adding a new provider: drop a `<name>_provider.py` with
`select_render_plan(...)` in this directory and add a branch in the
dispatch function below.
"""
from __future__ import annotations

import logging
import os
import time as _time
from typing import Any, Callable, Optional

logger = logging.getLogger("app.render.llm")
logger.info("llm: dispatcher loaded (build=2026-06-04.sprint4c-render-plan-dual)")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")
DEFAULT_PROVIDER = "gemini"

# When LLM_FALLBACK_ENABLED=1, a None result from the primary provider
# triggers sequential fallback through the remaining SUPPORTED_PROVIDERS.
# Default ON — set LLM_FALLBACK_ENABLED=0 to opt out (primary-only, no
# cross-provider fallback; lower cost/latency on a failing render).
_LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "1") == "1"


def _disabled_providers() -> "set[str]":
    """Providers explicitly turned OFF via ``LLM_DISABLED_PROVIDERS`` (comma-
    separated, e.g. ``openai,claude``). Read at CALL time so the lock can be
    toggled by editing ``.env`` + restarting, with no code change. Empty by
    default → every SUPPORTED_PROVIDER stays eligible (pre-existing behaviour)."""
    raw = os.getenv("LLM_DISABLED_PROVIDERS", "") or ""
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _provider_chain(primary: str) -> "list[str]":
    """Ordered providers to try: ``primary`` first, then the cross-provider
    fallbacks (when ``LLM_FALLBACK_ENABLED``), with any ``LLM_DISABLED_PROVIDERS``
    filtered out. Never returns empty — falls back to ``gemini`` so the render
    pipeline always has a usable provider even if the primary was disabled."""
    chain = [primary]
    if _LLM_FALLBACK_ENABLED:
        chain += [p for p in SUPPORTED_PROVIDERS if p != primary]
    disabled = _disabled_providers()
    filtered = [p for p in chain if p not in disabled]
    return filtered or ["gemini"]

# Story Intelligence pipeline (architecture-review naming, 2026-06-30):
# the recap path runs up to THREE LLM passes — story understanding, editorial
# planning, then scene binding. The flags below independently gate the first
# two; pass-3 (binding) always runs. Failure at any earlier pass is non-fatal
# (Sacred Contract #3) — the next pass degrades to the data it does have.
#
# Pass 1 — Story Understanding (StoryModel). When ON, the binding pass plans
# FROM a committed whole-film understanding. Default ON — set RECAP_TWO_PASS=0
# (legacy env name kept for back-compat) for the pre-R7 single-pass behaviour.
from app.features.render.ai.llm.recap_profile import recap_flag as _recap_flag
_RECAP_TWO_PASS: bool = _recap_flag("RECAP_TWO_PASS")

# Pass 2 — Editorial Blueprint. When ON (and pass-1 produced a StoryModel), a
# cheap LLM call (NO transcript) plans HOW to tell the recap FROM the Story
# Model before scene binding. Default OFF — set RECAP_EDITORIAL_PASS=1 to
# enable. Binding proceeds without the blueprint if pass-2 fails.
_RECAP_EDITORIAL_PASS: bool = _recap_flag("RECAP_EDITORIAL_PASS")


def _inc_recap_pass(phase: str, status: str) -> None:
    """Best-effort recap two-pass metric — never raises (observation only)."""
    try:
        from app.services.metrics import LLM_RECAP_PASS_CALLS
        LLM_RECAP_PASS_CALLS.labels(phase=phase, status=status).inc()
    except Exception:
        pass


def _inc_recap_two_pass(has_story: bool, status: str) -> None:
    """Best-effort pass-2-outcome-by-story-availability metric — never raises."""
    try:
        from app.services.metrics import LLM_RECAP_TWO_PASS_TOTAL
        LLM_RECAP_TWO_PASS_TOTAL.labels(story_model="yes" if has_story else "no", status=status).inc()
    except Exception:
        pass


def _safe_callback(cb: Optional[Callable[..., None]], *args, **kwargs) -> None:
    """Invoke an optional pass-done callback, swallowing every exception.

    Architecture-review Batch A (2026-06-30). The recap dispatcher exposes
    ``on_pass1_done`` / ``on_pass2_done`` hooks so the pipeline can fire
    WebSocket events between hidden LLM passes. Sacred Contract #3 spirit:
    a flaky callback (or a buggy lambda) must never break the dispatch —
    the LLM call already succeeded, the event is best-effort observation.
    """
    if cb is None:
        return
    try:
        cb(*args, **kwargs)
    except Exception as exc:  # pragma: no cover — defensive only
        logger.warning("llm: pass-done callback raised %s — ignored", exc)


def _get_provider_impl(provider_name: str):
    """Return the select_render_plan callable for the named provider."""
    if provider_name == "gemini":
        from app.features.render.ai.llm.providers.gemini import select_render_plan as _impl
    elif provider_name == "openai":
        from app.features.render.ai.llm.providers.openai import select_render_plan as _impl
    elif provider_name == "claude":
        from app.features.render.ai.llm.providers.claude import select_render_plan as _impl
    else:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s — falling back to gemini",
            provider_name, SUPPORTED_PROVIDERS,
        )
        from app.features.render.ai.llm.providers.gemini import select_render_plan as _impl
    return _impl


def _get_recap_impl(provider_name: str):
    """Return the select_recap_plan callable for the named provider."""
    if provider_name == "openai":
        from app.features.render.ai.llm.providers.openai import select_recap_plan as _impl
    elif provider_name == "claude":
        from app.features.render.ai.llm.providers.claude import select_recap_plan as _impl
    else:
        from app.features.render.ai.llm.providers.gemini import select_recap_plan as _impl
    return _impl


def _get_story_impl(provider_name: str):
    """Return the select_story_model (pass-1) callable for the named provider, or
    None if that provider has no pass-1 implementation. Defensive — never raises."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        return getattr(_mod, "select_story_model", None)
    except Exception as exc:
        logger.warning("llm: _get_story_impl(%s) import failed %s", provider_name, exc)
        return None


def _get_editorial_impl(provider_name: str):
    """Return the select_editorial_blueprint (pass-2) callable for the named
    provider, or None if that provider has no pass-2 impl. Defensive — never raises."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        return getattr(_mod, "select_editorial_blueprint", None)
    except Exception as exc:
        logger.warning("llm: _get_editorial_impl(%s) import failed %s", provider_name, exc)
        return None


def _get_content_impl(provider_name: str):
    """Return the select_content_plan (Content Mode) callable for the named
    provider, or None if that provider has no impl. Defensive — never raises."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        return getattr(_mod, "select_content_plan", None)
    except Exception as exc:
        logger.warning("llm: _get_content_impl(%s) import failed %s", provider_name, exc)
        return None


def select_content_plan(
    *,
    provider: str = DEFAULT_PROVIDER,
    script: str,
    target_duration_sec: float = 90.0,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    resolve_key: Optional[Callable[[str], str]] = None,
) -> Optional["ContentPlan"]:
    """Dispatch Content Mode planning (render_format="content") to a provider.

    The provider reads a raw script and emits a ContentPlan (scenes + narration +
    emotion/speed/pause + subtitle-style suggestion). Returns a ContentPlan or
    None (Sacred Contract #3 — never raises). When LLM_FALLBACK_ENABLED=1 and the
    primary returns None, the remaining providers that HAVE an impl are tried in
    order. Providers without a select_content_plan are skipped (v1 ships Gemini
    only; openai/claude add theirs in a later phase).

    ``resolve_key`` (review LOW-1): when given, the api_key for EACH provider tried
    is resolved via ``resolve_key(provider)`` so a cross-provider fallback uses the
    right key (a Gemini fallback must not receive an OpenAI key). Falls back to the
    fixed ``api_key`` when not supplied."""
    if not script or not str(script).strip():
        return None
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = _provider_chain(primary)
    base_kwargs = dict(
        script=script, target_duration_sec=target_duration_sec,
        target_language=target_language, tone=tone, model=model,
    )
    for _p in chain:
        impl = _get_content_impl(_p)
        if impl is None:
            continue
        _key = api_key
        if resolve_key is not None:
            try:
                _key = resolve_key(_p) or ""
            except Exception:
                _key = api_key
        try:
            result = impl(api_key=_key, **base_kwargs)
        except Exception as exc:  # defensive — provider modules already never raise
            logger.warning("llm: select_content_plan provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            if _p != primary:
                logger.info("llm: content fallback succeeded provider=%s (primary=%s None)", _p, primary)
            return result
    logger.warning("llm: select_content_plan produced no plan (providers tried=%s)", chain)
    return None


def _get_story_call_fn(provider_name: str, api_key: str, model: Optional[str]):
    """Return a bound ``call_fn(system, user) -> str | None`` for Story Intelligence
    by reusing the provider's raw content-style call (``_call_<p>_content``), or
    None when that provider has no such call. Defensive — never raises.

    This keeps ALL Story orchestration in story_director + this dispatcher and
    touches the provider modules ZERO (they already expose the raw content call
    for Content Mode)."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        raw_call = getattr(_mod, f"_call_{provider_name}_content", None)
        if raw_call is None:
            return None
        resolved_model = model or getattr(_mod, "_DEFAULT_MODEL", None)
        if not resolved_model:
            return None
        return lambda _sys, _usr: raw_call(api_key, resolved_model, _sys, _usr)
    except Exception as exc:
        logger.warning("llm: _get_story_call_fn(%s) failed %s", provider_name, exc)
        return None


def generate_story_plan_v2(
    *,
    provider: str = "openai",
    source: str = "paste",
    chapter: Optional[str] = None,
    idea: Optional[str] = None,
    duration_sec: int = 0,
    genre: str = "",
    language: str = "vi",
    art_style: str = "",
    aspect_ratio: str = "16:9",
    subtitle_mode: str = "hook_only",
    ceiling: Optional[int] = None,
    series_id: str = "",
    chapter_no: int = 0,
    seed: int = 0,
    prior_context: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    resolve_key: Optional[Callable[[str], str]] = None,
) -> Optional["StoryPlan"]:
    """Story v2 — ONE super call → StoryPlan v2 (mode A adapt / B idea). GPT-centric
    default; super model from ``STORY_SUPER_MODEL`` (gpt-4o, big context). Returns a
    StoryPlan or None (Sacred Contract #3 — never raises)."""
    from app.features.render.ai.llm.story_director_v2 import run_super_plan
    if ceiling is None:
        try:
            ceiling = int(os.getenv("STORY_MAX_IMAGES", "15") or 15)
        except (TypeError, ValueError):
            ceiling = 15
    super_model = model or (os.getenv("STORY_SUPER_MODEL", "gpt-4o").strip() or "gpt-4o")
    primary = (provider or "openai").strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "openai" if "openai" in SUPPORTED_PROVIDERS else DEFAULT_PROVIDER
    for _p in _provider_chain(primary):
        _key = api_key
        if resolve_key is not None:
            try:
                _key = resolve_key(_p) or ""
            except Exception:
                _key = api_key
        if not _key:
            continue
        call_fn = _get_story_call_fn(_p, _key, super_model)
        if call_fn is None:
            continue
        try:
            plan = run_super_plan(
                call_fn=call_fn, source=source, chapter=chapter, idea=idea,
                duration_sec=duration_sec, genre=genre, language=language, art_style=art_style,
                aspect_ratio=aspect_ratio, subtitle_mode=subtitle_mode, ceiling=ceiling,
                series_id=series_id, chapter_no=chapter_no, seed=seed,
                prior_context=prior_context, provider_label=_p,
            )
        except Exception as exc:
            logger.warning("llm: generate_story_plan_v2 provider=%s raised %s", _p, exc)
            plan = None
        if plan is not None:
            if _p != primary:
                logger.info("llm: story-plan-v2 fallback succeeded provider=%s (primary=%s None)", _p, primary)
            return plan
    logger.warning("llm: generate_story_plan_v2 produced no plan")
    return None


def generate_publish_meta(
    *,
    provider: str = DEFAULT_PROVIDER,
    topic: str = "",
    tone: str = "",
    audience: str = "",
    target_language: str = "vi-VN",
    narration_sample: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    resolve_key: Optional[Callable[[str], str]] = None,
) -> Optional[dict]:
    """CU-14 — dispatch publish-metadata generation. Returns a dict or None
    (Sacred Contract #3). Providers without an impl are skipped (v1 Gemini-only)."""
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = _provider_chain(primary)
    base = dict(topic=topic, tone=tone, audience=audience,
                target_language=target_language, narration_sample=narration_sample, model=model)
    for _p in chain:
        try:
            if _p == "openai":
                from app.features.render.ai.llm.providers import openai as _mod
            elif _p == "claude":
                from app.features.render.ai.llm.providers import claude as _mod
            else:
                from app.features.render.ai.llm.providers import gemini as _mod
            impl = getattr(_mod, "generate_publish_meta", None)
        except Exception:
            impl = None
        if impl is None:
            continue
        _key = api_key
        if resolve_key is not None:
            try:
                _key = resolve_key(_p) or ""
            except Exception:
                _key = api_key
        try:
            result = impl(api_key=_key, **base)
        except Exception as exc:
            logger.warning("llm: generate_publish_meta provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            return result
    return None


def select_story_model(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
):
    """Dispatch pass-1 Story Model selection to a provider. Returns a StoryModel or
    None (Sacred Contract #3). With LLM_FALLBACK_ENABLED, providers that have a
    pass-1 impl are tried in order until one yields a model."""
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = _provider_chain(primary)
    kwargs = dict(
        srt_content=srt_content, video_duration=video_duration,
        target_language=target_language, tone=tone, api_key=api_key, model=model,
    )
    for _p in chain:
        impl = _get_story_impl(_p)
        if impl is None:
            continue
        try:
            result = impl(**kwargs)
        except Exception as exc:  # defensive — provider modules already never raise
            logger.warning("llm: select_story_model provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            if _p != primary:
                logger.info("llm: story fallback succeeded provider=%s (primary=%s None)", _p, primary)
            _inc_recap_pass("story", "success")
            return result
    _inc_recap_pass("story", "empty")
    return None


def select_editorial_blueprint(
    *,
    provider: str = DEFAULT_PROVIDER,
    story_model,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
):
    """Dispatch pass-2 Editorial Blueprint selection to a provider. Returns an
    EditorialBlueprint or None (Sacred Contract #3). With LLM_FALLBACK_ENABLED,
    providers that have a pass-2 impl are tried in order until one yields a plan."""
    if story_model is None:
        return None
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = _provider_chain(primary)
    kwargs = dict(
        story_model=story_model, video_duration=video_duration,
        target_language=target_language, tone=tone, api_key=api_key, model=model,
    )
    for _p in chain:
        impl = _get_editorial_impl(_p)
        if impl is None:
            continue
        try:
            result = impl(**kwargs)
        except Exception as exc:  # defensive — provider modules already never raise
            logger.warning("llm: select_editorial_blueprint provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            if _p != primary:
                logger.info("llm: editorial fallback succeeded provider=%s (primary=%s None)", _p, primary)
            _inc_recap_pass("editorial", "success")
            return result
    _inc_recap_pass("editorial", "empty")
    return None


def _get_episode_narration_impl(provider_name: str):
    """Return the select_episode_narration callable for a provider, or None when
    that provider has no per-episode narration impl. Defensive — never raises."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        return getattr(_mod, "select_episode_narration", None)
    except Exception as exc:
        logger.warning("llm: _get_episode_narration_impl(%s) import failed %s", provider_name, exc)
        return None


def select_episode_narration(
    *,
    provider: str = DEFAULT_PROVIDER,
    episode_scenes: list,
    story_model=None,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    episode_title: str = "",
) -> Optional[dict]:
    """P1-2 — dispatch per-episode narration authoring to the named provider.

    Returns ``{index: text}`` or None (the caller keeps its original narration).
    No cross-provider fallback — this is an OPTIONAL refinement; a provider
    without an impl simply yields None. Never raises (Sacred Contract #3)."""
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    impl = _get_episode_narration_impl(primary)
    if impl is None:
        return None
    try:
        return impl(
            episode_scenes=episode_scenes, story_model=story_model,
            target_language=target_language, tone=tone, api_key=api_key,
            model=model, episode_title=episode_title,
        )
    except Exception as exc:
        logger.warning("llm: select_episode_narration provider=%s raised %s", primary, exc)
        return None


def _get_content_narration_impl(provider_name: str):
    """Return the select_content_narration callable for a provider, or None when
    that provider has no impl. Defensive — never raises."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        return getattr(_mod, "select_content_narration", None)
    except Exception as exc:
        logger.warning("llm: _get_content_narration_impl(%s) import failed %s", provider_name, exc)
        return None


def select_content_narration(
    *,
    provider: str = DEFAULT_PROVIDER,
    scenes: list,
    topic: str = "",
    tone: str = "",
    target_language: str = "vi-VN",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[dict]:
    """Content per-scene narration refine — dispatch to the named provider.

    Returns ``{index: text}`` or None (the caller keeps its original narration).
    No cross-provider fallback — this is an OPTIONAL refinement; a provider
    without an impl simply yields None. Never raises (Sacred Contract #3)."""
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    impl = _get_content_narration_impl(primary)
    if impl is None:
        return None
    try:
        return impl(
            scenes=scenes, topic=topic, tone=tone,
            target_language=target_language, api_key=api_key, model=model,
        )
    except Exception as exc:
        logger.warning("llm: select_content_narration provider=%s raised %s", primary, exc)
        return None


def select_recap_plan(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    story_model: Optional[Any] = None,
    on_pass1_done: Optional[Callable[[Any], None]] = None,
    on_pass2_done: Optional[Callable[[Any], None]] = None,
) -> Optional["RecapPlan"]:
    """Dispatch recap scene-selection (render_format="recap") to a provider.

    The provider selects chronological, act-structured scenes covering the
    whole film. Returns a RecapPlan or None (Sacred Contract #3). When
    LLM_FALLBACK_ENABLED=1 and the primary returns None, the remaining
    providers are tried in order.

    Architecture-review Batch A — ``on_pass1_done`` and ``on_pass2_done``
    are optional callbacks the caller (recap_pipeline) uses to emit
    WebSocket events between the hidden Story Intelligence passes. Each is
    invoked with the produced model (StoryModel / EditorialBlueprint) on
    success or ``None`` on failure; failures inside the callback are
    swallowed and never break the LLM dispatch.

    Architecture-review Batch C — ``story_model`` is an OPTIONAL externally
    produced StoryModel (built by the Comprehension pipeline stage). When
    provided, the internal pass-1 is skipped entirely AND ``on_pass1_done``
    is NOT fired (the caller already observed it through the Comprehension
    stage's own WS events). When ``None`` (every pre-Batch-C caller),
    behaviour is bit-identical to Batch A: the internal pass-1 runs under
    the ``RECAP_TWO_PASS`` flag and ``on_pass1_done`` fires as before.
    """
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = _provider_chain(primary)
    # Pass 1 — Story Understanding. Two code paths:
    #   (a) External story_model provided (Batch C, recap_pipeline → Comprehension
    #       stage already produced one) → skip internal pass-1; do NOT fire
    #       on_pass1_done (caller has its own observation).
    #   (b) story_model is None (every pre-Batch-C caller; Batch C kill-switch
    #       path) → run the internal pass-1 under RECAP_TWO_PASS exactly like
    #       Batch A. Behaviour bit-identical for existing consumers.
    if story_model is not None:
        logger.info(
            "llm: recap pass-1 (story) externally provided — internal pass-1 skipped"
        )
    elif _RECAP_TWO_PASS:
        try:
            story_model = select_story_model(
                provider=primary, srt_content=srt_content, video_duration=video_duration,
                target_language=target_language, tone=tone, api_key=api_key, model=model,
            )
        except Exception as exc:
            logger.warning("llm: pass-1 story model raised %s — single-pass", exc)
            story_model = None
        logger.info("llm: recap pass-1 (story) story_model=%s", story_model is not None)
        _safe_callback(on_pass1_done, story_model)
    # Pass 2 — Editorial Blueprint. Best-effort, gated on the flag AND a
    # non-empty pass-1. None → binding proceeds without it (Sacred Contract #3).
    editorial = None
    if _RECAP_EDITORIAL_PASS and story_model is not None:
        try:
            editorial = select_editorial_blueprint(
                provider=primary, story_model=story_model, video_duration=video_duration,
                target_language=target_language, tone=tone, api_key=api_key, model=model,
            )
        except Exception as exc:
            logger.warning("llm: pass-2 editorial raised %s — binding without it", exc)
            editorial = None
        logger.info("llm: recap pass-2 (editorial) editorial=%s", editorial is not None)
        _safe_callback(on_pass2_done, editorial)
    kwargs = dict(
        srt_content=srt_content,
        video_duration=video_duration,
        target_language=target_language,
        tone=tone,
        api_key=api_key,
        model=model,
        story_model=story_model,
        editorial=editorial,
    )
    _has_story = story_model is not None
    for _p in chain:
        try:
            result = _get_recap_impl(_p)(**kwargs)
        except Exception as exc:  # defensive — provider modules already never raise
            logger.warning("llm: select_recap_plan provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            if _p != primary:
                logger.info("llm: recap fallback succeeded provider=%s (primary=%s None)", _p, primary)
            _inc_recap_pass("recap", "success")
            _inc_recap_two_pass(_has_story, "success")
            return result
        logger.warning("llm: recap provider=%s returned None", _p)
    _inc_recap_pass("recap", "empty")
    _inc_recap_two_pass(_has_story, "empty")
    return None


def select_render_plan(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str = "",
    model: Optional[str] = None,
    language: str = "auto",
    editorial_hint: str = "",
    target_duration: int = 0,
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
    target_platform: str = "",
    # S5 — creator preference hints (B+C). Defaults match what
    # build_render_plan_prompt treats as "no hint" so providers that
    # don't yet thread these through behave exactly as before.
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: Optional[str] = None,
    multi_variant: bool = False,
    structure_bias: Optional[str] = None,
    # C.1 Phase 3 (2026-06-30): optional StoryModel from the Comprehension
    # stage (Batch C / C.1 Phase 2). When provided, the active provider's
    # build_render_plan_prompt injects a _story_block_clips section so the
    # clip selection LLM grounds picks in whole-source semantic
    # understanding (theme, conflict, characters, emotional curve).
    # Default None → byte-identical pre-Phase-3 prompt; no LLM cache flush.
    story_model: Optional[Any] = None,
) -> Optional["RenderPlan"]:
    """Dispatch RenderPlan emission to the named LLM provider.

    The provider is asked to emit a full RenderPlan (clips + subtitle_policy +
    camera_strategy + audio_plan + overlays) in a single call.

    ``target_duration`` (T2.4 — Audit 2026-06-08 closure, Batch A
    V8-A1) is the creator's soft total-duration target in seconds, 0 =
    disabled (backward-compat default — callers that don't pass it
    behave exactly as pre-T2.4).

    ``clip_lock`` / ``clip_exclude`` (Strategic-1 — Audit 2026-06-08
    closure, Batch A V8-A12) are UP26 Pro Timeline Steering hard
    constraints — lists of {start_sec, end_sec} dicts. None / empty
    disables each prompt section (backward-compat default).

    When ``LLM_FALLBACK_ENABLED=1`` and the primary provider returns None,
    the remaining SUPPORTED_PROVIDERS are tried in order until one succeeds.
    Default is ON — set ``LLM_FALLBACK_ENABLED=0`` to opt out.

    Returns None on any failure. Sacred Contract #3 — provider modules
    catch all exceptions and surface None at the wire.
    """
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s — using gemini",
            provider, SUPPORTED_PROVIDERS,
        )
        primary = "gemini"

    chain = _provider_chain(primary)

    kwargs = dict(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
        api_key=api_key,
        model=model,
        language=language,
        editorial_hint=editorial_hint,
        target_duration=target_duration,
        clip_lock=clip_lock,
        clip_exclude=clip_exclude,
        target_platform=target_platform,
        # S5 — creator preferences (B+C)
        video_type=video_type,
        hook_strength=hook_strength,
        ai_target_market=ai_target_market,
        subtitle_emphasis=subtitle_emphasis,
        multi_variant=multi_variant,
        structure_bias=structure_bias,
        # C.1 Phase 3 — optional StoryModel forwarded to the provider
        story_model=story_model,
    )

    for _p in chain:
        _impl = _get_provider_impl(_p)
        _t0 = _time.perf_counter()
        result = _impl(**kwargs)
        _status = "success" if result is not None else "empty"
        try:
            from app.services.metrics import (
                LLM_RENDER_PLAN_CALLS, LLM_RENDER_PLAN_LATENCY, LLM_SEGMENTS_SELECTED,
            )
            LLM_RENDER_PLAN_CALLS.labels(provider=_p, status=_status).inc()
            LLM_RENDER_PLAN_LATENCY.labels(provider=_p).observe(_time.perf_counter() - _t0)
            if result is not None:
                LLM_SEGMENTS_SELECTED.labels(provider=_p).inc(len(result.clips))
        except Exception:
            pass
        if result is not None:
            if _p != primary:
                logger.info(
                    "llm: fallback succeeded provider=%s (primary=%s returned None)", _p, primary,
                )
            return result
        logger.warning("llm: provider=%s returned None", _p)

    return None
