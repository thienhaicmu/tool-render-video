/**
 * job-actions.test.tsx — tests for job action handlers in HistoryScreen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HistoryScreen } from '../src/features/jobs/HistoryScreen'
import { useUIStore } from '../src/stores/uiStore'

// ── Mock API modules ───────────────────────────────────────────────────────────

vi.mock('../src/api/jobs', () => ({
  getJobHistory: vi.fn(),
  deleteJob: vi.fn(),
}))

vi.mock('../src/api/render', () => ({
  cancelRender: vi.fn(),
  retryRender: vi.fn(),
  resumeRender: vi.fn(),
}))

import { getJobHistory, deleteJob } from '../src/api/jobs'
import { cancelRender, retryRender } from '../src/api/render'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeRunningItem(overrides = {}) {
  return {
    job_id: 'job-running',
    kind: 'render' as const,
    status: 'running',
    stage: 'rendering',
    title: 'Running Job',
    source_hint: 'https://youtube.com/watch?v=abc',
    timestamp: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    output_dir: null,
    completed_count: 1,
    failed_count: 0,
    unsupported_count: 0,
    total_count: 3,
    summary_text: 'Rendering…',
    can_open_folder: false,
    can_retry: false,
    can_rerun: false,
    ...overrides,
  }
}

function makeFailedItem(overrides = {}) {
  return {
    job_id: 'job-failed',
    kind: 'render' as const,
    status: 'failed',
    stage: 'done',
    title: 'Failed Job',
    source_hint: null,
    timestamp: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    output_dir: null,
    completed_count: 0,
    failed_count: 2,
    unsupported_count: 0,
    total_count: 2,
    summary_text: '2 failed',
    can_open_folder: false,
    can_retry: true,
    can_rerun: false,
    ...overrides,
  }
}

function makeCompletedItem(overrides = {}) {
  return {
    job_id: 'job-completed',
    kind: 'render' as const,
    status: 'completed',
    stage: 'done',
    title: 'Completed Job',
    source_hint: null,
    timestamp: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    output_dir: '/output',
    completed_count: 3,
    failed_count: 0,
    unsupported_count: 0,
    total_count: 3,
    summary_text: '3 done',
    can_open_folder: true,
    can_retry: false,
    can_rerun: false,
    ...overrides,
  }
}

function makeHistoryResponse(items: unknown[]) {
  return { items, limit: 20, offset: 0, has_more: false }
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  useUIStore.setState({ sidebarOpen: true, activePanel: 'history', notifications: [] })

  // Default: return running item
  vi.mocked(getJobHistory).mockResolvedValue(
    makeHistoryResponse([makeRunningItem()]) as any
  )
})

// ── Cancel action ─────────────────────────────────────────────────────────────

describe('Cancel action', () => {
  it('calls cancelRender with the jobId', async () => {
    vi.mocked(cancelRender).mockResolvedValue(undefined)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('cancel-btn-job-running'))

    await user.click(screen.getByTestId('cancel-btn-job-running'))
    await waitFor(() => expect(cancelRender).toHaveBeenCalledWith('job-running'))
  })

  it('shows success notification on cancel success', async () => {
    vi.mocked(cancelRender).mockResolvedValue(undefined)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('cancel-btn-job-running'))

    await user.click(screen.getByTestId('cancel-btn-job-running'))
    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      expect(notifications.some((n) => n.type === 'success')).toBe(true)
    })
  })

  it('shows error notification on cancel failure', async () => {
    vi.mocked(cancelRender).mockRejectedValue(new Error('Network error'))
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('cancel-btn-job-running'))

    await user.click(screen.getByTestId('cancel-btn-job-running'))
    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      expect(notifications.some((n) => n.type === 'error')).toBe(true)
    })
  })
})

// ── Retry action ──────────────────────────────────────────────────────────────

describe('Retry action', () => {
  beforeEach(() => {
    vi.mocked(getJobHistory).mockResolvedValue(
      makeHistoryResponse([makeFailedItem()]) as any
    )
  })

  it('calls retryRender with the jobId', async () => {
    vi.mocked(retryRender).mockResolvedValue({ job_id: 'job-failed', status: 'queued' })
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('retry-btn-job-failed'))

    await user.click(screen.getByTestId('retry-btn-job-failed'))
    await waitFor(() => expect(retryRender).toHaveBeenCalledWith('job-failed'))
  })

  it('shows success notification on retry success', async () => {
    vi.mocked(retryRender).mockResolvedValue({ job_id: 'job-failed', status: 'queued' })
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('retry-btn-job-failed'))

    await user.click(screen.getByTestId('retry-btn-job-failed'))
    await waitFor(() => {
      const { notifications } = useUIStore.getState()
      expect(notifications.some((n) => n.type === 'success')).toBe(true)
    })
  })
})

// ── Delete action ─────────────────────────────────────────────────────────────

describe('Delete action', () => {
  beforeEach(() => {
    vi.mocked(getJobHistory).mockResolvedValue(
      makeHistoryResponse([makeCompletedItem()]) as any
    )
  })

  it('calls window.confirm before deleteJob', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('delete-btn-job-completed'))

    await user.click(screen.getByTestId('delete-btn-job-completed'))
    expect(confirmSpy).toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('does NOT call deleteJob when confirm returns false', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('delete-btn-job-completed'))

    await user.click(screen.getByTestId('delete-btn-job-completed'))
    expect(deleteJob).not.toHaveBeenCalled()

    vi.restoreAllMocks()
  })

  it('calls deleteJob(jobId, true) when confirm returns true', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(deleteJob).mockResolvedValue({
      job_id: 'job-completed',
      deleted: true,
      deleted_files: 2,
      skipped_files: 0,
    })
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('delete-btn-job-completed'))

    await user.click(screen.getByTestId('delete-btn-job-completed'))
    await waitFor(() => expect(deleteJob).toHaveBeenCalledWith('job-completed', true))

    vi.restoreAllMocks()
  })
})

// ── Action loading state ──────────────────────────────────────────────────────

describe('Action loading state', () => {
  it('shows loading during in-flight cancel', async () => {
    // Make cancel hang so we can observe loading state
    let resolveFn: (() => void) | null = null
    vi.mocked(cancelRender).mockReturnValue(
      new Promise<void>((resolve) => { resolveFn = resolve })
    )
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('cancel-btn-job-running'))

    const cancelBtn = screen.getByTestId('cancel-btn-job-running') as HTMLButtonElement
    await user.click(cancelBtn)

    // Button should be disabled (loading)
    expect(cancelBtn.disabled).toBe(true)

    // Resolve to unblock
    resolveFn!()
  })
})
