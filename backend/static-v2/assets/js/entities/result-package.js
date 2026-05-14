/* parseResultPackage(jobId, resultRaw) — build ResultPackage from result_json.
   parseOutputClip(entry, jobId)       — build OutputClip from a ranking entry.
   streamUrl is ALWAYS derived from jobId + partNo; never trust output_file for playback.
   Handles: resultRaw as object OR string, missing fields, legacy aliases, partial results.
   Never throws.
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

  // Accept string input (double-parse safety for backends that double-encode)
  let raw = resultRaw;
  if (typeof raw === 'string') {
    try { raw = JSON.parse(raw); } catch {
      return _fallback(jid, 'result_json could not be parsed from string');
    }
  }

  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return _fallback(jid, 'result_json missing or not an object');
  }

  try {
    // Output ranking — primary source
    let rankingRaw = Array.isArray(raw.output_ranking) ? [...raw.output_ranking] : [];

    // Fallback: build synthetic ranking from legacy `outputs` array when ranking absent
    if (rankingRaw.length === 0 && Array.isArray(raw.outputs) && raw.outputs.length > 0) {
      raw.outputs.forEach((o, i) => {
        if (o && typeof o === 'object') {
          rankingRaw.push({
            part_no:        o.part_no ?? (i + 1),
            output_file:    o.output_file ?? '',
            output_rank:    i + 1,
            output_score:   o.viral_score ?? o.output_score ?? 0,
            is_best_clip:   i === 0,
            ranking_reason: o.ranking_reason ?? '',
            _synthetic:     true,
          });
        }
      });
    }

    const ranking = rankingRaw
      .map(e => parseOutputClip(e, jid))
      .filter(Boolean)
      .sort((a, b) => (a.rank || 999) - (b.rank || 999));

    // Backfill rank from position when missing
    ranking.forEach((c, i) => { if (!c.rank) c.rank = i + 1; });

    // Best clip — explicit field → first isBest in ranking → rank 1
    let bestClip = null;
    if (raw.best_clip && typeof raw.best_clip === 'object') {
      bestClip = parseOutputClip(raw.best_clip, jid);
    }
    if (!bestClip && ranking.length > 0) {
      bestClip = ranking.find(c => c.isBest) ?? ranking[0];
    }

    // Failed parts — normalize numbers and preserve detail objects
    const failedPartNumbers = Array.isArray(raw.failed_parts)
      ? raw.failed_parts.map(Number).filter(n => !isNaN(n)) : [];

    const failedPartDetails = Array.isArray(raw.failed_parts_detail)
      ? raw.failed_parts_detail.filter(d => d && typeof d === 'object') : [];

    // Counts — prefer explicit fields, fall back to derived values
    const selectedCount   = Number(raw.selected_segments_count ?? raw.selected_parts_count ?? ranking.length);
    const successfulCount = Number(raw.successful_outputs_count ?? ranking.length);
    const failedCount     = Number(raw.failed_outputs_count ?? failedPartNumbers.length);

    // Quality data from ai_render_quality_evaluation
    const qualityRaw = (raw.ai_render_quality_evaluation && typeof raw.ai_render_quality_evaluation === 'object')
      ? raw.ai_render_quality_evaluation : {};
    const renderQuality = (qualityRaw.score != null || qualityRaw.grade != null) ? {
      score: qualityRaw.score ?? qualityRaw.overall_score ?? null,
      grade: qualityRaw.grade ?? qualityRaw.letter_grade ?? null,
      summary: qualityRaw.summary ?? null,
    } : null;

    return {
      jobId:          jid,
      rawAvailable:   true,
      parseError:     null,
      outputs:        ranking,
      ranking,
      bestClip,
      bestExports:    Array.isArray(raw.best_exports) ? raw.best_exports : [],
      failedPartNumbers,
      failedPartDetails,
      selectedCount,
      successfulCount,
      failedCount,
      isPartialSuccess:         !!(raw.is_partial_success),
      rankingWarning:           raw.output_ranking_warning ?? null,
      voiceSummary:             raw.voice_summary ?? 'not used',
      subtitleTranslateSummary: raw.subtitle_translate_summary ?? 'not used',
      renderQuality,
      ai:  parseAIInsightSummary(raw),
      raw,
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
    renderQuality: null,
    ai: parseAIInsightSummary(null), raw: {},
  };
}
