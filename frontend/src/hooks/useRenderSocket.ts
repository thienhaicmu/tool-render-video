/**
 * useRenderSocket — React hook wrapping RenderSocketClient.
 * Cleans up on unmount. Does not reconnect for terminal job states.
 */
import { useEffect, useRef, useState } from 'react'
import { RenderSocketClient } from '../websocket/RenderSocketClient'
import type { WsProgressSummary } from '../types/api'

export interface RenderSocketState {
  stage: string | null
  progress: WsProgressSummary | null
  isConnected: boolean
  error: string | null
}

export function useRenderSocket(jobId: string | null): RenderSocketState {
  const clientRef = useRef<RenderSocketClient | null>(null)
  const [stage, setStage] = useState<string | null>(null)
  const [progress, setProgress] = useState<WsProgressSummary | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!jobId) return

    const client = new RenderSocketClient()
    clientRef.current = client

    client.onStageChange((s) => {
      setStage(s)
      setIsConnected(true)
    })

    client.onProgress((summary) => {
      setProgress(summary)
    })

    client.onComplete(() => {
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

  return { stage, progress, isConnected, error }
}
