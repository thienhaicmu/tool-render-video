/* parseResultPackage(jobId, resultRaw) — build ResultPackage from parsed result_json.
   parseOutputClip(entry, jobId)       — build OutputClip from a ranking entry.
   streamUrl is ALWAYS derived from jobId + partNo; never trust output_file for playback.
*/

import { parseAIInsightSummary } from './ai-insight.js';

export function parseOutputClip(entry, jobId) {
  if (!entry || typeof entry !== 'object') return null;
  const jid    = String(jobId ?? entry.job_id ?? '');
  const partNo = Number(entry.part_no ?? entry.part_number ?? 0);
  const score  = Number(entry.output_score ?? entry.output_rank_score ?? 0);
  const rank   = Number(entry.output_rank ?? 0);
  const isBest = !!(entry.is_best_clip || entry.is_best_output || rank === 1);
  return {
    jobId:             jid,
    partNo,
    rank,
    score,
    isBest,
    rankingReason:     entry.ranking_reason    ?? null,
    rankingComponents: entry.ranking_components ?? null,
    selectionReason:   entry.selection_reason  ?? null,
    reasons: Array.isArray(entry.reasons) ? entry.reasons : [],
    streamUrl: jid && partNo > 0
      ? `/api/jobs/${encodeURIComponent(jid)}/parts/${partNo}/stream`
      : null,
    _raw: entry,
  };
}

export function parseResultPackage(jobId, resultRaw) {
  const jid = String(jobId ?? '');

  if (!resultRaw || typeof resultRaw !== 'object') {
    return _fallback(jid, 'result_json missing or null');
  }

  try {
    const rankingRaw = Array.isArray(resultRaw.output_ranking) ? resultRaw.output_ranking : [];
    const ranking = rankingRaw
      .map(e => parseOutputClip(e, jid))
      .filter(Boolean)
      .sort((a, b) => (a.rank || 999) - (b.rank || 999));

    // Backfill rank from position if missing
    ranking.forEach((c, i) => { if (!c.rank) c.rank = i + 1; });

    // Best clip — from explicit field, or first isBest in ranking, or rank 1
    let bestClip = null;
    if (resultRaw.best_clip && typeof resultRaw.best_clip === 'object') {
      bestClip = parseOutputClip(resultRaw.best_clip, jid);
    }
    if (!bestClip && ranking.length > 0) {
      bestClip = ranking.find(c => c.isBest) ?? ranking[0];
    }

    const failedPartNumbers = Array.isArray(resultRaw.failed_parts)
      ? resultRaw.failed_parts.map(Number) : [];

    const failedPartDetails = Array.isArray(resultRaw.failed_parts_detail)
      ? resultRaw.failed_parts_detail : [];

    const selectedCount   = Number(resultRaw.selected_segments_count ?? resultRaw.selected_parts_count ?? ranking.length);
    const successfulCount = Number(resultRaw.successful_outputs_count ?? ranking.length);
    const failedCount     = Number(resultRaw.failed_outputs_count ?? failedPartNumbers.length);

    return {
      jobId:          jid,
      rawAvailable:   true,
      parseError:     null,
      outputs:        ranking,
      ranking,
      bestClip,
      bestExports:    Array.isArray(resultRaw.best_exports) ? resultRaw.best_exports : [],
      failedPartNumbers,
      failedPartDetails,
      selectedCount,
      successfulCount,
      failedCount,
      isPartialSuccess:         !!(resultRaw.is_partial_success),
      rankingWarning:           resultRaw.output_ranking_warning ?? null,
      voiceSummary:             resultRaw.voice_summary ?? 'not used',
      subtitleTranslateSummary: resultRaw.subtitle_translate_summary ?? 'not used',
      ai:  parseAIInsightSummary(resultRaw),
      raw: resultRaw,
    };
  } catch (err) {
    return _fallback(jid, `parse error: ${err.message}`);
  }
}

function _fallback(jobId, parseError) {
  return {
    jobId, rawAvailable: false, parseError,
    outputs: [], ranking: [], bestClip: null, bestExports: [],
    failedPartNumbers: [], failedPartDetails: [],
    selectedCount: 0, successfulCount: 0, failedCount: 0,
    isPartialSuccess: false, rankingWarning: null,
    voiceSummary: 'not used', subtitleTranslateSummary: 'not used',
    ai: parseAIInsightSummary(null), raw: {},
  };
}
