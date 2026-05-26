/**
 * FrameSection — motion_aware_crop, reframe_mode, frame_scale_x, frame_scale_y.
 */
import React from 'react'
import { FormField } from './FormField'
import { REFRAME_MODES } from '../../../lib/constants'
import type { RenderFormState } from '../RenderForm.types'

interface FrameSectionProps {
  state: RenderFormState
  onChange: (field: keyof RenderFormState, value: string | boolean | number) => void
}

export function FrameSection({ state, onChange }: FrameSectionProps) {
  return (
    <section style={sectionStyle}>
      <h3 style={headingStyle}>Frame & Motion</h3>

      <FormField
        label="Motion Tracking"
        hint="AI-powered subject tracking that keeps the focal point centered in the output frame"
      >
        <label style={toggleLabelStyle}>
          <input
            type="checkbox"
            checked={state.motion_aware_crop}
            onChange={(e) => onChange('motion_aware_crop', e.target.checked)}
            style={{ marginRight: '8px' }}
            data-testid="motion-aware-crop-toggle"
          />
          <span>Enable AI motion-aware crop</span>
        </label>
      </FormField>

      {state.motion_aware_crop && (
        <FormField
          label="Tracking Mode"
          hint="Subject tracking follows faces and bodies. Motion tracking uses pixel-difference (legacy)."
        >
          <div style={cardGroupStyle}>
            {REFRAME_MODES.map((mode) => (
              <button
                key={mode.value}
                type="button"
                style={{
                  ...cardStyle,
                  ...(state.reframe_mode === mode.value ? cardActiveStyle : {}),
                }}
                onClick={() => onChange('reframe_mode', mode.value)}
                data-testid={`reframe-mode-${mode.value}`}
              >
                <span style={cardLabelStyle}>{mode.label}</span>
                <span style={cardDescStyle}>{mode.description}</span>
              </button>
            ))}
          </div>
        </FormField>
      )}

      <FormField
        label="Frame Scale"
        hint="Horizontal and vertical zoom applied before crop. 100 = no zoom."
      >
        <div style={rowStyle}>
          <div style={scaleFieldStyle}>
            <span style={scaleLabelStyle}>X (horizontal)</span>
            <div style={scaleInputRowStyle}>
              <input
                type="range"
                min={80}
                max={130}
                step={1}
                value={state.frame_scale_x}
                onChange={(e) => onChange('frame_scale_x', parseInt(e.target.value, 10))}
                style={rangeStyle}
                aria-label="Frame Scale X"
                data-testid="frame-scale-x-range"
              />
              <span style={scaleValueStyle}>{state.frame_scale_x}%</span>
            </div>
          </div>

          <div style={scaleFieldStyle}>
            <span style={scaleLabelStyle}>Y (vertical)</span>
            <div style={scaleInputRowStyle}>
              <input
                type="range"
                min={80}
                max={130}
                step={1}
                value={state.frame_scale_y}
                onChange={(e) => onChange('frame_scale_y', parseInt(e.target.value, 10))}
                style={rangeStyle}
                aria-label="Frame Scale Y"
                data-testid="frame-scale-y-range"
              />
              <span style={scaleValueStyle}>{state.frame_scale_y}%</span>
            </div>
          </div>
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

const toggleLabelStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-primary)',
  cursor: 'pointer',
}

const cardGroupStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 'var(--space-2)',
}

const cardStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
  padding: '10px 12px',
  background: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  textAlign: 'left',
  transition: 'border-color 0.15s',
  fontFamily: 'var(--font-family-base)',
}

const cardActiveStyle: React.CSSProperties = {
  borderColor: 'var(--color-accent)',
  background: 'color-mix(in srgb, var(--color-accent) 8%, var(--color-bg-elevated))',
}

const cardLabelStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-sm)',
  fontWeight: 'var(--font-weight-semibold)' as unknown as number,
  color: 'var(--color-text-primary)',
}

const cardDescStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  lineHeight: '1.4',
}

const rowStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-3)',
}

const scaleFieldStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '4px',
}

const scaleLabelStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
}

const scaleInputRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
}

const rangeStyle: React.CSSProperties = {
  flex: 1,
  accentColor: 'var(--color-accent)',
}

const scaleValueStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-primary)',
  fontVariantNumeric: 'tabular-nums',
  minWidth: '42px',
  textAlign: 'right',
}
