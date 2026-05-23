/**
 * Sidebar — Navigation with collapse support.
 */
import React from 'react'
import { useUIStore } from '../stores/uiStore'
import type { ActivePanel } from '../stores/uiStore'

interface NavItem {
  panel: ActivePanel
  label: string
  icon: string
}

const NAV_ITEMS: NavItem[] = [
  { panel: 'render',   label: 'Render',   icon: '▶' },
  { panel: 'history',  label: 'History',  icon: '☰' },
  { panel: 'editor',   label: 'Editor',   icon: '✂' },
  { panel: 'settings', label: 'Settings', icon: '⚙' },
]

export function Sidebar() {
  const { sidebarOpen, activePanel, toggleSidebar, setActivePanel } = useUIStore()

  return (
    <aside style={{ ...styles.sidebar, width: sidebarOpen ? 'var(--sidebar-width)' : 'var(--sidebar-collapsed-width)' }}>
      <div style={styles.header}>
        {sidebarOpen && <span style={styles.logo}>Render Studio</span>}
        <button
          style={styles.collapseBtn}
          onClick={toggleSidebar}
          title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {sidebarOpen ? '◀' : '▶'}
        </button>
      </div>

      <nav style={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item.panel}
            style={{
              ...styles.navItem,
              ...(activePanel === item.panel ? styles.navItemActive : {}),
            }}
            onClick={() => setActivePanel(item.panel)}
            title={item.label}
            aria-current={activePanel === item.panel ? 'page' : undefined}
          >
            <span style={styles.navIcon}>{item.icon}</span>
            {sidebarOpen && <span style={styles.navLabel}>{item.label}</span>}
          </button>
        ))}
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
    backgroundColor: 'var(--color-bg-surface)',
    borderRight: '1px solid var(--color-border)',
    display: 'flex',
    flexDirection: 'column',
    transition: `width var(--duration-normal) var(--ease-default)`,
    overflow: 'hidden',
    zIndex: 'var(--z-raised)' as unknown as number,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-4)',
    borderBottom: '1px solid var(--color-border)',
    height: 'var(--topbar-height)',
    flexShrink: 0,
  },
  logo: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 'var(--font-weight-semibold)' as unknown as number,
    color: 'var(--color-text-primary)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
  },
  collapseBtn: {
    padding: 'var(--space-1) var(--space-2)',
    color: 'var(--color-text-secondary)',
    fontSize: 'var(--font-size-xs)',
    borderRadius: 'var(--radius-sm)',
    cursor: 'pointer',
    transition: `color var(--duration-fast)`,
    flexShrink: 0,
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-1)',
    padding: 'var(--space-3)',
    flex: 1,
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    padding: 'var(--space-2) var(--space-3)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--color-text-secondary)',
    fontSize: 'var(--font-size-base)',
    cursor: 'pointer',
    transition: `background-color var(--duration-fast), color var(--duration-fast)`,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textAlign: 'left',
    width: '100%',
  },
  navItemActive: {
    backgroundColor: 'var(--color-accent-muted)',
    color: 'var(--color-accent)',
  },
  navIcon: {
    fontSize: 'var(--font-size-md)',
    flexShrink: 0,
    width: '20px',
    textAlign: 'center',
  },
  navLabel: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
}
