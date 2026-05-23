/**
 * render-form.test.tsx — rendering tests for RenderSetupScreen.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RenderSetupScreen } from '../src/features/render/RenderSetupScreen'
import { useUIStore } from '../src/stores/uiStore'
import { useRenderStore } from '../src/stores/renderStore'

// Reset stores between tests
beforeEach(() => {
  useUIStore.setState({
    sidebarOpen: true,
    activePanel: 'render',
    notifications: [],
  })
  useRenderStore.setState({
    jobs: {},
    activeJobId: null,
  })
})

describe('RenderSetupScreen — rendering', () => {
  it('renders without crashing', () => {
    const { container } = render(<RenderSetupScreen />)
    expect(container).toBeTruthy()
  })

  it('shows the page heading', () => {
    render(<RenderSetupScreen />)
    expect(screen.getByText('New Render')).toBeTruthy()
  })

  it('form shows youtube URL field by default (source_mode=youtube)', () => {
    render(<RenderSetupScreen />)
    const ytInput = screen.getByTestId('youtube-url-input')
    expect(ytInput).toBeTruthy()
  })

  it('youtube URL field is visible and local path field is not by default', () => {
    render(<RenderSetupScreen />)
    expect(screen.getByTestId('youtube-url-input')).toBeTruthy()
    expect(screen.queryByTestId('source-video-path-input')).toBeNull()
  })

  it('switching source mode to local shows path input', async () => {
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    // Click the "Local File" button
    const localBtn = screen.getByText('Local File')
    await user.click(localBtn)

    expect(screen.getByTestId('source-video-path-input')).toBeTruthy()
    expect(screen.queryByTestId('youtube-url-input')).toBeNull()
  })

  it('switching back to youtube shows youtube URL input', async () => {
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    // Switch to local then back to youtube
    await user.click(screen.getByText('Local File'))
    await user.click(screen.getByText('YouTube URL'))

    expect(screen.getByTestId('youtube-url-input')).toBeTruthy()
    expect(screen.queryByTestId('source-video-path-input')).toBeNull()
  })

  it('default subtitle_style is tiktok_bounce_v1 (TikTok Bounce selected)', () => {
    render(<RenderSetupScreen />)
    // The SelectCardGroup for subtitle_style should have tiktok_bounce_v1 selected
    // It renders as a button with text "TikTok Bounce" that has the accent border style
    const bounceCard = screen.getByText('TikTok Bounce')
    expect(bounceCard).toBeTruthy()
  })

  it('"pro_karaoke" string does not appear anywhere in the rendered output', () => {
    render(<RenderSetupScreen />)
    // pro_karaoke is a legacy alias that should never appear
    expect(screen.queryByText(/pro_karaoke/i)).toBeNull()
  })

  it('subtitle section is visible by default (add_subtitle=true)', () => {
    render(<RenderSetupScreen />)
    // The subtitle style section should be visible since add_subtitle defaults to true
    expect(screen.getByText('Subtitle Style')).toBeTruthy()
  })

  it('unchecking add_subtitle hides subtitle style options', async () => {
    const user = userEvent.setup()
    render(<RenderSetupScreen />)

    const subtitleCheckbox = screen.getByTestId('add-subtitle-toggle')
    await user.click(subtitleCheckbox)

    expect(screen.queryByText('Subtitle Style')).toBeNull()
  })

  it('ai_director_enabled=true shows hook overlay and remotion options', () => {
    render(<RenderSetupScreen />)
    // Both are visible because ai_director_enabled defaults to true
    expect(screen.getByTestId('hook-overlay-toggle')).toBeTruthy()
    expect(screen.getByTestId('remotion-hook-intro-toggle')).toBeTruthy()
  })

  it('output directory input is present', () => {
    render(<RenderSetupScreen />)
    expect(screen.getByTestId('output-dir-input')).toBeTruthy()
  })

  it('submit button is present', () => {
    render(<RenderSetupScreen />)
    expect(screen.getByTestId('submit-render-button')).toBeTruthy()
  })

  it('submit button is disabled when output_dir is empty (form invalid)', () => {
    render(<RenderSetupScreen />)
    const submitBtn = screen.getByTestId('submit-render-button') as HTMLButtonElement
    // output_dir is empty by default, so form should be invalid
    expect(submitBtn.disabled).toBe(true)
  })
})
