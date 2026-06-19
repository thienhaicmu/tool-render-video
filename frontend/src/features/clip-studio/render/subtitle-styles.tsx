/**
 * subtitle-styles.tsx — shared style-variant maps for subtitle preview UI.
 *
 * Three contexts render the same set of style IDs in subtly different ways:
 *   - SubtitleDemo:        live in-card preview (CSSProperties for a span)
 *   - SubStyleCard:        fallback element rendered when the image probe
 *                          fails (full React.ReactNode with label baked in)
 *   - TranscriptOverlay:   subtitle overlay over the video preview
 *                          (CSSProperties with overlay-specific sizing)
 *
 * These are the FIVE CapCut/Opus-grade presets backed by the
 * ass_capcut engine. The previews approximate the rendered look (the real
 * per-word highlight + animation happens at render time via libass).
 */
import React from 'react'

/**
 * Canonical subtitle style IDs — matches CAPCUT_PRESETS in the backend
 * ass_capcut engine. Legacy IDs are accepted by the backend (aliased) but
 * are no longer offered in the UI.
 */
export const SUBTITLE_STYLE_IDS = [
  'opus_pop',
  'capcut_box',
  'punch_green',
  'karaoke_clean',
  'smooth_premiere',
] as const

export type SubtitleStyleId = (typeof SUBTITLE_STYLE_IDS)[number]

// ── 1. SubtitleDemo — in-card live preview ───────────────────────────────────

export const DEMO_VARIANTS: Record<string, React.CSSProperties> = {
  opus_pop: {
    fontFamily: 'var(--fh)', fontSize: '18px', fontWeight: 900, color: '#fff', letterSpacing: '.5px',
    textShadow: '-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000',
  },
  capcut_box: {
    fontFamily: 'var(--fh)', fontSize: '16px', fontWeight: 900, color: '#000',
    background: '#FFE500', padding: '4px 12px', borderRadius: '6px', display: 'inline-block',
  },
  punch_green: {
    fontFamily: 'var(--fh)', fontSize: '18px', fontWeight: 900, color: '#fff', letterSpacing: '.5px',
    textShadow: '-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000',
  },
  karaoke_clean: {
    fontFamily: 'var(--fb)', fontSize: '15px', fontWeight: 700, color: '#fff',
    textShadow: '0 2px 8px rgba(0,0,0,.9), -1px -1px 0 #000, 1px 1px 0 #000',
  },
  smooth_premiere: {
    fontFamily: 'var(--fb)', fontSize: '14px', fontWeight: 500, color: '#fff', letterSpacing: '.3px',
    textShadow: '0 1px 6px rgba(0,0,0,.9)',
  },
}

/** Highlight color used by SubtitleDemo for the "AI Clip" emphasized word. */
export const DEMO_HIGHLIGHT_COLORS: Record<string, string> = {
  opus_pop: '#FFE500',
  capcut_box: '#000',
  punch_green: '#00FF7F',
  karaoke_clean: '#FFE500',
  smooth_premiere: '#fff',
}

// ── 2. SubStyleCard — image-load fallback elements ────────────────────────────

export const CARD_CSS_FALLBACK: Record<string, React.ReactNode> = {
  opus_pop:        <span style={{ color: '#fff', fontSize: '12px', fontWeight: 900, fontFamily: 'var(--fh)', textShadow: '-1px -1px 0 #000,1px 1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000' }}>POP</span>,
  capcut_box:      <span style={{ color: '#000', fontSize: '11px', fontWeight: 900, fontFamily: 'var(--fh)', background: '#FFE500', padding: '2px 9px', borderRadius: '5px', display: 'inline-block' }}>BOX</span>,
  punch_green:     <span style={{ color: '#00FF7F', fontSize: '12px', fontWeight: 900, fontFamily: 'var(--fh)', textShadow: '-1px -1px 0 #000,1px 1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000' }}>PUNCH</span>,
  karaoke_clean:   <span style={{ color: '#fff', fontSize: '11px', fontWeight: 700, fontFamily: 'var(--fb)', textShadow: '0 1px 6px rgba(0,0,0,.9),-1px -1px 0 #000' }}>Karaoke</span>,
  smooth_premiere: <span style={{ color: '#fff', fontSize: '11px', fontWeight: 500, fontFamily: 'var(--fb)', textShadow: '0 1px 6px rgba(0,0,0,.9)' }}>Smooth</span>,
}

// ── 3. TranscriptOverlay — subtitle overlay on video preview ─────────────────

export const OVERLAY_VARIANTS: Record<string, React.CSSProperties> = {
  opus_pop:        { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#fff', letterSpacing: '.5px', textShadow: '-1px -1px 0 #000,1px 1px 0 #000,0 2px 8px rgba(0,0,0,.9)' },
  capcut_box:      { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 900, color: '#000', background: '#FFE500', padding: '3px 10px', borderRadius: '5px' },
  punch_green:     { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#fff', letterSpacing: '.5px', textShadow: '-1px -1px 0 #000,1px 1px 0 #000,0 2px 8px rgba(0,0,0,.9)' },
  karaoke_clean:   { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 700, color: '#fff', textShadow: '0 2px 8px rgba(0,0,0,.9),-1px -1px 0 #000' },
  smooth_premiere: { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 500, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
}

/** Highlight color used by TranscriptOverlay. */
export const OVERLAY_HIGHLIGHT_COLORS: Record<string, string> = {
  opus_pop: '#FFE500',
  capcut_box: '#000',
  punch_green: '#00FF7F',
  karaoke_clean: '#FFE500',
  smooth_premiere: '#fff',
}
