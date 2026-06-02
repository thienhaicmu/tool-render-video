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
 * Sprint 5.8 (audit 2026-06-02 P2-F4) — these were duplicated 3× inline
 * inside StepConfigure.tsx, which drifted over time (some IDs in one map,
 * missing in another). Centralizing makes drift visible.
 */
import React from 'react'

/**
 * The canonical list of valid subtitle style IDs. Adding a new style means
 * adding it here AND to each of the three variant maps below. TypeScript
 * does NOT enforce key parity across the three maps — engineer discipline
 * does. Leave the existing IDs in the same order in all three maps for
 * easier diffing.
 */
export const SUBTITLE_STYLE_IDS = [
  'pro_karaoke',
  'tiktok_bounce_v1',
  'viral_bold',
  'bold_cap',
  'story_clean_01',
  'boxed_caption',
  'clean_pro',
  'gaming',
  'neon_glow',
  'fire_bold',
  'color_pop',
  'dark_card',
  'slay_soft',
  'bold_stroke',
] as const

export type SubtitleStyleId = (typeof SUBTITLE_STYLE_IDS)[number]

// ── 1. SubtitleDemo — in-card live preview ───────────────────────────────────

export const DEMO_VARIANTS: Record<string, React.CSSProperties> = {
  pro_karaoke: {
    fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 700, color: '#fff', letterSpacing: '.5px',
    textShadow: '0 2px 8px rgba(0,0,0,.9), -1px -1px 0 #000, 1px 1px 0 #000',
  },
  tiktok_bounce_v1: {
    fontFamily: 'var(--fh)', fontSize: '17px', fontWeight: 800, color: '#fff', letterSpacing: '1px',
    textShadow: '-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000',
  },
  viral_bold: {
    fontFamily: 'var(--fh)', fontSize: '18px', fontWeight: 900, color: '#FFE500', textTransform: 'uppercase',
    textShadow: '-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000',
  },
  bold_cap: {
    fontFamily: 'var(--fh)', fontSize: '16px', fontWeight: 900, color: '#fff', textTransform: 'uppercase',
    textShadow: '-1px -1px 0 #000, 1px 1px 0 #000, 0 2px 6px rgba(0,0,0,.8)',
  },
  story_clean_01: {
    fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 500, color: '#fff',
    background: 'rgba(0,0,0,.55)', padding: '5px 14px', borderRadius: '2px',
    display: 'inline-block',
  },
  boxed_caption: {
    fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 700, color: '#fff',
    background: '#000', padding: '4px 12px', display: 'inline-block',
  },
  clean_pro: {
    fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 400, color: '#fff',
    textShadow: '0 1px 6px rgba(0,0,0,.9)',
  },
  gaming: {
    fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 700, color: '#00E5C8', letterSpacing: '1px',
    textShadow: '0 0 12px rgba(0,229,200,.8), -1px -1px 0 #000, 1px 1px 0 #000',
  },
  neon_glow: {
    fontFamily: 'var(--fh)', fontSize: '16px', fontWeight: 900, color: '#fff', letterSpacing: '.5px',
    textShadow: '0 0 8px #0ff, 0 0 20px #0ff, -2px -2px 0 #0ff, 2px 2px 0 #0ff',
  },
  fire_bold: {
    fontFamily: 'var(--fh)', fontSize: '18px', fontWeight: 900, color: '#FFE500', textTransform: 'uppercase',
    textShadow: '-2px -2px 0 #FF4500, 2px 2px 0 #FF4500, 0 0 10px rgba(255,69,0,.6)',
  },
  color_pop: {
    fontFamily: 'var(--fh)', fontSize: '18px', fontWeight: 900, color: '#FFE500',
    textShadow: '-3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000',
  },
  dark_card: {
    fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 700, color: '#fff',
    background: 'rgba(0,0,0,.78)', padding: '5px 14px', borderRadius: '4px',
    display: 'inline-block',
  },
  slay_soft: {
    fontFamily: 'var(--fh)', fontSize: '16px', fontWeight: 800, color: '#fff',
    textShadow: '-2px -2px 0 #FF69B4, 2px 2px 0 #FF69B4, 0 0 12px rgba(255,105,180,.5)',
  },
  bold_stroke: {
    fontFamily: 'var(--fh)', fontSize: '19px', fontWeight: 900, color: '#fff', textTransform: 'uppercase',
    textShadow: '-3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000, -3px 0 0 #000, 3px 0 0 #000',
  },
}

/** Highlight color used by SubtitleDemo for the "AI Clip" emphasized word. */
export const DEMO_HIGHLIGHT_COLORS: Record<string, string> = {
  pro_karaoke: '#00FF00',
  tiktok_bounce_v1: '#00E5C8',
  viral_bold: '#fff',
  bold_cap: '#00E5C8',
  gaming: '#fff',
}

// ── 2. SubStyleCard — image-load fallback elements ────────────────────────────

