/* parseAIInsightSummary — extract AI insight metadata from result_json object.
   Handles: ai_director, ai_render_influence, ai_ux, ai_render_quality_evaluation,
            ai_execution_metrics, render_quality_v2, Phase 59-62 intelligence fields.
   parseAIInsightSummary().intelligence → enriched for UI-R4B intelligence panel.
   All fields optional/defensive. Never throws.
*/

export function parseAIInsightSummary(resultRaw) {
  if (!resultRaw || typeof resultRaw !== 'object') {
    return _empty();
  }

  const director  = _obj(resultRaw.ai_director);
  const influence = _obj(resultRaw.ai_render_influence);
  const ux        = _obj(resultRaw.ai_ux);
  const quality   = _obj(resultRaw.ai_render_quality_evaluation);
  const beat      = _obj(resultRaw.ai_beat_execution);

  const directorEnabled   = !!(director.enabled ?? director.ai_director_enabled ?? false);
  const influenceEnabled  = !!(influence.enabled ?? influence.available ?? false);
  const advisoryAvailable = directorEnabled && !!(
    director.selected_segments || director.subtitle || director.camera || director.ai_summary
  );

  // Summary lines — from UX metadata or director ai_summary
  const summaryLines = [];
  if (Array.isArray(ux.summary_lines)) summaryLines.push(...ux.summary_lines.map(String));
  if (director.ai_summary) summaryLines.push(String(director.ai_summary));
  if (!summaryLines.length && directorEnabled) summaryLines.push('AI analysis completed.');

  // Warnings — quality gate blocks + quality evaluation warnings
  const warnings = [];
  if (Array.isArray(quality.warnings)) warnings.push(...quality.warnings.map(String));
  const blocked = director.quality_gated_influence?.blocked_count;
  if (blocked > 0) warnings.push(`${blocked} AI change${blocked > 1 ? 's' : ''} blocked by quality gate.`);

  // Applied/skipped changes from influence calibration
  const appliedChanges = [];
  const skippedChanges = [];
  const cal = influence.calibration ?? {};
  for (const [domain, c] of Object.entries(cal)) {
    const entry = { domain, ...(typeof c === 'object' ? c : {}) };
    if (c?.action === 'applied' || c?.action === 'increase') appliedChanges.push(entry);
    else skippedChanges.push(entry);
  }

  // Execution metrics from director or top-level
  const execMetrics = _obj(director.ai_execution_metrics ?? resultRaw.ai_execution_metrics);

  // render_quality_v2 — newer quality evaluation field
  const qualityV2    = _obj(director.render_quality_v2 ?? resultRaw.render_quality_v2);
  const qualityScore = quality.score ?? quality.overall_score ?? qualityV2.score ?? qualityV2.overall_score ?? null;
  const qualityGrade = quality.grade ?? quality.letter_grade ?? qualityV2.grade ?? qualityV2.letter_grade ?? null;
  const executionMode = execMetrics.mode ?? execMetrics.execution_mode ?? influence.mode ?? null;

  // Compact preview chips
  const previewChips = [];
  if (appliedChanges.length > 0) {
    previewChips.push({ type: 'applied', label: `${appliedChanges.length} applied` });
  }
  if (qualityScore !== null) {
    const pct = Math.round(Math.min(100, Math.max(0, Number(qualityScore))));
    previewChips.push({ type: 'quality', label: `Quality ${qualityGrade ?? pct}` });
  }
  if (executionMode && executionMode !== 'off') {
    previewChips.push({ type: 'mode', label: executionMode });
  }
  if (beat.enabled) {
    previewChips.push({ type: 'beat', label: 'Beat sync' });
  }

  return {
    available:                 directorEnabled || influenceEnabled,
    directorEnabled,
    advisoryAvailable,
    executionInfluenceEnabled: influenceEnabled,
    appliedChanges,
    skippedChanges,
    warnings,
    confidence:       director.confidence ?? null,
    summaryLines,
    qualityGate:      director.quality_gated_influence ?? null,
    executionMetrics: execMetrics,
    renderQuality:    (qualityScore !== null) ? { score: qualityScore, grade: qualityGrade } : null,
    executionMode,
    previewChips,
    intelligence:     _parseIntelligence(resultRaw, director),
    raw: { director, influence, ux, quality, beat },
  };
}

/* ── Intelligence panel — Phase 59-62 metadata extraction ────────────── */

function _parseIntelligence(raw, director) {
  try {
    return _parseIntelligenceCore(raw, director);
  } catch (_) {
    return _emptyIntelligence();
  }
}

