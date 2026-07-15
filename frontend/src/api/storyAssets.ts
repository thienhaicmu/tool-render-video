/**
 * Story asset library API — /api/story/assets (AL2). Powers the Review asset picker
 * (AL4): pick a library character/background instead of calling AI image gen.
 */
import { apiFetch, BASE_URL } from './client'

export interface StoryAsset {
  id: string
  kind: string        // character | background | object | frame
  region: string
  genre: string
  slug: string
  name: string
  tags: string
  style: string
  path: string
  transparent: boolean
  license: string
  source?: 'v3' | 'legacy' | string
  created_at: string
  updated_at: string
  identity_id?: string
  preview_url?: string
}

export interface AssetFilter {
  kind?: string
  region?: string
  genre?: string
  q?: string
}

export const listStoryAssets = (f: AssetFilter = {}) => {
  const qs = new URLSearchParams()
  if (f.kind) qs.set('kind', f.kind)
  if (f.region) qs.set('region', f.region)
  if (f.genre) qs.set('genre', f.genre)
  if (f.q) qs.set('q', f.q)
  const s = qs.toString()
  return apiFetch<{ assets: StoryAsset[] }>(`/api/story/assets${s ? `?${s}` : ''}`)
}

/** Approved Visual Library V3 identities used by Story Mode. */
export const listV3Assets = (f: AssetFilter = {}) => {
  const qs = new URLSearchParams()
  if (f.kind) qs.set('kind', f.kind)
  if (f.region) qs.set('region', f.region)
  if (f.genre) qs.set('genre', f.genre)
  if (f.q) qs.set('q', f.q)
  const s = qs.toString()
  return apiFetch<{ assets: StoryAsset[] }>(`/api/story/v3/assets${s ? `?${s}` : ''}`)
}

export const scanStoryAssets = () =>
  apiFetch<{ indexed: number; pruned: number; root: string }>('/api/story/assets/scan', { method: 'POST' })

/** Absolute URL to stream an asset's image (for <img src>). */
export const storyAssetImageUrl = (id: string) =>
  `${BASE_URL}/api/story/assets/${encodeURIComponent(id)}/image`

export const v3AssetImageUrl = (asset: StoryAsset) =>
  `${BASE_URL}${asset.preview_url || `/api/story/v3/assets/${asset.kind}/${encodeURIComponent(asset.identity_id || asset.id)}`}`
