/**
 * Icon set — P1.3 (frontend redesign): one SVG line-icon system.
 *
 * Replaces the mixed glyph vocabulary (⛁ ⏸ ⤴ ⤓ 📁 📋 📭 🎬 …) that
 * rendered differently per platform and carried no shared visual
 * language. Style matches the existing Sidebar icons: 24-viewBox line
 * icons, stroke 1.75, round caps.
 *
 * Usage: <IconFolder size={14} /> — inherits currentColor.
 */
import React from 'react'

interface IconProps {
  size?: number
  strokeWidth?: number
}

function base(size: number, strokeWidth: number, children: React.ReactNode) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    >
      {children}
    </svg>
  )
}

/** Stacked rows — queue / job list. */
export function IconQueue({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <rect x="3" y="4" width="18" height="5" rx="1.5" />
    <rect x="3" y="12" width="18" height="5" rx="1.5" />
    <path d="M3 20.5h12" />
  </>)
}

export function IconPause({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <path d="M9 5v14" />
    <path d="M15 5v14" />
  </>)
}

export function IconPlay({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <path d="M7 4.5l12 7.5-12 7.5z" />)
}

export function IconX({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <path d="M18 6L6 18M6 6l12 12" />)
}

/** Arrow to bar — send to front of queue. */
export function IconToTop({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <path d="M5 4h14" />
    <path d="M12 20V8" />
    <path d="M7 13l5-5 5 5" />
  </>)
}

/** Arrow to bar — send to back of queue. */
export function IconToBottom({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <path d="M5 20h14" />
    <path d="M12 4v12" />
    <path d="M7 11l5 5 5-5" />
  </>)
}

export function IconChevronUp({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <path d="M6 15l6-6 6 6" />)
}

export function IconChevronDown({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <path d="M6 9l6 6 6-6" />)
}

export function IconFolder({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth,
    <path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />)
}

export function IconClipboard({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <rect x="6" y="4" width="12" height="17" rx="2" />
    <path d="M9 4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2" />
  </>)
}

/** Open inbox tray — empty states. */
export function IconInbox({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <path d="M22 12h-6l-2 3h-4l-2-3H2" />
    <path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </>)
}

/** Clapper board — video / player placeholder. */
export function IconFilm({ size = 16, strokeWidth = 1.75 }: IconProps) {
  return base(size, strokeWidth, <>
    <rect x="2" y="6" width="20" height="14" rx="2" />
    <path d="M2 10h20" />
    <path d="M7 6l2 4M12 6l2 4M17 6l2 4" />
  </>)
}
