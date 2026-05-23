/**
 * quality-panel.test.tsx — rendering and behaviour tests for QualityPanel + related components.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Mock the quality store ────────────────────────────────────────────────────

const mockFetchJobSummary = vi.fn()
const mockRefreshJobSummary = vi.fn()
const mockFetchPartQuality = vi.fn()

// Default store state — overridden per test
let mockStoreState = {
  summaries: {} as Record<string, unknown>,
  reports: {} as Record<string, unknown>,
  loading: {} as Record<string, boolean>,
  errors: {} as Record<string, string>,
  fetchJobSummary: mockFetchJobSummary,
  refreshJobSummary: mockRefreshJobSummary,
  fetchPartQuality: mockFetchPartQuality,
  refreshPartQuality: vi.fn(),
  clearJob: vi.fn(),
}

vi.mock('../src/stores/qualityStore', () => ({
  useQualityStore: (selector: (s: typeof mockStoreState) => unknown) =>
    selector(mockStoreState),
}))

// ── Import components AFTER mock ──────────────────────────────────────────────

import { QualityPanel } from '../src/features/quality/QualityPanel'
import { QualityTraceRefs } from '../src/features/quality/QualityTraceRefs'
import { QualityEmptyState } from '../src/features/quality/QualityEmptyState'
import { QualityErrorState } from '../src/features/quality/QualityErrorState'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeAggregate(overrides = {}) {
  return {
    available_parts: 2,
    total_parts: 3,
    average_score: 88,
    critical_count: 0,
    error_count: 1,
    warning_count: 2,
    info_count: 0,
    ...overrides,
  }
}

function makeSummary(jobId = 'job-1', overrides = {}) {
  return {
    job_id: jobId,
    parts: [
      {
        part_no: 1,
        available: true,
        score: 90,
        issue_count: 1,
        critical_count: 0,
        error_count: 1,
        warning_count: 0,
        info_count: 0,
        report: null,
      },
    ],
    summary: makeAggregate(),
    ...overrides,
  }
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  mockStoreState = {
    summaries: {},
    reports: {},
    loading: {},
    errors: {},
    fetchJobSummary: mockFetchJobSummary,
    refreshJobSummary: mockRefreshJobSummary,
    fetchPartQuality: mockFetchPartQuality,
    refreshPartQuality: vi.fn(),
    clearJob: vi.fn(),
  }
  mockFetchJobSummary.mockResolvedValue(undefined)
  mockRefreshJobSummary.mockResolvedValue(undefined)
  mockFetchPartQuality.mockResolvedValue(undefined)
})

// ── QualityPanel rendering ────────────────────────────────────────────────────

describe('QualityPanel — basic rendering', () => {
  it('renders without crashing', () => {
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    expect(screen.getByTestId('quality-panel')).toBeTruthy()
  })
})

describe('QualityPanel — fetch guards', () => {
  it('does NOT call fetchJobSummary when status is queued', () => {
    render(<QualityPanel jobId="job-q" jobStatus="queued" />)
    expect(mockFetchJobSummary).not.toHaveBeenCalled()
  })

  it('does NOT call fetchJobSummary when status is running', () => {
    render(<QualityPanel jobId="job-r" jobStatus="running" />)
    expect(mockFetchJobSummary).not.toHaveBeenCalled()
  })

  it('calls fetchJobSummary when status is completed', async () => {
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    await waitFor(() => expect(mockFetchJobSummary).toHaveBeenCalledWith('job-1'))
  })

  it('calls fetchJobSummary when status is failed', async () => {
    render(<QualityPanel jobId="job-2" jobStatus="failed" />)
    await waitFor(() => expect(mockFetchJobSummary).toHaveBeenCalledWith('job-2'))
  })
})

describe('QualityPanel — pending status display', () => {
  it('shows "will be available after render" message for queued', () => {
    render(<QualityPanel jobId="job-q" jobStatus="queued" />)
    expect(screen.getByText(/will be available after render completes/i)).toBeTruthy()
  })

  it('shows "will be available after render" message for running', () => {
    render(<QualityPanel jobId="job-r" jobStatus="running" />)
    expect(screen.getByText(/will be available after render completes/i)).toBeTruthy()
  })
})

describe('QualityPanel — loading state', () => {
  it('shows loading state when loading is true in store', () => {
    mockStoreState.loading = { 'job-1': true }
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    expect(screen.getByTestId('quality-loading')).toBeTruthy()
  })
})

describe('QualityPanel — error state', () => {
  it('shows error state when store has a non-404 error', () => {
    mockStoreState.errors = { 'job-1': 'Internal server error' }
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    expect(screen.getByTestId('quality-error')).toBeTruthy()
    expect(screen.getByText('Internal server error')).toBeTruthy()
  })
})

describe('QualityPanel — loaded state', () => {
  it('shows QualitySummaryCard when summary is loaded', () => {
    mockStoreState.summaries = { 'job-1': makeSummary('job-1') }
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    expect(screen.getByTestId('quality-summary-card')).toBeTruthy()
  })

  it('shows Refresh button when loaded', () => {
    mockStoreState.summaries = { 'job-1': makeSummary('job-1') }
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    expect(screen.getByTestId('quality-refresh-btn')).toBeTruthy()
  })

  it('clicking Refresh calls refreshJobSummary', async () => {
    mockStoreState.summaries = { 'job-1': makeSummary('job-1') }
    const user = userEvent.setup()
    render(<QualityPanel jobId="job-1" jobStatus="completed" />)
    await user.click(screen.getByTestId('quality-refresh-btn'))
    expect(mockRefreshJobSummary).toHaveBeenCalledWith('job-1')
  })
})

// ── QualityPartCard expand + on-demand fetch ──────────────────────────────────

describe('QualityPartCard — expand and fetch', () => {
  it('expands and calls fetchPartQuality when part has no report', async () => {
    // Need to import QualityPartCard and provide part data
    const { QualityPartCard } = await import('../src/features/quality/QualityPartCard')
    const part = {
      part_no: 1,
      available: true,
      score: 85,
      issue_count: 2,
      critical_count: 0,
      error_count: 1,
      warning_count: 1,
      info_count: 0,
      report: null,
    }
    const user = userEvent.setup()
    render(<QualityPartCard jobId="job-1" part={part} />)

    const header = screen.getByTestId('quality-part-card-1')
    await user.click(header.querySelector('[role="button"]')!)
    await waitFor(() => expect(mockFetchPartQuality).toHaveBeenCalledWith('job-1', 1))
  })
})

// ── QualityTraceRefs ──────────────────────────────────────────────────────────

describe('QualityTraceRefs', () => {
  it("shows friendly label 'AI pacing applied' for 'ai.pacing_applied'", () => {
    render(<QualityTraceRefs traceRefs={['ai.pacing_applied']} />)
    expect(screen.getByText('AI pacing applied')).toBeTruthy()
  })

  it('shows "No AI trace references" when empty', () => {
    render(<QualityTraceRefs traceRefs={[]} />)
    expect(screen.getByText(/No AI trace references/i)).toBeTruthy()
  })

  it('does not show raw event string for known ref', () => {
    render(<QualityTraceRefs traceRefs={['ai.pacing_applied']} />)
    // Raw string should NOT appear
    expect(screen.queryByText('ai.pacing_applied')).toBeNull()
  })
})

// ── QualityEmptyState ─────────────────────────────────────────────────────────

describe('QualityEmptyState', () => {
  it('renders for 404/missing reports', () => {
    render(<QualityEmptyState />)
    expect(screen.getByTestId('quality-empty')).toBeTruthy()
    expect(screen.getByText(/Quality report not available/i)).toBeTruthy()
  })
})

// ── QualityErrorState ─────────────────────────────────────────────────────────

describe('QualityErrorState', () => {
  it('renders with retry button on API error', () => {
    const onRetry = vi.fn()
    render(<QualityErrorState error="API fetch failed" onRetry={onRetry} />)
    expect(screen.getByTestId('quality-error')).toBeTruthy()
    expect(screen.getByText('API fetch failed')).toBeTruthy()
    expect(screen.getByText('Retry')).toBeTruthy()
  })

  it('clicking Retry calls onRetry', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(<QualityErrorState error="Error" onRetry={onRetry} />)
    await user.click(screen.getByText('Retry'))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})

// ── JobDetailDrawer integration ───────────────────────────────────────────────

describe('JobDetailDrawer integration', () => {
  it('no longer contains "coming in Phase 6.3" text', async () => {
    vi.mock('../src/api/jobs', async (importOriginal) => {
      const actual = await importOriginal<typeof import('../src/api/jobs')>()
      return {
        ...actual,
        getJob: vi.fn().mockResolvedValue({
          job_id: 'job-drawer',
          kind: 'render',
          status: 'completed',
          stage: 'done',
          progress_percent: 100,
          message: '',
          payload_json: '{}',
          result_json: '{}',
          created_at: '2026-05-23T00:00:00Z',
          updated_at: '2026-05-23T00:00:00Z',
        }),
      }
    })

    const { JobDetailDrawer } = await import('../src/features/jobs/JobDetailDrawer')
    render(<JobDetailDrawer jobId="job-drawer" onClose={() => {}} />)

    // The old placeholder text must not be present
    expect(screen.queryByText(/coming in Phase 6\.3/i)).toBeNull()
  })

  it('does not expose raw JSON or AI internals in rendered output', async () => {
    mockStoreState.summaries = { 'job-clean': makeSummary('job-clean') }

    render(<QualityPanel jobId="job-clean" jobStatus="completed" />)

    // Should not find raw JSON blobs
    const panel = screen.getByTestId('quality-panel')
    expect(panel.textContent).not.toMatch(/"job_id"/)
    expect(panel.textContent).not.toMatch(/"ai_trace_refs"/)
  })
})
