/**
 * ThemeToggle — segmented control (light / system / dark).
 *
 * Reusable across shells (AppShell topbar + cs-shell topbar).
 * Reads/writes via stores/themeStore — single source of truth.
 */
import React from 'react'
import { useThemeStore, type ThemePreference } from '../../stores/themeStore'

function IconSun() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4"/>
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
    </svg>
  )
}

function IconMoon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  )
}

function IconMonitor() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2"/>
      <path d="M8 21h8M12 17v4"/>
    </svg>
  )
}

const OPTIONS: { value: ThemePreference; label: string; icon: React.ReactNode }[] = [
  { value: 'light',  label: 'Light',  icon: <IconSun /> },
  { value: 'system', label: 'System', icon: <IconMonitor /> },
  { value: 'dark',   label: 'Dark',   icon: <IconMoon /> },
]

export function ThemeToggle({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const { preference, setPreference } = useThemeStore()
  const dim = size === 'sm' ? 22 : 24
  const wrap = size === 'sm' ? 26 : 28

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: wrap,
        padding: 2,
        gap: 2,
        backgroundColor: 'var(--surface-card, rgba(0,0,0,0.2))',
        border: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
        borderRadius: 'var(--radius-md, 6px)',
      }}
    >
      {OPTIONS.map((opt) => {
        const isActive = preference === opt.value
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            title={opt.label}
            onClick={() => setPreference(opt.value)}
            style={{
              width: dim + 2,
              height: dim,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
              backgroundColor: isActive ? 'var(--surface-base)' : 'transparent',
              color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)',
              borderRadius: 'var(--radius-sm, 4px)',
              cursor: 'pointer',
              boxShadow: isActive ? 'var(--shadow-sm)' : 'none',
              transition: 'color 0.12s ease, background-color 0.12s ease, box-shadow 0.12s ease',
            }}
          >
            {opt.icon}
          </button>
        )
      })}
    </div>
  )
}
