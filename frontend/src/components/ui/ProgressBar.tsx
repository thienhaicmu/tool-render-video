/**
 * ProgressBar — animated fill bar 0–100.
 * Variants: default | success | error
 */
import React from 'react'

export type ProgressBarVariant = 'default' | 'success' | 'error'

export interface ProgressBarProps {
  value: number
  variant?: ProgressBarVariant
  showLabel?: boolean
  label?: string
  style?: React.CSSProperties
}

export function ProgressBar({
  value,
  variant = 'default',
  showLabel = false,
  label,
  style,
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value))
  const displayLabel = label ?? `${Math.round(clamped)}%`

  return (
    <div style={{ ...containerStyle, ...style }} role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
      <div
        style={{
          ...trackStyle,
        }}
      >
        <div
          style={{
            ...fillStyle,
            width: `${clamped}%`,
            backgroundColor: VARIANT_COLORS[variant],
          }}
        />
      </div>
      {showLabel && (
        <span style={labelStyle}>{displayLabel}</span>
      )}
    </div>
  )
}

const VARIANT_COLORS: Record<ProgressBarVariant, string> = {
  default: 'var(--color-accent)',
  success: 'var(--color-success)',
  error:   'var(--color-error)',
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
  width: '100%',
}

const trackStyle: React.CSSProperties = {
  flex: 1,
  height: '6px',
  backgroundColor: 'var(--color-bg-elevated)',
  borderRadius: 'var(--radius-full)',
  overflow: 'hidden',
}

const fillStyle: React.CSSProperties = {
  height: '100%',
  borderRadius: 'var(--radius-full)',
  transition: `width var(--duration-normal) var(--ease-default)`,
}

const labelStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  flexShrink: 0,
  minWidth: '36px',
  textAlign: 'right',
}
