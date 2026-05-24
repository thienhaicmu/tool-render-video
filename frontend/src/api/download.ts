import { apiFetch } from './client'
import type { JobPart } from '../types/api'

export interface DownloadItem {
  part_no: number
  url: string
  source: string
}

export interface DownloadBatchResponse {
  job_id: string
  status: string
  count: number
  output_dir: string
  items: DownloadItem[]
}

export async function createDownloadBatch(
  urls: string[],
  output_dir: string,
): Promise<DownloadBatchResponse> {
  return apiFetch<DownloadBatchResponse>('/api/download/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls, output_dir }),
  })
}

export async function retryDownloadItems(
  jobId: string,
  partNumbers?: number[],
): Promise<{ job_id: string; status: string; retried: number[] }> {
  return apiFetch(`/api/download/retry/${jobId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_numbers: partNumbers }),
  })
}

export type { JobPart }
