/* parseAIInsightSummary — extract AI insight metadata from result_json object.
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

  const directorEnabled      = !!(director.enabled ?? director.ai_director_enabled ?? false);
  const influenceEnabled     = !!(influence.enabled ?? influence.available ?? false);
  const advisoryAvailable    = directorEnabled && !!(
    director.selected_segments || director.subtitle || director.camera || director.ai_summary
  );

  const summaryLines = [];
  if (Array.isArray(ux.summary_lines)) summaryLines.push(...ux.summary_lines.map(String));
  if (director.ai_summary) summaryLines.push(String(director.ai_summary));
  if (!summaryLines.length && directorEnabled) summaryLines.push('AI analysis completed.');

  const warnings = [];
  if (Array.isArray(quality.warnings)) warnings.push(...quality.warnings.map(String));
  const blocked = director.quality_gated_influence?.blocked_count;
  if (blocked > 0) warnings.push(`${blocked} AI change${blocked > 1 ? 's' : ''} blocked by quality gate.`);

  const appliedChanges = [];
  const skippedChanges = [];
  const cal = influence.calibration ?? {};
  for (const [domain, c] of Object.entries(cal)) {
    const entry = { domain, ...(typeof c === 'object' ? c : {}) };
    if (c?.action === 'applied' || c?.action === 'increase') appliedChanges.push(entry);
    else skippedChanges.push(entry);
  }

  return {
    available:                 directorEnabled || influenceEnabled,
    directorEnabled,
    advisoryAvailable,
    executionInfluenceEnabled: influenceEnabled,
    appliedChanges,
    skippedChanges,
    warnings,
    confidence:  director.confidence ?? null,
    summaryLines,
    qualityGate: director.quality_gated_influence ?? null,
    raw:         { director, influence, ux, quality },
  };
}

function _empty() {
  return {
    available: false, directorEnabled: false, advisoryAvailable: false,
    executionInfluenceEnabled: false, appliedChanges: [], skippedChanges: [],
    warnings: [], summaryLines: [], raw: {},
  };
}

function _obj(v) { return (v && typeof v === 'object') ? v : {}; }
