/**
 * Notifications — fixed-position toast area at bottom-right.
 * Auto-removes after 5 seconds. Type-appropriate colors.
 */
import React, { useEffect } from 'react'
import { useUIStore } from '../../stores/uiStore'
import type { Notification } from '../../stores/uiStore'

export function Notifications() {
  const notifications = useUIStore((s) => s.notifications)
  const removeNotification = useUIStore((s) => s.removeNotification)

  return (
    <div style={containerStyle} aria-live="polite" aria-atomic="false">
      {notifications.map((n) => (
        <ToastItem key={n.id} notification={n} onRemove={removeNotification} />
      ))}
    </div>
  )
}

interface ToastItemProps {
  notification: Notification
  onRemove: (id: string) => void
}

function ToastItem({ notification, onRemove }: ToastItemProps) {
  useEffect(() => {
    const duration = notification.duration ?? 5000
    const timer = setTimeout(() => {
      onRemove(notification.id)
    }, duration)
    return () => clearTimeout(timer)
  }, [notification.id, notification.duration, onRemove])

  const typeColors: Record<Notification['type'], string> = {
    success: 'var(--color-success)',
    error: 'var(--color-error)',
    info: 'var(--color-info)',
    warning: 'var(--color-warning)',
  }

  const accent = typeColors[notification.type]

  return (
    <div
      role="alert"
      style={{
        ...toastStyle,
        borderLeftColor: accent,
      }}
    >
      <div style={toastContentStyle}>
        <span style={{ ...toastTitleStyle, color: accent }}>{notification.title}</span>
        {notification.message && (
          <span style={toastMessageStyle}>{notification.message}</span>
        )}
      </div>
      <button
        type="button"
        onClick={() => onRemove(notification.id)}
        style={closeButtonStyle}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  position: 'fixed',
  bottom: 'var(--space-6)',
  right: 'var(--space-6)',
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2)',
  zIndex: 'var(--z-toast)' as unknown as number,
  maxWidth: '360px',
  width: '100%',
  pointerEvents: 'none',
}

const toastStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 'var(--space-3)',
  padding: 'var(--space-3) var(--space-4)',
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderLeft: '3px solid',
  borderRadius: 'var(--radius-md)',
  boxShadow: 'var(--shadow-lg)',
  pointerEvents: 'all',
  animation: 'none',
}

const toastContentStyle: React.CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  gap: '2px',
  minWidth: 0,
}

const toastTitleStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-sm)',
  fontWeight: 'var(--font-weight-medium)' as unknown as number,
  lineHeight: 'var(--line-height-tight)',
  wordBreak: 'break-word',
}

const toastMessageStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  wordBreak: 'break-word',
}

const closeButtonStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--color-text-secondary)',
  cursor: 'pointer',
  fontSize: '18px',
  lineHeight: 1,
  padding: '0 2px',
  flexShrink: 0,
}
