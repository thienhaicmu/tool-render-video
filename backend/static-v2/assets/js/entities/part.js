/* Single entry-point for raw part JSON → normalized Part object. */

const VALID_STATUSES = new Set([
  'queued','running','completed','partial','failed','interrupted','unsupported','unavailable',
]);

const VALID_AI_STATES = new Set([
  'disabled','advisory','applied','skipped','blocked','unavailable',
]);

export function normalizePart(raw) {
  if (!raw || typeof raw !== 'object') return null;

  const status  = VALID_STATUSES.has(raw.status)  ? raw.status  : 'unavailable';
  const aiState = VALID_AI_STATES.has(raw.ai_state ?? raw.aiState)
    ? (raw.ai_state ?? raw.aiState)
    : 'unavailable';

  return {
    id:          String(raw.id ?? raw.part_id ?? ''),
    jobId:       String(raw.job_id ?? raw.jobId ?? ''),
    index:       Number(raw.index ?? raw.part_index ?? 0),
    status,
    aiState,
    title:       raw.title ?? raw.segment_title ?? `Part ${raw.index ?? ''}`,
    startTime:   raw.start_time  ?? raw.startTime  ?? null,
    endTime:     raw.end_time    ?? raw.endTime    ?? null,
    outputFile:  raw.output_file ?? raw.outputFile ?? null,
    errorMessage: raw.error_message ?? raw.errorMessage ?? null,
    aiMetadata:  raw.ai_metadata ?? raw.aiMetadata ?? null,
    _raw: raw,
  };
}

export function normalizePartList(rawList) {
  if (!Array.isArray(rawList)) return [];
  return rawList.map(normalizePart).filter(Boolean);
}
