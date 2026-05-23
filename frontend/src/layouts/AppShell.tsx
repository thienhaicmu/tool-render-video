/**
 * AppShell — Root layout: sidebar + topbar + content area.
 */
import React from 'react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { useUIStore } from '../stores/uiStore'

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)

  return (
    <div style={styles.shell}>
      <Sidebar />
      <div
        style={{
          ...styles.main,
          marginLeft: sidebarOpen
            ? 'var(--sidebar-width)'
            : 'var(--sidebar-collapsed-width)',
        }}
      >
        <Topbar />
        <main style={styles.content}>
          {children}
        </main>
      </div>
    </div>
  )
}

const styles = {
  shell: {
    display: 'flex',
    minHeight: '100vh',
    backgroundColor: 'var(--color-bg-primary)',
  } as React.CSSProperties,
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    transition: `margin-left var(--duration-normal) var(--ease-default)`,
    minWidth: 0,
  } as React.CSSProperties,
  content: {
    flex: 1,
    padding: 'var(--space-6)',
    overflowY: 'auto' as const,
    maxWidth: 'var(--content-max-width)',
    width: '100%',
    margin: '0 auto',
  } as React.CSSProperties,
}
