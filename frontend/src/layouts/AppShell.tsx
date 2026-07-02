/**
 * AppShell — Root layout: sidebar + topbar + content area.
 */
import React from 'react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { ActiveJobsDock } from './ActiveJobsDock'
import { Notifications } from '../components/ui/Notifications'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div style={styles.shell}>
      <Sidebar />
      <div
        style={{
          ...styles.main,
          marginLeft: 'var(--sidebar-width)',
        }}
      >
        <Topbar />
        {/* Step strip slot — rendered by screens that need it */}
        <main style={styles.content}>
          {children}
        </main>
      </div>
      <ActiveJobsDock />
      <Notifications />
    </div>
  )
}

const styles = {
  shell: {
    display: 'flex',
    // P2.1 — definite height chain so screens using height:100% (Studio,
    // History) size correctly; each screen manages its own inner scroll.
    height: '100vh',
    overflow: 'hidden',
    backgroundColor: 'var(--surface-base)',
  } as React.CSSProperties,
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    minWidth: 0,
    minHeight: 0,
  } as React.CSSProperties,
  content: {
    flex: 1,
    minHeight: 0,
    overflowY: 'auto' as const,
    // Reserve room for the fixed ActiveJobsDock on every screen (0px when
    // the dock is hidden). Replaces .cs-root's private bottom reservation.
    paddingBottom: 'var(--active-jobs-dock-h, 0px)',
  } as React.CSSProperties,
}
