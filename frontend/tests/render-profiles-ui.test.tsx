/**
 * render-profiles-ui.test.tsx — Pha 2 UI wiring.
 *
 * Mounts StepConfigure and verifies the Profiles bar:
 *   - renders the 3 built-in chips
 *   - clicking a chip calls applyProfile with that profile's config patch
 *   - "+ Save current" persists the current cfg and the new chip appears
 *
 * Queries are scoped to the PROFILES section because some chip labels
 * (e.g. "TikTok") also appear in the platform segmented control.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { StepConfigure } from '../src/features/clip-studio/render/steps/StepConfigure'
import { useT } from '../src/features/clip-studio/render/i18n'
import type { ConfigState } from '../src/features/clip-studio/render/types'

const t = useT('EN')

const cfg: ConfigState = {
  ratio: 'r916', minSec: 30, maxSec: 60, trimIn: 0, trimOut: 0, style: 'slay_soft_01',
  platform: 'tiktok', aiMarket: 'us',
  multiVariant: false, ctaEnabled: false, ctaType: 'auto',
  hookApplyEnabled: false, hookOverlayEnabled: false, structureBias: null,
  clipLock: [], clipExclude: [],
  subEnabled: true, subStyle: 'opus_pop', subHighlight: true, subFontSize: 0,
  subTranslate: false, subTranslateLang: 'en', subEmphasis: null,
  assetLogoPath: null, assetIntroPath: null, assetOutroPath: null,
  whisperModel: 'auto',
  narrEnabled: false, voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
  voiceSource: 'translated_subtitle', voiceText: '', voiceMixMode: 'replace_original',
  outputDir: 'D:\\out',
  renderProfile: 'balanced', targetDuration: 90, outputCount: 1, videoType: 'auto',
  hookStrength: 'balanced', focusMode: 'auto',
  llmEnabled: true, aiProvider: 'gemini', llmModel: '', llmLanguage: 'auto',
}

function mountConfigure(applyProfile = vi.fn()) {
  render(
    <StepConfigure
      cfg={cfg}
      cfgTab="ai"
      setCfgTab={() => {}}
      setCfgKey={() => {}}
      applyPreset={() => {}}
      applyProfile={applyProfile}
      sources={[{ value: 'C:\\v.mp4' }]}
      prepareResult={null}
      pickOutputDir={() => {}}
      onChangeSource={() => {}}
      t={t}
    />,
  )
  const section = screen.getByText('PROFILES').closest('.cfg-section') as HTMLElement
  return { section, applyProfile }
}

beforeEach(() => {
  localStorage.clear()
})

describe('Pha 2 — Profiles bar UI', () => {
  it('renders the 3 built-in profile chips', () => {
    const { section } = mountConfigure()
    const util = within(section)
    expect(util.getByText('TikTok')).toBeInTheDocument()
    expect(util.getByText('Reels')).toBeInTheDocument()
    expect(util.getByText('Shorts')).toBeInTheDocument()
  })

  it('clicking a built-in chip applies its config patch', async () => {
    const user = userEvent.setup()
    const { section, applyProfile } = mountConfigure()
    await user.click(within(section).getByText('Reels'))
    expect(applyProfile).toHaveBeenCalledTimes(1)
    expect(applyProfile).toHaveBeenCalledWith(
      expect.objectContaining({ platform: 'instagram_reels', ratio: 'r916' }),
    )
  })

  it('"Save current" persists a profile and shows its chip', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'prompt').mockReturnValue('My Vertical')
    const { section } = mountConfigure()

    await user.click(within(section).getByRole('button', { name: '+ Save current' }))

    await waitFor(() => expect(within(section).getByText('My Vertical')).toBeInTheDocument())
    // And it was persisted to localStorage.
    expect(localStorage.getItem('rw_render_profiles_v1')).toContain('My Vertical')
  })
})
