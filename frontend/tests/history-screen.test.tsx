/**
 * history-screen.test.tsx — integration tests for HistoryScreen.
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
  getJob: vi.fn(),
}))

vi.mock('../src/api/render', () => ({
  cancelRender: vi.fn(),
  retryRender: vi.fn(),
  resumeRender: vi.fn(),
}))

import { getJobHistory } from '../src/api/jobs'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeItem(overrides: Record<string, unknown> = {}) {
  return {
    job_id: 'job-abc',
    kind: 'render' as const,
    status: 'completed',
    stage: 'done',
    title: 'My Video',
    source_hint: 'https://youtube.com/watch?v=xyz',
    timestamp: new Date().toISOString(),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    output_dir: '/output',
    completed_count: 2,
    failed_count: 0,
    unsupported_count: 0,
    total_count: 2,
    summary_text: '2 parts done',
    can_open_folder: true,
    can_retry: false,
    can_rerun: false,
    ...overrides,
  }
}

function makeResponse(items: unknown[], overrides: Record<string, unknown> = {}) {
  return { items, limit: 20, offset: 0, has_more: false, ...overrides }
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  useUIStore.setState({ sidebarOpen: true, activePanel: 'history', notifications: [] })
})

// ── Rendering ─────────────────────────────────────────────────────────────────

describe('HistoryScreen — rendering', () => {
  it('renders without crashing', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([]) as any)
    const { container } = render(<HistoryScreen />)
    expect(container).toBeTruthy()
  })

  it('calls getJobHistory on mount', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([]) as any)
    render(<HistoryScreen />)
    await waitFor(() => expect(getJobHistory).toHaveBeenCalledWith(20, 0))
  })

  it('shows loading state initially', () => {
    // Never resolves during this test
    vi.mocked(getJobHistory).mockReturnValue(new Promise(() => {}))
    render(<HistoryScreen />)
    expect(screen.getByTestId('job-loading-state')).toBeTruthy()
  })

  it('shows empty state when items is empty', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([]) as any)
    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('No render jobs yet'))
    expect(screen.getByText('No render jobs yet')).toBeTruthy()
  })

  it('shows job list when items are provided', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([makeItem()]) as any)
    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('My Video'))
    expect(screen.getByText('My Video')).toBeTruthy()
  })
})

// ── Empty state CTA ───────────────────────────────────────────────────────────

describe('HistoryScreen — empty state CTA', () => {
  it('clicking "Create first render" switches to render panel', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([]) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('Create first render'))

    await user.click(screen.getByText('Create first render'))
    expect(useUIStore.getState().activePanel).toBe('render')
  })
})

// ── Refresh ───────────────────────────────────────────────────────────────────

describe('HistoryScreen — refresh', () => {
  it('refresh button triggers re-fetch', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([]) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => expect(getJobHistory).toHaveBeenCalledTimes(1))

    const refreshBtn = screen.getByTestId('refresh-btn')
    await user.click(refreshBtn)

    await waitFor(() => expect(getJobHistory).toHaveBeenCalledTimes(2))
  })
})

// ── Search filtering ──────────────────────────────────────────────────────────

describe('HistoryScreen — search filtering', () => {
  it('search filters by title', async () => {
    const items = [
      makeItem({ job_id: 'j1', title: 'My Great Video' }),
      makeItem({ job_id: 'j2', title: 'Another Clip'  }),
    ]
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse(items) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('My Great Video'))

    await user.type(screen.getByTestId('history-search-input'), 'great')

    expect(screen.getByText('My Great Video')).toBeTruthy()
    expect(screen.queryByText('Another Clip')).toBeNull()
  })

  it('search filters by job_id', async () => {
    const items = [
      makeItem({ job_id: 'unique-abc-123', title: 'Alpha'  }),
      makeItem({ job_id: 'other-xyz-456',  title: 'Beta'   }),
    ]
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse(items) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('Alpha'))

    await user.type(screen.getByTestId('history-search-input'), 'abc-123')

    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.queryByText('Beta')).toBeNull()
  })
})

// ── Status filtering ──────────────────────────────────────────────────────────

describe('HistoryScreen — status filter', () => {
  it("status filter 'running' shows only active jobs", async () => {
    const items = [
      makeItem({ job_id: 'j-run',  status: 'running',   title: 'Active Job'    }),
      makeItem({ job_id: 'j-done', status: 'completed', title: 'Finished Job'  }),
    ]
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse(items) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('Active Job'))

    await user.selectOptions(screen.getByTestId('history-status-filter'), 'running')

    expect(screen.getByText('Active Job')).toBeTruthy()
    expect(screen.queryByText('Finished Job')).toBeNull()
  })

  it("status filter 'completed' shows completed AND partial jobs", async () => {
    const items = [
      makeItem({ job_id: 'j-comp',    status: 'completed', title: 'Complete Job' }),
      makeItem({ job_id: 'j-partial', status: 'partial',   title: 'Partial Job'  }),
      makeItem({ job_id: 'j-failed',  status: 'failed',    title: 'Failed Job'   }),
    ]
    vi.mocked(getJobHistory).mockResolvedValue(makeResponse(items) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByText('Complete Job'))

    await user.selectOptions(screen.getByTestId('history-status-filter'), 'completed')

    expect(screen.getByText('Complete Job')).toBeTruthy()
    expect(screen.getByText('Partial Job')).toBeTruthy()
    expect(screen.queryByText('Failed Job')).toBeNull()
  })
})

// ── Job selection (detail panel) ──────────────────────────────────────────────

describe('HistoryScreen — job selection', () => {
  it('clicking a job item opens the detail panel', async () => {
    const { getJob } = await import('../src/api/jobs')
    vi.mocked(getJob).mockResolvedValue({
      job_id: 'job-abc',
      kind: 'render',
      status: 'completed',
      stage: 'done',
      progress_percent: 100,
      message: '',
      payload_json: '{}',
      result_json: '{}',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any)

    vi.mocked(getJobHistory).mockResolvedValue(makeResponse([makeItem()]) as any)
    const user = userEvent.setup()

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('job-list-item-job-abc'))

    await user.click(screen.getByTestId('job-list-item-job-abc'))

    await waitFor(() => screen.getByTestId('job-detail-drawer'))
    expect(screen.getByTestId('job-detail-drawer')).toBeTruthy()
  })
})

// ── Pagination ────────────────────────────────────────────────────────────────

describe('HistoryScreen — pagination', () => {
  it('Next button is visible when has_more=true', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(
      makeResponse([makeItem()], { has_more: true }) as any
    )

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('pagination-next'))

    const nextBtn = screen.getByTestId('pagination-next') as HTMLButtonElement
    expect(nextBtn.disabled).toBe(false)
  })

  it('Next button is disabled when has_more=false', async () => {
    vi.mocked(getJobHistory).mockResolvedValue(
      makeResponse([makeItem()], { has_more: false }) as any
    )

    render(<HistoryScreen />)
    await waitFor(() => screen.getByTestId('pagination-next'))

    const nextBtn = screen.getByTestId('pagination-next') as HTMLButtonElement
    expect(nextBtn.disabled).toBe(true)
  })
})
