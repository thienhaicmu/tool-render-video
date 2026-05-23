/**
 * SourceSection — source_mode toggle, youtube_url / source_video_path input.
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

      <FormField label="Source Mode">
        <div style={toggleGroupStyle}>
          <button
            type="button"
            style={{
              ...toggleBtnStyle,
              backgroundColor:
                state.source_mode === 'youtube'
                  ? 'var(--color-accent)'
                  : 'var(--color-bg-elevated)',
              color:
                state.source_mode === 'youtube'
                  ? '#FFFFFF'
                  : 'var(--color-text-secondary)',
              borderColor:
                state.source_mode === 'youtube'
                  ? 'var(--color-accent)'
                  : 'var(--color-border)',
            }}
            onClick={() => onChange('source_mode', 'youtube')}
          >
            YouTube URL
          </button>
          <button
            type="button"
            style={{
              ...toggleBtnStyle,
              backgroundColor:
                state.source_mode === 'local'
                  ? 'var(--color-accent)'
                  : 'var(--color-bg-elevated)',
              color:
                state.source_mode === 'local'
                  ? '#FFFFFF'
                  : 'var(--color-text-secondary)',
              borderColor:
                state.source_mode === 'local'
                  ? 'var(--color-accent)'
                  : 'var(--color-border)',
            }}
            onClick={() => onChange('source_mode', 'local')}
          >
            Local File
          </button>
        </div>
      </FormField>

      {state.source_mode === 'youtube' && (
        <FormField
          label="YouTube URL"
          error={errors.youtube_url}
          hint="Paste a YouTube video or Shorts URL"
        >
          <input
            type="text"
            value={state.youtube_url}
            onChange={(e) => onChange('youtube_url', e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            style={{
              ...inputStyle,
              borderColor: errors.youtube_url ? 'var(--color-error)' : 'var(--color-border)',
            }}
            aria-label="YouTube URL"
            data-testid="youtube-url-input"
          />
        </FormField>
      )}

      {state.source_mode === 'local' && (
        <FormField
          label="Source Video Path"
          error={errors.source_video_path}
          hint="Absolute path to the source video file"
        >
          <input
            type="text"
            value={state.source_video_path}
            onChange={(e) => onChange('source_video_path', e.target.value)}
            placeholder="C:\Videos\source.mp4"
            style={{
              ...inputStyle,
              borderColor: errors.source_video_path ? 'var(--color-error)' : 'var(--color-border)',
            }}
            aria-label="Source Video Path"
            data-testid="source-video-path-input"
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

const toggleGroupStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2)',
}

const toggleBtnStyle: React.CSSProperties = {
  padding: '6px 16px',
  fontSize: 'var(--font-size-sm)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  border: '1px solid',
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  transition: `background-color var(--duration-fast), color var(--duration-fast)`,
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
