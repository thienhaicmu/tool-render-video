/**
 * trim-controls.test.tsx — rendering and behaviour tests for TrimControls.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TrimControls } from '../src/features/editor/TrimControls'

function renderTrimControls(overrides: Partial<Parameters<typeof TrimControls>[0]> = {}) {
  const defaults = {
    durationSec: 60,
    trimStartSec: 0,
    trimEndSec: 30,
    isDirty: false,
    onTrimChange: vi.fn(),
    onReset: vi.fn(),
    ...overrides,
  }
  const utils = render(<TrimControls {...defaults} />)
  return { ...utils, ...defaults }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

describe('TrimControls — rendering', () => {
  it('renders start time input', () => {
    renderTrimControls()
    expect(screen.getByTestId('trim-start-input')).toBeTruthy()
  })

  it('renders end time input', () => {
    renderTrimControls()
    expect(screen.getByTestId('trim-end-input')).toBeTruthy()
  })

  it('shows trim duration display', () => {
    renderTrimControls({ trimStartSec: 0, trimEndSec: 30 })
    // 30 seconds = 0:30
    expect(screen.getByTestId('trim-duration-display').textContent).toBe('0:30')
  })

  it('shows duration with various values', () => {
    renderTrimControls({ trimStartSec: 10, trimEndSec: 75 })
    // 65 seconds = 1:05
    expect(screen.getByTestId('trim-duration-display').textContent).toBe('1:05')
  })
})

// ── Reset button ──────────────────────────────────────────────────────────────

describe('TrimControls — reset button', () => {
  it('reset button is disabled when isDirty=false', () => {
    renderTrimControls({ isDirty: false })
    const btn = screen.getByTestId('trim-reset-btn')
    expect(btn).toBeTruthy()
    // Button component uses pointer-events: none when disabled
    expect((btn as HTMLButtonElement).disabled).toBe(true)
  })

  it('reset button is enabled when isDirty=true', () => {
    renderTrimControls({ isDirty: true })
    const btn = screen.getByTestId('trim-reset-btn') as HTMLButtonElement
    expect(btn.disabled).toBe(false)
  })

  it('clicking reset calls onReset', async () => {
    const onReset = vi.fn()
    const user = userEvent.setup()
    renderTrimControls({ isDirty: true, onReset })
    await user.click(screen.getByTestId('trim-reset-btn'))
    expect(onReset).toHaveBeenCalledOnce()
  })
})

// ── Validation ────────────────────────────────────────────────────────────────

describe('TrimControls — validation', () => {
  it('shows validation error when start > end', async () => {
    const user = userEvent.setup()
    renderTrimControls({ trimStartSec: 0, trimEndSec: 10 })

    const startInput = screen.getByTestId('trim-start-input')
    await user.clear(startInput)
    await user.type(startInput, '20')

    // Should show a validation error (start >= end)
    await vi.waitFor(() => {
      expect(screen.queryByTestId('trim-validation-error')).toBeTruthy()
    })
  })

  it('shows validation error when end > duration', async () => {
    const user = userEvent.setup()
    renderTrimControls({ trimStartSec: 0, trimEndSec: 30, durationSec: 60 })

    const endInput = screen.getByTestId('trim-end-input')
    await user.clear(endInput)
    await user.type(endInput, '90')

    await vi.waitFor(() => {
      expect(screen.queryByTestId('trim-validation-error')).toBeTruthy()
    })
  })

  it('shows validation error when start < 0', async () => {
    const user = userEvent.setup()
    // Provide a negative starting value directly via props that render as negative
    renderTrimControls({ trimStartSec: -1, trimEndSec: 30, durationSec: 60 })

    const startInput = screen.getByTestId('trim-start-input')
    await user.clear(startInput)
    await user.type(startInput, '-5')

    await vi.waitFor(() => {
      expect(screen.queryByTestId('trim-validation-error')).toBeTruthy()
    })
  })

  it('shows validation error when trim < 1 second', async () => {
    const user = userEvent.setup()
    renderTrimControls({ trimStartSec: 0, trimEndSec: 30, durationSec: 60 })

    // Set end to 0.5 so trim = 0.5s
    const endInput = screen.getByTestId('trim-end-input')
    await user.clear(endInput)
    await user.type(endInput, '0.5')

    await vi.waitFor(() => {
      expect(screen.queryByTestId('trim-validation-error')).toBeTruthy()
    })
  })

  it('calls onTrimChange with correct values for valid trim', async () => {
    const onTrimChange = vi.fn()
    const user = userEvent.setup()
    renderTrimControls({
      trimStartSec: 0,
      trimEndSec: 30,
      durationSec: 60,
      onTrimChange,
    })

    const endInput = screen.getByTestId('trim-end-input')
    await user.clear(endInput)
    await user.type(endInput, '45')

    // Should have called onTrimChange with valid values
    expect(onTrimChange).toHaveBeenCalled()
    const lastCall = onTrimChange.mock.calls[onTrimChange.mock.calls.length - 1]
    expect(lastCall[0]).toBe(0)    // start
    expect(lastCall[1]).toBe(45)   // end
  })

  it('does not show validation error initially with valid defaults', () => {
    renderTrimControls({ trimStartSec: 0, trimEndSec: 30, durationSec: 60 })
    expect(screen.queryByTestId('trim-validation-error')).toBeNull()
  })
})
