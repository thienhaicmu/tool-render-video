/* Single entry-point for raw result package JSON → normalized ResultPackage. */

export function parseResultPackage(raw) {
  if (!raw || typeof raw !== 'object') return null;

  const parts = Array.isArray(raw.parts)
    ? raw.parts.map(p => ({
        id:         String(p.id ?? p.part_id ?? ''),
        index:      Number(p.index ?? 0),
        status:     p.status ?? 'unavailable',
        outputFile: p.output_file ?? p.outputFile ?? null,
        title:      p.title ?? `Part ${p.index ?? ''}`,
        aiState:    p.ai_state ?? p.aiState ?? 'unavailable',
        durationMs: p.duration_ms ?? p.durationMs ?? null,
      }))
    : [];

  const summary = raw.summary ?? raw.render_summary ?? {};

  return {
    jobId:        String(raw.job_id ?? raw.jobId ?? raw.id ?? ''),
    status:       raw.status ?? 'unavailable',
    platform:     raw.platform ?? null,
    partsTotal:   parts.length,
    partsOk:      parts.filter(p => p.status === 'completed').length,
    partsFailed:  parts.filter(p => p.status === 'failed').length,
    partsPartial: parts.filter(p => p.status === 'partial').length,
    parts,
    summary: {
      totalDurationMs: summary.total_duration_ms ?? summary.totalDurationMs ?? null,
      avgQualityScore: summary.avg_quality_score ?? summary.avgQualityScore ?? null,
      aiAppliedCount:  summary.ai_applied_count  ?? summary.aiAppliedCount  ?? 0,
      benchmarkStatus: summary.benchmark_status  ?? summary.benchmarkStatus ?? null,
    },
    finishedAt: raw.finished_at ?? raw.finishedAt ?? null,
    _raw: raw,
  };
}
