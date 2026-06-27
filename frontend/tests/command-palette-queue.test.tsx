/**
 * command-palette-queue.test.tsx — Pha 5.3.
 *
 * The command palette gains keyboard-driven queue actions. With a running
 * render + a queued render + a paused render present, the palette offers
 * "Open monitor", "Pause next", and "Resume paused", and clicking Pause
 * calls holdJob with the front-of-queue job.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../src/api/jobs', async () => {
  const actual = await vi.importActual<typeof import('../src/api/jobs')>('../src/api/jobs')
  return {
    ...actual,
    holdJob: vi.fn().mockResolvedValue({ job_id: 'job-q-1', held: true }),
    resumeJob: vi.fn().mockResolvedValue({ job_id: 'job-h-1', held: false }),
  }
})

import { CommandPalette } from '../src/components/CommandPalette'
import { useJobsStore } from '../src/stores/jobsStore'
import { useUIStore } from '../src/stores/uiStore'
import * as JobsAPI from '../src/api/jobs'

function histJob(job_id: string, status: string) {
  return {
    job_id, kind: 'render', status, progress_percent: 10, title: 'R ' + job_id,
    source_hint: '', stage: 'rendering', message: '',
    created_at: '2026-06-26T00:00:00Z', updated_at: '2026-06-26T00:00:00Z',
  }
}

beforeEach(() => {
  const id = useJobsStore.getState()._intervalId
  if (id) clearInterval(id)
  useJobsStore.setState({
    items: [histJob('job-run', 'running'), histJob('job-q-1', 'queued'), histJob('job-h-1', 'queued')],
    active: null, activeCount: 0,
    queueOrder: ['job-q-1'], heldIds: ['job-h-1'],
    loading: false, error: null, _refcount: 0, _intervalId: null,
  })
  useUIStore.setState({ lang: 'en' })
  ;(JobsAPI.holdJob as ReturnType<typeof vi.fn>).mockClear()
})

async function openPalette() {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, bubbles: true }))
}

describe('Pha 5.3 — command palette queue actions', () => {
  it('offers queue actions and pauses the front-of-queue render', async () => {
    const user = userEvent.setup()
    render(<CommandPalette />)
    await openPalette()

    expect(await screen.findByText('Open running render monitor')).toBeInTheDocument()
    expect(screen.getByText('Pause next queued render')).toBeInTheDocument()
    expect(screen.getByText('Resume a paused render')).toBeInTheDocument()

    await user.click(screen.getByText('Pause next queued render'))
    expect(JobsAPI.holdJob).toHaveBeenCalledWith('job-q-1')
  })

  it('hides queue actions when there is nothing to act on', async () => {
    useJobsStore.setState({ items: [], queueOrder: [], heldIds: [] })
    render(<CommandPalette />)
    await openPalette()

    // Palette is open (nav actions present) but queue actions are gone.
    expect(await screen.findByText('Open Clip Studio')).toBeInTheDocument()
    expect(screen.queryByText('Pause next queued render')).toBeNull()
    expect(screen.queryByText('Resume a paused render')).toBeNull()
    expect(screen.queryByText('Open running render monitor')).toBeNull()
  })
})
