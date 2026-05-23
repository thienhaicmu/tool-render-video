import { useState, type CSSProperties } from 'react'

export interface TimelineZoomControlProps {
  zoom: number
  onZoomChange: (zoom: number) => void
}

export function TimelineZoomControl({ zoom, onZoomChange }: TimelineZoomControlProps) {
  const [hovered, setHovered] = useState<'minus' | 'plus' | null>(null)

  const btnBase = (id: 'minus' | 'plus', disabled: boolean): CSSProperties => ({
    width: '20px',
    height: '20px',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-sm)',
    backgroundColor: !disabled && hovered === id ? 'var(--surface-card)' : 'transparent',
    color: 'var(--text-secondary)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: 'var(--text-sm)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    opacity: disabled ? 0.35 : 1,
    transition: 'background-color var(--duration-instant) var(--ease-out)',
    flexShrink: 0,
    lineHeight: 1,
    padding: 0,
  })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
      <button
        onClick={() => onZoomChange(zoom - 1)}
        disabled={zoom <= 1}
        onMouseEnter={() => setHovered('minus')}
        onMouseLeave={() => setHovered(null)}
        style={btnBase('minus', zoom <= 1)}
        aria-label="Zoom out"
      >
        −
      </button>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-tertiary)',
          minWidth: '24px',
          textAlign: 'center',
          userSelect: 'none',
        }}
      >
        {zoom}x
      </span>
      <button
        onClick={() => onZoomChange(zoom + 1)}
        disabled={zoom >= 4}
        onMouseEnter={() => setHovered('plus')}
        onMouseLeave={() => setHovered(null)}
        style={btnBase('plus', zoom >= 4)}
        aria-label="Zoom in"
      >
        +
      </button>
    </div>
  )
}
