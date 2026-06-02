/**
 * JobStatusBadge — maps a job status string to a labeled Badge.
 */
import { Badge } from '@/components/ui/Badge'
import type { BadgeVariant } from '@/components/ui/Badge'

interface StatusConfig {
  label: string
  variant: BadgeVariant
}

const STATUS_MAP: Record<string, StatusConfig> = {
  completed:   { label: 'Complete',    variant: 'success'  },
  partial:     { label: 'Partial',     variant: 'warning'  },
  running:     { label: 'Rendering',   variant: 'info'     },
  queued:      { label: 'Queued',      variant: 'neutral'  },
  failed:      { label: 'Failed',      variant: 'error'    },
  interrupted: { label: 'Interrupted', variant: 'warning'  },
  cancelled:   { label: 'Canceled',    variant: 'neutral'  },
  canceled:    { label: 'Canceled',    variant: 'neutral'  },
  cancelling:  { label: 'Canceling',   variant: 'warning'  },
}

const FALLBACK: StatusConfig = { label: 'Unknown', variant: 'neutral' }

export interface JobStatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

export function JobStatusBadge({ status, size = 'sm' }: JobStatusBadgeProps) {
  const config = STATUS_MAP[status] ?? FALLBACK
  return (
    <Badge variant={config.variant} size={size}>
      {config.label}
    </Badge>
  )
}
