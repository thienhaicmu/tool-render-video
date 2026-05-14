/* normalizePart — raw job_parts row → normalized JobPart.
   Backend fields: job_id, part_no, part_name, status, progress_percent,
                   start_sec, end_sec, duration, viral_score, motion_score,
                   hook_score, output_file, message
   Part statuses: waiting, cutting, transcribing, rendering, downloading,
                  done, failed, unsupported
*/

const ACTIVE_STATUSES = new Set(['waiting','cutting','transcribing','rendering','downloading']);

/* Map raw part status to StatusChip state */
export function mapPartChipStatus(raw) {
  if (!raw) return 'unavailable';
  if (raw === 'done')         return 'completed';
  if (raw === 'failed')       return 'failed';
  if (raw === 'unsupported')  return 'unsupported';
  if (ACTIVE_STATUSES.has(raw)) return 'running';
  if (raw === 'queued')       return 'queued';
  return 'unavailable';
}

export function normalizePart(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const jobId  = String(raw.job_id ?? '');
  const partNo = Number(raw.part_no ?? raw.index ?? 0);
  return {
    jobId,
    partNo,
    partName:        raw.part_name ?? raw.title ?? `Part ${partNo}`,
    status:          raw.status ?? null,
    chipStatus:      mapPartChipStatus(raw.status),
    progressPercent: Number(raw.progress_percent ?? 0),
    startSec:        raw.start_sec  ?? null,
    endSec:          raw.end_sec    ?? null,
    duration:        raw.duration   ?? null,
    viralScore:      Number(raw.viral_score  ?? 0),
    motionScore:     Number(raw.motion_score ?? 0),
    hookScore:       Number(raw.hook_score   ?? 0),
    message:         raw.message    ?? null,
    streamUrl:       jobId && partNo > 0
      ? `/api/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/stream`
      : null,
    _raw: raw,
  };
}

export function normalizePartList(rawList) {
  const list = Array.isArray(rawList) ? rawList : (rawList?.items ?? []);
  return list.map(normalizePart).filter(Boolean);
}
