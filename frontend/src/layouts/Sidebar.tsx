import React, { useState } from 'react'
import { useUIStore } from '../stores/uiStore'
import { useRenderStore } from '../stores/renderStore'
import { isTerminalStatus } from '../types/enums'
import { useI18n } from '../i18n/useI18n'
import type { ActivePanel } from '../stores/uiStore'

// ── SVG Icon set (CapCut-style line icons 20x20) ───────────────────────────────

function IconHome() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 10.5L12 3L21 10.5V20C21 20.55 20.55 21 20 21H15V16H9V21H4C3.45 21 3 20.55 3 20V10.5Z"/>
    </svg>
  )
}

function IconScissors() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
      <circle cx="6" cy="6" r="3"/>
      <circle cx="6" cy="18" r="3"/>
      <path d="M8.46 7.54L20 19M8.46 16.46L14 12L20 5"/>
    </svg>
  )
}

function IconGrid() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5"/>
      <rect x="14" y="3" width="7" height="7" rx="1.5"/>
      <rect x="3" y="14" width="7" height="7" rx="1.5"/>
      <rect x="14" y="14" width="7" height="7" rx="1.5"/>
    </svg>
  )
}

function IconDownload() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3V16"/>
      <path d="M7 12L12 17L17 12"/>
      <path d="M3 20H21"/>
    </svg>
  )
}

function IconUpload() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V3"/>
      <path d="M7 8L12 3L17 8"/>
      <path d="M3 20H21"/>
    </svg>
  )
}

function IconSettings() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
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
  labelKey: 'nav_home' | 'nav_studio' | 'nav_library' | 'nav_download' | 'nav_publish' | 'nav_settings'
  icon: React.ReactNode
}

const MAIN_NAV: NavItem[] = [
  { panel: 'home'    as ActivePanel, labelKey: 'nav_home',     icon: <IconHome /> },
  { panel: 'studio'  as ActivePanel, labelKey: 'nav_studio',   icon: <IconScissors /> },
  { panel: 'library' as ActivePanel, labelKey: 'nav_library',  icon: <IconGrid /> },
  { panel: 'download'as ActivePanel, labelKey: 'nav_download', icon: <IconDownload /> },
  { panel: 'publish' as ActivePanel, labelKey: 'nav_publish',  icon: <IconUpload /> },
]

const BOTTOM_NAV: NavItem[] = [
  { panel: 'settings' as ActivePanel, labelKey: 'nav_settings', icon: <IconSettings /> },
]

// ── NavGroup ──────────────────────────────────────────────────────────────────

function NavGroup({ items, activePanel, hoveredItem, setHoveredItem, setActivePanel }: {
  items: NavItem[]
  activePanel: ActivePanel
  hoveredItem: string | null
  setHoveredItem: (panel: string | null) => void
  setActivePanel: (panel: ActivePanel) => void
}) {
  const { t } = useI18n()

  return (
    <>
      {items.map((item) => {
        const isActive  = activePanel === item.panel
        const isHovered = hoveredItem === item.panel

        const bgColor   = isActive ? 'var(--accent-subtle)' : isHovered ? 'rgba(255,255,255,0.05)' : 'transparent'
        const textColor = isActive ? 'var(--accent-primary)' : isHovered ? 'var(--text-primary)' : 'var(--text-secondary)'

        return (
          <button
            key={item.panel}
            style={{
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              height: '38px',
              padding: '0 var(--space-3)',
              width: '100%',
              backgroundColor: bgColor,
              color: textColor,
              fontSize: 'var(--text-sm)',
              fontWeight: isActive
                ? ('var(--weight-semibold)' as unknown as number)
                : ('var(--weight-regular)' as unknown as number),
              cursor: 'pointer',
              border: 'none',
              textAlign: 'left',
              borderRadius: '8px',
              transition: 'background-color 0.12s ease, color 0.12s ease',
            }}
            onClick={() => setActivePanel(item.panel)}
            onMouseEnter={() => setHoveredItem(item.panel)}
            onMouseLeave={() => setHoveredItem(null)}
            aria-current={isActive ? 'page' : undefined}
            title={t(item.labelKey)}
          >
            {/* Left accent bar */}
            {isActive && (
              <span style={{
                position: 'absolute',
                left: 0,
                top: '50%',
                transform: 'translateY(-50%)',
                width: '3px',
                height: '20px',
                background: 'linear-gradient(180deg, #a855f7, #4d7cff)',
                borderRadius: '0 2px 2px 0',
              }} />
            )}
            {/* Icon */}
            <span style={{ flexShrink: 0, width: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {item.icon}
            </span>
            {/* Label */}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {t(item.labelKey)}
            </span>
          </button>
        )
      })}
    </>
  )
}

// ── Language toggle ────────────────────────────────────────────────────────────

function LangToggle() {
  const { lang, setLang } = useI18n()

  return (
    <div style={langStyles.wrap}>
      <button
        style={{ ...langStyles.btn, ...(lang === 'en' ? langStyles.active : {}) }}
        onClick={() => setLang('en')}
      >EN</button>
      <div style={langStyles.divider} />
      <button
        style={{ ...langStyles.btn, ...(lang === 'vi' ? langStyles.active : {}) }}
        onClick={() => setLang('vi')}
      >VI</button>
    </div>
  )
}

const langStyles: Record<string, React.CSSProperties> = {
  wrap: {
    display: 'flex',
    alignItems: 'center',
    height: '28px',
    backgroundColor: 'var(--surface-card)',
    border: '1px solid var(--border-subtle)',
    borderRadius: '6px',
    overflow: 'hidden',
    margin: '0 var(--space-3)',
  },
  btn: {
    flex: 1,
    height: '100%',
    border: 'none',
    backgroundColor: 'transparent',
    color: 'var(--text-tertiary)',
    fontSize: '11px',
    fontWeight: 600,
    letterSpacing: '0.04em',
    cursor: 'pointer',
    transition: 'color 0.12s ease, background-color 0.12s ease',
  },
  active: {
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-subtle)',
  },
  divider: {
    width: '1px',
    height: '16px',
    backgroundColor: 'var(--border-subtle)',
    flexShrink: 0,
  },
}

// ── Sidebar ────────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { activePanel, setActivePanel } = useUIStore()
  const [hoveredItem, setHoveredItem] = useState<string | null>(null)

  const { jobs, activeJobId } = useRenderStore()
  const activeJobStatus = activeJobId ? jobs[activeJobId]?.status : null
  const hasActiveRender = !!activeJobId && !!activeJobStatus && !isTerminalStatus(activeJobStatus)

  function safeNavigate(panel: ActivePanel) {
    if (hasActiveRender && panel !== activePanel) {
      if (!window.confirm('Render job đang chạy. Chuyển trang sẽ mất kết nối progress. Tiếp tục?')) return
    }
    setActivePanel(panel)
  }

  const sharedProps = { activePanel, hoveredItem, setHoveredItem, setActivePanel: safeNavigate }

  return (
    <aside style={styles.sidebar}>
      {/* Wordmark */}
      <div style={styles.header}>
        <span style={styles.logoMark}>✦</span>
        <span style={styles.wordmark}>AI Clip Studio</span>
      </div>

      <nav style={styles.nav}>
        <NavGroup items={MAIN_NAV} {...sharedProps} />
        <div style={{ flex: 1 }} />
        <hr style={styles.separator} />
        <LangToggle />
        <div style={{ height: 'var(--space-2)' }} />
        <NavGroup items={BOTTOM_NAV} {...sharedProps} />
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
    gap: '8px',
    padding: 'var(--space-4) var(--space-4)',
    borderBottom: '1px solid var(--border-subtle)',
    height: 'var(--topbar-height)',
    flexShrink: 0,
  },
  logoMark: {
    fontSize: '16px',
    background: 'linear-gradient(135deg, #a855f7, #4d7cff)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    flexShrink: 0,
  },
  wordmark: {
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--weight-semibold)' as unknown as number,
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    letterSpacing: '-0.01em',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    padding: 'var(--space-3) var(--space-2)',
    flex: 1,
    gap: '2px',
    overflow: 'hidden',
  },
  separator: {
    margin: 'var(--space-2) var(--space-2)',
    border: 'none',
    borderTop: '1px solid var(--border-subtle)',
  },
}
