/**
 * Topbar — Product wordmark, connection status, warmup/AI status badge.
 */
import React, { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

interface WarmupStatus {
  model?: string
  status?: string
  loaded?: boolean
  ready?: boolean
}

export function Topbar() {
  const [warmupStatus, setWarmupStatus] = useState<WarmupStatus | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        await apiFetch('/health')
        if (!cancelled) setIsConnected(true)
      } catch {
        if (!cancelled) setIsConnected(false)
      }
    }
    check()
    const timer = setInterval(check, 30_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const fetchWarmup = async () => {
      try {
        const data = await apiFetch<WarmupStatus>('/api/warmup/status')
        if (!cancelled) setWarmupStatus(data)
      } catch {
        // warmup status unavailable — not critical
      }
    }
    fetchWarmup()
    return () => { cancelled = true }
  }, [])

  return (
    <header style={styles.topbar}>
      <div style={styles.left}>
        <span style={styles.wordmark}>AI Clip Studio</span>
      </div>

      <div style={styles.right}>
        {warmupStatus && (
          <span
            style={{
              ...styles.statusBadge,
              ...(warmupStatus.loaded || warmupStatus.ready
                ? styles.statusBadgeReady
                : styles.statusBadgeLoading),
            }}
            title={`AI/Warmup: ${warmupStatus.status ?? 'unknown'}`}
          >
            AI {warmupStatus.loaded || warmupStatus.ready ? 'Ready' : 'Loading'}
          </span>
        )}

        <div
          style={{
            ...styles.connectionDot,
            backgroundColor: isConnected
              ? 'var(--status-success)'
              : 'var(--status-error)',
          }}
          title={isConnected ? 'Backend connected' : 'Backend disconnected'}
        />
      </div>
    </header>
  )
}

const styles: Record<string, React.CSSProperties> = {
  topbar: {
    height: 'var(--topbar-height)',
    backgroundColor: 'var(--surface-panel)',
    borderBottom: '1px solid var(--border-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-6)',
    flexShrink: 0,
    position: 'sticky',
    top: 0,
    zIndex: 'var(--z-raised)' as unknown as number,
  },
  left: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-4)',
  },
  wordmark: {
    fontSize: 'var(--text-md)',
    fontWeight: 'var(--weight-semibold)' as unknown as number,
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-ui)',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  statusBadge: {
    fontSize: 'var(--text-xs)',
    padding: '2px var(--space-2)',
    borderRadius: 'var(--radius-full)',
  },
  statusBadgeReady: {
    color: 'var(--status-success)',
    backgroundColor: 'var(--status-success-bg)',
  },
  statusBadgeLoading: {
    color: 'var(--status-warning)',
    backgroundColor: 'var(--status-warning-bg)',
  },
  connectionDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    transition: `background-color var(--duration-panel)`,
  },
}
