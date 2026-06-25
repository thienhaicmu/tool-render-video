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
    minHeight: '100vh',
    backgroundColor: 'var(--surface-base)',
  } as React.CSSProperties,
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    minWidth: 0,
  } as React.CSSProperties,
  content: {
    flex: 1,
    overflowY: 'auto' as const,
  } as React.CSSProperties,
}
