/**
 * settings-creator-context-form.test.tsx — Audit ST-13 / TEST09 closure (Batch 10D).
 *
 * Settings → Creator Context form CRUD smoke. The form is the only UI
 * write-path into ``creator_prefs`` in the DB. AI Director reads this
 * blob on every render, so a silent regression here biases every future
 * clip selection.
 *
 * Pins:
 *   - Initial mount calls getCreatorContext and hydrates inputs from the response.
 *   - Editing fields + clicking Save calls putCreatorContext with the new payload,
 *     including content_pillars parsed from the CSV input.
 *   - Successful save surfaces the 'Đã lưu' status message.
 *
 * The system-info section also fetched on mount is mocked to a 404-shaped
 * empty response so the section just shows nothing (no error spam).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock both API modules BEFORE component import.
vi.mock('../src/api/creatorContext', async () => {
  const actual = await vi.importActual<typeof import('../src/api/creatorContext')>(
    '../src/api/creatorContext'
  )
  return {
    ...actual,
    getCreatorContext: vi.fn(),
    putCreatorContext: vi.fn(),
  }
})

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/api/client')>(
    '../src/api/client'
  )
  return {
    ...actual,
    // SettingsScreen also calls /api/render/system-info on mount via apiFetch.
    // Throw a quiet rejection so the section silently fails without
    // dirtying assertions; getCreatorContext path is the one under test.
    apiFetch: vi.fn().mockRejectedValue(new Error('system-info unavailable')),
  }
})

import { SettingsScreen } from '../src/features/settings/SettingsScreen'
import * as CC from '../src/api/creatorContext'
import { useUIStore } from '../src/stores/uiStore'

const mockedGet = CC.getCreatorContext as unknown as ReturnType<typeof vi.fn>
const mockedPut = CC.putCreatorContext as unknown as ReturnType<typeof vi.fn>


describe('SettingsScreen — Creator Context form CRUD', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedPut.mockReset()
    // These assertions pin the Vietnamese labels; default lang is 'en'.
    useUIStore.setState({ lang: 'vi' })
  })

  it('hydrates inputs from getCreatorContext on mount', async () => {
    mockedGet.mockResolvedValue({
      is_configured: true,
      creator_context: {
        creator_id: 'k1',
        channel_name: 'Test Channel',
        brand_voice: 'viral',
        target_audience: 'us',
        content_pillars: ['recipe', 'tutorial'],
        market: 'us',
        language: 'en',
        notes: 'Casual tone',
      },
    })

    render(<SettingsScreen />)

    // Wait for the form to load (loading state → form). Use the testid
    // anchors declared on the inputs.
    const channelInput = await screen.findByTestId('cc-channel-name') as HTMLInputElement
    expect(channelInput.value).toBe('Test Channel')

    expect((screen.getByTestId('cc-brand-voice') as HTMLInputElement).value).toBe('viral')
    expect((screen.getByTestId('cc-target-audience') as HTMLInputElement).value).toBe('us')
    // Content pillars are rendered joined CSV per pillarsToCsv() helper.
    expect((screen.getByTestId('cc-content-pillars') as HTMLInputElement).value).toBe('recipe, tutorial')
    expect((screen.getByTestId('cc-market') as HTMLInputElement).value).toBe('us')
    expect((screen.getByTestId('cc-language') as HTMLInputElement).value).toBe('en')
    expect((screen.getByTestId('cc-notes') as HTMLTextAreaElement).value).toBe('Casual tone')

    // "ĐÃ CẤU HÌNH" badge shown because is_configured=true.
    expect(screen.getByText('ĐÃ CẤU HÌNH')).toBeInTheDocument()
  })

  it('saves edited fields and surfaces Đã lưu status', async () => {
    mockedGet.mockResolvedValue({
      is_configured: false,
      creator_context: {
        creator_id: '', channel_name: '', brand_voice: '', target_audience: '',
        content_pillars: [], market: '', language: '', notes: '',
      },
    })
    mockedPut.mockResolvedValue({
      is_configured: true,
      creator_context: {
        creator_id: 'k1',
        channel_name: 'New Channel',
        brand_voice: 'educational',
        target_audience: 'vn',
        content_pillars: ['cooking', 'travel', 'review'],
        market: 'vn',
        language: 'vi',
        notes: 'friendly host',
      },
    })

    const user = userEvent.setup()
    render(<SettingsScreen />)

    const channelInput = await screen.findByTestId('cc-channel-name') as HTMLInputElement
    await user.type(channelInput, 'New Channel')
    await user.type(screen.getByTestId('cc-brand-voice'), 'educational')
    await user.type(screen.getByTestId('cc-content-pillars'), 'cooking, travel, review')
    await user.type(screen.getByTestId('cc-language'), 'vi')

    await user.click(screen.getByTestId('cc-save'))

    expect(mockedPut).toHaveBeenCalledTimes(1)
    const sentBody = mockedPut.mock.calls[0][0]
    expect(sentBody.channel_name).toBe('New Channel')
    expect(sentBody.brand_voice).toBe('educational')
    expect(sentBody.language).toBe('vi')
    // CSV → array parsed via pillarsFromCsv (trim + filter empty).
    expect(sentBody.content_pillars).toEqual(['cooking', 'travel', 'review'])

    await waitFor(() => expect(screen.getByTestId('cc-status')).toHaveTextContent('Đã lưu'))
  })

  it('shows Lưu thất bại when putCreatorContext rejects', async () => {
    mockedGet.mockResolvedValue({
      is_configured: false,
      creator_context: {
        creator_id: '', channel_name: '', brand_voice: '', target_audience: '',
        content_pillars: [], market: '', language: '', notes: '',
      },
    })
    mockedPut.mockRejectedValue(new Error('500 Server Error'))

    const user = userEvent.setup()
    render(<SettingsScreen />)

    const channelInput = await screen.findByTestId('cc-channel-name') as HTMLInputElement
    await user.type(channelInput, 'x')
    await user.click(screen.getByTestId('cc-save'))

    await waitFor(() => expect(screen.getByTestId('cc-status')).toHaveTextContent('Lưu thất bại'))
  })
})
