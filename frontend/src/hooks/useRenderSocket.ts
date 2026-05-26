/**
 * useRenderSocket — React hook wrapping RenderSocketClient.
 * Cleans up on unmount. Does not reconnect for terminal job states.
 */
import { useEffect, useRef, useState } from 'react'
import { RenderSocketClient } from '../websocket/RenderSocketClient'
import { isTerminalStatus } from '../types/enums'
import type { WsProgressSummary, JobPart } from '../types/api'

export interface RenderSocketState {
  stage: string | null
  jobStatus: string | null      // from job.status on terminal events
  jobMessage: string | null     // from job.message (second arg of onStageChange)
  progress: WsProgressSummary | null
  liveParts: JobPart[]          // per-event parts array (all parts, current state)
  isConnected: boolean
  isTerminal: boolean           // derived from jobStatus
  error: string | null
}

export function useRenderSocket(jobId: string | null): RenderSocketState {
  const clientRef = useRef<RenderSocketClient | null>(null)
  const [stage, setStage] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<string | null>(null)
  const [jobMessage, setJobMessage] = useState<string | null>(null)
  const [progress, setProgress] = useState<WsProgressSummary | null>(null)
  const [liveParts, setLiveParts] = useState<JobPart[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!jobId) return

    const client = new RenderSocketClient()
    clientRef.current = client

    client.onStageChange((s, msg) => {
      setStage(s)
      setIsConnected(true)
      setJobMessage(msg)
    })

    client.onProgress((summary, parts) => {
      setProgress(summary)
      if (parts.length > 0) setLiveParts(parts)
    })

    client.onComplete((event) => {
      setJobStatus(event.job.status)
      setIsConnected(false)
    })

    client.onError((err) => {
      setError(err)
      setIsConnected(false)
    })

    client.connect(jobId)

    return () => {
      client.disconnect()
      clientRef.current = null
    }
  }, [jobId])

  return {
    stage,
    jobStatus,
    jobMessage,
    progress,
    liveParts,
    isConnected,
    isTerminal: isTerminalStatus(jobStatus ?? ''),
    error,
  }
}
