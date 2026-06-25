/**
 * System resource snapshot — backs the GPU/CPU dots in the Clip Studio
 * status bar (S4.2). Polled every 3 s while the user is on a screen
 * that subscribes via useSystemResources.
 *
 * Backend: backend/app/routes/system.py — GET /api/system/resources.
 * Every metric field is nullable; null means "unable to measure" (lib
 * not installed, no NVIDIA, transient failure). The endpoint never
 * 5xxs, so callers can poll on a fixed cadence without retry logic.
 */
import { apiFetch } from './client'

export interface ResourceSnapshot {
  cpu_percent:      number | null
  ram_percent:      number | null
  ram_used_mb:      number | null
  ram_total_mb:     number | null
  gpu_percent:      number | null
  gpu_mem_used_mb:  number | null
  gpu_mem_total_mb: number | null
  gpu_name:         string | null
  disk_free_mb:     number | null
  disk_total_mb:    number | null
}

export async function getSystemResources(): Promise<ResourceSnapshot> {
  return apiFetch<ResourceSnapshot>('/api/system/resources')
}
