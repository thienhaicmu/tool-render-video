import { useState } from 'react'

export interface TimelineClipProps {
  id: string
  start: number
  end: number
  color: string
  isSelected?: boolean
  isAiSelected?: boolean
  zoom?: number
  onClick?: () => void
  onHover?: (hovered: boolean) => void
  // B12 ready — leave as optional no-op
  onTrimStart?: () => void
  onTrimEnd?: () => void
}

export function TimelineClip({
  id: _id,
  start,
  end,
  color,
  isSelected = false,
  isAiSelected = false,
  zoom = 1,
  onClick,
  onHover,
}: TimelineClipProps) {
  const [isHovered, setIsHovered] = useState(false)

  const showTrimHandles = isHovered || isSelected

  let borderColor = 'transparent'
  let boxShadow = 'none'

  if (isSelected) {
    borderColor = 'var(--accent-primary)'
    boxShadow = 'var(--shadow-card)'
  } else if (isAiSelected && !isSelected) {
    borderColor = 'var(--ai-active)'
  } else if (isHovered) {
    borderColor = 'var(--border-default)'
  }

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => { setIsHovered(true); onHover?.(true) }}
      onMouseLeave={() => { setIsHovered(false); onHover?.(false) }}
      style={{
        position: 'absolute',
        top: '3px',
        bottom: '3px',
        left: `${start * 100 * zoom}%`,
        width: `${(end - start) * 100 * zoom}%`,
        backgroundColor: color,
        borderRadius: 'var(--radius-sm)',
        border: `1.5px solid ${borderColor}`,
        boxShadow,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color var(--duration-instant) var(--ease-out), box-shadow var(--duration-instant) var(--ease-out)',
        boxSizing: 'border-box',
      }}
    >
      {/* Left trim handle */}
      <div
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: '6px',
          backgroundColor: 'var(--border-strong)',
          borderRadius: 'var(--radius-sm) 0 0 var(--radius-sm)',
          cursor: 'ew-resize',
          opacity: showTrimHandles ? 1 : 0,
          transition: 'opacity var(--duration-instant) var(--ease-out)',
        }}
      />
      {/* Right trim handle */}
      <div
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          right: 0,
          width: '6px',
          backgroundColor: 'var(--border-strong)',
          borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
          cursor: 'ew-resize',
          opacity: showTrimHandles ? 1 : 0,
          transition: 'opacity var(--duration-instant) var(--ease-out)',
        }}
      />
    </div>
  )
}
