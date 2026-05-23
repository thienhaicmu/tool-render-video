/**
 * OutputSection — output_dir and max_export_parts.
 */
import React from 'react'
import { FormField } from './FormField'
import type { RenderFormState, RenderFormErrors } from '../RenderForm.types'

interface OutputSectionProps {
  state: RenderFormState
  errors: RenderFormErrors
  onChange: (field: keyof RenderFormState, value: string | boolean | number) => void
}

export function OutputSection({ state, errors, onChange }: OutputSectionProps) {
  return (
    <section style={sectionStyle}>
      <h3 style={headingStyle}>Output</h3>

      <FormField
        label="Output Directory"
        error={errors.output_dir}
        hint="Folder where rendered parts will be saved"
      >
        <input
          type="text"
          value={state.output_dir}
          onChange={(e) => onChange('output_dir', e.target.value)}
          placeholder="D:\renders\my-project"
          style={{
            ...inputStyle,
            borderColor: errors.output_dir ? 'var(--color-error)' : 'var(--color-border)',
          }}
          aria-label="Output Directory"
          data-testid="output-dir-input"
        />
      </FormField>

      <FormField
        label="Max Export Parts"
        error={errors.max_export_parts}
        hint="Maximum number of clips to export from this video"
      >
        <input
          type="number"
          value={state.max_export_parts}
          onChange={(e) => onChange('max_export_parts', parseInt(e.target.value, 10) || 1)}
          min={1}
          max={50}
          style={{
            ...inputStyle,
            width: '120px',
            borderColor: errors.max_export_parts ? 'var(--color-error)' : 'var(--color-border)',
          }}
          aria-label="Max Export Parts"
          data-testid="max-export-parts-input"
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

const inputStyle: React.CSSProperties = {
  padding: '8px 12px',
  fontSize: 'var(--font-size-base)',
  color: 'var(--color-text-primary)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid',
  borderRadius: 'var(--radius-md)',
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'var(--font-family-base)',
}
