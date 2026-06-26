/**
 * active-jobs-dock-queue.test.tsx — Pha 3 (Queue Workspace) UI wiring.
 *
 * The dock shows each queued render's position (#N/M) from the scheduler's
 * dispatch order, and a "move to top" control for any job that isn't
 * already first. Verifies:
 *   - position label renders from queueOrder
 *   - the #1 job has no move-top button; a later job does
 *   - clicking it calls moveJobToTop with that job_id
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../src/api/jobs', async () => {
  const actual = await vi.importActual<typeof import('../src/api/jobs')>('../src/api/jobs')
  return {
    ...actual,
    getJobHistory: vi.fn().mockResolvedValue({
      items: [
        mkJob('job-A', 'First clip'),
        mkJob('job-B', 'Second clip'),
      ],
      has_more: false,
    }),
    getQueueStatus: vi.fn().mockResolvedValue({
      max_concurrent: 1, active: 0, pending: 2, available_slots: 1,
      order: ['job-A', 'job-B'],
    }),
    moveJobToTop: vi.fn().mockResolvedValue({ job_id: 'job-B', moved: true }),
    moveJobToBottom: vi.fn().mockResolvedValue({ job_id: 'job-A', moved: true }),
  }
})

function mkJob(job_id: string, title: string) {
  return {
    job_id, kind: 'render', status: 'queued', progress_percent: 0,
    title, source_hint: '', stage: '', message: '',
    created_at: '2026-06-26T00:00:00Z', updated_at: '2026-06-26T00:00:00Z',
  }
}

import { ActiveJobsDock } from '../src/layouts/ActiveJobsDock'
import { useJobsStore } from '../src/stores/jobsStore'
import * as JobsAPI from '../src/api/jobs'

beforeEach(() => {
  const id = useJobsStore.getState()._intervalId
  if (id) clearInterval(id)
  useJobsStore.setState({
    items: [], active: null, activeCount: 0, queueOrder: [],
    loading: false, error: null, _refcount: 0, _intervalId: null,
  })
  ;(JobsAPI.moveJobToTop as ReturnType<typeof vi.fn>).mockClear()
  ;(JobsAPI.moveJobToBottom as ReturnType<typeof vi.fn>).mockClear()
})

describe('Pha 3 — dock queue position + move-to-top', () => {
  it('shows positions and bumps a non-first job to the top', async () => {
    const user = userEvent.setup()
    render(<ActiveJobsDock />)

    // Positions render from queueOrder once the poll resolves.
    expect(await screen.findByText(/#1\/2/)).toBeInTheDocument()
    expect(screen.getByText(/#2\/2/)).toBeInTheDocument()

    // Only the non-first job (job-B, #2) exposes a move-to-top control.
    const moveBtn = screen.getByTitle('Move to top of queue')
    await user.click(moveBtn)

    expect(JobsAPI.moveJobToTop).toHaveBeenCalledTimes(1)
    expect(JobsAPI.moveJobToTop).toHaveBeenCalledWith('job-B')
  })

  it('shows move-to-bottom for a non-last job and bumps it down', async () => {
    const user = userEvent.setup()
    render(<ActiveJobsDock />)
    await screen.findByText(/#1\/2/)

    // job-A is #1 (not last) → has move-to-bottom; job-B is last → not.
    const downBtn = screen.getByTitle('Move to bottom of queue')
    await user.click(downBtn)

    expect(JobsAPI.moveJobToBottom).toHaveBeenCalledTimes(1)
    expect(JobsAPI.moveJobToBottom).toHaveBeenCalledWith('job-A')
  })
})
