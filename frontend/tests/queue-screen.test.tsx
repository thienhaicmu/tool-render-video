/**
 * queue-screen.test.tsx — WP5.
 *
 * Smoke coverage for the QueueScreen panel that superseded the deleted
 * QueueDrawer overlay. Verifies it renders the queue header and lists an
 * active job via the shared JobRow.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('@/api/jobs', () => ({
  getJobHistory: vi.fn(),
  getQueueStatus: vi.fn(),
  moveJobToTop: vi.fn(),
  moveJobToBottom: vi.fn(),
  moveJob: vi.fn(),
  holdJob: vi.fn(),
  resumeJob: vi.fn(),
}))
vi.mock('@/api/render', () => ({ cancelRender: vi.fn() }))
vi.mock('@/api/platformDownloader', () => ({ cancelJob: vi.fn() }))

import { QueueScreen } from '../src/features/queue/QueueScreen'
import { getJobHistory, getQueueStatus } from '@/api/jobs'
import { useJobsStore } from '../src/stores/jobsStore'

const emptyQueue = { max_concurrent: 1, active: 0, pending: 0, available_slots: 1, order: [], held: [] }

beforeEach(() => {
  vi.clearAllMocks()
  useJobsStore.setState({
    items: [], active: null, activeCount: 0, queueOrder: [], heldIds: [],
    loading: false, error: null, _refcount: 0, _intervalId: null,
  })
  vi.mocked(getQueueStatus).mockResolvedValue(emptyQueue)
})

describe('QueueScreen', () => {
  it('renders the queue header even when empty', async () => {
    vi.mocked(getJobHistory).mockResolvedValue({ items: [], has_more: false } as never)
    render(<QueueScreen />)
    await waitFor(() => expect(screen.getByText('Render queue')).toBeTruthy())
  })

  it('lists an active render job by title', async () => {
    vi.mocked(getJobHistory).mockResolvedValue({
      items: [{
        job_id: 'job-1', kind: 'render', status: 'running',
        progress_percent: 40, title: 'My clip', source_hint: '', stage: 'rendering',
        message: '', created_at: '', updated_at: '',
      }],
      has_more: false,
    } as never)
    render(<QueueScreen />)
    await waitFor(() => expect(screen.getByText('My clip')).toBeTruthy())
  })
})
