/**
 * Topbar — P2.1 single-shell: the ONE topbar for the whole app.
 * Wordmark, active-job badge, notifications, theme, language, health.
 * The Studio's private topbar chrome (its own brand/theme/lang/bell/gear
 * cluster) was merged in here.
 */
import React from 'react'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { NotificationCenter } from '../components/NotificationCenter'
import { ActiveJobBadge } from '../features/clip-studio/ActiveJobBadge'
import { useUIStore } from '../stores/uiStore'
import { useBackendHealth } from '../hooks/useBackendHealth'

// ── Language toggle (single instance app-wide since P1.2) ────────────────────

function LangToggle() {
  const lang = useUIStore((s) => s.lang)
  const setLang = useUIStore((s) => s.setLang)
  const btn = (code: 'en' | 'vi', label: string) => (
    <button
      onClick={() => setLang(code)}
      style={{
        height: '100%',
        padding: '0 8px',
        border: 'none',
        backgroundColor: lang === code ? 'var(--accent-subtle)' : 'transparent',
        color: lang === code ? 'var(--accent-primary)' : 'var(--text-tertiary)',
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: '0.04em',
        cursor: 'pointer',
        transition: 'color 0.12s ease, background-color 0.12s ease',
      }}
    >
      {label}
    </button>
  )
  return (
    <div style={{
      display: 'flex',
      alignItems: 'stretch',
      height: 24,
      backgroundColor: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 6,
      overflow: 'hidden',
    }}>
      {btn('en', 'EN')}
      {btn('vi', 'VI')}
    </div>
  )
}

// ── Topbar ───────────────────────────────────────────────────────────────────

export function Topbar() {
  // P0.1 — shared refcounted health poll (also drives the Studio status bar).
  const { apiOk, whisperReady, warmupStatus } = useBackendHealth()
  const isConnected = apiOk === true
  const setActivePanel = useUIStore((s) => s.setActivePanel)

  return (
    <header style={styles.topbar}>
      <div style={styles.left}>
        <button
          type="button"
          onClick={() => setActivePanel('clip-studio')}
          style={styles.brand}
          title="Back to Studio"
        >
          <span style={styles.brandMark} aria-hidden="true">✦</span>
          <span style={styles.wordmark}>AI Clip Studio</span>
        </button>
      </div>

      <div style={styles.right}>
        {/* Pulsing pill while a render runs — click opens its monitor. */}
        <ActiveJobBadge onClick={() => setActivePanel('clip-studio')} />
        <NotificationCenter />
        <ThemeToggle />
        <LangToggle />

        {warmupStatus && (
          <span
            style={{
              ...styles.statusBadge,
              ...(whisperReady ? styles.statusBadgeReady : styles.statusBadgeLoading),
            }}
            title={`AI/Warmup: ${warmupStatus.status ?? 'unknown'}`}
          >
            <span
              style={{
                ...styles.statusDot,
                backgroundColor: whisperReady
                  ? 'var(--status-success)'
                  : 'var(--status-warning)',
              }}
            />
            AI {whisperReady ? 'Ready' : 'Loading'}
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
  brand: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    padding: 0,
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'inherit',
  },
  brandMark: {
    width: 24,
    height: 24,
    borderRadius: 7,
    background: 'var(--brand-gradient)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#fff',
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: '-0.04em',
    lineHeight: 1,
    boxShadow:
      '0 1px 0 rgba(255, 255, 255, 0.30) inset, 0 2px 8px rgba(139, 92, 246, 0.35)',
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
