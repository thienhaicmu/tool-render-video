/**
 * queue-drawer.test.tsx — Pha 3.3a coverage.
 *
 * The Queue drawer lists all active jobs with the full reorder control set.
 * Verifies it renders positions and that the up/down controls call moveJob
 * with the right delta. Controls are gated by queue position:
 *   - first job (#1): ▼ down + ⤓ bottom (no up)
 *   - last job  (#2): ▲ up + ⤴ top   (no down)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../src/api/jobs', async () => {
  const actual = await vi.importActual<typeof import('../src/api/jobs')>('../src/api/jobs')
  return {
    ...actual,
    getJobHistory: vi.fn().mockResolvedValue({
      items: [mkJob('job-A', 'First clip'), mkJob('job-B', 'Second clip')],
      has_more: false,
    }),
    getQueueStatus: vi.fn().mockResolvedValue({
      max_concurrent: 1, active: 0, pending: 2, available_slots: 1,
      order: ['job-A', 'job-B'], held: [],
    }),
    moveJobToTop: vi.fn().mockResolvedValue({ job_id: 'job-B', moved: true }),
    moveJobToBottom: vi.fn().mockResolvedValue({ job_id: 'job-A', moved: true }),
    moveJob: vi.fn().mockResolvedValue({ job_id: 'x', moved: true }),
    holdJob: vi.fn().mockResolvedValue({ job_id: 'job-A', held: true }),
    resumeJob: vi.fn().mockResolvedValue({ job_id: 'job-A', held: false }),
  }
})

function mkJob(job_id: string, title: string) {
  return {
    job_id, kind: 'render', status: 'queued', progress_percent: 0,
    title, source_hint: '', stage: '', message: '',
    created_at: '2026-06-26T00:00:00Z', updated_at: '2026-06-26T00:00:00Z',
  }
}

import { QueueDrawer } from '../src/layouts/QueueDrawer'
import { useJobsStore } from '../src/stores/jobsStore'
import { useUIStore } from '../src/stores/uiStore'
import * as JobsAPI from '../src/api/jobs'

beforeEach(() => {
  const id = useJobsStore.getState()._intervalId
  if (id) clearInterval(id)
  useJobsStore.setState({
    items: [], active: null, activeCount: 0, queueOrder: [], heldIds: [],
    loading: false, error: null, _refcount: 0, _intervalId: null,
  })
  useUIStore.setState({ queueDrawerOpen: true })
  ;(JobsAPI.getQueueStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
    max_concurrent: 1, active: 0, pending: 2, available_slots: 1,
    order: ['job-A', 'job-B'], held: [],
  })
  ;(JobsAPI.moveJob as ReturnType<typeof vi.fn>).mockClear()
  ;(JobsAPI.holdJob as ReturnType<typeof vi.fn>).mockClear()
  ;(JobsAPI.resumeJob as ReturnType<typeof vi.fn>).mockClear()
})

describe('Pha 3.3a — Queue drawer', () => {
  it('renders positions and wires up/down reorder', async () => {
    const user = userEvent.setup()
    render(<QueueDrawer />)

    // Drawer header + positions render once the poll resolves.
    expect(await screen.findByText('Render queue')).toBeInTheDocument()
    expect(screen.getByText('#1/2')).toBeInTheDocument()
    expect(screen.getByText('#2/2')).toBeInTheDocument()

    // Only the last job exposes "move up"; only the first exposes "move down".
    await user.click(screen.getByTitle('Move up'))
    expect(JobsAPI.moveJob).toHaveBeenLastCalledWith('job-B', -1)

    await user.click(screen.getByTitle('Move down'))
    expect(JobsAPI.moveJob).toHaveBeenLastCalledWith('job-A', 1)
  })

  it('pauses a queued job via the ⏸ control', async () => {
    const user = userEvent.setup()
    render(<QueueDrawer />)
    await screen.findByText('#1/2')
    // Pause buttons appear for both queued render jobs.
    const pauseButtons = screen.getAllByTitle('Pause')
    expect(pauseButtons.length).toBe(2)
    await user.click(pauseButtons[0]) // job-A
    expect(JobsAPI.holdJob).toHaveBeenCalledWith('job-A')
  })

  it('shows Paused + Resume for a held job', async () => {
    // job-A is held → out of `order`, listed in `held`.
    ;(JobsAPI.getQueueStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      max_concurrent: 1, active: 0, pending: 1, available_slots: 1,
      order: ['job-B'], held: ['job-A'],
    })
    const user = userEvent.setup()
    render(<QueueDrawer />)

    expect(await screen.findByText('Paused')).toBeInTheDocument()
    // Resume control present; clicking it resumes job-A.
    await user.click(screen.getByTitle('Resume'))
    expect(JobsAPI.resumeJob).toHaveBeenCalledWith('job-A')
  })

  it('renders nothing when closed', () => {
    useUIStore.setState({ queueDrawerOpen: false })
    const { container } = render(<QueueDrawer />)
    expect(container).toBeEmptyDOMElement()
  })
})
