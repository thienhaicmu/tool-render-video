/**
 * job-detail-open-editor.test.tsx — tests for "Open in Editor" integration in JobDetailDrawer.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Mock stores ───────────────────────────────────────────────────────────────

const mockOpenEditor = vi.fn()
const mockSetActivePanel = vi.fn()

let mockEditorStoreState = {
  openEditor: mockOpenEditor,
}

let mockUIStoreState = {
  setActivePanel: mockSetActivePanel,
}

vi.mock('../src/stores/editorStore', () => ({
  useEditorStore: (selector: (s: typeof mockEditorStoreState) => unknown) =>
    selector(mockEditorStoreState),
}))

vi.mock('../src/stores/uiStore', () => ({
  useUIStore: (selector: (s: typeof mockUIStoreState) => unknown) =>
    selector(mockUIStoreState),
}))

// ── Mock quality store ────────────────────────────────────────────────────────

const mockFetchJobSummary = vi.fn().mockResolvedValue(undefined)

vi.mock('../src/stores/qualityStore', () => ({
  useQualityStore: (selector: (s: unknown) => unknown) =>
    selector({
      summaries: {},
      reports: {},
      loading: {},
      errors: {},
      fetchJobSummary: mockFetchJobSummary,
      refreshJobSummary: vi.fn(),
      fetchPartQuality: vi.fn(),
      refreshPartQuality: vi.fn(),
      clearJob: vi.fn(),
    }),
}))

// ── Mock useRenderSocket ──────────────────────────────────────────────────────

vi.mock('../src/hooks/useRenderSocket', () => ({
  useRenderSocket: () => ({
    stage: null,
    jobStatus: null,
    jobMessage: null,
    progress: null,
    isConnected: false,
    isTerminal: true,
    error: null,
  }),
}))

// ── Mock API ──────────────────────────────────────────────────────────────────

const mockGetJob = vi.fn()

vi.mock('../src/api/jobs', () => ({
  getJob: (...args: unknown[]) => mockGetJob(...args),
  getJobParts: vi.fn().mockResolvedValue([]),
}))

// ── Helper to make a job ──────────────────────────────────────────────────────

function makeJob(status: string) {
  return {
    job_id: 'job-test',
    kind: 'render',
    status,
    stage: 'done',
    progress_percent: 100,
    message: '',
    payload_json: '{}',
    result_json: '{}',
    created_at: '2026-05-23T00:00:00Z',
    updated_at: '2026-05-23T00:00:00Z',
  }
}

// ── Import after mocks ────────────────────────────────────────────────────────

import { JobDetailDrawer } from '../src/features/jobs/JobDetailDrawer'

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  mockEditorStoreState = { openEditor: mockOpenEditor }
  mockUIStoreState = { setActivePanel: mockSetActivePanel }
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('JobDetailDrawer — Open in Editor button', () => {
  it('button is present for completed job', async () => {
    mockGetJob.mockResolvedValue(makeJob('completed'))
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('open-in-editor-btn')).toBeTruthy())
  })

  it('button is enabled for completed job', async () => {
    mockGetJob.mockResolvedValue(makeJob('completed'))
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => {
      const btn = screen.getByTestId('open-in-editor-btn') as HTMLButtonElement
      expect(btn.disabled).toBe(false)
    })
  })

  it('button is disabled for queued job', async () => {
    mockGetJob.mockResolvedValue(makeJob('queued'))
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => {
      const btn = screen.getByTestId('open-in-editor-btn') as HTMLButtonElement
      expect(btn.disabled).toBe(true)
    })
  })

  it('button is disabled for running job', async () => {
    mockGetJob.mockResolvedValue(makeJob('running'))
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => {
      const btn = screen.getByTestId('open-in-editor-btn') as HTMLButtonElement
      expect(btn.disabled).toBe(true)
    })
  })

  it('button is disabled for failed job', async () => {
    mockGetJob.mockResolvedValue(makeJob('failed'))
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => {
      const btn = screen.getByTestId('open-in-editor-btn') as HTMLButtonElement
      expect(btn.disabled).toBe(true)
    })
  })

  it('button is enabled for completed_with_errors job', async () => {
    mockGetJob.mockResolvedValue(makeJob('completed_with_errors'))
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => {
      const btn = screen.getByTestId('open-in-editor-btn') as HTMLButtonElement
      expect(btn.disabled).toBe(false)
    })
  })

  it('clicking button calls openEditor(jobId, 1)', async () => {
    mockGetJob.mockResolvedValue(makeJob('completed'))
    const user = userEvent.setup()
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => screen.getByTestId('open-in-editor-btn'))
    await user.click(screen.getByTestId('open-in-editor-btn'))
    expect(mockOpenEditor).toHaveBeenCalledWith('job-test', 1)
  })

  it('clicking button calls setActivePanel("editor")', async () => {
    mockGetJob.mockResolvedValue(makeJob('completed'))
    const user = userEvent.setup()
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => screen.getByTestId('open-in-editor-btn'))
    await user.click(screen.getByTestId('open-in-editor-btn'))
    expect(mockSetActivePanel).toHaveBeenCalledWith('editor')
  })

  it('no backend mutation call when button clicked', async () => {
    mockGetJob.mockResolvedValue(makeJob('completed'))
    const user = userEvent.setup()
    render(<JobDetailDrawer jobId="job-test" onClose={() => {}} />)
    await waitFor(() => screen.getByTestId('open-in-editor-btn'))
    await user.click(screen.getByTestId('open-in-editor-btn'))
    // Only getJob should have been called (for fetching job detail) — no POST/DELETE
    expect(mockGetJob).toHaveBeenCalledOnce()
    // openEditor and setActivePanel are pure store mutations — no API call
    expect(mockOpenEditor).toHaveBeenCalledOnce()
    expect(mockSetActivePanel).toHaveBeenCalledOnce()
  })
})
