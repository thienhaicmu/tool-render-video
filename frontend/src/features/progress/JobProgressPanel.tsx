/**
 * JobProgressPanel — live WebSocket progress panel for a render job.
 * Renders inside JobDetailDrawer (380px width).
 *
 * - Active jobs: connects WebSocket via useRenderSocket
 * - Terminal jobs: no connection, shows static summary
 */
import { useState, useEffect, useRef } from 'react'
import { ProgressBar } from '../../components/ui/ProgressBar'
import { Button } from '../../components/ui/Button'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { useUIStore } from '../../stores/uiStore'
import { cancelRender } from '../../api/render'
import { isTerminalStatus } from '../../types/enums'
import { isActiveStatus } from '../jobs/jobs.utils'
import { ConnectionStatusBadge } from './ConnectionStatusBadge'
import { ProgressStageTimeline } from './ProgressStageTimeline'
import { ProgressPartList } from './ProgressPartList'
import { ProgressMessageLog } from './ProgressMessageLog'
import {
  normalizeProgressPercent,
  getStageLabel,
  getStatusLabel,
  deriveConnectionStatus,
  extractLatestMessage,
} from './progress.utils'
import { MAX_LOG_MESSAGES } from './progress.types'
import './JobProgressPanel.css'

export interface JobProgressPanelProps {
  jobId: string
  initialStatus?: string
  initialProgress?: number
  compact?: boolean
}

/** Inner component that always calls useRenderSocket (hooks must not be conditional) */
function ActiveProgressPanel({
  jobId,
  initialProgress,
  messages,
  onNewMessage,
  onCancelRequest,
  isCanceling,
  showCancel,
}: {
  jobId: string
  initialProgress: number
  messages: string[]
  onNewMessage: (msg: string) => void
  onCancelRequest: () => void
  isCanceling: boolean
  showCancel: boolean
}) {
  const { stage, jobStatus, jobMessage, progress, isConnected, isTerminal, error } =
    useRenderSocket(jobId)

  // Track new messages
  const prevMessage = useRef<string | null>(null)
  useEffect(() => {
    const extracted = extractLatestMessage(jobMessage)
    if (extracted && extracted !== prevMessage.current) {
      prevMessage.current = extracted
      onNewMessage(extracted)
    }
  }, [jobMessage, onNewMessage])

  const overallPct = normalizeProgressPercent(
    progress?.overall_progress_percent ?? initialProgress,
  )
  const stageLabel = getStageLabel(stage ?? progress?.current_stage)
  const connStatus = deriveConnectionStatus(isConnected, isTerminal, error)
  const activeParts = progress?.active_parts ?? []
  const completedParts = progress?.completed_parts ?? 0
  const failedParts = progress?.failed_parts ?? 0
  const totalParts = progress?.total_parts ?? 0

  const displayStatus = jobStatus ? getStatusLabel(jobStatus) : null

  return (
    <div className="job-progress-panel" data-testid="job-progress-panel">
      {/* Header row: stage label + connection badge */}
      <div className="job-progress-header">
        <span className="job-progress-stage-label">
          {displayStatus ?? stageLabel}
        </span>
        <ConnectionStatusBadge status={connStatus} size="sm" />
      </div>

      {/* Stage timeline */}
      <ProgressStageTimeline currentStage={stage ?? progress?.current_stage ?? null} />

      {/* Main progress bar + percentage */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <span className="job-progress-percent">{overallPct}%</span>
        <ProgressBar value={overallPct} />
      </div>

      {/* Per-part list */}
      <ProgressPartList
        activeParts={activeParts}
        completedParts={completedParts}
        failedParts={failedParts}
        totalParts={totalParts}
      />

      {/* Message log */}
      {messages.length > 0 && <ProgressMessageLog messages={messages} />}

      {/* Cancel button */}
      {showCancel && (
        <div>
          <Button
            variant="danger"
            size="sm"
            loading={isCanceling}
            disabled={isCanceling}
            onClick={onCancelRequest}
            data-testid="cancel-render-btn"
          >
            {isCanceling ? 'Canceling...' : 'Cancel'}
          </Button>
        </div>
      )}
    </div>
  )
}

/** Inner component for terminal jobs — no WebSocket connection */
function TerminalProgressPanel({
  initialStatus,
  initialProgress,
}: {
  initialStatus: string
  initialProgress: number
}) {
  // Still call useRenderSocket — but with null to avoid connection
  useRenderSocket(null)

  const overallPct = normalizeProgressPercent(initialProgress)
  const connStatus = deriveConnectionStatus(false, true, null)

  return (
    <div className="job-progress-panel" data-testid="job-progress-panel">
      <div className="job-progress-header">
        <span className="job-progress-terminal-heading">
          {getStatusLabel(initialStatus)}
        </span>
        <ConnectionStatusBadge status={connStatus} size="sm" />
      </div>
      {overallPct > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
          <span className="job-progress-percent">{overallPct}%</span>
          <ProgressBar
            value={overallPct}
            variant={
              initialStatus === 'failed' || initialStatus === 'interrupted'
                ? 'error'
                : initialStatus === 'completed' || initialStatus === 'completed_with_errors'
                  ? 'success'
                  : 'default'
            }
          />
        </div>
      )}
    </div>
  )
}

export function JobProgressPanel({
  jobId,
  initialStatus = '',
  initialProgress = 0,
  compact: _compact = false,
}: JobProgressPanelProps) {
  const [messages, setMessages] = useState<string[]>([])
  const [isCanceling, setIsCanceling] = useState(false)
  const addNotification = useUIStore((s) => s.addNotification)

  const isJobTerminal = isTerminalStatus(initialStatus)
  const showCancel = isActiveStatus(initialStatus)

  const handleNewMessage = (msg: string) => {
    setMessages((prev) => {
      const next = [...prev, msg]
      return next.length > MAX_LOG_MESSAGES ? next.slice(-MAX_LOG_MESSAGES) : next
    })
  }

  const handleCancelRequest = async () => {
    if (isCanceling) return
    const confirmed = window.confirm('Cancel this render job?')
    if (!confirmed) return
    setIsCanceling(true)
    try {
      await cancelRender(jobId)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to cancel job'
      addNotification({ type: 'error', title: 'Cancel failed', message })
      setIsCanceling(false)
    }
  }

  if (isJobTerminal) {
    return (
      <TerminalProgressPanel
        initialStatus={initialStatus}
        initialProgress={initialProgress}
      />
    )
  }

  return (
    <ActiveProgressPanel
      jobId={jobId}
      initialProgress={initialProgress}
      messages={messages}
      onNewMessage={handleNewMessage}
      onCancelRequest={() => void handleCancelRequest()}
      isCanceling={isCanceling}
      showCancel={showCancel}
    />
  )
}
