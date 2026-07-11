/**
 * Story project persistence API — /api/story/projects (SP1).
 *
 * A "project" is a saved Story Studio session (input config + edited StoryPlan v2)
 * so work survives a reload / app restart. Orthogonal to render jobs.
 */
import { apiFetch } from './client'

export interface StoryProjectListItem {
  id: string
  name: string
  language: string
  source: string
  status: string
  created_at: string
  updated_at: string
}

export interface StoryProjectFull extends StoryProjectListItem {
  config: Record<string, unknown>
  plan: unknown | null
}

export interface SaveProjectRequest {
  id?: string
  name?: string
  language?: string
  source?: string
  config?: Record<string, unknown>
  plan?: unknown | null
  status?: string
}

export const saveStoryProject = (req: SaveProjectRequest) =>
  apiFetch<{ id: string }>('/api/story/projects', { method: 'POST', body: JSON.stringify(req) })

export const listStoryProjects = () =>
  apiFetch<{ projects: StoryProjectListItem[] }>('/api/story/projects')

export const getStoryProject = (id: string) =>
  apiFetch<StoryProjectFull>(`/api/story/projects/${encodeURIComponent(id)}`)

export const deleteStoryProject = (id: string) =>
  apiFetch<{ deleted: boolean; id: string }>(`/api/story/projects/${encodeURIComponent(id)}`, { method: 'DELETE' })