function _parseIntelligenceCore(raw, director) {
  const em   = _obj(director.ai_execution_metrics    ?? raw.ai_execution_metrics);
  const es   = _obj(director.ai_execution_summary    ?? raw.ai_execution_summary);
  const mode = _obj(director.ai_execution_mode       ?? raw.ai_execution_mode);
  const crs  = _obj(director.creator_render_strategy ?? raw.creator_render_strategy);
  const prs  = _obj(director.platform_render_strategy ?? raw.platform_render_strategy);
  const arch = _obj(director.creator_archetype_strategy ?? raw.creator_archetype_strategy);
  const bm   = _obj(director.creator_benchmark_summary ?? raw.creator_benchmark_summary);
  const rf   = _obj(director.creator_preference_reinforcement ?? raw.creator_preference_reinforcement);
  const pqf  = _obj(director.platform_quality_feedback ?? raw.platform_quality_feedback);
  const ot   = _obj(director.render_outcome_tracking ?? raw.render_outcome_tracking);
  const lic  = _obj(director.learning_influence_calibration ?? raw.learning_influence_calibration);
  const qv2  = _obj(director.render_quality_v2 ?? raw.render_quality_v2);

  /* ── Applied items ──────────────────────────────────────────────── */
  const appliedItems = [];
  const subM = _obj(em.subtitle);
  const camM = _obj(em.camera);
  const segM = _obj(em.segment);

  if (subM.applied === true) {
    appliedItems.push({ domain: 'subtitle', label: 'Subtitle style',  detail: _presetLabel(subM.preset_applied) });
  }
  if (camM.applied === true) {
    appliedItems.push({ domain: 'camera',   label: 'Camera framing',  detail: _reframeLabel(camM.reframe_mode_applied) });
  }
  if (segM.applied === true) {
    const sc = segM.selected_count, tc = segM.total_count;
    appliedItems.push({ domain: 'segment',  label: 'Clip selection',  detail: (sc != null && tc != null) ? `${sc} of ${tc} segments` : 'AI selection applied' });
  }
  // Fallback from render_outcome_tracking
  if (appliedItems.length === 0 && ot.available) {
    const ae = _obj(ot.ai_execution);
    if (ae.subtitle_applied) appliedItems.push({ domain: 'subtitle', label: 'Subtitle style',  detail: null });
    if (ae.camera_applied)   appliedItems.push({ domain: 'camera',   label: 'Camera framing',  detail: null });
    if (ae.segment_applied)  appliedItems.push({ domain: 'segment',  label: 'Clip selection',  detail: null });
  }

  /* ── Strategy — best source: crs > prs > arch ───────────────────── */
  const bestStrategy = (crs.available === true) ? crs
    : (prs.available === true) ? prs
    : (arch.available === true) ? arch
    : null;

  const creatorTypeRaw = ot.creator_type ?? bestStrategy?.creator_type ?? null;
  const platformRaw    = ot.platform     ?? prs.platform ?? pqf.platform ?? null;
  const stratConf      = bestStrategy?.confidence ?? null;
  const strategyNotes  = Array.isArray(bestStrategy?.reasoning)
    ? bestStrategy.reasoning.slice(0, 2).map(String) : [];

  /* ── Quality scores ─────────────────────────────────────────────── */
  let qualityScores = null;
  if (ot.available && ot.quality && typeof ot.quality === 'object') {
    const q = ot.quality;
    if (q.overall != null) {
      qualityScores = {
        overall:  Math.round(Number(q.overall)),
        subtitle: q.subtitle != null ? Math.round(Number(q.subtitle)) : null,
        camera:   q.camera   != null ? Math.round(Number(q.camera))   : null,
        hook:     q.hook     != null ? Math.round(Number(q.hook))     : null,
      };
    }
  }
  if (!qualityScores) {
    const overall = qv2.score ?? qv2.overall_score ?? null;
    if (overall != null) {
      qualityScores = {
        overall:  Math.round(Number(overall)),
        subtitle: qv2.subtitle_score != null ? Math.round(Number(qv2.subtitle_score)) : null,
        camera:   qv2.camera_score   != null ? Math.round(Number(qv2.camera_score))   : null,
        hook:     qv2.hook_score     != null ? Math.round(Number(qv2.hook_score))     : null,
      };
    }
  }

  /* ── Creator fit ────────────────────────────────────────────────── */
  let creatorFit = null;
  if (ot.available && ot.benchmark_result) {
    creatorFit = _obj(ot.benchmark_result).creator_fit ?? null;
  }
  if (!creatorFit && bm.available) {
    const bsMap = { best_fit: 'high', improving: 'medium', needs_review: 'low' };
    creatorFit = bsMap[bm.benchmark_status] ?? null;
  }

  /* ── Learning items ─────────────────────────────────────────────── */
  const learningItems = [];
  if (rf.available && Array.isArray(rf.reasoning)) {
    learningItems.push(...rf.reasoning.slice(0, 3).map(String));
  }
  if (learningItems.length === 0 && lic.available && Array.isArray(lic.reasoning)) {
    learningItems.push(...lic.reasoning.slice(0, 2).map(String));
  }
  if (learningItems.length === 0 && ot.available && Array.isArray(ot.reasoning)) {
    for (const r of ot.reasoning) {
      const s = String(r);
      if (/improv|reinforc|fit|applied/i.test(s)) {
        learningItems.push(s);
        if (learningItems.length >= 2) break;
      }
    }
  }

  /* ── Suggestions ────────────────────────────────────────────────── */
  const suggestions = [];
  if (pqf.available && Array.isArray(pqf.improvement_opportunities)) {
    suggestions.push(...pqf.improvement_opportunities.slice(0, 3).map(String));
  }

  /* ── Execution mode + assistance ────────────────────────────────── */
  const modeStr          = em.mode ?? mode.mode ?? ot.execution_mode ?? null;
  const modeLabel        = _modeLabel(modeStr);
  const assistanceDomains = appliedItems.length;
  const assistanceLabel  = _assistanceLabel(es.overall_ai_assistance ?? null, assistanceDomains);
  const confVal          = stratConf ?? ot.confidence ?? null;
  const confidenceLabel  = _confLabel(confVal);
  const platformFit      = (pqf.available === true) ? (pqf.platform_fit != null ? Math.round(Number(pqf.platform_fit)) : null) : null;

  const hasData = !!(
    appliedItems.length > 0 || creatorTypeRaw || qualityScores ||
    learningItems.length > 0 || suggestions.length > 0
  );

  return {
    appliedItems,
    creatorType:      _formatType(creatorTypeRaw),
    platform:         _formatPlatform(platformRaw),
    platformFit,
    confidence:       confVal,
    confidenceLabel,
    strategyNotes,
    qualityScores,
    creatorFit:       _formatFit(creatorFit),
    learningItems,
    suggestions,
    modeLabel,
    assistanceLabel,
    assistanceDomains,
    aiEffectiveness:  ot.ai_effectiveness  ?? null,
    overallResult:    ot.overall_result    ?? null,
    hasData,
  };
}

