/**
 * File upload API.
 *
 * IMPORTANT: Only /api/upload-file (hyphen form) is used — for BGM/audio assets.
 * The old /api/upload/* (slash domain) endpoints have been removed and will 404.
 */
import { apiFetchFormData } from './client'
import type { UploadFileResponse } from '../types/api'

/**
 * Upload a BGM/audio asset file for the editor.
 * POST /api/upload-file  (field name: "file")
 * Returns: { path: string }
 */
export async function uploadFile(file: File): Promise<UploadFileResponse> {
  const form = new FormData()
  form.append('file', file)
  return apiFetchFormData<UploadFileResponse>('/api/upload-file', form)
}

// ── REMOVED ENDPOINTS — DO NOT USE ───────────────────────────────────────────
// POST /api/upload/accounts/ensure  → 404 (removed Phase 4F.5A)
// POST /api/upload/login/check      → 404 (removed Phase 4F.5A)
// POST /api/upload/login/start      → 404 (removed Phase 4F.5A)
// POST /api/upload/queue/add        → 404 (removed Phase 4F.5A)
// GET  /api/upload/queue            → 404 (removed Phase 4F.5A)
// POST /api/upload/queue/{id}/run   → 404 (removed Phase 4F.5A)
// POST /api/upload/queue/{id}/cancel→ 404 (removed Phase 4F.5A)
