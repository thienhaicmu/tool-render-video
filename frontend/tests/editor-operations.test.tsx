/**
 * editor-operations.test.tsx — Phase 6.8 editor action integration tests.
 *
 * Tests:
 * - Apply Trim button disabled when no trim is set
 * - Apply Trim button enabled when valid trim range exists
 * - Re-render Selection button disabled when no trim
 * - Export Clip button disabled when export dir is empty
 * - Export dir input changes enable Export button
 * - Metadata panel renders with expected testids
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditorMetadataPanel } from '../src/features/editor/EditorMetadataPanel'

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../src/stores/uiStore', () => ({
  useUIStore: (selector: (s: object) => unknown) => {
    const store = {
      addNotification: vi.fn(),
      setActivePanel: vi.fn(),
    }
    return selector(store)
  },
}))

vi.mock('../src/api/editing', () => ({
  trimJobPart: vi.fn().mockResolvedValue({
    status: 'ok',
    job_id: 'test-job',
    part_no: 1,
    output_file: '/fake/out.mp4',
    duration_sec: 10.0,
    trim_start_sec: 5.0,
    trim_end_sec: 15.0,
    output_mode: 'new_job',
  }),
  rerenderSelection: vi.fn().mockResolvedValue({
    status: 'queued',
    new_job_id: 'rerender_test-job_abc12345',
    parent_job_id: 'test-job',
    parent_part_no: 1,
    trim_start_sec: 5.0,
    trim_end_sec: 15.0,
  }),
  exportClip: vi.fn().mockResolvedValue({
    status: 'ok',
    job_id: 'test-job',
    part_no: 1,
    source_file: 'part1.mp4',
    exported_to: '/exports/part1.mp4',
    destination_dir: '/exports',
  }),
}))

// ── Default props ──────────────────────────────────────────────────────────────

const defaultProps = {
  jobId: 'test-job-001',
  partNo: 1,
  jobStatus: 'completed',
  durationSec: 30.0,
  trimStartSec: 0.0,
  trimEndSec: 30.0,  // same as duration = no trim
  mediaUrl: '/api/render/jobs/test-job-001/parts/1/media',
}

describe('EditorMetadataPanel — rendering', () => {
  it('renders the metadata panel with testid', () => {
    render(<EditorMetadataPanel {...defaultProps} />)
    expect(screen.getByTestId('editor-metadata-panel')).toBeInTheDocument()
  })

  it('shows job id in the panel', () => {
    render(<EditorMetadataPanel {...defaultProps} />)
    expect(screen.getByTestId('editor-job-id')).toHaveTextContent('test-job-001')
  })

  it('renders apply-trim, rerender, and export buttons', () => {
    render(<EditorMetadataPanel {...defaultProps} />)
    expect(screen.getByTestId('apply-trim-btn')).toBeInTheDocument()
    expect(screen.getByTestId('rerender-btn')).toBeInTheDocument()
    expect(screen.getByTestId('export-clip-btn')).toBeInTheDocument()
  })

  it('renders export dir input', () => {
    render(<EditorMetadataPanel {...defaultProps} />)
    expect(screen.getByTestId('export-dir-input')).toBeInTheDocument()
  })
})

describe('EditorMetadataPanel — Apply Trim button state', () => {
  it('is disabled when trim equals full duration (no trim set)', () => {
    render(<EditorMetadataPanel {...defaultProps} trimStartSec={0} trimEndSec={30} />)
    expect(screen.getByTestId('apply-trim-btn')).toBeDisabled()
  })

  it('is disabled when duration is 0 (video not loaded)', () => {
    render(<EditorMetadataPanel {...defaultProps} durationSec={0} trimStartSec={0} trimEndSec={0} />)
    expect(screen.getByTestId('apply-trim-btn')).toBeDisabled()
  })

  it('is enabled when valid trim range is set', () => {
    render(
      <EditorMetadataPanel
        {...defaultProps}
        trimStartSec={5}
        trimEndSec={15}
        durationSec={30}
      />
    )
    expect(screen.getByTestId('apply-trim-btn')).not.toBeDisabled()
  })

  it('is disabled when trim duration is below minimum (< 1s)', () => {
    render(
      <EditorMetadataPanel
        {...defaultProps}
        trimStartSec={5.0}
        trimEndSec={5.5}
        durationSec={30}
      />
    )
    expect(screen.getByTestId('apply-trim-btn')).toBeDisabled()
  })
})

describe('EditorMetadataPanel — Re-render Selection button state', () => {
  it('is disabled when trim equals full duration', () => {
    render(<EditorMetadataPanel {...defaultProps} trimStartSec={0} trimEndSec={30} />)
    expect(screen.getByTestId('rerender-btn')).toBeDisabled()
  })

  it('is enabled when valid trim range is set', () => {
    render(
      <EditorMetadataPanel
        {...defaultProps}
        trimStartSec={5}
        trimEndSec={20}
        durationSec={30}
      />
    )
    expect(screen.getByTestId('rerender-btn')).not.toBeDisabled()
  })
})

describe('EditorMetadataPanel — Export Clip button state', () => {
  it('is disabled when export dir input is empty', () => {
    render(<EditorMetadataPanel {...defaultProps} />)
    expect(screen.getByTestId('export-clip-btn')).toBeDisabled()
  })

  it('is enabled when export dir input has text', async () => {
    const user = userEvent.setup()
    render(<EditorMetadataPanel {...defaultProps} />)
    const input = screen.getByTestId('export-dir-input')
    await user.type(input, '/my/export/dir')
    expect(screen.getByTestId('export-clip-btn')).not.toBeDisabled()
  })
})
