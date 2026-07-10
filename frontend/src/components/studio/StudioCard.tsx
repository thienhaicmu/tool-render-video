/**
 * StudioCard.tsx — a grouped config/section card with an optional icon chip,
 * title, and right-aligned aside slot. Mode-agnostic base (mirrors Content's
 * SectionCard but owns no studio-specific strings). Tokens only.
 */
import React from 'react'

export function StudioCard({ icon, title, aside, children, className }: {
  icon?: string
  title?: string
  aside?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={`st-card${className ? ' ' + className : ''}`}>
      {(title || icon || aside) && (
        <div className="st-card-hd">
          {icon && <span className="st-card-icon" aria-hidden>{icon}</span>}
          {title && <span className="st-card-title">{title}</span>}
          {aside && <span className="st-card-aside">{aside}</span>}
        </div>
      )}
      {children}
    </section>
  )
}
