/**
 * ConnectionStatusBadge — shows WebSocket connection state.
 */
import { Badge } from '@/components/ui/Badge'
import type { BadgeVariant } from '@/components/ui/Badge'
import type { ConnectionStatus } from './progress.types'

export interface ConnectionStatusBadgeProps {
  status: ConnectionStatus
  size?: 'sm' | 'md'
}

interface StatusConfig {
  label: string
  variant: BadgeVariant
}

const STATUS_CONFIG: Record<ConnectionStatus, StatusConfig> = {
  connecting:   { label: 'Connecting',   variant: 'neutral' },
  live:         { label: 'Live',         variant: 'success' },
  reconnecting: { label: 'Reconnecting', variant: 'warning' },
  disconnected: { label: 'Disconnected', variant: 'error' },
  terminal:     { label: 'Done',         variant: 'neutral' },
}

export function ConnectionStatusBadge({ status, size = 'sm' }: ConnectionStatusBadgeProps) {
  const config = STATUS_CONFIG[status]
  return (
    <Badge variant={config.variant} size={size} data-testid="connection-status-badge">
      {config.label}
    </Badge>
  )
}
