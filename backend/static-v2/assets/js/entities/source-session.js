/* Single entry-point for raw session JSON → normalized SourceSession. */

export function normalizeSession(raw) {
  if (!raw || typeof raw !== 'object') return null;

  return {
    id:           String(raw.id ?? raw.session_id ?? ''),
    creatorType:  raw.creator_type  ?? raw.creatorType  ?? null,
    platform:     raw.platform      ?? null,
    sourceFile:   raw.source_file   ?? raw.sourceFile   ?? null,
    outputDir:    raw.output_dir    ?? raw.outputDir    ?? null,
    uploadedAt:   raw.uploaded_at   ?? raw.uploadedAt   ?? null,
    durationMs:   raw.duration_ms   ?? raw.durationMs   ?? null,
    fileSize:     raw.file_size     ?? raw.fileSize     ?? null,
    videoMeta:    raw.video_meta    ?? raw.videoMeta    ?? null,
    _raw: raw,
  };
}

export function normalizeSessionList(rawList) {
  if (!Array.isArray(rawList)) return [];
  return rawList.map(normalizeSession).filter(Boolean);
}
