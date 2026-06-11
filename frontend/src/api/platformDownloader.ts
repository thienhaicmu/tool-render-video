const BASE = '/api/downloader'

export interface VideoInfo {
  title: string
  platform: string
  duration: number
  thumbnail: string
  formats: { height: number; fps: number; ext: string; filesize: number }[]
}

export interface DownloadJob {
  id: string
  url: string
  platform: string
  status: 'queued' | 'downloading' | 'done' | 'failed'
  progress: number
  speed_str: string
  eta_str: string
  output_path: string
  output_dir: string
  filename: string
  title: string
  duration: number
  height: number
  fps: number
  filesize: number
  error_msg: string
  created_at: string
  updated_at: string
}

async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function getVideoInfo(url: string): Promise<VideoInfo> {
  return _fetch<VideoInfo>(`${BASE}/info?url=${encodeURIComponent(url)}`)
}

export async function startDownload(
  url: string,
  outputDir: string,
  quality = 'best',
): Promise<{ job_id: string; platform: string }> {
  return _fetch(`${BASE}/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, output_dir: outputDir, quality }),
  })
}

export async function startBatch(
  urls: string[],
  outputDir: string,
  quality = 'best',
): Promise<{ jobs: { job_id: string; url: string; platform: string }[] }> {
  return _fetch(`${BASE}/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls, output_dir: outputDir, quality }),
  })
}

export async function listJobs(limit = 100): Promise<DownloadJob[]> {
  return _fetch<DownloadJob[]>(`${BASE}/jobs?limit=${limit}`)
}

export async function getJob(jobId: string): Promise<DownloadJob> {
  return _fetch<DownloadJob>(`${BASE}/jobs/${jobId}`)
}

export async function cancelJob(jobId: string): Promise<void> {
  await _fetch(`${BASE}/jobs/${jobId}`, { method: 'DELETE' })
}

export function subscribeJob(
  jobId: string,
  onUpdate: (job: DownloadJob) => void,
  onDone?: () => void,
): WebSocket {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${protocol}://${location.host}/api/downloader/jobs/${jobId}/ws`)
  ws.onmessage = (e) => {
    try {
      const job: DownloadJob = JSON.parse(e.data)
      onUpdate(job)
      if (job.status === 'done' || job.status === 'failed') {
        ws.close()
        onDone?.()
      }
    } catch {
      // ignore parse errors
    }
  }
  ws.onerror = () => ws.close()
  return ws
}

export function formatFilesize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function platformLabel(platform: string): string {
  const map: Record<string, string> = {
    youtube: 'YT', tiktok: 'TT', instagram: 'IG',
    facebook: 'FB', twitter: 'X', bilibili: 'BL',
    reddit: 'RD', vimeo: 'VI', dailymotion: 'DM', twitch: 'TW',
  }
  return map[platform] || '??'
}

export function platformColor(platform: string): string {
  const map: Record<string, string> = {
    youtube: '#FF0000',
    tiktok: '#010101',
    instagram: '#C13584',
    facebook: '#1877F2',
    twitter: '#000000',
    bilibili: '#00A1D6',
    reddit: '#FF4500',
    vimeo: '#1AB7EA',
    dailymotion: '#0066DC',
    twitch: '#9146FF',
  }
  return map[platform] || '#666'
}

// ── Catalog + Queue ───────────────────────────────────────────────────────────

const CATALOG_BASE = '/api/downloader/catalog'

export interface CatalogAsset {
  asset_id: string
  url: string
  platform: string
  status: 'pending' | 'downloading' | 'ready' | 'processing' | 'archived' | 'deleted' | 'failed'
  storage_tier: string
  storage_path: string
  filename: string
  title: string
  duration: number
  height: number
  fps: number
  filesize: number
  quality: string
  ref_count: number
  created_at: string
  updated_at: string
  expires_at: string
}

export interface QueueItem {
  queue_id: string
  url: string
  platform: string
  quality: string
  priority: number
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  retry_count: number
  max_retries: number
  download_job_id: string
  asset_id: string
  error_msg: string
  created_at: string
  updated_at: string
  started_at: string
  completed_at: string
}

export async function listCatalog(status?: string, limit = 100): Promise<CatalogAsset[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  return _fetch<CatalogAsset[]>(`${CATALOG_BASE}/?${params}`)
}

export async function archiveCatalogAsset(assetId: string): Promise<void> {
  await _fetch(`${CATALOG_BASE}/${assetId}/archive`, { method: 'POST' })
}

export async function deleteCatalogAsset(assetId: string): Promise<void> {
  await _fetch(`${CATALOG_BASE}/${assetId}`, { method: 'DELETE' })
}

export async function listQueue(status?: string, limit = 100): Promise<QueueItem[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  return _fetch<QueueItem[]>(`${CATALOG_BASE}/queue?${params}`)
}

export async function addToQueue(
  url: string,
  opts: { platform?: string; quality?: string; priority?: number; max_retries?: number } = {},
): Promise<{ queue_id: string; platform: string }> {
  return _fetch(`${CATALOG_BASE}/queue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, ...opts }),
  })
}

export async function cancelQueueItem(queueId: string): Promise<void> {
  await _fetch(`${CATALOG_BASE}/queue/${queueId}`, { method: 'DELETE' })
}
