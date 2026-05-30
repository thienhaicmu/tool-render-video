import React, { useState, useEffect } from 'react'
import { BASE_URL } from '../../../../api/client'
import { getPreviewVideoUrl, getPreviewTranscript, testCloudAi } from '../../../../api/render'
import type { TranscriptSegment, PrepareSourceResponse } from '../../../../api/render'
import type { ConfigState, CfgTab, Source, Ratio } from '../types'
import type { Strings } from '../i18n'
import { RATIO_INFO, STYLES, SUB_STYLE_GROUPS, QUALITY_MAP } from '../constants'
import { fmtDuration, Tog } from '../utils'

// ── Subtitle preview — visual approximation of each style ────────────────────
function SubtitleDemo({ style }: { style: string }) {
  const baseBox: React.CSSProperties = {
    position: 'absolute', bottom: '20px', left: 0, right: 0,
    textAlign: 'center', padding: '0 10px', pointerEvents: 'none', zIndex: 2,
  }

  const variants: Record<string, React.CSSProperties> = {
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

  const textStyle = variants[style] ?? variants['pro_karaoke']
  const hlColor: Record<string, string> = {
    pro_karaoke: '#00FF00', tiktok_bounce_v1: '#00E5C8', viral_bold: '#fff',
    bold_cap: '#00E5C8', gaming: '#fff',
  }
  const hlC = hlColor[style] ?? 'var(--cyan)'

  return (
    <div style={baseBox}>
      <span style={textStyle}>
        Đây là{' '}
        <span style={{ color: hlC, WebkitTextFillColor: hlC }}> AI Clip</span>
        {' '}Studio
      </span>
    </div>
  )
}

// ── SubtitlePreview — real FFmpeg/libass rendered preview frame ───────────────
function SubtitlePreview({ style, aspectRatio, fontSize }: {
  style: string; aspectRatio: string; fontSize: number
}) {
  const [imgSrc, setImgSrc] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed]  = useState(false)

  useEffect(() => {
    setLoading(true)
    setFailed(false)
    const params = new URLSearchParams({
      style,
      aspect_ratio: aspectRatio,
      font_size: String(fontSize > 0 ? fontSize : 0),
      text: 'This is a preview subtitle',
    })
    const url = `${BASE_URL}/api/render/subtitle-preview?${params}`
    const timer = setTimeout(() => {
      const img = new Image()
      img.onload  = () => { setImgSrc(url); setLoading(false) }
      img.onerror = () => { setFailed(true); setLoading(false) }
      img.src = url
    }, 350)
    return () => clearTimeout(timer)
  }, [style, aspectRatio, fontSize])

  if (failed) return <SubtitleDemo style={style} />

  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'stretch' }}>
      {loading && (
        <div style={{
          position: 'absolute', inset: 0,
          background: 'rgba(17,24,39,.85)',
          display: 'flex', alignItems: 'flex-end', justifyContent: 'center', paddingBottom: 24,
        }}>
          <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid rgba(255,255,255,.15)', borderTopColor: 'var(--accent)', animation: 'rw-spin .8s linear infinite' }} />
        </div>
      )}
      {imgSrc && (
        <img
          src={imgSrc}
          alt="Subtitle preview"
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      )}
    </div>
  )
}

// ── SubStyleCard — loads real FFmpeg/libass preview from /api/render/subtitle-preview
// Falls back to CSS approximation only when backend is unreachable.
function SubStyleCard({ id, label, selected, onSelect }: {
  id: string; label: string; selected: boolean; onSelect: () => void
}) {
  const [imgSrc, setImgSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams({ style: id, aspect_ratio: '9:16', font_size: '0', text: 'AI Clip' })
    const url = `${BASE_URL}/api/render/subtitle-preview?${params}`
    const img = new Image()
    img.onload  = () => { if (!cancelled) setImgSrc(url) }
    img.onerror = () => { if (!cancelled) setFailed(true) }
    img.src = url
    return () => { cancelled = true }
  }, [id])

  // CSS fallbacks — shown only when backend is unavailable
  const CSS_FALLBACK: Record<string, React.ReactNode> = {
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

  return (
    <div
      className={`sub-style-card${selected ? ' on' : ''}`}
      onClick={onSelect}
    >
      <div className="ssc-frame" style={{ overflow: 'hidden' }}>
        {imgSrc ? (
          <img src={imgSrc} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        ) : failed ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
            {CSS_FALLBACK[id] ?? <span style={{ color: '#888', fontSize: '10px' }}>{label}</span>}
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid rgba(255,255,255,.15)', borderTopColor: 'var(--accent)', animation: 'rw-spin .8s linear infinite' }} />
          </div>
        )}
      </div>
      <span className="ssc-label">{label}</span>
    </div>
  )
}

