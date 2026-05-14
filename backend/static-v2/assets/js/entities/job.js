/* Single entry-point for raw job JSON → normalized Job object.
   All consumers use this — no component-level JSON.parse for jobs.
*/

const VALID_STATUSES = new Set([
  'queued','running','completed','partial','failed','interrupted','unsupported','unavailable',
]);

export function normalizeJob(raw) {
  if (!raw || typeof raw !== 'object') return null;

  const status = VALID_STATUSES.has(raw.status) ? raw.status : 'unavailable';

  return {
    id:          String(raw.id ?? raw.job_id ?? ''),
    status,
    platform:    raw.platform   ?? raw.target_platform ?? null,
    createdAt:   raw.created_at ?? raw.createdAt ?? null,
    updatedAt:   raw.updated_at ?? raw.updatedAt ?? null,
    finishedAt:  raw.finished_at ?? raw.finishedAt ?? null,
    sourceFile:  raw.source_file ?? raw.sourceFile ?? null,
    outputDir:   raw.output_dir  ?? raw.outputDir  ?? null,
    partsTotal:  raw.parts_total ?? raw.total_parts ?? 0,
    partsOk:     raw.parts_ok    ?? raw.completed_parts ?? 0,
    errorMessage: raw.error_message ?? raw.errorMessage ?? null,
    aiEnabled:   raw.ai_enabled ?? raw.aiEnabled ?? false,
    executionMode: raw.execution_mode ?? raw.executionMode ?? 'balanced',
    _raw: raw,
  };
}
