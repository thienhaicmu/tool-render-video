/**
 * Card — Content container with hover and selected states.
 * Source: docs/design/components.md component #3
 */
import React, { useState } from 'react'

export interface CardProps {
  children: React.ReactNode
  style?: React.CSSProperties
  hoverable?: boolean
  selected?: boolean
  onClick?: () => void
}

export function Card({ children, style, hoverable = false, selected = false, onClick }: CardProps) {
  const [isHovered, setIsHovered] = useState(false)

  const showHover = hoverable && isHovered

  return (
    <div
      style={{
        backgroundColor: showHover ? 'var(--surface-card-hover)' : 'var(--surface-card)',
        border: `1px solid ${selected ? 'var(--accent-primary)' : showHover ? 'var(--accent-subtle-hover)' : 'var(--border-subtle)'}`,
        boxShadow: showHover ? 'var(--shadow-panel)' : 'var(--shadow-card)',
        borderRadius: 'var(--radius-lg)',
        transition: `background-color var(--duration-card) var(--ease-in-out), border-color var(--duration-card) var(--ease-in-out)`,
        cursor: onClick ? 'pointer' : undefined,
        ...style,
      }}
      onMouseEnter={hoverable ? () => setIsHovered(true) : undefined}
      onMouseLeave={hoverable ? () => setIsHovered(false) : undefined}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
