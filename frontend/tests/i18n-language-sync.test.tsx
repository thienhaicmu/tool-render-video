/**
 * i18n-language-sync.test.tsx — Pha 1.2 coverage.
 *
 * The Clip Studio EN/VI toggle was previously component-local state,
 * disconnected from the global uiStore.lang that the dock / palette /
 * notifications read — so the app could show two languages at once.
 *
 * Pha 1.2 unifies on uiStore.lang. This pins that:
 *   - the toggle writes uiStore.lang ('en' | 'vi')
 *   - a translated surface (the render Step-1 eyebrow, driven by the
 *     mapped 'EN' | 'VI' lang prop) flips in lockstep
 *
 * All data deps are mocked inert (same pattern as the handoff test) so
 * the test is offline + deterministic.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../src/api/platformDownloader', async () => {
  const actual = await vi.importActual<typeof import('../src/api/platformDownloader')>(
    '../src/api/platformDownloader',
  )
  return {
    ...actual,
    listJobs: vi.fn().mockResolvedValue([]),
    getVideoInfo: vi.fn().mockResolvedValue({ title: '', platform: 'youtube', duration: 0, thumbnail: '', formats: [] }),
    startDownload: vi.fn(),
    cancelJob: vi.fn().mockResolvedValue(undefined),
  }
})
vi.mock('../src/api/outputDir', () => ({
  getDefaultOutputDir: vi.fn().mockResolvedValue({ is_configured: false, path: '' }),
  putDefaultOutputDir: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('../src/api/renderDefaults', () => ({
  getRenderDefaults: vi.fn().mockResolvedValue({ is_configured: false, render_defaults: {} }),
}))
vi.mock('../src/api/jobs', async () => {
  const actual = await vi.importActual<typeof import('../src/api/jobs')>('../src/api/jobs')
  return { ...actual, getJobHistory: vi.fn().mockResolvedValue({ items: [], has_more: false }) }
})
vi.mock('../src/api/system', () => ({
  getSystemResources: vi.fn().mockResolvedValue({}),
}))

import { ClipStudio } from '../src/features/clip-studio/ClipStudio'
import { useUIStore } from '../src/stores/uiStore'

beforeEach(() => {
  useUIStore.setState({ lang: 'en', sendToRenderSourcePath: null })
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ present: false }),
  }) as unknown as typeof fetch
})

afterEach(() => {
  // uiStore is a singleton — reset lang so it doesn't leak into other suites.
  useUIStore.setState({ lang: 'en' })
})

describe('Pha 1.2 — language unification', () => {
  it('EN/VI toggle drives uiStore.lang and flips a translated surface', async () => {
    const user = userEvent.setup()
    render(<ClipStudio />)

    // Default English: Step-1 eyebrow reads the EN copy.
    expect(screen.getByText(/AI ready to clip/i)).toBeInTheDocument()
    expect(useUIStore.getState().lang).toBe('en')

    // Toggle to Vietnamese.
    await user.click(screen.getByRole('button', { name: 'VI' }))

    expect(useUIStore.getState().lang).toBe('vi')
    expect(screen.getByText(/AI sẵn sàng/i)).toBeInTheDocument()

    // Toggle back to English.
    await user.click(screen.getByRole('button', { name: 'EN' }))

    expect(useUIStore.getState().lang).toBe('en')
    expect(screen.getByText(/AI ready to clip/i)).toBeInTheDocument()
  })
})
