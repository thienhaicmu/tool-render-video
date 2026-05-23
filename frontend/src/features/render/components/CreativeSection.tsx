/**
 * CreativeSection — target_platform, aspect_ratio, effect_preset.
 */
import React from 'react'
import { FormField } from './FormField'
import { SelectCardGroup } from './SelectCardGroup'
import { PLATFORMS, ASPECT_RATIOS, EFFECT_PRESETS } from '../../../lib/constants'
import type { RenderFormState } from '../RenderForm.types'

interface CreativeSectionProps {
  state: RenderFormState
  onChange: (field: keyof RenderFormState, value: string | boolean | number) => void
}

export function CreativeSection({ state, onChange }: CreativeSectionProps) {
  return (
    <section style={sectionStyle}>
      <h3 style={headingStyle}>Creative Direction</h3>

      <FormField label="Target Platform">
        <SelectCardGroup
          options={PLATFORMS.map((p) => ({ value: p.value, label: p.label }))}
          value={state.target_platform}
          onChange={(v) => onChange('target_platform', v)}
          columns={3}
        />
      </FormField>

      <FormField label="Aspect Ratio">
        <SelectCardGroup
          options={ASPECT_RATIOS.map((a) => ({
            value: a.value,
            label: a.label,
            description: a.description,
          }))}
          value={state.aspect_ratio}
          onChange={(v) => onChange('aspect_ratio', v)}
          columns={3}
        />
      </FormField>

      <FormField label="Effect Preset">
        <SelectCardGroup
          options={EFFECT_PRESETS.map((e) => ({
            value: e.value,
            label: e.label,
            description: e.description,
          }))}
          value={state.effect_preset}
          onChange={(v) => onChange('effect_preset', v)}
          columns={2}
        />
      </FormField>
    </section>
  )
}

const sectionStyle: React.CSSProperties = {
  marginBottom: 'var(--space-6)',
}

const headingStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-base)',
  fontWeight: 'var(--font-weight-semibold)' as unknown as number,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-4) 0',
  paddingBottom: 'var(--space-2)',
  borderBottom: '1px solid var(--color-border)',
}
