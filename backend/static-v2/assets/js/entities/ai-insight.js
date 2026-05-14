/* parseAIInsightSummary — extract AI insight metadata from result_json object.
   Handles: ai_director, ai_render_influence, ai_ux, ai_render_quality_evaluation,
            ai_execution_metrics, render_quality_v2.
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

  const directorEnabled      = !!(director.enabled ?? director.ai_director_enabled ?? false);
  const influenceEnabled     = !!(influence.enabled ?? influence.available ?? false);
  const advisoryAvailable    = directorEnabled && !!(
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
  const qualityV2 = _obj(director.render_quality_v2 ?? resultRaw.render_quality_v2);
  const qualityScore = quality.score ?? quality.overall_score ?? qualityV2.score ?? qualityV2.overall_score ?? null;
  const qualityGrade = quality.grade ?? quality.letter_grade ?? qualityV2.grade ?? qualityV2.letter_grade ?? null;
  const executionMode = execMetrics.mode ?? execMetrics.execution_mode ?? influence.mode ?? null;

  // Compact preview chips — only shown when AI is available
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
    confidence:      director.confidence ?? null,
    summaryLines,
    qualityGate:     director.quality_gated_influence ?? null,
    executionMetrics: execMetrics,
    renderQuality:   (qualityScore !== null) ? { score: qualityScore, grade: qualityGrade } : null,
    executionMode,
    previewChips,
    raw: { director, influence, ux, quality, beat },
  };
}

function _empty() {
  return {
    available: false, directorEnabled: false, advisoryAvailable: false,
    executionInfluenceEnabled: false, appliedChanges: [], skippedChanges: [],
    warnings: [], summaryLines: [], previewChips: [],
    executionMetrics: {}, renderQuality: null, executionMode: null,
    raw: {},
  };
}

function _obj(v) { return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }
