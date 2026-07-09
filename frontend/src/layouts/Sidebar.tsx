/**
 * Sidebar — WP2 nav rail: a 72px rail where every destination shows an icon
 * AND a visible label (discoverability), not a tooltip-only glyph. Adds the
 * Queue and Editor destinations (Editor previously had no nav home). Visible
 * on every screen including Studio.
 */
import React, { useState } from 'react'
import { useUIStore } from '../stores/uiStore'
import { useI18n } from '../i18n/useI18n'
import type { ActivePanel } from '../stores/uiStore'
import type { TranslationKey } from '../i18n/translations'
import { IconQueue, IconSpark, IconScissors } from '../components/icons'

// ── Local icons not in the shared set ──────────────────────────────────────────

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
      <path d="M12 3V16"/><path d="M7 12L12 17L17 12"/><path d="M3 20H21"/>
    </svg>
  )
}

function IconContent() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 5h16" /><path d="M4 10h16" /><path d="M4 15h10" /><path d="M4 20h7" />
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

// ── Nav definitions ─────────────────────────────────────────────────────────────

interface NavItem {
  panel: ActivePanel
  labelKey: TranslationKey
  icon: React.ReactNode
}

const MAIN_NAV: NavItem[] = [
  { panel: 'clip-studio', labelKey: 'nav_studio',   icon: <IconSpark size={19} /> },
  { panel: 'content-studio', labelKey: 'nav_content', icon: <IconContent /> },
  { panel: 'story-studio', labelKey: 'nav_story',   icon: <IconContent /> },
  { panel: 'queue',       labelKey: 'nav_queue',    icon: <IconQueue size={19} /> },
  { panel: 'library',     labelKey: 'nav_library',  icon: <IconGrid /> },
  { panel: 'download',    labelKey: 'nav_download', icon: <IconDownload /> },
  { panel: 'editor',      labelKey: 'nav_editor',   icon: <IconScissors size={19} /> },
]

const BOTTOM_NAV: NavItem[] = [
  { panel: 'settings', labelKey: 'nav_settings', icon: <IconSettings /> },
]

// ── Rail button (icon + label) ──────────────────────────────────────────────────

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
        width: 60,
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
        padding: '8px 0 6px',
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
    >
      {isActive && (
        <span style={{
          position: 'absolute',
          left: -6,
          top: '50%',
          transform: 'translateY(-50%)',
          width: 3,
          height: 22,
          background: 'linear-gradient(180deg, var(--ai-active), var(--accent-primary))',
          borderRadius: '0 2px 2px 0',
        }} />
      )}
      {item.icon}
      <span style={{
        fontSize: 10,
        fontWeight: isActive ? 700 : 500,
        letterSpacing: '.01em',
        lineHeight: 1,
        whiteSpace: 'nowrap',
      }}>
        {t(item.labelKey)}
      </span>
    </button>
  )
}

// ── Sidebar ──────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePanel, setActivePanel } = useUIStore()
  const [hoveredItem, setHoveredItem] = useState<string | null>(null)

  const shared = { activePanel, hoveredItem, setHoveredItem, setActivePanel }

  return (
    <aside style={styles.sidebar}>
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
    gap: 4,
    overflow: 'hidden',
  },
}
