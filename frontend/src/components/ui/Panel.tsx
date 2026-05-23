/**
 * Panel — Structural container with surface-panel background.
 * No hover state, no click handler. Layout primitive only.
 */
import React from 'react'

export interface PanelProps {
  children: React.ReactNode
  style?: React.CSSProperties
  shadow?: boolean
  border?: boolean
  className?: string
}

export function Panel({ children, style, shadow = false, border = false, className }: PanelProps) {
  return (
    <div
      className={className}
      style={{
        backgroundColor: 'var(--surface-panel)',
        borderRadius: 'var(--radius-xl)',
        ...(border ? { border: '1px solid var(--border-subtle)' } : {}),
        ...(shadow ? { boxShadow: 'var(--shadow-panel)' } : {}),
        ...style,
      }}
    >
      {children}
    </div>
  )
}
