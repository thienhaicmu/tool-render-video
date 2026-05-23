/**
 * Badge — status indicator used for quality scores, job states, etc.
 * Variants: success | warning | error | info | neutral
 */
import React from 'react'

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral'

export interface BadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
  size?: 'sm' | 'md'
  style?: React.CSSProperties
}

export function Badge({ variant = 'neutral', children, size = 'md', style }: BadgeProps) {
  return (
    <span
      style={{
        ...BASE_STYLE,
        ...VARIANT_STYLES[variant],
        ...SIZE_STYLES[size],
        ...style,
      }}
    >
      {children}
    </span>
  )
}

const BASE_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontFamily: 'var(--font-family-base)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  borderRadius: 'var(--radius-full)',
  whiteSpace: 'nowrap',
}

const VARIANT_STYLES: Record<BadgeVariant, React.CSSProperties> = {
  success: {
    color: 'var(--color-success)',
    backgroundColor: 'var(--color-success-muted)',
  },
  warning: {
    color: 'var(--color-warning)',
    backgroundColor: 'var(--color-warning-muted)',
  },
  error: {
    color: 'var(--color-error)',
    backgroundColor: 'var(--color-error-muted)',
  },
  info: {
    color: 'var(--color-info)',
    backgroundColor: 'var(--color-info-muted)',
  },
  neutral: {
    color: 'var(--color-text-secondary)',
    backgroundColor: 'var(--color-bg-elevated)',
  },
}

const SIZE_STYLES: Record<'sm' | 'md', React.CSSProperties> = {
  sm: {
    fontSize: 'var(--font-size-xs)',
    padding: '2px 6px',
    lineHeight: 1.4,
  },
  md: {
    fontSize: 'var(--font-size-sm)',
    padding: '3px 8px',
    lineHeight: 1.5,
  },
}
