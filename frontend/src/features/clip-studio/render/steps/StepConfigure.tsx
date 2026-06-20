import React, { useState, useEffect } from 'react'
import { BASE_URL } from '@/api/client'
import { getPreviewVideoUrl, getPreviewTranscript, testCloudAi } from '@/api/render'
import type { TranscriptSegment, PrepareSourceResponse } from '@/api/render'
import type { ConfigState, CfgTab, Source, Ratio } from '../types'
import type { Strings } from '../i18n'
import { RATIO_INFO, STYLES, SUB_STYLE_GROUPS, QUALITY_MAP } from '../constants'
import {
  DEMO_VARIANTS,
  DEMO_HIGHLIGHT_COLORS,
  CARD_CSS_FALLBACK,
  OVERLAY_VARIANTS,
  OVERLAY_HIGHLIGHT_COLORS,
} from '../subtitle-styles'
import { fmtDuration, Tog } from '../utils'

// ── Subtitle preview — visual approximation of each style ────────────────────
function SubtitleDemo({ style }: { style: string }) {
  const baseBox: React.CSSProperties = {
    position: 'absolute', bottom: '20px', left: 0, right: 0,
    textAlign: 'center', padding: '0 10px', pointerEvents: 'none', zIndex: 2,
  }

  const textStyle = DEMO_VARIANTS[style] ?? DEMO_VARIANTS['opus_pop']
  const hlC = DEMO_HIGHLIGHT_COLORS[style] ?? 'var(--cyan)'

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
    // 16:9 so the subtitle (rendered at the bottom of the frame) stays visible
    // inside the landscape card. A 9:16 preview gets center-cropped by the
    // card's object-fit:cover, hiding the text → blank-looking cards.
    const params = new URLSearchParams({ style: id, aspect_ratio: '16:9', font_size: '0', text: 'AI Clip' })
    const url = `${BASE_URL}/api/render/subtitle-preview?${params}`
    const img = new Image()
    img.onload  = () => { if (!cancelled) setImgSrc(url) }
    img.onerror = () => { if (!cancelled) setFailed(true) }
    img.src = url
    return () => { cancelled = true }
  }, [id])

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
            {CARD_CSS_FALLBACK[id] ?? <span style={{ color: '#888', fontSize: '10px' }}>{label}</span>}
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

  const style = OVERLAY_VARIANTS[subStyle] ?? OVERLAY_VARIANTS['opus_pop']
  const hlC = OVERLAY_HIGHLIGHT_COLORS[subStyle] ?? 'var(--cyan)'

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
// Sprint 5.7: wrapped in React.memo (export below) so the step subtree only
// re-renders when its props actually change. RenderWorkflow always-mounts
// all 4 steps and toggles `.active` via class, so without memo every state
// tick in step 3 (progress) re-renders steps 1, 2, 4 unnecessarily.
function StepConfigureBase({
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
    setTestStatus('testing')
    setTestMsg('')
    try {
      const res = await testCloudAi(
        cfg.aiProvider as 'gemini' | 'openai' | 'claude',
        '',  // server reads key from .env
        cfg.llmModel || undefined,
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
  const activeSubGroup = SUB_STYLE_GROUPS.find(g => g.ids.includes(cfg.subStyle))?.set ?? 'opus_pop'
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

        {/* A. Focus / reframe */}
        <div className="cfg-section">
          <div className="cfg-sec-hd">
            <span>FOCUS</span>
            <span className="cfg-sec-api">reframe_mode</span>
          </div>
          <div className="seg" style={{ flexWrap: 'wrap', gap: '5px' }}>
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

            {/* UP26 Pro Timeline Steering — audit-2026-06-08 closure.
                structure_bias re-weights the ranking formula (Strategic-1c).
                'AI auto' = null payload, leaves the formula at the default
                balanced weights. */}
            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>STRUCTURE BIAS</span>
                <span className="cfg-sec-api">structure_bias</span>
              </div>
              <div className="seg">
                {([
                  { v: null,       l: 'AI auto'  },
                  { v: 'hook',     l: 'Hook'     },
                  { v: 'balanced', l: 'Balanced' },
                  { v: 'story',    l: 'Story'    },
                ] as Array<{ v: ConfigState['structureBias']; l: string }>).map(({ v, l }) => (
                  <div key={l} className={`seg-b${cfg.structureBias === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('structureBias', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}

            {/* UP26 Pro Timeline Steering — audit-2026-06-08 closure.
                subtitle_emphasis multiplies sub_font_size (Strategic-1c).
                'AI auto' = null payload, falls back to the operator-supplied
                sub_font_size without the multiplier. */}
            {adv && (
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>SUBTITLE EMPHASIS</span>
                <span className="cfg-sec-api">subtitle_emphasis</span>
              </div>
              <div className="seg">
                {([
                  { v: null,         l: 'AI auto'   },
                  { v: 'subtle',     l: 'Subtle'    },
                  { v: 'balanced',   l: 'Balanced'  },
                  { v: 'aggressive', l: 'Aggressive'},
                ] as Array<{ v: ConfigState['subEmphasis']; l: string }>).map(({ v, l }) => (
                  <div key={l} className={`seg-b${cfg.subEmphasis === v ? ' on' : ''}`}
                    onClick={() => setCfgKey('subEmphasis', v)}>{l}</div>
                ))}
              </div>
            </div>
            )}


            {/* LLM segment selection — Phase I */}
            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>AI PROVIDER</span>
                <span className="cfg-sec-api">ai_provider</span>
              </div>
              <div className="tog-row" style={{ alignItems: 'flex-start' }}>
                <div>
                  <div className="tog-lbl">Auto-select clips with AI</div>
                  <div className="tog-desc">AI reads transcript and picks best segments. API keys configured in server .env.</div>
                </div>
                <Tog checked={cfg.llmEnabled} onChange={(v) => setCfgKey('llmEnabled', v)} />
              </div>

              {cfg.llmEnabled && (
                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {/* Provider selector — Gemini, OpenAI, Claude */}
                  <div style={{ display: 'flex', gap: 4 }}>
                    {(['gemini', 'openai', 'claude'] as const).map((p) => (
                      <button
                        key={p}
                        onClick={() => { setCfgKey('aiProvider', p); setTestStatus('idle') }}
                        style={{
                          flex: 1, padding: '8px 0', borderRadius: 6, fontSize: 12, fontWeight: 600,
                          cursor: 'pointer',
                          border: `1px solid ${cfg.aiProvider === p ? '#a855f7' : 'var(--border-default)'}`,
                          backgroundColor: cfg.aiProvider === p ? 'rgba(168,85,247,.15)' : 'transparent',
                          color: cfg.aiProvider === p ? '#a855f7' : 'var(--text-secondary)',
                          transition: 'all .12s',
                        }}
                      >
                        {p === 'gemini' ? 'Gemini' : p === 'openai' ? 'OpenAI' : 'Claude'}
                        <span style={{ fontSize: 9, marginLeft: 6, opacity: 0.7 }}>
                          {p === 'gemini' ? '· 1M/day' : p === 'openai' ? '· GPT-4o' : '· Sonnet'}
                        </span>
                      </button>
                    ))}
                  </div>

                  {/* Test button — uses server-side key from .env */}
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={handleTestConnection}
                      disabled={testStatus === 'testing'}
                      style={{
                        flex: 1, padding: '6px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                        cursor: testStatus !== 'testing' ? 'pointer' : 'not-allowed',
                        border: `1px solid ${testStatus === 'ok' ? 'var(--color-success)' : testStatus === 'error' ? 'var(--color-error)' : 'var(--border-default)'}`,
                        backgroundColor: testStatus === 'ok' ? 'rgba(34,197,94,.15)' : testStatus === 'error' ? 'rgba(239,68,68,.12)' : 'var(--surface-input)',
                        color: testStatus === 'ok' ? 'var(--color-success)' : testStatus === 'error' ? 'var(--color-error)' : 'var(--text-secondary)',
                      }}
                    >
                      {testStatus === 'testing' ? 'Testing...' : testStatus === 'ok' ? `✓ ${cfg.aiProvider} OK` : testStatus === 'error' ? `✗ ${testMsg}` : `Test ${cfg.aiProvider} key (server)`}
                    </button>
                  </div>
                  {testStatus === 'ok' && (
                    <div style={{ fontSize: 10, color: 'var(--color-success)' }}>Connected · {testMsg}</div>
                  )}

                  {/* Model override (optional) */}
                  <input
                    type="text"
                    value={cfg.llmModel}
                    onChange={(e) => setCfgKey('llmModel', e.target.value)}
                    placeholder={cfg.aiProvider === 'openai' ? 'gpt-4o (optional)' : cfg.aiProvider === 'claude' ? 'claude-sonnet-4-6 (optional)' : 'gemini-2.5-flash (optional)'}
                    style={{
                      width: '100%', padding: '6px 8px', borderRadius: 6, fontSize: 11,
                      border: '1px solid var(--border-default)', backgroundColor: 'var(--surface-input)',
                      color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
                    }}
                  />

                  {/* Language */}
                  <select
                    value={cfg.llmLanguage}
                    onChange={(e) => setCfgKey('llmLanguage', e.target.value)}
                    style={{
                      width: '100%', padding: '6px 8px', borderRadius: 6, fontSize: 11,
                      border: '1px solid var(--border-default)', backgroundColor: 'var(--surface-input)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    <option value="auto">Auto-detect language</option>
                    <option value="vi">Vietnamese</option>
                    <option value="en">English</option>
                    <option value="zh">Chinese</option>
                    <option value="ja">Japanese</option>
                    <option value="ko">Korean</option>
                    <option value="th">Thai</option>
                  </select>

                  <div style={{ fontSize: 10, color: '#a855f7', lineHeight: 1.4 }}>
                    ✦ Keys set in .env on server. Edit .env to rotate or switch defaults.
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
                  { id: 'opus_pop',        label: 'Pop'     },
                  { id: 'capcut_box',      label: 'Box'     },
                  { id: 'punch_green',     label: 'Punch'   },
                  { id: 'karaoke_clean',   label: 'Karaoke' },
                  { id: 'smooth_premiere', label: 'Smooth'  },
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
                  { v: 'ko-KR' as const, l: '🇰🇷 KO'    },
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

            <div className="cfg-section">
              <div className="cfg-sec-hd">
                <span>AUDIO MIX</span>
                <span className="cfg-sec-api">voice_mix_mode</span>
              </div>
              <div className="seg" style={{ flexDirection: 'column', gap: '3px' }}>
                {([
                  { v: 'replace_original'  as const, l: 'Replace original',       d: 'Original audio removed — narration only' },
                  { v: 'keep_original_low' as const, l: 'Keep original (lowered)', d: 'Original kept, ducked while narration speaks' },
                ]).map(({ v, l, d }) => (
                  <div key={v} className={`seg-b${cfg.voiceMixMode === v ? ' on' : ''}`}
                    style={{ textAlign: 'left', padding: '7px 10px' }}
                    onClick={() => setCfgKey('voiceMixMode', v)}>
                    <div>{l}</div>
                    <div style={{ fontSize: '9px', color: cfg.voiceMixMode === v ? 'rgba(255,255,255,.6)' : 'var(--text-3)', marginTop: '1px', fontFamily: 'var(--fb)', fontWeight: 400 }}>{d}</div>
                  </div>
                ))}
              </div>
            </div>

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

          </div>

        </div>
      </div>{/* /cfg-right */}
    </div>
  )
}

export const StepConfigure = React.memo(StepConfigureBase)
