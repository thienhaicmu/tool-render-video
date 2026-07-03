/**
 * render-compose-monitor.test.tsx — Pha 4 coverage.
 *
 * The old broad auto-reattach forced the render wizard to Step 3 (Monitor)
 * whenever ANY background job was running, hijacking the user out of Compose.
 * Pha 4 removes that: the wizard stays on Compose; Monitor opens only on an
 * explicit signal (uiStore.monitorJobId).
 *
 * This pins the regression: with a RUNNING render job known to the UI, the
 * wizard must remain on the SOURCE step (not jump to RENDERING).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

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
  return {
    ...actual,
    getJobHistory: vi.fn().mockResolvedValue({
      items: [{
        job_id: 'run-1', kind: 'render', status: 'running', progress_percent: 0,
        title: 'Active render', source_hint: '', stage: 'rendering', message: '',
        created_at: '2026-06-26T00:00:00Z', updated_at: '2026-06-26T00:00:00Z',
      }],
      has_more: false,
    }),
    getQueueStatus: vi.fn().mockResolvedValue({
      max_concurrent: 1, active: 1, pending: 0, available_slots: 0, order: [], held: [],
    }),
  }
})
vi.mock('../src/api/system', () => ({ getSystemResources: vi.fn().mockResolvedValue({}) }))

import { ClipStudio } from '../src/features/clip-studio/ClipStudio'
import { useUIStore } from '../src/stores/uiStore'
import { useJobsStore } from '../src/stores/jobsStore'

beforeEach(() => {
  const id = useJobsStore.getState()._intervalId
  if (id) clearInterval(id)
  useJobsStore.setState({
    items: [], active: null, activeCount: 0, queueOrder: [], heldIds: [],
    loading: false, error: null, _refcount: 0, _intervalId: null,
  })
  useUIStore.setState({ lang: 'en', monitorJobId: null })
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true, json: () => Promise.resolve({ present: false }),
  }) as unknown as typeof fetch
})

describe('Pha 4 — compose is not hijacked by a running job', () => {
  it('stays on the Create screen even when a render is running (no auto-hijack)', async () => {
    // A running job is seeded via the getJobHistory mock + jobsStore poll.
    // Post-redesign the broad auto-reattach is gone: RenderWorkflow must NOT
    // jump to the Monitor just because a render is active — it stays on the
    // Create hero (drop zone). (ActiveJobBadge moved to the AppShell Topbar,
    // which ClipStudio doesn't render, so we assert on the Create hero
    // instead of the badge.)
    const { container } = render(<ClipStudio />)

    // Create hero (drop zone) is shown — not the monitor.
    await screen.findByText(/AI ready to clip/i)
    expect(container.querySelector('.rnd-screen')).toBeNull()
  })
})