// ── TranscriptOverlay — subtitle preview overlaid on video, cycles through segs ──
function TranscriptOverlay({ sessionId, subStyle, subEnabled }: { sessionId: string; subStyle: string; subEnabled: boolean }) {
  const [segs, setSegs] = useState<TranscriptSegment[] | null>(null)
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    let cancelled = false
    getPreviewTranscript(sessionId).then(res => {
      if (!cancelled) setSegs(res.segments?.slice(0, 30) ?? [])
    }).catch(() => {
      if (!cancelled) setSegs([])
    })
    return () => { cancelled = true }
  }, [sessionId])

  useEffect(() => {
    if (!segs?.length) return
    const id = setInterval(() => setIdx(i => (i + 1) % segs.length), 2500)
    return () => clearInterval(id)
  }, [segs])

  if (!segs?.length) return null

  const text = segs[idx]?.text ?? ''
  const words = text.trim().split(/\s+/)
  const hlIdx = Math.floor(words.length / 2)

  const variants: Record<string, React.CSSProperties> = {
    pro_karaoke:      { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 800, color: '#fff', textShadow: '-1px -1px 0 #000, 1px 1px 0 #000' },
    tiktok_bounce_v1: { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '0 2px 8px rgba(0,0,0,.9)' },
    viral_bold:       { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#FFE500', letterSpacing: '1px', textShadow: '-1px -1px 0 #000,1px 1px 0 #000' },
    bold_cap:         { fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 900, color: '#fff', textTransform: 'uppercase' as const, textShadow: '0 2px 8px rgba(0,0,0,.9)' },
    boxed_caption:    { fontFamily: 'var(--fb)', fontSize: '12px', fontWeight: 700, color: '#fff', background: 'rgba(0,0,0,.75)', padding: '3px 8px', borderRadius: '4px' },
    story_clean_01:   { fontFamily: 'var(--fb)', fontSize: '12px', fontWeight: 400, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
    clean_pro:        { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 400, color: '#fff', textShadow: '0 1px 6px rgba(0,0,0,.9)' },
    gaming:           { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 700, color: '#00E5C8', letterSpacing: '1px', textShadow: '0 0 12px rgba(0,229,200,.8)' },
    neon_glow:        { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '0 0 8px #0ff,0 0 18px #0ff,-1px -1px 0 #0ff,1px 1px 0 #0ff' },
    fire_bold:        { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#FFE500', textTransform: 'uppercase' as const, textShadow: '-1.5px -1.5px 0 #FF4500,1.5px 1.5px 0 #FF4500' },
    color_pop:        { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#FFE500', textShadow: '-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000' },
    dark_card:        { fontFamily: 'var(--fb)', fontSize: '13px', fontWeight: 600, color: '#fff', background: 'rgba(0,0,0,.78)', padding: '3px 10px', borderRadius: '4px' },
    slay_soft:        { fontFamily: 'var(--fh)', fontSize: '14px', fontWeight: 900, color: '#fff', textShadow: '-1.5px -1.5px 0 #FF69B4,1.5px 1.5px 0 #FF69B4,0 0 10px rgba(255,105,180,.5)' },
    bold_stroke:      { fontFamily: 'var(--fh)', fontSize: '15px', fontWeight: 900, color: '#fff', textTransform: 'uppercase' as const, textShadow: '-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000,-2px 0 0 #000,2px 0 0 #000' },
  }
  const hlColor: Record<string, string> = {
    pro_karaoke: '#00FF00', tiktok_bounce_v1: '#00E5C8', viral_bold: '#fff',
    bold_cap: '#00E5C8', gaming: '#fff', neon_glow: '#0ff',
    fire_bold: '#fff', color_pop: '#fff', dark_card: '#0ff',
    slay_soft: '#FF69B4', bold_stroke: '#FFE500',
  }
  const style = variants[subStyle] ?? variants['clean_pro']
  const hlC = hlColor[subStyle] ?? 'var(--cyan)'

  const showSub = subEnabled

  return (
    <div style={{
      position: 'absolute', bottom: '18%', left: 0, right: 0,
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      gap: '2px', padding: '0 8px', pointerEvents: 'none',
    }}>
      <div style={{
        background: 'rgba(0,0,0,.55)', borderRadius: '4px', padding: '3px 8px',
        fontSize: '9px', color: 'rgba(255,255,255,.7)', fontFamily: 'var(--fb)',
        maxWidth: '90%', textAlign: 'center', lineHeight: 1.4,
        display: showSub ? 'none' : 'block',
      }}>
        {text}
      </div>

      {showSub && (
        <div style={{ ...style, maxWidth: '90%', textAlign: 'center', lineHeight: 1.5 }}>
          {words.map((w, i) => (
            <span key={i}>
              {i === hlIdx
                ? <span style={{ color: hlC, WebkitTextFillColor: hlC }}>{w}</span>
                : w}
              {i < words.length - 1 ? ' ' : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Step 2 — Configure ────────────────────────────────────────────────────────
export function StepConfigure({
  cfg, cfgTab, setCfgTab, setCfgKey, applyPreset,
  sources, prepareResult, pickOutputDir, onChangeSource, t,
}: {
  cfg: ConfigState
  cfgTab: CfgTab
  setCfgTab: (tab: CfgTab) => void
  setCfgKey: <K extends keyof ConfigState>(k: K, v: ConfigState[K]) => void
  applyPreset: (id: string) => void
  sources: Source[]
  prepareResult: PrepareSourceResponse | null
  pickOutputDir: () => void
  onChangeSource: () => void
  t: Strings
}) {
  void applyPreset
  const [cfgMode, setCfgMode] = React.useState<'quick' | 'advanced'>('quick')
  const adv = cfgMode === 'advanced'

  type TestStatus = 'idle' | 'testing' | 'ok' | 'error'
  const [testStatus, setTestStatus] = React.useState<TestStatus>('idle')
  const [testMsg, setTestMsg]       = React.useState('')

  async function handleTestConnection() {
    if (!cfg.aiCloudApiKey) return
    setTestStatus('testing')
    setTestMsg('')
    try {
      const res = await testCloudAi(
        cfg.aiCloudProvider,
        cfg.aiCloudApiKey,
        cfg.aiCloudModel || undefined,
      )
      if (res.ok) {
        setTestStatus('ok')
        setTestMsg(`${res.model} · ${res.latency_ms}ms`)
      } else {
        setTestStatus('error')
        setTestMsg(res.error ?? 'Connection failed')
      }
    } catch {
      setTestStatus('error')
      setTestMsg('Request failed')
    }
  }

  const src          = sources[0]
  const ratioInfo    = RATIO_INFO[cfg.ratio]
  const previewVideoUrl = prepareResult ? getPreviewVideoUrl(prepareResult.session_id) : null
  const styleLabel   = STYLES.find(s => s.id === cfg.style)?.label ?? cfg.style
  const activeSubGroup = SUB_STYLE_GROUPS.find(g => g.ids.includes(cfg.subStyle))?.set ?? 'clean_pro'
  const qualityLabel   = QUALITY_MAP.find(q => q.v === cfg.renderProfile)?.l ?? '1080p'

  void activeSubGroup

  return (
    <div className="cfg-screen">

      {/* ── LEFT ──────────────────────────────────────────────────────────── */}
      <div className="cfg-left">

        {/* ── Quick / Advanced mode toggle ── */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <div style={{ display: 'flex', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, padding: 3, gap: 3 }}>
            {(['quick', 'advanced'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setCfgMode(m)}
                style={{
                  padding: '4px 14px', borderRadius: 6, fontSize: 11, fontWeight: 700,
                  letterSpacing: '.04em', textTransform: 'uppercase', cursor: 'pointer', border: 'none',
                  background: cfgMode === m ? 'var(--accent)' : 'transparent',
                  color: cfgMode === m ? '#fff' : 'var(--text-3)',
                  transition: 'background .12s, color .12s',
                }}
              >
                {m === 'quick' ? 'Quick' : 'Advanced'}
              </button>
            ))}
          </div>
        </div>

        {/* Source card */}
        <div className="cfg-src-card">
          <div className="cfg-src-thumb">📁</div>
          <div className="cfg-src-info">
            <div className="cfg-src-name">
              {prepareResult?.title || (src?.value ? src.value.slice(0, 28) + '…' : 'No source')}
            </div>
            <div className="cfg-src-meta">
              {prepareResult ? fmtDuration(prepareResult.duration) : 'Local File'}
            </div>
            <button className="cfg-src-change" onClick={onChangeSource}>{t.cfgChangeSource}</button>
          </div>
        </div>

        {/* C. Duration */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>CLIP DURATION</span>
            <span className="cfg-sec-api">min_part_sec · max_part_sec</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
            {[
              { min: 30,  max: 60  },
              { min: 45,  max: 90  },
              { min: 60,  max: 120 },
              { min: 90,  max: 180 },
            ].map(({ min, max }) => (
              <div key={`${min}-${max}`}
                className={`seg-b${cfg.minSec === min && cfg.maxSec === max ? ' on' : ''}`}
                onClick={() => { setCfgKey('minSec', min); setCfgKey('maxSec', max) }}>
                {min}–{max}s
              </div>
            ))}
          </div>
          {adv && (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '8px' }}>
            <span style={{ fontSize: '10px', color: 'var(--text-3)', width: '28px' }}>MIN</span>
            <input
              type="number" min={15} max={300} value={cfg.minSec}
              onChange={e => { const v = parseInt(e.target.value, 10); if (!isNaN(v)) setCfgKey('minSec', Math.max(15, Math.min(300, v))) }}
              style={{ width: '56px', padding: '3px 5px', borderRadius: '5px', fontSize: '11px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-1)', textAlign: 'right', outline: 'none' }}
            />
            <span style={{ fontSize: '10px', color: 'var(--text-3)' }}>s</span>
            <span style={{ fontSize: '10px', color: 'var(--text-3)', width: '28px', marginLeft: '6px' }}>MAX</span>
            <input
              type="number" min={15} max={600} value={cfg.maxSec}
              onChange={e => { const v = parseInt(e.target.value, 10); if (!isNaN(v)) setCfgKey('maxSec', Math.max(15, Math.min(600, v))) }}
              style={{ width: '56px', padding: '3px 5px', borderRadius: '5px', fontSize: '11px', border: '1px solid var(--border)', background: 'var(--bg-card)', color: 'var(--text-1)', textAlign: 'right', outline: 'none' }}
            />
            <span style={{ fontSize: '10px', color: 'var(--text-3)' }}>s</span>
          </div>
          )}
        </div>

        {/* D. Output count */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>OUTPUT VIDEOS</span>
            <span className="cfg-sec-api">output_count</span>
          </div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
            {[1, 3, 5, 10].map(v => (
              <div key={v} className={`seg-b${cfg.outputCount === v ? ' on' : ''}`}
                onClick={() => setCfgKey('outputCount', v)}>{v}</div>
            ))}
            <div className="clip-count-row">
              <button className="cnt-btn" onClick={() => setCfgKey('outputCount', Math.max(1, cfg.outputCount - 1))}>−</button>
              <span className="cnt-val">{cfg.outputCount}</span>
              <button className="cnt-btn" onClick={() => setCfgKey('outputCount', Math.min(20, cfg.outputCount + 1))}>+</button>
            </div>
          </div>
        </div>

        {/* A. Platform */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>{t.cfgPlatform}</span>
            <span className="cfg-sec-api">target_platform</span>
          </div>
          <div className="seg">
            {([
              { v: 'tiktok'          as const, l: 'TikTok'   },
              { v: 'youtube_shorts'  as const, l: 'YT Short' },
              { v: 'instagram_reels' as const, l: 'Reels'    },
            ]).map(({ v, l }) => (
              <div key={v} className={`seg-b${cfg.platform === v ? ' on' : ''}`}
                onClick={() => setCfgKey('platform', v)}>{l}</div>
            ))}
          </div>
        </div>

        {/* A. Frame */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>FRAME</span>
            <span className="cfg-sec-api">aspect_ratio</span>
          </div>
          <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
            {(['r916', 'r34', 'r45', 'r11', 'r169'] as Ratio[]).map(r => (
              <div key={r} className={`seg-b${cfg.ratio === r ? ' on' : ''}`}
                onClick={() => setCfgKey('ratio', r)}>{RATIO_INFO[r].label}</div>
            ))}
          </div>
        </div>

        {/* A. Quality */}
        {adv && (
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>QUALITY</span>
            <span className="cfg-sec-api">render_profile</span>
          </div>
          <div className="seg">
            {QUALITY_MAP.map(({ v, l }) => (
              <div key={v} className={`seg-b${cfg.renderProfile === v ? ' on' : ''}`}
                onClick={() => setCfgKey('renderProfile', v)}>{l}</div>
            ))}
          </div>
        </div>
        )}

        {/* M. Output folder */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>{t.cfgSaveFolder}</span>
            <span className="cfg-sec-api">output_dir</span>
          </div>
          <div className="dir-row">
            <input className="dir-in" type="text" placeholder="D:\Videos\Output" value={cfg.outputDir}
              onChange={(e) => setCfgKey('outputDir', e.target.value)} />
            <button className="btn-xs" onClick={pickOutputDir}>Browse</button>
          </div>
          {prepareResult?.export_dir && (
            <div style={{ fontSize: '10px', color: 'var(--text-3)', marginTop: '6px', wordBreak: 'break-all', lineHeight: 1.5 }}>
              Default: {prepareResult.export_dir}
            </div>
          )}
        </div>

      </div>{/* /cfg-left */}

      {/* ── CENTER ────────────────────────────────────────────────────────── */}
      <div className="cfg-center">
        <div className="cfg-center-top">
          <span className="pv-chip ac">{ratioInfo.label} · {ratioInfo.sub}</span>
          <span className="pv-chip cy">{styleLabel}</span>
          <span className="pv-chip">{cfg.platform.replace(/_/g, ' ')}</span>
          <div style={{ flex: 1 }} />
          <span className="pv-chip">{cfg.targetDuration}s</span>
          <span className="pv-chip">×{cfg.outputCount}</span>
          <span className="pv-chip">{qualityLabel}</span>
        </div>

        <div className="cfg-canvas">
          <div className="pv-grid-bg" />
          <div className={`pv-frame ${cfg.ratio}`}>
            <span className="pvc tl" /><span className="pvc tr" />
            <span className="pvc bl" /><span className="pvc br" />
            {previewVideoUrl ? (
              <>
                <video
                  key={previewVideoUrl}
                  src={previewVideoUrl}
                  autoPlay muted loop playsInline
                  style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                />
                {cfg.subEnabled && <SubtitleDemo style={cfg.subStyle} />}
              </>
            ) : cfg.subEnabled ? (
              <SubtitlePreview
                style={cfg.subStyle}
                aspectRatio={RATIO_INFO[cfg.ratio].api}
                fontSize={cfg.subFontSize}
              />
            ) : (
              <div className="pv-placeholder">
                <span className="pv-play">▶</span>
                <span className="pv-hint">Preview updates as you configure</span>
              </div>
            )}
            {prepareResult && (
              <TranscriptOverlay sessionId={prepareResult.session_id} subStyle={cfg.subStyle} subEnabled={cfg.subEnabled} />
            )}
          </div>
        </div>

        <div className="cfg-style-strip">
          <div className="cfg-sec-hd" style={{ marginBottom: '10px' }}>
            <span>{t.cfgVisualStyle}</span>
            <span className="cfg-sec-api">effect_preset</span>
          </div>
          <div className="style-strip-list">
            {STYLES.map((s) => (
              <div key={s.id} className={`style-strip-c${cfg.style === s.id ? ' on' : ''}`}
                onClick={() => setCfgKey('style', s.id)}>
                <div className="style-strip-ico">{s.ico}</div>
                <div className="style-strip-nm">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>{/* /cfg-center */}

      {/* ── RIGHT ─────────────────────────────────────────────────────────── */}
      <div className="cfg-right">
        <div className="cfg-tabs">
          {([
            { id: 'ai'     as CfgTab, label: t.cfgTabAI     },
            { id: 'sub'    as CfgTab, label: t.cfgTabSub    },
            { id: 'narr'   as CfgTab, label: t.cfgTabNarr   },
          ]).map((tab) => (
            <button key={tab.id} className={`cfg-tab${cfgTab === tab.id ? ' on' : ''}`} onClick={() => setCfgTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>

        <div className="cfg-tab-body">

          {/* ── AI tab ── */}
          <div className={`cfg-tab-pane${cfgTab === 'ai' ? ' active' : ''}`}>

            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>VIDEO TYPE</span>
                <span className="cfg-sec-api">video_type</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'auto'          as ConfigState['videoType'], l: 'Auto'      },
                  { v: 'viral'         as ConfigState['videoType'], l: 'Viral'     },
                  { v: 'storytelling'  as ConfigState['videoType'], l: 'Story'     },
                  { v: 'educational'   as ConfigState['videoType'], l: 'Edu'       },
                  { v: 'emotional'     as ConfigState['videoType'], l: 'Emotional' },
                  { v: 'high_retention'as ConfigState['videoType'], l: 'Retention' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.videoType === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('videoType', v)}>{l}</div>
                ))}
              </div>
            </div>

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>MARKET</span>
                <span className="cfg-sec-api">ai_target_market</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'us',  l: '🇺🇸 US'  },
                  { v: 'vn',  l: '🇻🇳 VN'  },
                  { v: 'jp',  l: '🇯🇵 JP'  },
                  { v: 'kr',  l: '🇰🇷 KR'  },
                  { v: 'eu',  l: '🇪🇺 EU'  },
                  { v: 'sea', l: '🌏 SEA' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.aiMarket === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('aiMarket', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>ENERGY</span>
                <span className="cfg-sec-api">energy_style</span>
              </div>
              <div className="seg">
                {([
                  { v: 'auto'     as ConfigState['energyStyle'], l: 'Auto'     },
                  { v: 'fast'     as ConfigState['energyStyle'], l: 'Fast'     },
                  { v: 'balanced' as ConfigState['energyStyle'], l: 'Balanced' },
                  { v: 'slow'     as ConfigState['energyStyle'], l: 'Slow'     },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.energyStyle === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('energyStyle', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>HOOK</span>
                <span className="cfg-sec-api">hook_strength</span>
              </div>
              <div className="seg">
                {([
                  { v: 'aggressive' as ConfigState['hookStrength'], l: 'Aggressive' },
                  { v: 'balanced'   as ConfigState['hookStrength'], l: 'Balanced'   },
                  { v: 'soft'       as ConfigState['hookStrength'], l: 'Soft'       },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.hookStrength === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('hookStrength', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>FOCUS</span>
                <span className="cfg-sec-api">reframe_mode</span>
              </div>
              <div className="seg">
                {([
                  { v: 'auto'   as ConfigState['focusMode'], l: 'Auto'   },
                  { v: 'face'   as ConfigState['focusMode'], l: 'Face'   },
                  { v: 'object' as ConfigState['focusMode'], l: 'Object' },
                  { v: 'center' as ConfigState['focusMode'], l: 'Center' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.focusMode === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('focusMode', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>OUTPUT LANGUAGE</span>
                <span className="cfg-sec-api">output_language</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'auto', l: 'Keep original' },
                  { v: 'vi',   l: '🇻🇳 VI'        },
                  { v: 'en',   l: '🇺🇸 EN'        },
                  { v: 'ja',   l: '🇯🇵 JA'        },
                  { v: 'ko',   l: '🇰🇷 KO'        },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.outputLanguage === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('outputLanguage', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {/* AI Director */}
            <div className="cfg-section">
              <div className="tog-row">
                <div>
                  <div className="tog-lbl">{t.cfgAIDirector}</div>
                  <div className="tog-desc">{t.cfgAIDirectorDesc}</div>
                </div>
                <Tog checked={cfg.aiEnabled} onChange={(v) => setCfgKey('aiEnabled', v)} />
              </div>

              {cfg.aiEnabled && (
                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase' as const, color: 'var(--text-tertiary)' }}>
                    Analyzer
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {(['local', 'cloud', 'hybrid'] as const).map((m) => (
                      <button key={m} onClick={() => {
                        setCfgKey('aiAnalysisMode', m)
                        if (m !== 'local' && cfg.aiCloudApiKey) setCfgKey('aiContentDriven', true)
                      }} style={{
                        flex: 1, padding: '5px 0', borderRadius: 6, fontSize: 11, fontWeight: 600,
                        cursor: 'pointer', border: `1px solid ${cfg.aiAnalysisMode === m ? '#a855f7' : 'var(--border-default)'}`,
                        backgroundColor: cfg.aiAnalysisMode === m ? 'rgba(168,85,247,.15)' : 'transparent',
                        color: cfg.aiAnalysisMode === m ? '#a855f7' : 'var(--text-secondary)',
                        transition: 'all .12s', textTransform: 'capitalize' as const,
                      }}>
                        {m}
                      </button>
                    ))}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                    {cfg.aiAnalysisMode === 'local' && 'Offline — no API cost'}
                    {cfg.aiAnalysisMode === 'cloud' && 'Cloud only — best quality'}
                    {cfg.aiAnalysisMode === 'hybrid' && '70% cloud + 30% local'}
                  </div>

                  {cfg.aiAnalysisMode !== 'local' && (
                    <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 6, marginTop: 4 }}>
                      <div style={{ display: 'flex', gap: 4 }}>
                        {(['groq', 'openai'] as const).map((p) => (
                          <button key={p} onClick={() => setCfgKey('aiCloudProvider', p)} style={{
                            flex: 1, padding: '4px 0', borderRadius: 6, fontSize: 11, fontWeight: 600,
                            cursor: 'pointer', border: `1px solid ${cfg.aiCloudProvider === p ? '#3b82f6' : 'var(--border-default)'}`,
                            backgroundColor: cfg.aiCloudProvider === p ? 'rgba(59,130,246,.15)' : 'transparent',
                            color: cfg.aiCloudProvider === p ? '#3b82f6' : 'var(--text-secondary)',
                            transition: 'all .12s',
                          }}>
                            {p === 'groq' ? 'Groq (Free)' : 'OpenAI'}
                          </button>
                        ))}
                      </div>
                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        <input
                          type="password"
                          value={cfg.aiCloudApiKey}
                          onChange={(e) => {
                            const key = e.target.value
                            setCfgKey('aiCloudApiKey', key)
                            setTestStatus('idle')
                            if (key) setCfgKey('aiContentDriven', true)
                          }}
                          placeholder={cfg.aiCloudProvider === 'groq' ? 'gsk_...' : 'sk-...'}
                          style={{
                            flex: 1, padding: '6px 8px', borderRadius: 6, fontSize: 11,
                            border: `1px solid ${testStatus === 'ok' ? '#22c55e' : testStatus === 'error' ? '#ef4444' : 'var(--border-default)'}`,
                            backgroundColor: 'var(--surface-input)',
                            color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box' as const,
                          }}
                        />
                        <button
                          onClick={handleTestConnection}
                          disabled={!cfg.aiCloudApiKey || testStatus === 'testing'}
                          style={{
                            padding: '6px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                            cursor: cfg.aiCloudApiKey && testStatus !== 'testing' ? 'pointer' : 'not-allowed',
                            border: '1px solid var(--border-default)',
                            backgroundColor: testStatus === 'ok' ? 'rgba(34,197,94,.15)' : testStatus === 'error' ? 'rgba(239,68,68,.12)' : 'var(--surface-input)',
                            color: testStatus === 'ok' ? '#22c55e' : testStatus === 'error' ? '#ef4444' : 'var(--text-secondary)',
                            whiteSpace: 'nowrap' as const, flexShrink: 0,
                          }}
                        >
                          {testStatus === 'testing' ? '...' : testStatus === 'ok' ? '✓' : testStatus === 'error' ? '✗' : 'Test'}
                        </button>
                      </div>
                      {(testStatus === 'ok' || testStatus === 'error') && (
                        <div style={{ fontSize: 10, color: testStatus === 'ok' ? '#22c55e' : '#ef4444', marginTop: -2 }}>
                          {testStatus === 'ok' ? `Connected · ${testMsg}` : testMsg}
                        </div>
                      )}
                      <input
                        type="text"
                        value={cfg.aiCloudModel}
                        onChange={(e) => setCfgKey('aiCloudModel', e.target.value)}
                        placeholder={cfg.aiCloudProvider === 'groq' ? 'llama-3.3-70b-versatile (optional)' : 'gpt-4o-mini (optional)'}
                        style={{
                          width: '100%', padding: '6px 8px', borderRadius: 6, fontSize: 11,
                          border: '1px solid var(--border-default)', backgroundColor: 'var(--surface-input)',
                          color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box' as const,
                        }}
                      />
                    </div>
                  )}

                  {/* AI Content-Driven Selection */}
                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border-default)' }}>
                    <div className="tog-row" style={{ alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                          AI selects clips
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2, lineHeight: 1.4 }}>
                          {cfg.aiAnalysisMode === 'local'
                            ? 'AI picks clips from transcript analysis. Add cloud key for best results.'
                            : cfg.aiCloudApiKey
                              ? 'AI overrides heuristic clip ranking with semantic selection.'
                              : 'Enter API key above to enable cloud-powered clip selection.'}
                        </div>
                      </div>
                      <Tog
                        checked={cfg.aiContentDriven}
                        onChange={(v) => setCfgKey('aiContentDriven', v)}
                      />
                    </div>
                    {cfg.aiContentDriven && (
                      <div style={{ fontSize: 10, color: '#a855f7', marginTop: 4 }}>
                        ✦ AI will read transcript early and select the best clips semantically
                      </div>
                    )}
                  </div>

                </div>
              )}
            </div>

          </div>

          {/* ── SUB tab ── */}
          <div className={`cfg-tab-pane${cfgTab === 'sub' ? ' active' : ''}`}>

            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgEnableSub}</span>
                <Tog checked={cfg.subEnabled} onChange={(v) => setCfgKey('subEnabled', v)} />
              </div>
            </div>

            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>STYLE</span>
                <span className="cfg-sec-api">subtitle_style</span>
              </div>
              <div className="sub-style-grid">
                {([
                  { id: 'tiktok_bounce_v1',  label: 'Bounce'  },
                  { id: 'viral_bold',        label: 'Viral'   },
                  { id: 'bold_cap',          label: 'Caps'    },
                  { id: 'neon_glow',         label: 'Neon'    },
                  { id: 'fire_bold',         label: 'Fire'    },
                  { id: 'color_pop',         label: 'Pop'     },
                  { id: 'slay_soft',         label: 'Slay'    },
                  { id: 'bold_stroke',       label: 'Stroke'  },
                  { id: 'dark_card',         label: 'Card'    },
                  { id: 'clean_pro',         label: 'Clean'   },
                  { id: 'story_clean_01',    label: 'Story'   },
                  { id: 'gaming',            label: 'Gaming'  },
                ] as const).map(({ id, label }) => (
                  <SubStyleCard
                    key={id} id={id} label={label}
                    selected={cfg.subStyle === id}
                    onSelect={() => setCfgKey('subStyle', id)}
                  />
                ))}
              </div>
            </div>

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>{t.cfgFontSize}</span>
                <span className="cfg-sec-api">sub_font_size</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <input
                  type="range" min={0} max={200} step={8}
                  value={cfg.subFontSize}
                  onChange={(e) => setCfgKey('subFontSize', Number(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontFamily: 'var(--fh)', fontSize: '13px', fontWeight: 700, minWidth: '40px', textAlign: 'right', color: 'var(--accent)' }}>
                  {cfg.subFontSize === 0 ? 'Auto' : cfg.subFontSize}
                </span>
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>LANGUAGE</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {(['auto', 'vi', 'en', 'ja', 'ko'] as string[]).map(v => (
                  <div key={v} className={`seg-b${cfg.subLanguage === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('subLanguage', v)}>{v === 'auto' ? 'Auto' : v.toUpperCase()}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>AMOUNT</span>
                <span className="cfg-sec-api">subtitle_density</span>
              </div>
              <div className="seg">
                {([
                  { v: 'low'    as ConfigState['subDensity'], l: 'Low'    },
                  { v: 'medium' as ConfigState['subDensity'], l: 'Medium' },
                  { v: 'high'   as ConfigState['subDensity'], l: 'High'   },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.subDensity === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('subDensity', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="tog-row">
                <div>
                  <span className="tog-lbl">{t.cfgAutoTranslate}</span>
                </div>
                <Tog checked={cfg.subTranslate} onChange={(v) => setCfgKey('subTranslate', v)} />
              </div>
              {cfg.subTranslate && (
                <div style={{ marginTop: '8px' }}>
                  <div className="seg">
                    {([
                      { v: 'vi' as const, l: '🇻🇳 Việt'   },
                      { v: 'en' as const, l: '🇺🇸 English' },
                      { v: 'ja' as const, l: '🇯🇵 日本語'   },
                    ]).map(({ v, l }) => (
                      <div key={v} className={`seg-b${cfg.subTranslateLang === v ? ' on' : ''}`}
                        onClick={() => setCfgKey('subTranslateLang', v)}>{l}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            )}

          </div>

          {/* ── NARR tab ── */}
          <div className={`cfg-tab-pane${cfgTab === 'narr' ? ' active' : ''}`}>

            <div className="cfg-section">
              <div className="tog-row">
                <span className="tog-lbl">{t.cfgEnableVoice}</span>
                <Tog checked={cfg.narrEnabled} onChange={(v) => setCfgKey('narrEnabled', v)} />
              </div>
            </div>

            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>LANGUAGE</span>
                <span className="cfg-sec-api">voice_language</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'vi-VN' as const, l: '🇻🇳 VI'    },
                  { v: 'en-US' as const, l: '🇺🇸 EN'    },
                  { v: 'en-GB' as const, l: '🇬🇧 EN-GB' },
                  { v: 'ja-JP' as const, l: '🇯🇵 JA'    },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.voiceLang === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('voiceLang', v)}>{l}</div>
                ))}
              </div>
            </div>

            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>VOICE</span>
                <span className="cfg-sec-api">voice_gender</span>
              </div>
              <div className="seg">
                <div className={`seg-b${cfg.voiceGender === 'female' ? ' on' : ''}`} onClick={() => setCfgKey('voiceGender', 'female')}>♀ Female</div>
                <div className={`seg-b${cfg.voiceGender === 'male'   ? ' on' : ''}`} onClick={() => setCfgKey('voiceGender', 'male')}>♂ Male</div>
              </div>
            </div>

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>STYLE</span>
                <span className="cfg-sec-api">narration_style</span>
              </div>
              <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
                {([
                  { v: 'auto'      as ConfigState['narrationStyle'], l: 'Auto'      },
                  { v: 'energetic' as ConfigState['narrationStyle'], l: 'Energetic' },
                  { v: 'calm'      as ConfigState['narrationStyle'], l: 'Calm'      },
                  { v: 'emotional' as ConfigState['narrationStyle'], l: 'Emotional' },
                ]).map(({ v, l }) => (
                  <div key={v} className={`seg-b${cfg.narrationStyle === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('narrationStyle', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>SOURCE</span>
                <span className="cfg-sec-api">voice_source</span>
              </div>
              <div className="seg" style={{ flexDirection: 'column', gap: '3px' }}>
                {([
                  { v: 'subtitle'            as const, l: t.cfgVoiceSrcAuto,   d: t.cfgVoiceSrcAutoDesc   },
                  { v: 'translated_subtitle' as const, l: t.cfgVoiceSrcTrans,  d: t.cfgVoiceSrcTransDesc  },
                  { v: 'manual'              as const, l: t.cfgVoiceSrcManual, d: t.cfgVoiceSrcManualDesc },
                ]).map(({ v, l, d }) => (
                  <div key={v} className={`seg-b${cfg.voiceSource === v ? ' on' : ''}`}
                    style={{ textAlign: 'left', padding: '7px 10px' }}
                    onClick={() => setCfgKey('voiceSource', v)}>
                    <div>{l}</div>
                    <div style={{ fontSize: '9px', color: cfg.voiceSource === v ? 'rgba(255,255,255,.6)' : 'var(--text-3)', marginTop: '1px', fontFamily: 'var(--fb)', fontWeight: 400 }}>{d}</div>
                  </div>
                ))}
              </div>
              {cfg.voiceSource === 'manual' && (
                <div style={{ marginTop: '8px' }}>
                  <textarea
                    className="dir-in"
                    placeholder={t.cfgVoiceSrcManualDesc}
                    value={cfg.voiceText}
                    onChange={(e) => setCfgKey('voiceText', e.target.value)}
                    style={{ width: '100%', minHeight: '80px', resize: 'vertical', fontFamily: 'var(--fb)', fontSize: '12px' }}
                  />
                </div>
              )}
            </div>
            )}

          </div>

        </div>
      </div>{/* /cfg-right */}
    </div>
  )
}