/* ── Intelligence helper functions ───────────────────────────────────── */

function _presetLabel(p) {
  return { viral_bold: 'Bold style applied', clean_pro: 'Clean professional style', boxed_caption: 'Boxed caption style' }[p] ?? null;
}

function _reframeLabel(m) {
  return { subject: 'Subject tracking', motion: 'Motion tracking', face: 'Face tracking' }[m] ?? null;
}

function _modeLabel(m) {
  return { off: 'Off', safe: 'Safe', balanced: 'Balanced', aggressive: 'Aggressive' }[m] ?? null;
}

function _assistanceLabel(level, domains) {
  const m = { high: 'Full AI assistance', medium: 'Partial AI assistance', low: 'Light AI assistance', none: 'No AI changes' };
  if (m[level]) return m[level];
  if (domains > 0) return `${domains} AI improvement${domains !== 1 ? 's' : ''} applied`;
  return null;
}

function _confLabel(v) {
  if (v == null) return null;
  const f = Number(v);
  return f >= 0.75 ? 'High' : f >= 0.50 ? 'Medium' : 'Low';
}

function _formatType(t) {
  if (!t || t === 'unknown') return null;
  const m = {
    podcast: 'Podcast', talking_head: 'Talking Head', educational: 'Educational',
    viral_short_form: 'Viral', storytelling: 'Storytelling', interview: 'Interview',
    motivation: 'Motivation', motivational: 'Motivation',
  };
  return m[t] ?? String(t).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function _formatPlatform(p) {
  if (!p) return null;
  const m = {
    tiktok: 'TikTok', youtube: 'YouTube', instagram: 'Instagram',
    shorts: 'YouTube Shorts', youtube_shorts: 'YouTube Shorts',
    reels: 'Reels', instagram_reels: 'Reels', facebook: 'Facebook',
  };
  return m[String(p).toLowerCase()] ?? String(p);
}

function _formatFit(f) {
  if (!f) return null;
  return { high: 'High', medium: 'Medium', low: 'Low' }[String(f).toLowerCase()] ?? null;
}

function _emptyIntelligence() {
  return {
    appliedItems: [], creatorType: null, platform: null, platformFit: null,
    confidence: null, confidenceLabel: null, strategyNotes: [],
    qualityScores: null, creatorFit: null, learningItems: [], suggestions: [],
    modeLabel: null, assistanceLabel: null, assistanceDomains: 0,
    aiEffectiveness: null, overallResult: null, hasData: false,
  };
}

/* ── Shared utilities ─────────────────────────────────────────────────── */

function _empty() {
  return {
    available: false, directorEnabled: false, advisoryAvailable: false,
    executionInfluenceEnabled: false, appliedChanges: [], skippedChanges: [],
    warnings: [], summaryLines: [], previewChips: [],
    executionMetrics: {}, renderQuality: null, executionMode: null,
    intelligence: _emptyIntelligence(),
    raw: {},
  };
}

function _obj(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }
