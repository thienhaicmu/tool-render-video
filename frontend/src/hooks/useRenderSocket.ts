/**
 * useRenderSocket — React hook wrapping RenderSocketClient.
 * Cleans up on unmount. Does not reconnect for terminal job states.
 */
import { useEffect, useRef, useState } from 'react'
import { RenderSocketClient } from '../websocket/RenderSocketClient'
import { isTerminalStatus } from '../types/enums'
import { useRenderStore } from '../stores/renderStore'
import type { WsProgressSummary, JobPart, JobErrorKind } from '../types/api'

export interface RenderSocketState {
  stage: string | null
  jobStatus: string | null      // from job.status on terminal events
  jobMessage: string | null     // from job.message (second arg of onStageChange)
  progress: WsProgressSummary | null
  liveParts: JobPart[]          // per-event parts array (all parts, current state)
  isConnected: boolean
  isReconnecting: boolean       // true while attempting to re-establish a dropped connection
  isTerminal: boolean           // derived from jobStatus
  error: string | null
  errorKind: JobErrorKind | null  // structured error classification, set on FAILED
}

export function useRenderSocket(jobId: string | null, wsPathOverride?: string): RenderSocketState {
  const clientRef    = useRef<RenderSocketClient | null>(null)
  const progressRef  = useRef<string>('')   // fingerprint to skip no-op updates
  const partsRef     = useRef<string>('')

  const [stage, setStage]           = useState<string | null>(null)
  const [jobStatus, setJobStatus]   = useState<string | null>(null)
  const [jobMessage, setJobMessage] = useState<string | null>(null)
  const [progress, setProgress]     = useState<WsProgressSummary | null>(null)
  const [liveParts, setLiveParts]   = useState<JobPart[]>([])
  const [isConnected, setIsConnected]       = useState(false)
  const [isReconnecting, setIsReconnecting] = useState(false)
  const [error, setError]                   = useState<string | null>(null)
  const [errorKind, setErrorKind]           = useState<JobErrorKind | null>(null)

  const updateJobStatus = useRenderStore((s) => s.updateJobStatus)

  useEffect(() => {
    if (!jobId) return

    const client = new RenderSocketClient()
    clientRef.current = client

    client.onStageChange((s, msg) => {
      setStage(s)
      setIsConnected(true)
      setIsReconnecting(false)
      setJobMessage(msg)
    })

    client.onProgress((summary, parts) => {
      // Only trigger re-render if data materially changed
      const pKey = `${summary.overall_progress_percent}|${summary.completed_parts}|${summary.failed_parts}|${summary.active_parts}`
      if (pKey !== progressRef.current) {
        progressRef.current = pKey
        setProgress(summary)
      }
      if (parts.length > 0) {
        const partsKey = parts.map(p => `${p.part_no}:${p.status}:${p.progress_percent}`).join(',')
        if (partsKey !== partsRef.current) {
          partsRef.current = partsKey
          setLiveParts(parts)
        }
      }
    })

    client.onComplete((event) => {
      const status = event.job.status
      setJobStatus(status)
      setErrorKind(event.job.error_kind ?? null)
      setIsConnected(false)
      // Sync terminal status into the store so any component reading store sees correct state
      updateJobStatus(jobId, status)
    })

    client.onReconnecting(() => {
      setIsConnected(false)
      setIsReconnecting(true)
    })

    client.onError((err) => {
      setError(err)
      setIsConnected(false)
      setIsReconnecting(false)
    })

    client.connect(jobId, wsPathOverride)

    return () => {
      client.disconnect()
      clientRef.current = null
    }
  }, [jobId, wsPathOverride, updateJobStatus])

  return {
    stage,
    jobStatus,
    jobMessage,
    progress,
    liveParts,
    isConnected,
    isReconnecting,
    isTerminal: isTerminalStatus(jobStatus ?? ''),
    error,
    errorKind,
  }
}
