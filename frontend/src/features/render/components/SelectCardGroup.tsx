/**
 * SelectCardGroup — a grid of clickable option cards.
 * Selected card gets an accent border highlight.
 */
import React from 'react'

export interface SelectCardOption {
  value: string
  label: string
  description?: string
}

interface SelectCardGroupProps {
  options: SelectCardOption[]
  value: string
  onChange: (value: string) => void
  columns?: number
}

export function SelectCardGroup({
  options,
  value,
  onChange,
  columns = 2,
}: SelectCardGroupProps) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: 'var(--space-2)',
      }}
    >
      {options.map((opt) => {
        const isSelected = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            style={{
              ...cardStyle,
              borderColor: isSelected ? 'var(--color-accent)' : 'var(--color-border)',
              backgroundColor: isSelected
                ? 'var(--color-accent-muted, rgba(108, 99, 255, 0.12))'
                : 'var(--color-bg-elevated)',
              boxShadow: isSelected ? '0 0 0 1px var(--color-accent)' : 'none',
            }}
          >
            <span style={labelStyle}>{opt.label}</span>
            {opt.description && (
              <span style={descStyle}>{opt.description}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: '2px',
  padding: 'var(--space-3) var(--space-3)',
  border: '1px solid',
  borderRadius: 'var(--radius-md)',
  cursor: 'pointer',
  transition: `border-color var(--duration-fast), background-color var(--duration-fast), box-shadow var(--duration-fast)`,
  textAlign: 'left',
  width: '100%',
}

const labelStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-sm)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  color: 'var(--color-text-primary)',
  lineHeight: 'var(--line-height-tight)',
}

const descStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  lineHeight: 'var(--line-height-base)',
}
