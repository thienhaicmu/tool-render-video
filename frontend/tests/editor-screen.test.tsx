/**
 * editor-screen.test.tsx — rendering and behaviour tests for EditorScreen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Mock stores ───────────────────────────────────────────────────────────────

const mockSetActivePanel = vi.fn()
let mockUIStoreState = {
  setActivePanel: mockSetActivePanel,
}

vi.mock('../src/stores/uiStore', () => ({
  useUIStore: (selector: (s: typeof mockUIStoreState) => unknown) =>
    selector(mockUIStoreState),
}))

let mockEditorStoreState = {
  selectedJobId: null as string | null,
  selectedPartNo: null as number | null,
  mediaUrl: null as string | null,
  durationSec: 0,
  trimStartSec: 0,
  trimEndSec: 0,
  isDirty: false,
  openEditor: vi.fn(),
  setDuration: vi.fn(),
  setTrim: vi.fn(),
  resetTrim: vi.fn(),
  closeEditor: vi.fn(),
}

vi.mock('../src/stores/editorStore', () => ({
  useEditorStore: (selector: (s: typeof mockEditorStoreState) => unknown) =>
    selector(mockEditorStoreState),
}))

// ── Mock API ──────────────────────────────────────────────────────────────────

const mockGetJobParts = vi.fn()

vi.mock('../src/api/jobs', () => ({
  getJobParts: (...args: unknown[]) => mockGetJobParts(...args),
}))

// ── Import after mocks ────────────────────────────────────────────────────────

import { EditorScreen } from '../src/features/editor/EditorScreen'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makePart(partNo: number, status = 'done') {
  return {
    part_no: partNo,
    status,
    progress_percent: 100,
    output_file: `/output/part_${partNo}.mp4`,
    updated_at: '2026-05-23T00:00:00Z',
  }
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  mockGetJobParts.mockResolvedValue([])

  mockEditorStoreState = {
    selectedJobId: null,
    selectedPartNo: null,
    mediaUrl: null,
    durationSec: 0,
    trimStartSec: 0,
    trimEndSec: 0,
    isDirty: false,
    openEditor: vi.fn(),
    setDuration: vi.fn(),
    setTrim: vi.fn(),
    resetTrim: vi.fn(),
    closeEditor: vi.fn(),
  }

  mockUIStoreState = {
    setActivePanel: mockSetActivePanel,
  }
})

// ── Empty state ───────────────────────────────────────────────────────────────

describe('EditorScreen — empty state', () => {
  it('renders EditorEmptyState when no selectedJobId', () => {
    render(<EditorScreen />)
    expect(screen.getByTestId('editor-empty-state')).toBeTruthy()
  })

  it('shows "No media selected" text', () => {
    render(<EditorScreen />)
    expect(screen.getByText('No media selected')).toBeTruthy()
  })

  it('"Go to History" button calls setActivePanel("history")', async () => {
    const user = userEvent.setup()
    render(<EditorScreen />)
    await user.click(screen.getByTestId('go-to-history-btn'))
    expect(mockSetActivePanel).toHaveBeenCalledWith('history')
  })
})

// ── With job selected ─────────────────────────────────────────────────────────

describe('EditorScreen — with job selected', () => {
  beforeEach(() => {
    mockEditorStoreState.selectedJobId = 'job-123'
    mockEditorStoreState.selectedPartNo = 1
    mockEditorStoreState.mediaUrl = '/api/render/jobs/job-123/parts/1/media'
    mockGetJobParts.mockResolvedValue([makePart(1)])
  })

  it('calls getJobParts on mount when job is selected', async () => {
    render(<EditorScreen />)
    await waitFor(() => expect(mockGetJobParts).toHaveBeenCalledWith('job-123'))
  })

  it('renders video player when mediaUrl is set', async () => {
    render(<EditorScreen />)
    await waitFor(() => expect(screen.getByTestId('video-preview')).toBeTruthy())
  })

  it('does not show empty state when job is selected', async () => {
    render(<EditorScreen />)
    await waitFor(() => {
      expect(screen.queryByTestId('editor-empty-state')).toBeNull()
    })
  })
})

// ── Part selector ─────────────────────────────────────────────────────────────

describe('EditorScreen — part selector', () => {
  it('renders part selector when multiple parts available', async () => {
    mockEditorStoreState.selectedJobId = 'job-multi'
    mockEditorStoreState.selectedPartNo = 1
    mockEditorStoreState.mediaUrl = '/api/render/jobs/job-multi/parts/1/media'
    mockGetJobParts.mockResolvedValue([makePart(1), makePart(2), makePart(3)])

    render(<EditorScreen />)
    await waitFor(() => expect(screen.getByTestId('part-selector')).toBeTruthy())
  })

  it('does NOT render part selector when only one part', async () => {
    mockEditorStoreState.selectedJobId = 'job-single'
    mockEditorStoreState.selectedPartNo = 1
    mockEditorStoreState.mediaUrl = '/api/render/jobs/job-single/parts/1/media'
    mockGetJobParts.mockResolvedValue([makePart(1)])

    render(<EditorScreen />)
    await waitFor(() => {
      expect(screen.queryByTestId('part-selector')).toBeNull()
    })
  })

  it('shows loading state while fetching parts', () => {
    mockEditorStoreState.selectedJobId = 'job-loading'
    // getJobParts never resolves — stays in loading
    mockGetJobParts.mockReturnValue(new Promise(() => {}))

    render(<EditorScreen />)
    expect(screen.getByTestId('editor-loading-state')).toBeTruthy()
  })

  it('shows error state when getJobParts fails', async () => {
    mockEditorStoreState.selectedJobId = 'job-err'
    mockGetJobParts.mockRejectedValue(new Error('Network error'))

    render(<EditorScreen />)
    await waitFor(() => expect(screen.getByTestId('editor-error-state')).toBeTruthy())
  })
})
