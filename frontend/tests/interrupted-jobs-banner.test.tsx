/**
 * interrupted-jobs-banner.test.tsx — Pha 5B.
 *
 * With interrupted render jobs present, the banner appears and "Resume all"
 * loops resumeRender over each. Hidden when there are none.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Hoisted so the (hoisted) vi.mock factory below can reference them.
const { ITEMS, job } = vi.hoisted(() => {
  function job(job_id: string, status: string) {
    return {
      job_id, kind: 'render', status, progress_percent: 30, title: 'R ' + job_id,
      source_hint: '', stage: 'rendering', message: '',
      created_at: '2026-06-26T00:00:00Z', updated_at: '2026-06-26T00:00:00Z',
    }
  }
  return {
    job,
    ITEMS: [job('job-i1', 'interrupted'), job('job-i2', 'interrupted'), job('job-done', 'completed')],
  }
})

vi.mock('../src/api/jobs', async () => {
  const actual = await vi.importActual<typeof import('../src/api/jobs')>('../src/api/jobs')
  return {
    ...actual,
    getJobHistory: vi.fn().mockResolvedValue({ items: ITEMS, has_more: false }),
    getQueueStatus: vi.fn().mockResolvedValue({ max_concurrent: 1, active: 0, pending: 0, available_slots: 1, order: [], held: [] }),
  }
})
vi.mock('../src/api/render', async () => {
  const actual = await vi.importActual<typeof import('../src/api/render')>('../src/api/render')
  return { ...actual, resumeRender: vi.fn().mockResolvedValue({ job_id: 'x', status: 'queued' }) }
})

import { InterruptedJobsBanner } from '../src/features/clip-studio/InterruptedJobsBanner'
import { useJobsStore } from '../src/stores/jobsStore'
import { useUIStore } from '../src/stores/uiStore'
import * as RenderAPI from '../src/api/render'
import * as JobsAPI from '../src/api/jobs'

beforeEach(() => {
  const id = useJobsStore.getState()._intervalId
  if (id) clearInterval(id)
  useJobsStore.setState({
    items: [], active: null, activeCount: 0, queueOrder: [], heldIds: [],
    loading: false, error: null, _refcount: 0, _intervalId: null,
  })
  useUIStore.setState({ lang: 'en' })
  ;(RenderAPI.resumeRender as ReturnType<typeof vi.fn>).mockClear()
  ;(JobsAPI.getJobHistory as ReturnType<typeof vi.fn>).mockResolvedValue({ items: ITEMS, has_more: false })
})

describe('Pha 5B — interrupted jobs banner', () => {
  it('shows the count and resumes all interrupted renders', async () => {
    const user = userEvent.setup()
    render(<InterruptedJobsBanner />)

    expect(await screen.findByText(/render\(s\) interrupted/)).toBeInTheDocument()
    await user.click(screen.getByText('Resume all'))

    expect(RenderAPI.resumeRender).toHaveBeenCalledTimes(2)
    expect(RenderAPI.resumeRender).toHaveBeenCalledWith('job-i1')
    expect(RenderAPI.resumeRender).toHaveBeenCalledWith('job-i2')
  })

  it('renders nothing when no jobs are interrupted', async () => {
    ;(JobsAPI.getJobHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [job('job-done', 'completed')], has_more: false,
    })
    const { container } = render(<InterruptedJobsBanner />)
    // Give the poll a tick to resolve, then assert nothing rendered.
    await new Promise((r) => setTimeout(r, 50))
    expect(container).toBeEmptyDOMElement()
  })
})
