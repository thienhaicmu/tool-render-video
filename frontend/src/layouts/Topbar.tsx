/**
 * Topbar — App title, connection status, warmup/AI status badge.
 */
import React, { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { useRenderStore } from '../stores/renderStore'

interface WarmupStatus {
  model?: string
  status?: string
  loaded?: boolean
  ready?: boolean
}

export function Topbar() {
  const activeJobId = useRenderStore((s) => s.activeJobId)
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
        <h1 style={styles.title}>Render Studio</h1>
        {activeJobId && (
          <span style={styles.jobBadge}>
            Job: {activeJobId.slice(0, 8)}…
          </span>
        )}
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
              ? 'var(--color-success)'
              : 'var(--color-error)',
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
    backgroundColor: 'var(--color-bg-surface)',
    borderBottom: '1px solid var(--color-border)',
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
  title: {
    fontSize: 'var(--font-size-lg)',
    fontWeight: 'var(--font-weight-semibold)' as unknown as number,
    color: 'var(--color-text-primary)',
  },
  jobBadge: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--color-accent)',
    backgroundColor: 'var(--color-accent-muted)',
    padding: '2px var(--space-2)',
    borderRadius: 'var(--radius-full)',
    fontFamily: 'var(--font-family-mono)',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  statusBadge: {
    fontSize: 'var(--font-size-xs)',
    padding: '2px var(--space-2)',
    borderRadius: 'var(--radius-full)',
  },
  statusBadgeReady: {
    color: 'var(--color-success)',
    backgroundColor: 'var(--color-success-muted)',
  },
  statusBadgeLoading: {
    color: 'var(--color-warning)',
    backgroundColor: 'var(--color-warning-muted)',
  },
  connectionDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    transition: `background-color var(--duration-normal)`,
  },
}
