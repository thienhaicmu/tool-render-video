/**
 * ProgressMessageLog — collapsible log of recent stage messages.
 */
import { useState } from 'react'
import { MAX_LOG_MESSAGES } from './progress.types'

export interface ProgressMessageLogProps {
  messages: string[]
}

export function ProgressMessageLog({ messages }: ProgressMessageLogProps) {
  const [expanded, setExpanded] = useState(false)

  // Show nothing when empty
  if (messages.length === 0) return null

  const recent = messages.slice(-MAX_LOG_MESSAGES)
  const isCollapsible = recent.length > 2

  const displayed = isCollapsible && !expanded ? recent.slice(-2) : recent

  return (
    <div data-testid="progress-message-log" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      {displayed.map((msg, idx) => (
        <div
          key={idx}
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            opacity: 0.8,
            wordBreak: 'break-word',
          }}
        >
          {msg}
        </div>
      ))}
      {isCollapsible && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text-secondary)',
            fontSize: 'var(--font-size-xs)',
            cursor: 'pointer',
            padding: 0,
            textAlign: 'left',
            opacity: 0.7,
          }}
        >
          {expanded ? 'Hide log' : `Show log (${recent.length} entries)`}
        </button>
      )}
    </div>
  )
}
