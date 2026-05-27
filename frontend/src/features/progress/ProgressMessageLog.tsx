/**
 * ProgressMessageLog — collapsible log of recent stage messages with timestamps.
 */
import { useState } from 'react'
import type { LogMessage } from './progress.types'
import { MAX_LOG_MESSAGES } from './progress.types'

export interface ProgressMessageLogProps {
  messages: LogMessage[]
}

export function ProgressMessageLog({ messages }: ProgressMessageLogProps) {
  const [expanded, setExpanded] = useState(false)

  if (messages.length === 0) return null

  const recent = messages.slice(-MAX_LOG_MESSAGES)
  const isCollapsible = recent.length > 3

  const displayed = isCollapsible && !expanded ? recent.slice(-3) : recent

  return (
    <div
      data-testid="progress-message-log"
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}
    >
      {displayed.map((msg, idx) => (
        <div
          key={idx}
          style={{
            display: 'flex',
            gap: 'var(--space-2)',
            alignItems: 'flex-start',
          }}
        >
          <span
            style={{
              fontSize: 'var(--font-size-xs)',
              color: 'var(--color-text-secondary)',
              opacity: 0.7,
              flexShrink: 0,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            [{msg.ts}]
          </span>
          <span
            style={{
              fontSize: 'var(--font-size-xs)',
              color: 'var(--color-text-primary)',
              opacity: 0.8,
              wordBreak: 'break-word',
              flex: 1,
            }}
          >
            {msg.text}
          </span>
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
