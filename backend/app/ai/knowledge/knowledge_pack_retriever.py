"""
knowledge_pack_retriever.py — Deterministic knowledge pack retrieval. Phase 53A.

Simple tag/domain overlap scoring — no embeddings, no vector DB, no internet.

Public API:
    retrieve_knowledge(domain, tags, max_results, packs_dir) -> dict
    retrieve_knowledge_context(edit_plan, packs_dir)         -> dict

Safety contract:
    ✅ Local only — no internet, no cloud API, no vector DB
    ✅ Never raises — returns fallback dict on any error
    ✅ Deterministic — same inputs always produce same output
    ✅ Bounded — max_results limits output size
    ✅ Advisory only — knowledge informs, never executes
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List, Optional

from app.ai.knowledge.knowledge_pack_schema import (
    KnowledgeContext,
    KnowledgeMatch,
    KnowledgePack,
    KnowledgePackRule,
    fallback_knowledge_context,
)
from app.ai.knowledge.knowledge_pack_loader import load_knowledge_packs

logger = logging.getLogger("app.ai.knowledge.pack_retriever")

_DEFAULT_MAX_RESULTS: int = 10


def retrieve_knowledge(
    domain: Optional[str] = None,
    tags: Optional[List[str]] = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
    packs_dir: Optional[Path] = None,
) -> dict:
    """Retrieve matching knowledge rules by domain and tag overlap. Never raises.

    Args:
        domain:      Target domain string (e.g. "subtitle", "camera").
                     None means all domains match.
        tags:        List of tag strings to match against pack + rule tags.
        max_results: Maximum number of matches to return (default 10).
        packs_dir:   Override for the packs directory (used in tests).

    Returns:
        {"knowledge_matches": [KnowledgeMatch.to_dict(), ...]}
        Empty list on no matches or any error.
    """
    try:
        return _retrieve(domain, tags or [], int(max_results), packs_dir)
    except Exception as exc:
        logger.debug("knowledge_retriever_failed: %s", exc)
        return {"knowledge_matches": []}


def retrieve_knowledge_context(
    edit_plan: Any,
    packs_dir: Optional[Path] = None,
) -> dict:
    """Build a KnowledgeContext from edit plan signals. Never raises.

    Reads Phase 52A/B/C results and pacing metadata to infer relevant domains
    and tags, then retrieves matching knowledge rules.

    Returns:
        {"knowledge_context": KnowledgeContext.to_dict()}
    """
    try:
        return _build_context(edit_plan, packs_dir)
    except Exception as exc:
        logger.debug("retrieve_knowledge_context_failed: %s", exc)
        return {"knowledge_context": fallback_knowledge_context()}


# ---------------------------------------------------------------------------
# Internal retrieval
# ---------------------------------------------------------------------------

def _retrieve(
    domain: Optional[str],
    tags: List[str],
    max_results: int,
    packs_dir: Optional[Path],
) -> dict:
    packs = load_knowledge_packs(packs_dir)
    if not packs:
        return {"knowledge_matches": []}

    query_tags = {t.lower().strip() for t in tags if t}
    query_domain = domain.lower().strip() if domain else None

    matches: List[tuple] = []  # (score, pack_id, rule_id, KnowledgeMatch)

    for pack in packs:
        pack_domain = pack.domain.lower()
        pack_tags   = {t.lower() for t in pack.tags}

        # Domain score
        domain_score = 2 if (query_domain is None or pack_domain == query_domain) else 0
        if query_domain is not None and pack_domain != query_domain:
            continue  # strict domain filter when domain is specified

        for rule in pack.rules:
            rule_tags = {t.lower() for t in rule.applies_to}
            all_rule_tags = pack_tags | rule_tags

            # Tag overlap score
            tag_score = len(query_tags & all_rule_tags) if query_tags else 0

            total_score = domain_score + tag_score

            match = KnowledgeMatch(
                pack_id=pack.id,
                rule_id=rule.id,
                domain=pack.domain,
                title=rule.title,
                recommendation=dict(rule.recommendation),
                confidence=rule.confidence,
                _score=float(total_score),
            )
            # Stable sort key: (-score, pack_id, rule_id) for full determinism
            matches.append((-total_score, pack.id, rule.id, match))

    # Sort: highest score first; ties broken by pack_id then rule_id (alphabetical)
    matches.sort(key=lambda x: (x[0], x[1], x[2]))

    top = [m for _, _, _, m in matches[:max(1, max_results)]]

    return {"knowledge_matches": [m.to_dict() for m in top]}


# ---------------------------------------------------------------------------
# Context builder (edit_plan → KnowledgeContext)
# ---------------------------------------------------------------------------

def _build_context(edit_plan: Any, packs_dir: Optional[Path]) -> dict:
    if edit_plan is None:
        return {"knowledge_context": fallback_knowledge_context()}

    # Infer domains from available subsystem results
    domains: List[str] = []
    tags: List[str] = []

    sqv2 = _get(edit_plan, "subtitle_quality_v2")
    cqv2 = _get(edit_plan, "camera_quality_v2")
    hqv2 = _get(edit_plan, "hook_quality_v2")
    pacing = _get(edit_plan, "pacing")
    moi    = _get(edit_plan, "market_optimization_intelligence")

    if sqv2.get("overall", 0) > 0 or sqv2.get("confidence", 0.0) > 0.0:
        domains.append("subtitle")
        tags.extend(["subtitle", "readability"])

    if cqv2.get("overall", 0) > 0 or cqv2.get("confidence", 0.0) > 0.0:
        domains.append("camera")
        tags.extend(["camera"])

    if hqv2.get("overall", 0) > 0 or hqv2.get("confidence", 0.0) > 0.0:
        domains.append("hook")
        tags.extend(["hook"])

    # Pacing tags
    pacing_style = str(pacing.get("pacing_style") or "").lower()
    energy = float(pacing.get("energy_level") or 0.0)
    if pacing_style in ("upbeat", "fast", "dynamic"):
        tags.append("short_form")
    if energy >= 0.60:
        tags.append("mobile")

    # Market tags
    market = str(moi.get("target_market") or "").lower()
    if market:
        tags.append(market)

    # Retrieve for each active domain and aggregate
    all_matches: List[KnowledgeMatch] = []
    reasoning: List[str] = []

    if not domains:
        # No active subsystems — return minimal empty context
        return {"knowledge_context": fallback_knowledge_context()}

    seen_rules: set = set()
    for dom in sorted(set(domains)):
        result = _retrieve(dom, tags, _DEFAULT_MAX_RESULTS, packs_dir)
        for m_dict in result.get("knowledge_matches") or []:
            key = (m_dict.get("pack_id"), m_dict.get("rule_id"))
            if key not in seen_rules:
                seen_rules.add(key)
                all_matches.append(KnowledgeMatch(
                    pack_id=str(m_dict.get("pack_id") or ""),
                    rule_id=str(m_dict.get("rule_id") or ""),
                    domain=str(m_dict.get("domain") or dom),
                    title=str(m_dict.get("title") or ""),
                    recommendation=dict(m_dict.get("recommendation") or {}),
                    confidence=float(m_dict.get("confidence") or 0.0),
                ))
        if result.get("knowledge_matches"):
            reasoning.append(
                f"Matched {dom} knowledge for {'mobile' if 'mobile' in tags else 'creator'} format"
            )

    if not all_matches:
        ctx = KnowledgeContext(
            available=False,
            domains=list(sorted(set(domains))),
            matches=[],
            confidence=0.0,
            reasoning=["No knowledge rules matched the current plan context"],
        )
        return {"knowledge_context": ctx.to_dict()}

    avg_conf = sum(m.confidence for m in all_matches) / len(all_matches)

    ctx = KnowledgeContext(
        available=True,
        domains=list(sorted(set(domains))),
        matches=all_matches,
        confidence=round(avg_conf, 2),
        reasoning=reasoning,
    )

    logger.debug(
        "knowledge_context_built domains=%s matches=%d confidence=%.2f",
        ctx.domains, len(ctx.matches), ctx.confidence,
    )

    return {"knowledge_context": ctx.to_dict()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(edit_plan: Any, attr: str) -> dict:
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}
