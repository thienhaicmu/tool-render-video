/**
 * RenderSetupScreen — top-level screen component for the render panel.
 * Plugged into App.tsx PANEL_MAP as the 'render' panel.
 */
import React from 'react'
import { RenderForm } from './RenderForm'

export function RenderSetupScreen() {
  return (
    <div style={screenStyle}>
      <div style={headerStyle}>
        <h1 style={titleStyle}>New Render</h1>
        <p style={subtitleStyle}>
          Configure source, output settings, and creative options — then start rendering.
        </p>
      </div>
      <RenderForm />
    </div>
  )
}

const screenStyle: React.CSSProperties = {
  width: '100%',
}

const headerStyle: React.CSSProperties = {
  marginBottom: 'var(--space-6)',
}

const titleStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-2xl)',
  fontWeight: 'var(--font-weight-bold)' as unknown as number,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-2) 0',
}

const subtitleStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-base)',
  color: 'var(--color-text-secondary)',
  margin: 0,
}
