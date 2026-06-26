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
  it('stays on the SOURCE step even when a render is running', async () => {
    const { container } = render(<ClipStudio />)

    // Wait until the running job is known (the ActiveJobBadge surfaces it).
    await screen.findByText(/Rendering ·/)

    // The wizard must still be on the SOURCE step — not auto-jumped to Monitor.
    const activeStep = container.querySelector('.rw-step.active')
    expect(activeStep?.textContent).toContain('SOURCE')
  })
})
