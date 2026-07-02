/**
 * Sidebar — P2.1 single-shell: slim 56px icon-only nav rail, visible on
 * EVERY screen including Clip Studio. The old 220px labeled sidebar was
 * invisible while the user was in Studio (fullscreen shell), which hid
 * the app's primary navigation from its primary workflow.
 *
 * Labels surface via title tooltips + aria-labels; the active item gets
 * an accent background and a left accent bar.
 */
import React, { useState } from 'react'
import { useUIStore } from '../stores/uiStore'
import { useI18n } from '../i18n/useI18n'
import type { ActivePanel } from '../stores/uiStore'

// ── SVG Icon set (CapCut-style line icons) ─────────────────────────────────────

function IconScissors() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <circle cx="6" cy="6" r="3"/>
      <circle cx="6" cy="18" r="3"/>
      <path d="M8.46 7.54L20 19M8.46 16.46L14 12L20 5"/>
    </svg>
  )
}

function IconGrid() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5"/>
      <rect x="14" y="3" width="7" height="7" rx="1.5"/>
      <rect x="3" y="14" width="7" height="7" rx="1.5"/>
      <rect x="14" y="14" width="7" height="7" rx="1.5"/>
    </svg>
  )
}

function IconDownload() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3V16"/>
      <path d="M7 12L12 17L17 12"/>
      <path d="M3 20H21"/>
    </svg>
  )
}

function IconSettings() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <path d="M4 6H20M4 12H20M4 18H20"/>
      <circle cx="8" cy="6" r="2" fill="currentColor" stroke="none"/>
      <circle cx="16" cy="12" r="2" fill="currentColor" stroke="none"/>
      <circle cx="8" cy="18" r="2" fill="currentColor" stroke="none"/>
    </svg>
  )
}

// ── Nav item definitions ───────────────────────────────────────────────────────

interface NavItem {
  panel: ActivePanel
  labelKey: 'nav_studio' | 'nav_library' | 'nav_download' | 'nav_settings'
  icon: React.ReactNode
}

const MAIN_NAV: NavItem[] = [
  { panel: 'clip-studio', labelKey: 'nav_studio',   icon: <IconScissors /> },
  { panel: 'library',     labelKey: 'nav_library',  icon: <IconGrid /> },
  { panel: 'download',    labelKey: 'nav_download', icon: <IconDownload /> },
]

const BOTTOM_NAV: NavItem[] = [
  { panel: 'settings', labelKey: 'nav_settings', icon: <IconSettings /> },
]

// ── Rail button ────────────────────────────────────────────────────────────────

function RailButton({ item, activePanel, hoveredItem, setHoveredItem, setActivePanel }: {
  item: NavItem
  activePanel: ActivePanel
  hoveredItem: string | null
  setHoveredItem: (panel: string | null) => void
  setActivePanel: (panel: ActivePanel) => void
}) {
  const { t } = useI18n()
  const isActive  = activePanel === item.panel
  const isHovered = hoveredItem === item.panel

  return (
    <button
      style={{
        position: 'relative',
        width: 40,
        height: 40,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: isActive
          ? 'var(--accent-subtle)'
          : isHovered ? 'var(--surface-card-hover)' : 'transparent',
        color: isActive ? 'var(--accent-primary)' : isHovered ? 'var(--text-primary)' : 'var(--text-secondary)',
        cursor: 'pointer',
        border: 'none',
        borderRadius: 10,
        transition: 'background-color 0.12s ease, color 0.12s ease',
      }}
      onClick={() => setActivePanel(item.panel)}
      onMouseEnter={() => setHoveredItem(item.panel)}
      onMouseLeave={() => setHoveredItem(null)}
      aria-current={isActive ? 'page' : undefined}
      aria-label={t(item.labelKey)}
      title={t(item.labelKey)}
    >
      {/* Left accent bar */}
      {isActive && (
        <span style={{
          position: 'absolute',
          left: -8,
          top: '50%',
          transform: 'translateY(-50%)',
          width: 3,
          height: 20,
          background: 'linear-gradient(180deg, var(--ai-active), var(--accent-primary))',
          borderRadius: '0 2px 2px 0',
        }} />
      )}
      {item.icon}
    </button>
  )
}

// ── Sidebar (slim rail) ────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePanel, setActivePanel } = useUIStore()
  const [hoveredItem, setHoveredItem] = useState<string | null>(null)

  const shared = { activePanel, hoveredItem, setHoveredItem, setActivePanel }

  return (
    <aside style={styles.sidebar}>
      {/* Logo mark (wordmark lives in the Topbar) */}
      <div style={styles.header}>
        <span style={styles.logoMark} title="AI Clip Studio">✦</span>
      </div>

      <nav style={styles.nav}>
        {MAIN_NAV.map((item) => <RailButton key={item.panel} item={item} {...shared} />)}
        <div style={{ flex: 1 }} />
        {BOTTOM_NAV.map((item) => <RailButton key={item.panel} item={item} {...shared} />)}
      </nav>
    </aside>
  )
}

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    position: 'fixed',
    top: 0,
    left: 0,
    height: '100vh',
    width: 'var(--sidebar-width)',
    backgroundColor: 'var(--surface-panel)',
    borderRight: '1px solid var(--border-subtle)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    zIndex: 'var(--z-raised)' as unknown as number,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: 'var(--topbar-height)',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
  },
  logoMark: {
    width: 26,
    height: 26,
    borderRadius: 8,
    background: 'var(--brand-gradient)',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#fff',
    fontSize: 14,
    fontWeight: 700,
    lineHeight: 1,
    boxShadow:
      '0 1px 0 rgba(255, 255, 255, 0.30) inset, 0 2px 8px rgba(139, 92, 246, 0.35)',
    flexShrink: 0,
    userSelect: 'none',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    padding: 'var(--space-3) 0',
    flex: 1,
    gap: 6,
    overflow: 'hidden',
  },
}
