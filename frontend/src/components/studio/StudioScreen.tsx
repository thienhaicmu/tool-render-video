/**
 * StudioScreen.tsx — mode-agnostic page shell for the Studio family (Story now,
 * Content later). A gradient hero (icon + title + subtitle), an optional stepper
 * slot, optional header actions, and a body container. Presentational only — all
 * colours come from styles/tokens.css via the `.st-*` classes in studio.css, so
 * dark + light both work and no studio owns the look.
 */
import React from 'react'
import './studio.css'

export function StudioScreen({ icon, title, subtitle, stepper, actions, children }: {
  icon?: string
  title: string
  subtitle?: React.ReactNode
  stepper?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="st-screen">
      <header className="st-hero">
        <div className="st-hero-row">
          {icon && <span className="st-hero-icon" aria-hidden>{icon}</span>}
          <div className="st-hero-text">
            <h1 className="st-hero-h1">{title}</h1>
            {subtitle != null && <p className="st-hero-sub">{subtitle}</p>}
          </div>
          {actions && <div className="st-hero-actions">{actions}</div>}
        </div>
        {stepper}
      </header>
      <div className="st-body">{children}</div>
    </div>
  )
}
