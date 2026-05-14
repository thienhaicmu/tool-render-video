/* normalizeJob — raw job row → normalized Job.
   Backend fields: job_id, kind, status, stage, progress_percent,
                   message, payload_json (string), result_json (string),
                   created_at, updated_at
*/

import { TERMINAL_STATUSES } from '../transport.js';

const VALID_STATUSES = new Set([
  'queued','running','completed','completed_with_errors',
  'partial','failed','interrupted','unsupported','unavailable',
]);

function safeParse(str) {
  if (!str) return null;
  if (typeof str === 'object') return str;
  try { return JSON.parse(str); } catch { return null; }
}

export function normalizeJob(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const status = VALID_STATUSES.has(raw.status) ? raw.status : 'unavailable';
  return {
    jobId:          String(raw.job_id ?? raw.id ?? ''),
    kind:           raw.kind ?? 'render',
    status,
    stage:          raw.stage ?? null,
    progressPercent: Number(raw.progress_percent ?? 0),
    message:        raw.message ?? null,
    payload:        safeParse(raw.payload_json),
    resultRaw:      safeParse(raw.result_json),
    createdAt:      raw.created_at ?? null,
    updatedAt:      raw.updated_at ?? null,
    isTerminal:     TERMINAL_STATUSES.has(status),
    _raw: raw,
  };
}