export const CARD_CSS_FALLBACK: Record<string, React.ReactNode> = {
  tiktok_bounce_v1: <span style={{ color: '#fff', fontSize: '12px', fontWeight: 900, fontFamily: 'var(--fh)', textShadow: '-1px -1px 0 #000,1px 1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000' }}>BOUNCE</span>,
  viral_bold:  <span style={{ color: '#FFE500', fontSize: '12px', fontWeight: 900, fontFamily: 'var(--fh)', textTransform: 'uppercase', textShadow: '-1.5px -1.5px 0 #000,1.5px 1.5px 0 #000,1.5px -1.5px 0 #000,-1.5px 1.5px 0 #000' }}>VIRAL</span>,
  bold_cap:    <span style={{ color: '#fff', fontSize: '12px', fontWeight: 900, fontFamily: 'var(--fh)', textTransform: 'uppercase', textShadow: '-1px -1px 0 #000,1px 1px 0 #000,0 2px 8px rgba(0,0,0,.9)' }}>CAPS</span>,
  clean_pro:   <span style={{ color: '#fff', fontSize: '11px', fontWeight: 400, fontFamily: 'var(--fb)', textShadow: '0 1px 6px rgba(0,0,0,.9)' }}>Clean</span>,
  story_clean_01: <span style={{ background: 'rgba(0,0,0,.6)', padding: '2px 8px', borderRadius: '2px', color: '#f6f6f6', fontSize: '10px', fontWeight: 500, fontFamily: 'var(--fb)', display: 'inline-block' }}>Story</span>,
  gaming:      <span style={{ color: '#00E5C8', fontSize: '12px', fontWeight: 700, fontFamily: 'var(--fh)', letterSpacing: '1px', textShadow: '0 0 10px rgba(0,229,200,.9),-1px -1px 0 #000,1px 1px 0 #000' }}>GAMING</span>,
  neon_glow:   <span style={{ color: '#fff', fontSize: '13px', fontWeight: 900, fontFamily: 'var(--fh)', textShadow: '0 0 8px #0ff,0 0 18px #0ff,-1px -1px 0 #0ff,1px 1px 0 #0ff' }}>NEON</span>,
  fire_bold:   <span style={{ color: '#FFE500', fontSize: '13px', fontWeight: 900, fontFamily: 'var(--fh)', textTransform: 'uppercase', textShadow: '-1.5px -1.5px 0 #FF4500,1.5px 1.5px 0 #FF4500,0 0 8px rgba(255,69,0,.7)' }}>FIRE</span>,
  color_pop:   <span style={{ color: '#FFE500', fontSize: '13px', fontWeight: 900, fontFamily: 'var(--fh)', textShadow: '-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000' }}>POP!</span>,
  dark_card:   <span style={{ background: 'rgba(0,0,0,.78)', padding: '2px 10px', borderRadius: '4px', color: '#fff', fontSize: '10px', fontWeight: 600, fontFamily: 'var(--fb)', display: 'inline-block' }}>Card</span>,
  slay_soft:   <span style={{ color: '#fff', fontSize: '13px', fontWeight: 900, fontFamily: 'var(--fh)', textShadow: '-1.5px -1.5px 0 #FF69B4,1.5px 1.5px 0 #FF69B4,0 0 8px rgba(255,105,180,.5)' }}>SLAY</span>,
  bold_stroke: <span style={{ color: '#fff', fontSize: '13px', fontWeight: 900, fontFamily: 'var(--fh)', textTransform: 'uppercase', textShadow: '-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000,-2px 0 0 #000,2px 0 0 #000' }}>STROKE</span>,
}

// ── 3. TranscriptOverlay — subtitle overlay on video preview ─────────────────

export const OVERLAY_VARIANTS: Record<string, React.CSSProperties> = {
  pro_karaoke:      { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 800, color: '#fff', textShadow: '-1px -1px 0 #000, 1px 1px 0 #000' },
  tiktok_bounce_v1: { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '0 2px 8px rgba(0,0,0,.9)' },
  viral_bold:       { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#FFE500', letterSpacing: '1px', textShadow: '-1px -1px 0 #000,1px 1px 0 #000' },
  bold_cap:         { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 900, color: '#fff', textTransform: 'uppercase', textShadow: '0 2px 8px rgba(0,0,0,.9)' },
  boxed_caption:    { fontFamily: 'var(--fb)', fontSize: '12px', fontWeight: 700, color: '#fff', background: 'rgba(0,0,0,.75)', padding: '3px 8px', borderRadius: '4px' },
  story_clean_01:   { fontFamily: 'var(--fb)', fontSize: '12px', fontWeight: 400, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
  clean_pro:        { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 400, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
  gaming:           { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 700, color: '#00E5C8', letterSpacing: '1px', textShadow: '0 0 12px rgba(0,229,200,.8)' },
  neon_glow:        { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '0 0 8px #0ff,0 0 18px #0ff,-1px -1px 0 #0ff,1px 1px 0 #0ff' },
  fire_bold:        { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#FFE500', textTransform: 'uppercase', textShadow: '-1.5px -1.5px 0 #FF4500,1.5px 1.5px 0 #FF4500' },
  color_pop:        { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#FFE500', textShadow: '-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000' },
  dark_card:        { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 600, color: '#fff', background: 'rgba(0,0,0,.78)', padding: '3px 10px', borderRadius: '4px' },
  slay_soft:        { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '-1.5px -1.5px 0 #FF69B4,1.5px 1.5px 0 #FF69B4,0 0 10px rgba(255,105,180,.5)' },
  bold_stroke:      { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#fff', textTransform: 'uppercase', textShadow: '-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000,-2px 0 0 #000,2px 0 0 #000' },
}

/** Highlight color used by TranscriptOverlay (broader set than DEMO version). */
export const OVERLAY_HIGHLIGHT_COLORS: Record<string, string> = {
  pro_karaoke: '#00FF00',
  tiktok_bounce_v1: '#00E5C8',
  viral_bold: '#fff',
  bold_cap: '#00E5C8',
  gaming: '#fff',
  neon_glow: '#0ff',
  fire_bold: '#fff',
  color_pop: '#fff',
  dark_card: '#0ff',
  slay_soft: '#FF69B4',
  bold_stroke: '#FFE500',
}
