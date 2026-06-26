/**
 * download-to-render-handoff.test.tsx — Pha 1.1 coverage.
 *
 * End-to-end smoke of the Download→Render handoff. A finished download
 * exposes a "→ Render" button; clicking it must:
 *   1. (producer)  stash the file path in uiStore.sendToRenderSourcePath
 *   2. (ClipStudio) flip the active tab from Download back to Render
 *   3. (consumer)  RenderWorkflow pre-fill the source on a clean Step 1
 *                  and clear the seed so a revisit doesn't re-apply it
 *
 * The whole ClipStudio is mounted so all three mechanisms are exercised
 * together — the handoff spans three components wired only through the
 * shared store, so a unit test of any one piece would miss the seam.
 *
 * All data-fetching deps are mocked inert so the test is offline +
 * deterministic; the one meaningful fixture is a single `done` download
 * job returned by listJobs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Hoisted so the vi.mock factory (itself hoisted to the top of the file)
// can reference it without a "cannot access before initialization" error.
const DONE_JOB = vi.hoisted(() => ({
  id: 'dl-1',
  url: 'https://youtube.com/watch?v=abc',
  platform: 'youtube',
  status: 'done' as const,
  progress: 100,
  speed_str: '',
  eta_str: '',
  output_path: 'D:\\Videos\\clip.mp4',
  output_dir: 'D:\\Videos',
  filename: 'clip.mp4',
  title: 'My Downloaded Clip',
  duration: 120,
  height: 1080,
  fps: 30,
  filesize: 10 * 1024 * 1024,
  error_msg: '',
  created_at: '2026-06-26T00:00:00Z',
  updated_at: '2026-06-26T00:00:00Z',
}))

// Keep the real label/color/format helpers; only stub the network calls.
vi.mock('../src/api/platformDownloader', async () => {
  const actual = await vi.importActual<typeof import('../src/api/platformDownloader')>(
    '../src/api/platformDownloader',
  )
  return {
    ...actual,
    listJobs: vi.fn().mockResolvedValue([DONE_JOB]),
    getVideoInfo: vi.fn().mockResolvedValue({ title: '', platform: 'youtube', duration: 0, thumbnail: '', formats: [] }),
    startDownload: vi.fn(),
    cancelJob: vi.fn().mockResolvedValue(undefined),
  }
})

vi.mock('../src/api/outputDir', () => ({
  getDefaultOutputDir: vi.fn().mockResolvedValue({ is_configured: false, path: '' }),
  putDefaultOutputDir: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../src/api/renderDefaults', () => ({
  getRenderDefaults: vi.fn().mockResolvedValue({ is_configured: false, render_defaults: {} }),
}))

vi.mock('../src/api/jobs', async () => {
  const actual = await vi.importActual<typeof import('../src/api/jobs')>('../src/api/jobs')
  return {
    ...actual,
    getJobHistory: vi.fn().mockResolvedValue({ items: [], has_more: false }),
  }
})

vi.mock('../src/api/system', () => ({
  getSystemResources: vi.fn().mockResolvedValue({}),
}))

import { ClipStudio } from '../src/features/clip-studio/ClipStudio'
import { useUIStore } from '../src/stores/uiStore'

beforeEach(() => {
  // Clean handoff state + a cookie-status fetch stub (DownloadTab probes
  // it on mount inside a try/catch — stubbed so it resolves quietly).
  useUIStore.setState({ sendToRenderSourcePath: null })
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ present: false }),
  }) as unknown as typeof fetch
})

function activeTabLabel(container: HTMLElement): string | undefined {
  return container.querySelector('.cs-nav-tab.active')?.textContent ?? undefined
}

describe('Pha 1.1 — Download→Render handoff', () => {
  it('sends a finished download to the Render tab with the source pre-filled', async () => {
    const user = userEvent.setup()
    const { container } = render(<ClipStudio />)

    // Default landing tab is Render.
    expect(activeTabLabel(container)).toBe('Render')

    // Navigate to Download so the finished-job row becomes visible.
    await user.click(screen.getByRole('button', { name: 'Download' }))
    expect(activeTabLabel(container)).toBe('Download')

    // The "→ Render" handoff button appears once listJobs resolves.
    const handoffBtn = await screen.findByTitle(/Tạo clip từ video này/i)

    // Pre-condition: nothing staged yet.
    expect(useUIStore.getState().sendToRenderSourcePath).toBeNull()

    await user.click(handoffBtn)

    // ClipStudio flips back to the Render tab…
    await waitFor(() => expect(activeTabLabel(container)).toBe('Render'))

    // …RenderWorkflow consumes the seed and clears it…
    await waitFor(() => expect(useUIStore.getState().sendToRenderSourcePath).toBeNull())

    // …and the downloaded file is pre-filled as the render source.
    // Scope by the full-path title (unique to RenderWorkflow's source
    // list) — "clip.mp4" alone also matches the still-mounted download row.
    const sourceItem = await screen.findByTitle('D:\\Videos\\clip.mp4')
    expect(sourceItem).toHaveTextContent('clip.mp4')
  })
})
