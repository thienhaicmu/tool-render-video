/**
 * SegRow.tsx — generic segmented control (tab-style single-select row).
 * Mode-agnostic base used for source tabs, enum pickers, etc. Tokens only.
 */
import React from 'react'

export interface SegOption<T extends string> {
  value: T
  label: React.ReactNode
  icon?: string
}

export function SegRow<T extends string>({ options, value, onChange, ariaLabel }: {
  options: SegOption<T>[]
  value: T
  onChange: (v: T) => void
  ariaLabel?: string
}) {
  return (
    <div className="st-seg-row" role="tablist" aria-label={ariaLabel}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button key={o.value} type="button" role="tab" aria-selected={on}
            className={`st-seg${on ? ' is-on' : ''}`} onClick={() => onChange(o.value)}>
            {o.icon && <span className="st-seg-icon" aria-hidden>{o.icon}</span>}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
