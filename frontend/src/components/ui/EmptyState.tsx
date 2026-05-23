/**
 * EmptyState — Placeholder for sections with no content.
 * Source: docs/design/components.md component #10
 */
import React from 'react'

export type EmptyStateVariant = 'no-jobs' | 'no-clips' | 'source-needed' | 'ai-unavailable'

export interface EmptyStateProps {
  variant?: EmptyStateVariant
  icon?: React.ReactNode
  primary?: string
  secondary?: string
  cta?: React.ReactNode
}

interface VariantDefaults {
  icon: string
  primary: string
  secondary: string
}

const VARIANT_DEFAULTS: Record<EmptyStateVariant, VariantDefaults> = {
  'no-jobs': {
    icon: '○',
    primary: 'No jobs yet',
    secondary: 'Start a render to see progress',
  },
  'no-clips': {
    icon: '⊟',
    primary: 'No clips selected',
    secondary: 'Open a source to begin',
  },
  'source-needed': {
    icon: '▦',
    primary: 'No source loaded',
    secondary: 'Add a URL or local file',
  },
  'ai-unavailable': {
    icon: '⚡',
    primary: 'AI unavailable',
    secondary: 'Check system settings',
  },
}

export function EmptyState({ variant, icon, primary, secondary, cta }: EmptyStateProps) {
  const defaults = variant ? VARIANT_DEFAULTS[variant] : null

  const resolvedIcon = icon ?? (defaults ? defaults.icon : null)
  const resolvedPrimary = primary ?? defaults?.primary
  const resolvedSecondary = secondary ?? defaults?.secondary

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-4)',
        maxWidth: '320px',
        margin: '0 auto',
        textAlign: 'center',
      }}
    >
      {resolvedIcon !== null && (
        <span
          style={{
            fontSize: '32px',
            color: 'var(--text-tertiary)',
            lineHeight: 1,
          }}
          aria-hidden="true"
        >
          {resolvedIcon}
        </span>
      )}

      {resolvedPrimary && (
        <span
          style={{
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--weight-semibold)' as unknown as number,
            color: 'var(--text-secondary)',
          }}
        >
          {resolvedPrimary}
        </span>
      )}

      {resolvedSecondary && (
        <span
          style={{
            fontSize: 'var(--text-sm)',
            color: 'var(--text-tertiary)',
          }}
        >
          {resolvedSecondary}
        </span>
      )}

      {cta && <div>{cta}</div>}
    </div>
  )
}
