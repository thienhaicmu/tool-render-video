/**
 * SourceSection — local video file input for render.
 */
import React from 'react'
import { FormField } from './FormField'
import type { RenderFormState, RenderFormErrors } from '../RenderForm.types'

interface SourceSectionProps {
  state: RenderFormState
  errors: RenderFormErrors
  onChange: (field: keyof RenderFormState, value: string | boolean | number) => void
}

export function SourceSection({ state, errors, onChange }: SourceSectionProps) {
  return (
    <section style={sectionStyle}>
      <h3 style={headingStyle}>Source</h3>

      <FormField
        label="Source Video Path"
        error={errors.source_video_path}
        hint="Absolute path to the source video file"
      >
        <div style={filePickerRowStyle}>
          <input
            type="text"
            value={state.source_video_path}
            onChange={(e) => onChange('source_video_path', e.target.value)}
            placeholder="C:\Videos\source.mp4"
            style={{
              ...inputStyle,
              borderColor: errors.source_video_path ? 'var(--color-error)' : 'var(--color-border)',
              flex: 1,
            }}
            aria-label="Source Video Path"
            data-testid="source-video-path-input"
          />
          <button
            type="button"
            style={browseButtonStyle}
            onClick={async () => {
              const picked = await window.electronAPI?.pickVideoFile?.()
              if (picked) onChange('source_video_path', picked)
            }}
          >
            Browse
          </button>
        </div>
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

const filePickerRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2)',
  alignItems: 'center',
}

const browseButtonStyle: React.CSSProperties = {
  padding: '8px 14px',
  fontSize: 'var(--font-size-sm)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  color: 'var(--color-text-secondary)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  flexShrink: 0,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
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
