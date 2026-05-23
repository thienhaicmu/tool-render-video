/**
 * SubtitleSection — add_subtitle toggle, subtitle_style (shown only when add_subtitle=true).
 */
import React from 'react'
import { FormField } from './FormField'
import { SelectCardGroup } from './SelectCardGroup'
import { SUBTITLE_STYLES } from '../../../lib/constants'
import type { RenderFormState } from '../RenderForm.types'

interface SubtitleSectionProps {
  state: RenderFormState
  onChange: (field: keyof RenderFormState, value: string | boolean | number) => void
}

export function SubtitleSection({ state, onChange }: SubtitleSectionProps) {
  return (
    <section style={sectionStyle}>
      <h3 style={headingStyle}>Subtitles</h3>

      <FormField label="Add Subtitles">
        <label style={toggleLabelStyle}>
          <input
            type="checkbox"
            checked={state.add_subtitle}
            onChange={(e) => onChange('add_subtitle', e.target.checked)}
            style={{ marginRight: '8px' }}
            data-testid="add-subtitle-toggle"
          />
          <span>Auto-generate subtitles for this video</span>
        </label>
      </FormField>

      {state.add_subtitle && (
        <FormField
          label="Subtitle Style"
          hint="Choose a caption style that matches your content"
        >
          <SelectCardGroup
            options={SUBTITLE_STYLES.map((s) => ({
              value: s.value,
              label: s.label,
              description: s.description,
            }))}
            value={state.subtitle_style}
            onChange={(v) => onChange('subtitle_style', v)}
            columns={2}
          />
        </FormField>
      )}
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

const toggleLabelStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-primary)',
  cursor: 'pointer',
}
