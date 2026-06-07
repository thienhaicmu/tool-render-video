/**
 * settings-data-retention-form.test.tsx — Batch 10R (MT-7 UI).
 *
 * Settings → Data Retention form behavior. Backend wired in Batch 10A
 * as ST-12; this is the FE toggle that completes MT-7 in the audit
 * roadmap.
 *
 * Pins:
 *   - Initial mount calls getDataRetention and hydrates the number input.
 *   - Save calls putDataRetention with the entered value; success
 *     surfaces a status message that distinguishes the 0 (disabled)
 *     case from N > 0 days.
 *   - The input clamps to [0, 365] in the change handler — out-of-range
 *     values are coerced before reaching the API.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('../src/api/dataRetention', async () => {
  const actual = await vi.importActual<typeof import('../src/api/dataRetention')>(
    '../src/api/dataRetention'
  )
  return {
    ...actual,
    getDataRetention: vi.fn(),
    putDataRetention: vi.fn(),
  }
})

// CreatorContext + system-info API are also called by SettingsScreen
// on mount. Stub them out so the test isolates the data-retention
// section.
vi.mock('../src/api/creatorContext', async () => {
  const actual = await vi.importActual<typeof import('../src/api/creatorContext')>(
    '../src/api/creatorContext'
  )
  return {
    ...actual,
    getCreatorContext: vi.fn().mockResolvedValue({
      is_configured: false,
      creator_context: actual.BLANK_CREATOR_CONTEXT,
    }),
    putCreatorContext: vi.fn(),
  }
})

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>(
    '../src/api/client'
  )
  return {
    ...actual,
    apiFetch: vi.fn().mockRejectedValue(new Error('system-info unavailable')),
  }
})

import { SettingsScreen } from '../src/features/settings/SettingsScreen'
import * as DR from '../src/api/dataRetention'

const mockedGet = DR.getDataRetention as unknown as ReturnType<typeof vi.fn>
const mockedPut = DR.putDataRetention as unknown as ReturnType<typeof vi.fn>


describe('SettingsScreen — Data Retention form', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPut.mockReset()
  })

  it('hydrates from getDataRetention on mount', async () => {
    mockedGet.mockResolvedValue({
      is_configured: true,
      data_retention: { job_retention_days: 30 },
    })

    render(<SettingsScreen />)

    const input = await screen.findByTestId('dr-job-retention-days') as HTMLInputElement
    await waitFor(() => expect(input.value).toBe('30'))

    // "AUTO-PRUNE 30D" badge shown when configured + non-zero.
    expect(screen.getByText(/AUTO-PRUNE 30D/i)).toBeInTheDocument()
  })

  it('saves the edited value and surfaces the non-zero status message', async () => {
    mockedGet.mockResolvedValue({
      is_configured: false,
      data_retention: { job_retention_days: 0 },
    })
    mockedPut.mockResolvedValue({
      is_configured: true,
      data_retention: { job_retention_days: 60 },
    })

    const user = userEvent.setup()
    render(<SettingsScreen />)

    const input = await screen.findByTestId('dr-job-retention-days') as HTMLInputElement
    // Clear and type 60.
    await user.clear(input)
    await user.type(input, '60')

    await user.click(screen.getByTestId('dr-save'))

    expect(mockedPut).toHaveBeenCalledTimes(1)
    expect(mockedPut).toHaveBeenCalledWith({ job_retention_days: 60 })

    await waitFor(() =>
      expect(screen.getByTestId('dr-status')).toHaveTextContent('60 ngày'),
    )
  })

  it('shows the disabled status message when saving 0', async () => {
    mockedGet.mockResolvedValue({
      is_configured: true,
      data_retention: { job_retention_days: 14 },
    })
    mockedPut.mockResolvedValue({
      is_configured: true,
      data_retention: { job_retention_days: 0 },
    })

    const user = userEvent.setup()
    render(<SettingsScreen />)

    const input = await screen.findByTestId('dr-job-retention-days') as HTMLInputElement
    await user.clear(input)
    await user.type(input, '0')

    await user.click(screen.getByTestId('dr-save'))

    await waitFor(() =>
      expect(screen.getByTestId('dr-status')).toHaveTextContent(/Tắt auto-prune/i),
    )
  })

  it('shows TẮT badge when saved value is 0 (configured-as-disabled)', async () => {
    mockedGet.mockResolvedValue({
      is_configured: true,
      data_retention: { job_retention_days: 0 },
    })

    render(<SettingsScreen />)

    await screen.findByTestId('dr-job-retention-days')
    // is_configured=True but days=0 → badge shows TẮT (disabled), not
    // AUTO-PRUNE. There may be other "TẮT" text in the doc — scope to
    // the data-retention section.
    const section = screen.getByTestId('data-retention-section')
    expect(section.textContent).toMatch(/Tắt/i)
    expect(section.textContent).not.toMatch(/AUTO-PRUNE/i)
  })

  it('clamps out-of-range typed input to [0, 365]', async () => {
    mockedGet.mockResolvedValue({
      is_configured: false,
      data_retention: { job_retention_days: 0 },
    })

    const user = userEvent.setup()
    render(<SettingsScreen />)

    const input = await screen.findByTestId('dr-job-retention-days') as HTMLInputElement
    await user.clear(input)
    await user.type(input, '999')
    // Clamped client-side before save.
    expect(input.value).toBe('365')
  })
})
