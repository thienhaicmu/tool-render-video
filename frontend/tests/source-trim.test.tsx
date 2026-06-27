/**
 * source-trim.test.tsx — Pha 5.7.
 *
 * With a prepared source (known duration), StepConfigure shows the TRIM
 * SOURCE control and the In slider writes cfg.trimIn via setCfgKey. Hidden
 * when no source is prepared.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { StepConfigure } from '../src/features/clip-studio/render/steps/StepConfigure'
import { useT } from '../src/features/clip-studio/render/i18n'
import type { ConfigState } from '../src/features/clip-studio/render/types'
import type { PrepareSourceResponse } from '../src/api/render'

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

const prepared = {
  session_id: 'sess-1', title: 'My Video', duration: 120, export_dir: 'D:\\out',
} as unknown as PrepareSourceResponse

function mountConfigure(prepareResult: PrepareSourceResponse | null, setCfgKey = vi.fn()) {
  render(
    <StepConfigure
      cfg={cfg} cfgTab="ai" setCfgTab={() => {}} setCfgKey={setCfgKey}
      applyPreset={() => {}} applyProfile={() => {}}
      sources={[{ value: 'C:\\v.mp4' }]} prepareResult={prepareResult}
      pickOutputDir={() => {}} onChangeSource={() => {}} t={t}
    />,
  )
  return setCfgKey
}

describe('Pha 5.7 — source trim', () => {
  it('shows the trim control and writes trimIn from the In slider', () => {
    const setCfgKey = mountConfigure(prepared)

    const section = screen.getByText('TRIM SOURCE').closest('.cfg-section') as HTMLElement
    expect(section).toBeTruthy()

    // Two range sliders (In, Out) in the trim section.
    const sliders = section.querySelectorAll('input[type="range"]')
    expect(sliders.length).toBe(2)

    fireEvent.change(sliders[0], { target: { value: '10' } })
    expect(setCfgKey).toHaveBeenCalledWith('trimIn', 10)
  })

  it('is hidden when no source is prepared', () => {
    mountConfigure(null)
    expect(screen.queryByText('TRIM SOURCE')).toBeNull()
  })
})
