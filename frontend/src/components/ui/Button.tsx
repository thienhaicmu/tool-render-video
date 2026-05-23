/**
 * Button — shared UI component.
 * Variants: primary | secondary | ghost | danger
 * Sizes: sm | md | lg
 */
import React from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  children: React.ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled,
  children,
  style,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading

  return (
    <button
      disabled={isDisabled}
      aria-busy={loading}
      style={{
        ...BASE_STYLE,
        ...VARIANT_STYLES[variant],
        ...SIZE_STYLES[size],
        ...(isDisabled ? DISABLED_STYLE : {}),
        ...style,
      }}
      {...rest}
    >
      {loading && <span style={spinnerStyle} aria-hidden="true">⟳</span>}
      {children}
    </button>
  )
}

const BASE_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '6px',
  fontFamily: 'var(--font-ui)',
  fontWeight: 'var(--weight-medium)' as unknown as number,
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  transition: `background-color var(--duration-fast) var(--ease-in-out), color var(--duration-fast) var(--ease-in-out), opacity var(--duration-fast) var(--ease-in-out), box-shadow var(--duration-fast) var(--ease-in-out)`,
  border: '1px solid transparent',
  outline: 'none',
  userSelect: 'none',
  whiteSpace: 'nowrap',
}

const VARIANT_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    backgroundColor: 'var(--accent-primary)',
    color: '#FFFFFF',
    borderColor: 'var(--accent-primary)',
  },
  secondary: {
    backgroundColor: 'var(--surface-card)',
    color: 'var(--text-primary)',
    borderColor: 'var(--border-default)',
  },
  ghost: {
    backgroundColor: 'transparent',
    color: 'var(--accent-primary)',
    borderColor: 'var(--accent-subtle)',
  },
  danger: {
    backgroundColor: 'color-mix(in srgb, var(--status-error) 15%, transparent)',
    color: 'var(--status-error)',
    borderColor: 'color-mix(in srgb, var(--status-error) 40%, transparent)',
  },
}

const SIZE_STYLES: Record<ButtonSize, React.CSSProperties> = {
  sm: {
    fontSize: 'var(--text-sm)',
    padding: '0 10px',
    height: '28px',
  },
  md: {
    fontSize: 'var(--text-base)',
    padding: '0 14px',
    height: '32px',
  },
  lg: {
    fontSize: 'var(--text-md)',
    padding: '0 20px',
    height: '40px',
  },
}

const DISABLED_STYLE: React.CSSProperties = {
  opacity: 0.45,
  cursor: 'not-allowed',
  pointerEvents: 'none',
}

const spinnerStyle: React.CSSProperties = {
  display: 'inline-block',
  animation: 'spin 1s linear infinite',
}
