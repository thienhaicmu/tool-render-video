/**
 * FormField — wraps a label, children, optional hint, and optional error message.
 */
import React from 'react'

interface FormFieldProps {
  label: string
  error?: string
  hint?: string
  children: React.ReactNode
}

export function FormField({ label, error, hint, children }: FormFieldProps) {
  return (
    <div style={styles.field}>
      <label style={styles.label}>{label}</label>
      {children}
      {hint && !error && <p style={styles.hint}>{hint}</p>}
      {error && <p style={styles.error}>{error}</p>}
    </div>
  )
}

const styles = {
  field: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '6px',
    marginBottom: 'var(--space-4)',
  },
  label: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 'var(--font-weight-medium)' as unknown as number,
    color: 'var(--color-text-primary)',
    lineHeight: 'var(--line-height-tight)',
  },
  hint: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--color-text-secondary)',
    margin: 0,
  },
  error: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--color-error)',
    margin: 0,
  },
}
