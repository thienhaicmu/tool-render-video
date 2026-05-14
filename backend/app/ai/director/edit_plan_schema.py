"""
edit_plan_schema.py — AI edit plan data structures.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIClipPlan:
    start: float
    end: float
    score: float
    reason: str = ""
    source: str = "local_ai"


@dataclass
class AISubtitlePlan:
    """Subtitle behavior planning. Phase 5 expands with emphasis/density/awareness fields."""
    tone: str = "default"
    highlight_keywords: bool = False
    max_words_per_line: Optional[int] = None
    # Phase 5
    emphasis_style: str = "none"
    density: str = "normal"
    beat_aware: bool = False
    emotion_aware: bool = False
    reason: str = ""


@dataclass
class AICameraPlan:
    """Camera behavior planning. Phase 5 expands with zoom/follow/energy fields."""
    mode: str = "default"
    behavior: str = "none"
    subtitle_safe: bool = True
    # Phase 5
    zoom_strength: float = 1.0
    follow_strength: float = 0.5
    motion_energy: Optional[float] = None
    reason: str = ""


@dataclass
class AIPacingPlan:
    """Beat and emotion pacing metadata attached to the AI edit plan.

    Observation-only in Phase 4 — does not yet influence render commands.
    """
    beat_available: bool = False
    bpm: Optional[float] = None
    beat_count: int = 0
    energy_level: Optional[float] = None
    pacing_style: str = "default"
    emotion: str = "neutral"
    emotion_score: float = 0.0
    suggested_cut_style: str = "standard"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "beat_available": self.beat_available,
            "bpm": self.bpm,
            "beat_count": self.beat_count,
            "energy_level": self.energy_level,
            "pacing_style": self.pacing_style,
            "emotion": self.emotion,
            "emotion_score": self.emotion_score,
            "suggested_cut_style": self.suggested_cut_style,
            "warnings": list(self.warnings),
        }


@dataclass
class AIBeatExecutionPlan:
    """Beat-aware execution plan. Phase 11 — metadata-only, no timing mutations."""
    enabled: bool = False
    beat_available: bool = False
    bpm: Optional[float] = None
    beat_count: int = 0
    pulse_strength: float = 0.0
    suggested_transition_style: str = "none"
    execution_mode: str = "metadata_only"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "beat_available": self.beat_available,
            "bpm": self.bpm,
            "beat_count": self.beat_count,
            "pulse_strength": self.pulse_strength,
            "suggested_transition_style": self.suggested_transition_style,
            "execution_mode": self.execution_mode,
            "warnings": list(self.warnings),
        }


@dataclass
class AIEditPlan:
    enabled: bool
    mode: str
    selected_segments: List[AIClipPlan]
    subtitle: AISubtitlePlan
    camera: AICameraPlan
    warnings: List[str] = field(default_factory=list)
    fallback_used: bool = False
    memory_context: dict = field(default_factory=dict)
    pacing: AIPacingPlan = field(default_factory=AIPacingPlan)
    # Phase 6 — explainability
    explainability: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    # Phase 11 — beat execution plan (populated by beat_execution module)
    beat_execution: dict = field(default_factory=dict)
    # Phase 12 — story intelligence (populated by story_analyzer module)
    story: dict = field(default_factory=dict)
    # Phase 13 — smart preset evolution (populated by preset_analyzer module)
    preset_evolution: dict = field(default_factory=dict)
    # Phase 14 — creator style intelligence (populated by style_classifier module)
    creator_style: dict = field(default_factory=dict)
    # Phase 15 — external knowledge (populated by knowledge_retriever module)
    external_knowledge: dict = field(default_factory=dict)
    # Phase 16 — retention intelligence (populated by retention_analyzer module)
    retention: dict = field(default_factory=dict)
    # Phase 17 — dynamic subtitle execution (populated by subtitle_execution module)
    subtitle_execution: dict = field(default_factory=dict)
    # Phase 18 — beat-synced visual execution (populated by visual_execution module)
    beat_visual_execution: dict = field(default_factory=dict)
    # Phase 19 — retention-driven timing mutation (populated by timing_recommender module)
    timing_mutation: dict = field(default_factory=dict)
    # Phase 20 — story-driven edit optimization (populated by story_recommender module)
    story_optimization: dict = field(default_factory=dict)
    # Phase 21 — safe autonomous variant rendering (populated by variant_generator module)
    variants: dict = field(default_factory=dict)
    # Phase 22 — AI best variant selection (populated by variant_selector module)
    variant_selection: dict = field(default_factory=dict)
    # Phase 23 — Creator style adaptation (populated by style_classifier/style_adapter modules)
    creator_style_adaptation: dict = field(default_factory=dict)
    # Phase 24 — AI render decision preview (populated by decision_preview module)
    render_decision_preview: dict = field(default_factory=dict)
    # Phase 25 — safe execution recommendation pack (populated by execution_recommendation module)
    execution_recommendations: dict = field(default_factory=dict)
    # Phase 26 — execution simulation layer (populated by execution_simulator module)
    execution_simulation: dict = field(default_factory=dict)
    # Phase 27 — safe bounded render mutations (populated by mutation_engine module)
    safe_render_mutations: dict = field(default_factory=dict)
    # Phase 28 — safe multi-variant render planning (populated by multivariant_planner module)
    multivariant_render_plans: dict = field(default_factory=dict)
    # Phase 29 — safe multi-variant render execution (populated by multivariant_execution module)
    multivariant_execution: dict = field(default_factory=dict)
    # Phase 30 — AI output ranking and best export recommendation (populated by output_ranker module)
    output_ranking: dict = field(default_factory=dict)
    # Phase 31 — AI apply policy layer (populated by policy_engine module)
    ai_apply_policy: dict = field(default_factory=dict)
    # Phase 32 — safe timing mutation apply (populated by timing_apply_engine module)
    timing_apply: dict = field(default_factory=dict)
    # Phase 33 — subtitle text optimization apply (populated by subtitle_apply_engine module)
    subtitle_text_apply: dict = field(default_factory=dict)
    # Phase 34 — safe camera motion apply (populated by camera_apply_engine module)
    camera_motion_apply: dict = field(default_factory=dict)
    # Phase 35 — AI clip candidate discovery (populated by clip_candidate_engine module)
    clip_candidate_discovery: dict = field(default_factory=dict)
    # Phase 36 — AI clip segment selection (populated by clip_segment_selector module)
    clip_segment_selection: dict = field(default_factory=dict)
    # Phase 37 — AI multi-clip batch planning (populated by clip_batch_planner module)
    clip_batch_planning: dict = field(default_factory=dict)
    # Phase 38 — AI feature enhancement integration (populated by feature_enhancement_engine module)
    feature_enhancement: dict = field(default_factory=dict)
    # Phase 39 — External creator knowledge ingestion (populated by knowledge_registry module)
    creator_knowledge: dict = field(default_factory=dict)
    # Phase 40 — Creator pattern extraction (populated by pattern_registry module)
    creator_patterns: dict = field(default_factory=dict)
    # Phase 41 — Retrieval-based creator intelligence (populated by retrieval_engine module)
    creator_retrieval: dict = field(default_factory=dict)
    # Phase 42 — Adaptive creator intelligence (populated by adaptive_learning module)
    adaptive_creator_intelligence: dict = field(default_factory=dict)
    # Phase 43 — Creator feedback loop intelligence (populated by feedback_learning module)
    creator_feedback_intelligence: dict = field(default_factory=dict)
    # Phase 44 — Market-aware optimization intelligence (populated by market_optimizer module)
    market_optimization_intelligence: dict = field(default_factory=dict)
    # Phase 45 — AI render quality evaluation (populated post-render by quality_evaluator module)
    render_quality_evaluation: dict = field(default_factory=dict)
    # Phase 46 — Creator preset evolution intelligence (populated by preset_evolution_engine module)
    creator_preset_evolution: dict = field(default_factory=dict)
    # Phase 47 — Multi-signal AI render orchestration (populated by render_orchestrator module)
    multi_signal_orchestration: dict = field(default_factory=dict)
    # Phase 48 — Safe controlled influence pack (populated by influence_engine module)
    safe_influence_pack: dict = field(default_factory=dict)
    # Phase 50A — Deep subtitle preference intelligence (populated by subtitle_preference_inference module)
    creator_subtitle_preference: dict = field(default_factory=dict)
    # Phase 50B — Creator camera preference intelligence (populated by camera_preference_inference module)
    creator_camera_preference: dict = field(default_factory=dict)
    # Phase 50C — Subtitle preference safe influence (populated by subtitle_influence_engine module)
    creator_subtitle_influence: dict = field(default_factory=dict)
    # Phase 50D — Unified creator preference fusion profile (populated by fusion_engine module)
    creator_preference_profile: dict = field(default_factory=dict)
    # Phase 51A — Safe strategy variant generator (populated by variant_generator module)
    strategy_variants: dict = field(default_factory=dict)
    # Phase 51B — Variant evaluation engine (populated by variant_evaluator module)
    variant_evaluation: dict = field(default_factory=dict)
    # Phase 51C — Best strategy reasoning (populated by strategy_reasoner module)
    best_strategy_reasoning: dict = field(default_factory=dict)
    # Phase 52A — Subtitle quality intelligence v2 (populated by subtitle_quality_evaluator module)
    subtitle_quality_v2: dict = field(default_factory=dict)
    # Phase 52B — Camera quality intelligence v2 (populated by camera_quality_evaluator module)
    camera_quality_v2: dict = field(default_factory=dict)
    # Phase 52C — Hook quality intelligence v2 (populated by hook_quality_evaluator module)
    hook_quality_v2: dict = field(default_factory=dict)
    # Phase 52D — Unified quality score v2 (populated by unified_quality_evaluator module)
    render_quality_v2: dict = field(default_factory=dict)
    # Phase 53A — Knowledge injection foundation (populated by knowledge_pack_retriever module)
    knowledge_injection: dict = field(default_factory=dict)
    # Phase 53E — Knowledge-aware render reasoning context (populated by knowledge_reasoning_context module)
    knowledge_reasoning_context: dict = field(default_factory=dict)
    # Phase 54 — Knowledge-aware influence upgrade (populated by knowledge_influence_context module)
    knowledge_influence_context: dict = field(default_factory=dict)
    # Phase 55A — Platform knowledge foundation (populated by platform_knowledge_retriever module)
    platform_context: dict = field(default_factory=dict)
    # Phase 55B — Platform subtitle intelligence (populated by platform_subtitle_retriever module)
    platform_subtitle_context: dict = field(default_factory=dict)
    # Phase 55C — Platform camera intelligence (populated by platform_camera_retriever module)
    platform_camera_context: dict = field(default_factory=dict)
    # Phase 55D — Platform hook & retention intelligence (populated by platform_hook_retriever module)
    platform_hook_context: dict = field(default_factory=dict)
    # Phase 55E — Platform-aware render strategy (populated by platform_render_strategy_engine module)
    platform_render_strategy: dict = field(default_factory=dict)
    # Phase 56 — Platform-aware strategy influence (populated by platform_strategy_influence_context module)
    platform_strategy_influence: dict = field(default_factory=dict)
    # Phase 57 — Platform-aware quality feedback loop (populated by platform_quality_feedback_evaluator module)
    platform_quality_feedback: dict = field(default_factory=dict)
    # Phase 59A — Subtitle influence promotion result (populated by subtitle_promotion_engine module)
    subtitle_execution_promotion: dict = field(default_factory=dict)
    # Phase 59B — Camera influence promotion result (populated by camera_promotion_engine module)
    camera_execution_promotion: dict = field(default_factory=dict)
    # Phase 59C — Segment selection promotion result (populated by segment_promotion_engine module)
    segment_selection_promotion: dict = field(default_factory=dict)
    # Phase 59D — Quality-gated influence result (populated by quality_gate_engine module)
    quality_gated_influence: dict = field(default_factory=dict)
    # Phase 60A — AI execution metrics and telemetry (populated by ai_execution_metrics_engine)
    ai_execution_metrics: dict = field(default_factory=dict)
    # Phase 60A — Compact AI execution summary (populated by ai_execution_metrics_engine)
    ai_execution_summary: dict = field(default_factory=dict)
    # Phase 60B — A/B render evaluation result (populated by ab_evaluation_engine)
    ai_ab_evaluation: dict = field(default_factory=dict)
    # Phase 60C — Creator benchmark validation (populated by creator_benchmark_engine)
    creator_benchmark_summary: dict = field(default_factory=dict)
    # Phase 60D — AI execution mode and rollback control
    ai_execution_mode: dict = field(default_factory=dict)
    ai_execution_rollback: dict = field(default_factory=dict)
    # Phase 61A — Creator archetype strategy (advisory metadata only)
    creator_archetype_strategy: dict = field(default_factory=dict)
    # Phase 61B — Creator subtitle style promotion (advisory metadata only)
    creator_subtitle_style_promotion: dict = field(default_factory=dict)
    # Phase 61C — Creator camera style promotion (advisory metadata only)
    creator_camera_style_promotion: dict = field(default_factory=dict)
    # Phase 61D — Creator render strategy fusion (advisory metadata only)
    creator_render_strategy: dict = field(default_factory=dict)
    # Phase 62A — Render outcome tracking (tracking-only, no mutation)
    render_outcome_tracking: dict = field(default_factory=dict)
    # Phase 62B — Creator preference reinforcement (reinforcement metadata only)
    creator_preference_reinforcement: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # Compact confidence subset exposed as top-level key for easy result_json access.
        compact_confidence = {
            k: self.confidence.get(k)
            for k in ("overall", "semantic", "memory", "pacing")
            if self.confidence.get(k) is not None
        }
        # Summary without the nested confidence copy to avoid duplication.
        summary = self.explainability.get("summary", {})
        ai_summary = {k: v for k, v in summary.items() if k != "confidence"}

        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "selected_segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "score": s.score,
                    "reason": s.reason,
                    "source": s.source,
                }
                for s in self.selected_segments
            ],
            "subtitle": {
                "tone": self.subtitle.tone,
                "highlight_keywords": self.subtitle.highlight_keywords,
                "max_words_per_line": self.subtitle.max_words_per_line,
                "emphasis_style": self.subtitle.emphasis_style,
                "density": self.subtitle.density,
                "beat_aware": self.subtitle.beat_aware,
                "emotion_aware": self.subtitle.emotion_aware,
                "reason": self.subtitle.reason,
            },
            "camera": {
                "mode": self.camera.mode,
                "behavior": self.camera.behavior,
                "subtitle_safe": self.camera.subtitle_safe,
                "zoom_strength": self.camera.zoom_strength,
                "follow_strength": self.camera.follow_strength,
                "motion_energy": self.camera.motion_energy,
                "reason": self.camera.reason,
            },
            "warnings": list(self.warnings),
            "fallback_used": self.fallback_used,
            "memory_context": dict(self.memory_context),
            "pacing": self.pacing.to_dict(),
            "explainability": dict(self.explainability),
            "confidence": dict(self.confidence),
            "ai_summary": ai_summary,
            "ai_confidence": compact_confidence,
            "beat_execution": dict(self.beat_execution),
            "story": dict(self.story),
            "preset_evolution": dict(self.preset_evolution),
            "creator_style": dict(self.creator_style),
            "external_knowledge": dict(self.external_knowledge),
            "retention": dict(self.retention),
            "subtitle_execution": dict(self.subtitle_execution),
            "beat_visual_execution": dict(self.beat_visual_execution),
            "timing_mutation": dict(self.timing_mutation),
            "story_optimization": dict(self.story_optimization),
            "variants": dict(self.variants),
            "variant_selection": dict(self.variant_selection),
            "creator_style_adaptation": dict(self.creator_style_adaptation),
            "render_decision_preview": dict(self.render_decision_preview),
            "execution_recommendations": dict(self.execution_recommendations),
            "execution_simulation": dict(self.execution_simulation),
            "safe_render_mutations": dict(self.safe_render_mutations),
            "multivariant_render_plans": dict(self.multivariant_render_plans),
            "multivariant_execution": dict(self.multivariant_execution),
            "output_ranking": dict(self.output_ranking),
            "ai_apply_policy": dict(self.ai_apply_policy),
            "timing_apply": dict(self.timing_apply),
            "subtitle_text_apply": dict(self.subtitle_text_apply),
            "camera_motion_apply": dict(self.camera_motion_apply),
            "clip_candidate_discovery": dict(self.clip_candidate_discovery),
            "clip_segment_selection": dict(self.clip_segment_selection),
            "clip_batch_planning": dict(self.clip_batch_planning),
            "feature_enhancement": dict(self.feature_enhancement),
            "creator_knowledge": dict(self.creator_knowledge),
            "creator_patterns": dict(self.creator_patterns),
            "creator_retrieval": dict(self.creator_retrieval),
            "adaptive_creator_intelligence": dict(self.adaptive_creator_intelligence),
            "creator_feedback_intelligence": dict(self.creator_feedback_intelligence),
            "market_optimization_intelligence": dict(self.market_optimization_intelligence),
            "render_quality_evaluation": dict(self.render_quality_evaluation),
            "creator_preset_evolution": dict(self.creator_preset_evolution),
            "multi_signal_orchestration": dict(self.multi_signal_orchestration),
            "safe_influence_pack": dict(self.safe_influence_pack),
            "creator_subtitle_preference": dict(self.creator_subtitle_preference),
            "creator_camera_preference": dict(self.creator_camera_preference),
            "creator_subtitle_influence": dict(self.creator_subtitle_influence),
            "creator_preference_profile": dict(self.creator_preference_profile),
            "strategy_variants": dict(self.strategy_variants),
            "variant_evaluation": dict(self.variant_evaluation),
            "best_strategy_reasoning": dict(self.best_strategy_reasoning),
            "subtitle_quality_v2": dict(self.subtitle_quality_v2),
            "camera_quality_v2": dict(self.camera_quality_v2),
            "hook_quality_v2": dict(self.hook_quality_v2),
            "render_quality_v2": dict(self.render_quality_v2),
            "knowledge_injection": dict(self.knowledge_injection),
            "knowledge_reasoning_context": dict(self.knowledge_reasoning_context),
            "knowledge_influence_context": dict(self.knowledge_influence_context),
            "platform_context": dict(self.platform_context),
            "platform_subtitle_context": dict(self.platform_subtitle_context),
            "platform_camera_context": dict(self.platform_camera_context),
            "platform_hook_context": dict(self.platform_hook_context),
            "platform_render_strategy": dict(self.platform_render_strategy),
            "platform_strategy_influence": dict(self.platform_strategy_influence),
            "platform_quality_feedback": dict(self.platform_quality_feedback),
            "subtitle_execution_promotion":  dict(self.subtitle_execution_promotion),
            "camera_execution_promotion":    dict(self.camera_execution_promotion),
            "segment_selection_promotion":   dict(self.segment_selection_promotion),
            "quality_gated_influence":       dict(self.quality_gated_influence),
            "ai_execution_metrics":          dict(self.ai_execution_metrics),
            "ai_execution_summary":          dict(self.ai_execution_summary),
            "ai_ab_evaluation":              dict(self.ai_ab_evaluation),
            "creator_benchmark_summary":     dict(self.creator_benchmark_summary),
            "ai_execution_mode":             dict(self.ai_execution_mode),
            "ai_execution_rollback":         dict(self.ai_execution_rollback),
            "creator_archetype_strategy":         dict(self.creator_archetype_strategy),
            "creator_subtitle_style_promotion":   dict(self.creator_subtitle_style_promotion),
            "creator_camera_style_promotion":     dict(self.creator_camera_style_promotion),
            "creator_render_strategy":            dict(self.creator_render_strategy),
            "render_outcome_tracking":            dict(self.render_outcome_tracking),
            "creator_preference_reinforcement":   dict(self.creator_preference_reinforcement),
        }
