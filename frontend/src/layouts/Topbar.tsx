/**
 * Topbar — product wordmark, theme toggle, AI warmup status, connection.
 */
import React, { useEffect, useState } from 'react'
import { apiFetch } from '../api/client'
import { ThemeToggle } from '../components/ui/ThemeToggle'

interface WarmupStatus {
  model?: string
  status?: string
  loaded?: boolean
  ready?: boolean
}

// ── Topbar ───────────────────────────────────────────────────────────────────

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
        <ThemeToggle />

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
            <span
              style={{
                ...styles.statusDot,
                backgroundColor: warmupStatus.loaded || warmupStatus.ready
                  ? 'var(--status-success)'
                  : 'var(--status-warning)',
              }}
            />
            AI {warmupStatus.loaded || warmupStatus.ready ? 'Ready' : 'Loading'}
          </span>
        )}

        <span
          style={{
            ...styles.statusBadge,
            ...(isConnected ? styles.statusBadgeReady : styles.statusBadgeError),
          }}
          title={isConnected ? 'Backend connected' : 'Backend disconnected'}
        >
          <span
            style={{
              ...styles.statusDot,
              backgroundColor: isConnected ? 'var(--status-success)' : 'var(--status-error)',
            }}
          />
          {isConnected ? 'Connected' : 'Offline'}
        </span>
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
    padding: '0 var(--space-5)',
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
    letterSpacing: '-0.015em',
  },
  right: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  statusBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 'var(--text-xs)',
    fontWeight: 'var(--weight-medium)' as unknown as number,
    padding: '4px 8px',
    height: 24,
    borderRadius: 'var(--radius-full)',
    border: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--surface-card)',
  },
  statusBadgeReady: {
    color: 'var(--text-secondary)',
  },
  statusBadgeLoading: {
    color: 'var(--status-warning)',
  },
  statusBadgeError: {
    color: 'var(--status-error)',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    flexShrink: 0,
    transition: 'background-color var(--duration-panel)',
  },
}
