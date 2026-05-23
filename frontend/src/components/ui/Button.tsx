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
  fontFamily: 'var(--font-family-base)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  transition: `background-color var(--duration-fast), color var(--duration-fast), opacity var(--duration-fast), box-shadow var(--duration-fast)`,
  border: '1px solid transparent',
  outline: 'none',
  userSelect: 'none',
  whiteSpace: 'nowrap',
}

const VARIANT_STYLES: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    backgroundColor: 'var(--color-accent)',
    color: '#FFFFFF',
    borderColor: 'var(--color-accent)',
  },
  secondary: {
    backgroundColor: 'var(--color-bg-elevated)',
    color: 'var(--color-text-primary)',
    borderColor: 'var(--color-border)',
  },
  ghost: {
    backgroundColor: 'transparent',
    color: 'var(--color-text-secondary)',
    borderColor: 'transparent',
  },
  danger: {
    backgroundColor: 'var(--color-error)',
    color: '#FFFFFF',
    borderColor: 'var(--color-error)',
  },
}

const SIZE_STYLES: Record<ButtonSize, React.CSSProperties> = {
  sm: {
    fontSize: 'var(--font-size-sm)',
    padding: '4px 10px',
    height: '28px',
  },
  md: {
    fontSize: 'var(--font-size-base)',
    padding: '6px 16px',
    height: '36px',
  },
  lg: {
    fontSize: 'var(--font-size-md)',
    padding: '10px 20px',
    height: '44px',
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
