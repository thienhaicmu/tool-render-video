/* parsePrepareSourceResponse — normalize POST /api/render/prepare-source response.
   parsePreviewTranscript     — normalize GET /api/render/preview-transcript/{id} response.
   normalizeSession / normalizeSessionList — normalize session list items.
*/

export function parsePrepareSourceResponse(raw) {
  if (!raw || !raw.session_id) return null;
  return {
    sessionId:       String(raw.session_id),
    previewVideoUrl: `/api/render/preview-video/${encodeURIComponent(raw.session_id)}`,
    duration:        raw.duration   ?? null,
    title:           raw.title      ?? null,
    exportDir:       raw.export_dir ?? null,
    sourceMode:      raw.source_mode ?? null,
    _raw: raw,
  };
}

export function parsePreviewTranscript(raw) {
  if (!raw || !Array.isArray(raw.segments)) return { segments: [] };
  return {
    segments: raw.segments.map(s => ({
      start: Number(s.start ?? 0),
      end:   Number(s.end   ?? 0),
      text:  String(s.text  ?? ''),
    })),
  };
}

export function normalizeSession(raw) {
  if (!raw || typeof raw !== 'object') return null;
  return {
    id:          String(raw.id ?? raw.session_id ?? ''),
    creatorType: raw.creator_type ?? null,
    platform:    raw.platform     ?? null,
    sourceFile:  raw.source_file  ?? null,
    outputDir:   raw.output_dir   ?? null,
    uploadedAt:  raw.uploaded_at  ?? null,
    durationMs:  raw.duration_ms  ?? null,
    fileSize:    raw.file_size    ?? null,
    _raw: raw,
  };
}

export function normalizeSessionList(rawList) {
  if (!Array.isArray(rawList)) return [];
  return rawList.map(normalizeSession).filter(Boolean);
}
