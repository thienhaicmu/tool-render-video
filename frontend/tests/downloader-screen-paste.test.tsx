/**
 * downloader-screen-paste.test.tsx — Audit ST-13 / TEST09 closure (Batch 10D).
 *
 * Smoke coverage of the URL paste → submit → startBatch flow in
 * DownloaderScreen. The user pastes one or more URLs into a textarea,
 * picks a quality, sets an output dir, and clicks "Download". This is
 * the primary entry point for the downloader; if it silently breaks the
 * user has no way to start a download.
 *
 * Pins:
 *   - The submit button is disabled when input is empty.
 *   - The output-dir validation surfaces a localized error message
 *     when URLs are present but the dir is empty.
 *   - On success: startBatch is called with the URLs split on newline,
 *     trimmed, and empty lines dropped — plus the chosen outputDir + quality.
 *   - URL input is cleared after a successful submit.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock the API module BEFORE importing the component so the inline
// imports resolve to mocks.
vi.mock('../src/api/platformDownloader', async () => {
  const actual = await vi.importActual<typeof import('../src/api/platformDownloader')>(
    '../src/api/platformDownloader'
  )
  return {
    ...actual,
    listJobs: vi.fn().mockResolvedValue([]),
    startBatch: vi.fn(),
    cancelJob: vi.fn().mockResolvedValue(undefined),
    subscribeJob: vi.fn().mockReturnValue({ close: () => {} }),
  }
})

import { DownloaderScreen } from '../src/features/downloader/DownloaderScreen'
import * as PD from '../src/api/platformDownloader'

const mockedStartBatch = PD.startBatch as unknown as ReturnType<typeof vi.fn>


describe('DownloaderScreen — URL paste flow', () => {
  beforeEach(() => {
    mockedStartBatch.mockReset()
    mockedStartBatch.mockResolvedValue({ jobs: [] })
  })

  it('disables the Download button when the URL textarea is empty', async () => {
    render(<DownloaderScreen />)
    // Wait for initial listJobs to settle (no-op).
    const btn = await screen.findByRole('button', { name: /TẢI XUỐNG/i })
    expect(btn).toBeDisabled()
  })

  it('surfaces a localized error when URLs present but output dir missing', async () => {
    const user = userEvent.setup()
    render(<DownloaderScreen />)

    const textarea = await screen.findByPlaceholderText(/Dán URL/i)
    await user.type(textarea, 'https://youtube.com/watch?v=abc')

    const btn = screen.getByRole('button', { name: /TẢI XUỐNG/i })
    expect(btn).not.toBeDisabled()
    await user.click(btn)

    // Error message from line 219 of DownloaderScreen.tsx.
    expect(await screen.findByText(/Vui lòng chọn thư mục lưu/i)).toBeInTheDocument()
    expect(mockedStartBatch).not.toHaveBeenCalled()
  })

  it('splits URLs on newline, trims, drops empties, and clears input on success', async () => {
    const user = userEvent.setup()
    mockedStartBatch.mockResolvedValue({
      jobs: [
        { job_id: 'j1', url: 'https://youtube.com/watch?v=a', platform: 'youtube' },
        { job_id: 'j2', url: 'https://tiktok.com/@u/video/b', platform: 'tiktok' },
      ],
    })

    render(<DownloaderScreen />)

    const textarea = await screen.findByPlaceholderText(/Dán URL/i)
    // Three URLs, padded with whitespace and a blank line. We use paste
    // because the input pattern in the wild is paste-driven.
    textarea.focus()
    await user.paste(
      '  https://youtube.com/watch?v=a  \n\n  https://tiktok.com/@u/video/b\nhttps://instagram.com/p/c '
    )

    const dirInput = screen.getByPlaceholderText(/Thư mục lưu/i)
    await user.type(dirInput, 'D:\\Videos\\Downloads')

    // Pick a non-default quality so the call shape is meaningful.
    const q720 = screen.getByRole('button', { name: '720p' })
    await user.click(q720)

    const btn = screen.getByRole('button', { name: /TẢI XUỐNG/i })
    await user.click(btn)

    // startBatch invoked with cleaned URL list + outputDir + chosen quality.
    expect(mockedStartBatch).toHaveBeenCalledTimes(1)
    expect(mockedStartBatch).toHaveBeenCalledWith(
      [
        'https://youtube.com/watch?v=a',
        'https://tiktok.com/@u/video/b',
        'https://instagram.com/p/c',
      ],
      'D:\\Videos\\Downloads',
      '720p',
    )

    // After success, the URL input is cleared (line 233 of source).
    await new Promise((r) => setTimeout(r, 0))
    expect((textarea as HTMLTextAreaElement).value).toBe('')
  })
})
