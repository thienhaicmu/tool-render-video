/**
 * Sidebar — Primary navigation. Fixed width, no collapse in B5.
 */
import React, { useState } from 'react'
import { useUIStore } from '../stores/uiStore'
import type { ActivePanel } from '../stores/uiStore'

interface NavItem {
  panel: ActivePanel
  label: string
  icon: string
}

const MAIN_NAV: NavItem[] = [
  { panel: 'home'    as ActivePanel, label: 'Home',    icon: '⌂' },
  { panel: 'studio'  as ActivePanel, label: 'Studio',  icon: '✦' },
  { panel: 'library' as ActivePanel, label: 'Library', icon: '⊟' },
  { panel: 'publish' as ActivePanel, label: 'Publish', icon: '⬆' },
]

const BOTTOM_NAV: NavItem[] = [
  { panel: 'settings' as ActivePanel, label: 'Settings', icon: '⚙' },
]

function NavGroup({ items, activePanel, hoveredItem, setHoveredItem, setActivePanel }: {
  items: NavItem[]
  activePanel: ActivePanel
  hoveredItem: string | null
  setHoveredItem: (panel: string | null) => void
  setActivePanel: (panel: ActivePanel) => void
}) {
  return (
    <>
      {items.map((item) => {
        const isActive = activePanel === item.panel
        const isHovered = hoveredItem === item.panel

        let bgColor = 'transparent'
        let textColor = 'var(--text-secondary)'

        if (isActive) {
          bgColor = 'var(--accent-subtle)'
          textColor = 'var(--accent-primary)'
        } else if (isHovered) {
          bgColor = 'var(--surface-card)'
          textColor = 'var(--text-primary)'
        }

        return (
          <button
            key={item.panel}
            style={{
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-3)',
              height: '36px',
              padding: '0 var(--space-4)',
              width: '100%',
              backgroundColor: bgColor,
              color: textColor,
              fontSize: 'var(--text-base)',
              fontWeight: 'var(--weight-medium)' as unknown as number,
              cursor: 'pointer',
              border: 'none',
              textAlign: 'left',
              borderRadius: 'var(--radius-md)',
              transition: `background-color var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out)`,
            }}
            onClick={() => setActivePanel(item.panel)}
            onMouseEnter={() => setHoveredItem(item.panel)}
            onMouseLeave={() => setHoveredItem(null)}
            aria-current={isActive ? 'page' : undefined}
            title={item.label}
          >
            {/* Left accent bar — visible only when active */}
            {isActive && (
              <span
                style={{
                  position: 'absolute',
                  left: 0,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '20px',
                  backgroundColor: 'var(--accent-primary)',
                  borderRadius: '1px',
                }}
              />
            )}
            <span style={{ fontSize: '18px', width: '18px', textAlign: 'center', flexShrink: 0 }}>
              {item.icon}
            </span>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.label}
            </span>
          </button>
        )
      })}
    </>
  )
}

export function Sidebar() {
  const { activePanel, setActivePanel } = useUIStore()
  const [hoveredItem, setHoveredItem] = useState<string | null>(null)

  const sharedProps = { activePanel, hoveredItem, setHoveredItem, setActivePanel }

  return (
    <aside style={styles.sidebar}>
      {/* Header / wordmark */}
      <div style={styles.header}>
        <span style={styles.wordmark}>AI Clip Studio</span>
      </div>

      <nav style={styles.nav}>
        <NavGroup items={MAIN_NAV} {...sharedProps} />

        <div style={{ flex: 1 }} />

        <hr style={{ borderTop: '1px solid var(--border-subtle)', border: 'none', margin: 'var(--space-2) 0' }} />

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
    padding: 'var(--space-4)',
    borderBottom: '1px solid var(--border-subtle)',
    height: 'var(--topbar-height)',
    flexShrink: 0,
  },
  wordmark: {
    fontSize: 'var(--text-md)',
    fontWeight: 'var(--weight-semibold)' as unknown as number,
    color: 'var(--text-primary)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    padding: 'var(--space-3)',
    flex: 1,
    gap: '2px',
  },
  separator: {
    margin: 'var(--space-2) 0',
    border: 'none',
    borderTop: '1px solid var(--border-subtle)',
  },
}
