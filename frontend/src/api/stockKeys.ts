/**
 * Stock API keys — Pexels / Pixabay for the FREE stock-image visual provider
 * (Content Studio). Backend: backend/app/routes/settings.py
 *   GET /api/settings/stock-keys → StockKeysStatus (set/not-set booleans)
 *   PUT /api/settings/stock-keys (body={pexels?, pixabay?}) → StockKeysStatus
 *
 * SECURITY: the raw keys are never returned — the API answers only with
 * "set / not set" booleans. A blank field on PUT leaves the saved key as-is.
 * Saving applies to the live backend immediately (no restart).
 */
import { apiFetch } from './client'

/** Matches backend StockKeysStatus (routes/settings.py) — booleans only. */
export interface StockKeysStatus {
  pexels_set: boolean
  pixabay_set: boolean
}

export async function getStockKeys(): Promise<StockKeysStatus> {
  return apiFetch<StockKeysStatus>('/api/settings/stock-keys')
}

export async function putStockKeys(
  body: { pexels?: string; pixabay?: string },
): Promise<StockKeysStatus> {
  return apiFetch<StockKeysStatus>('/api/settings/stock-keys', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
