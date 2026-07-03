/**
 * ContentStudio — dedicated Content Studio workflow (render_format="content").
 *
 * A SEPARATE studio from clip-studio's source-video-centric RenderWorkflow.
 * Three phases (the spec's mandatory flow):
 *
 *   script  — paste/import a script + config → "Generate Content Plan"
 *             (POST /api/content/plan; AI Director, no render)
 *   review  — MANDATORY: edit narration / emotion / duration / prompt, add /
 *             delete / reorder scenes → "Approve & Render"
 *             (submitRender with content_plan_override = the edited plan)
 *   monitor — live progress via useRenderSocket (stage, per-scene, terminal)
 *
 * Reuses shared building blocks (renderStore.submitRender, useRenderSocket,
 * RATIO_INFO, i18n, theme CSS vars). The render runs on the SHARED engine — no
 * pipeline duplication.
 */
import React, { useMemo, useRef, useState } from 'react'
import type { RenderRequest } from '@/types/api'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useRenderSocket } from '../../hooks/useRenderSocket'
import { RATIO_INFO } from '../clip-studio/render/constants'
import type { Ratio } from '../clip-studio/render/types'
import { generateContentPlan, previewNarration, type ContentPlan, type ContentScene } from '../../api/content'
import { BASE_URL } from '../../api/client'

type BgKind = 'color' | 'image' | 'video'
type Phase = 'script' | 'review'

const RATIOS: Ratio[] = ['r916', 'r11', 'r169']
const VOICE_LANGS = ['vi-VN', 'en-US', 'en-GB', 'ja-JP', 'ko-KR'] as const
const TTS_ENGINES = ['edge', 'xtts', 'gemini'] as const
const SUB_STYLES = ['tiktok_bounce_v1', 'capcut_box', 'opus_pop', 'minimal_clean'] as const
const EMOTIONS = ['normal', 'excited', 'calm', 'suspense', 'epic', 'sad', 'happy', 'curious', 'motivating', 'surprise'] as const

interface Config {
  ratio: Ratio
  targetDuration: number
  bgKind: BgKind
  bgColor: string
  bgAssetPath: string
  voiceLang: typeof VOICE_LANGS[number]
  voiceGender: 'female' | 'male'
  ttsEngine: typeof TTS_ENGINES[number]
  subEnabled: boolean
  subStyle: string
  outputDir: string
  tone: string
}

const DEFAULT_CFG: Config = {
  ratio: 'r916', targetDuration: 90, bgKind: 'color', bgColor: '#101820', bgAssetPath: '',
  voiceLang: 'vi-VN', voiceGender: 'female', ttsEngine: 'edge',
  subEnabled: true, subStyle: 'tiktok_bounce_v1', outputDir: '', tone: '',
}

export function ContentStudio() {
  const { lang } = useI18n()
  const vi = lang === 'vi'
  const { submitRender } = useRenderStore()

  const [phase, setPhase] = useState<Phase>('script')
  const [script, setScript] = useState('')
  const [cfg, setCfg] = useState<Config>(DEFAULT_CFG)
  const [plan, setPlan] = useState<ContentPlan | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setCfgKey = <K extends keyof Config>(k: K, v: Config[K]) => setCfg((p) => ({ ...p, [k]: v }))

  function buildPayload(planOverride: ContentPlan): RenderRequest {
    const bgValue = cfg.bgKind === 'color' ? cfg.bgColor : cfg.bgAssetPath.trim()
    // Reindex densely so per-scene temp files never collide after edits.
    const reindexed: ContentPlan = {
      ...planOverride,
      scenes: planOverride.scenes.map((s, i) => ({ ...s, index: i })),
    }
    return {
      source_mode: 'local',
      source_video_path: '',
      render_format: 'content',
      content_script: script.trim(),
      content_plan_override: JSON.stringify(reindexed),
      content_background_kind: cfg.bgKind,
      content_background_value: bgValue,
      content_visual_provider: 'local',
      output_dir: cfg.outputDir.trim() || 'output',
      aspect_ratio: RATIO_INFO[cfg.ratio].api,
      target_duration: cfg.targetDuration,
      add_subtitle: cfg.subEnabled,
      subtitle_style: cfg.subStyle,
      voice_language: cfg.voiceLang,
      voice_gender: cfg.voiceGender,
      tts_engine: cfg.ttsEngine,
      ai_provider: 'gemini',
    }
  }

  async function handleGeneratePlan() {
    if (!script.trim() || busy) return
    setError(null)
    setBusy(true)
    try {
      const { plan: p } = await generateContentPlan({
        script: script.trim(),
        target_duration: cfg.targetDuration,
        voice_language: cfg.voiceLang,
        tone: cfg.tone || undefined,
      })
      if (!p?.scenes?.length) {
        setError(vi ? 'AI không tạo được kế hoạch. Kiểm tra API key / thử lại.' : 'AI produced no plan. Check API key / retry.')
      } else {
        setPlan(p)
        setPhase('review')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleApproveRender() {
    if (!plan || busy) return
    setError(null)
    setBusy(true)
    try {
      if (cfg.bgKind !== 'color' && !cfg.bgAssetPath.trim()) {
        setError(vi ? 'Chưa chọn ảnh/video nền.' : 'Pick a background image/video.')
        setBusy(false)
        return
      }
      const id = await submitRender(buildPayload(plan))
      setJobId(id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  if (jobId) {
    return <ContentMonitor jobId={jobId} vi={vi} onNew={() => { setJobId(null); setPlan(null); setPhase('script'); setError(null) }} />
  }
  if (phase === 'review' && plan) {
    return (
      <ReviewPhase
        vi={vi} plan={plan} setPlan={setPlan} busy={busy} error={error}
        voice={{ lang: cfg.voiceLang, gender: cfg.voiceGender, engine: cfg.ttsEngine }}
        onBack={() => setPhase('script')} onApprove={handleApproveRender}
      />
    )
  }
  return (
    <ScriptPhase
      vi={vi} script={script} setScript={setScript} cfg={cfg} setCfgKey={setCfgKey}
      busy={busy} error={error} onGenerate={handleGeneratePlan}
    />
  )
}

// ── Phase 1: script + config ────────────────────────────────────────────────

function ScriptPhase({ vi, script, setScript, cfg, setCfgKey, busy, error, onGenerate }: {
  vi: boolean; script: string; setScript: (s: string) => void
  cfg: Config; setCfgKey: <K extends keyof Config>(k: K, v: Config[K]) => void
  busy: boolean; error: string | null; onGenerate: () => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const charCount = script.trim().length

  function importFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => setScript(String(r.result || ''))
    r.readAsText(f)
    e.target.value = ''
  }

  return (
    <div style={S.screen}>
      <Stepper vi={vi} step={1} />
      <div style={S.header}>
        <h1 style={S.h1}>Content Studio</h1>
        <p style={S.sub}>{vi
          ? 'Bước 1 — Viết kịch bản. AI Content Director sẽ lập kế hoạch cảnh + lời kể để bạn duyệt trước khi render.'
          : 'Step 1 — Write the script. The AI Content Director drafts scenes + narration for you to review before rendering.'}</p>
      </div>

      <div style={S.grid}>
        <section style={S.card}>
          <div style={S.cardHd}>
            <span style={S.cardTitle}>{vi ? 'Kịch bản' : 'Script'}</span>
            <span style={S.count}>{charCount} {vi ? 'ký tự' : 'chars'}</span>
          </div>
          <textarea style={S.textarea} value={script} onChange={(e) => setScript(e.target.value)}
            placeholder={vi
              ? 'Dán kịch bản / bài viết / tin tức…\n\nVí dụ: "Hôm nay chúng ta tìm hiểu vì sao Napoleon thất bại ở Waterloo."'
              : 'Paste your script / article / news…\n\ne.g. "Today we explore why Napoleon lost at Waterloo."'} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button style={S.btnGhost} onClick={() => fileRef.current?.click()}>{vi ? 'Nhập .txt / .md' : 'Import .txt / .md'}</button>
            {script && <button style={S.btnGhost} onClick={() => setScript('')}>{vi ? 'Xoá' : 'Clear'}</button>}
            <input ref={fileRef} type="file" accept=".txt,.md,.markdown,text/plain" hidden onChange={importFile} />
          </div>
        </section>

        <section style={S.card}>
          <div style={S.cardHd}><span style={S.cardTitle}>{vi ? 'Cấu hình' : 'Configuration'}</span></div>

          <Field label={vi ? 'Tỉ lệ khung' : 'Aspect ratio'}>
            <div style={S.segRow}>
              {RATIOS.map((r) => <button key={r} style={seg(cfg.ratio === r)} onClick={() => setCfgKey('ratio', r)}>{RATIO_INFO[r].label}</button>)}
            </div>
          </Field>
          <Field label={vi ? 'Thời lượng mục tiêu (giây)' : 'Target duration (sec)'}>
            <input type="number" min={15} max={600} style={S.input} value={cfg.targetDuration}
              onChange={(e) => setCfgKey('targetDuration', Math.max(15, Math.min(600, Number(e.target.value) || 90)))} />
          </Field>
          <Field label={vi ? 'Nền' : 'Background'}>
            <div style={S.segRow}>
              {(['color', 'image', 'video'] as BgKind[]).map((k) => (
                <button key={k} style={seg(cfg.bgKind === k)} onClick={() => setCfgKey('bgKind', k)}>
                  {k === 'color' ? (vi ? 'Màu' : 'Color') : k === 'image' ? (vi ? 'Ảnh' : 'Image') : 'Video'}
                </button>
              ))}
            </div>
            {cfg.bgKind === 'color' ? (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
                <input type="color" value={cfg.bgColor} onChange={(e) => setCfgKey('bgColor', e.target.value)} style={{ width: 40, height: 32, border: 'none', background: 'none', cursor: 'pointer' }} />
                <input style={S.input} value={cfg.bgColor} onChange={(e) => setCfgKey('bgColor', e.target.value)} />
              </div>
            ) : (
              <input style={{ ...S.input, marginTop: 8 }} value={cfg.bgAssetPath} onChange={(e) => setCfgKey('bgAssetPath', e.target.value)}
                placeholder={vi ? 'Đường dẫn file trên máy…' : 'Local file path…'} />
            )}
          </Field>
          <Field label={vi ? 'Giọng đọc' : 'Voice'}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <select style={S.input} value={cfg.voiceLang} onChange={(e) => setCfgKey('voiceLang', e.target.value as typeof VOICE_LANGS[number])}>
                {VOICE_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
              <select style={S.input} value={cfg.voiceGender} onChange={(e) => setCfgKey('voiceGender', e.target.value as 'female' | 'male')}>
                <option value="female">{vi ? 'Nữ' : 'Female'}</option>
                <option value="male">{vi ? 'Nam' : 'Male'}</option>
              </select>
              <select style={S.input} value={cfg.ttsEngine} onChange={(e) => setCfgKey('ttsEngine', e.target.value as typeof TTS_ENGINES[number])}>
                {TTS_ENGINES.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
              </select>
            </div>
          </Field>
          <Field label={vi ? 'Phụ đề' : 'Subtitles'}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button style={seg(cfg.subEnabled)} onClick={() => setCfgKey('subEnabled', !cfg.subEnabled)}>{cfg.subEnabled ? (vi ? 'Bật' : 'On') : (vi ? 'Tắt' : 'Off')}</button>
              {cfg.subEnabled && (
                <select style={S.input} value={cfg.subStyle} onChange={(e) => setCfgKey('subStyle', e.target.value)}>
                  {SUB_STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
            </div>
          </Field>
          <Field label={vi ? 'Thư mục lưu' : 'Save folder'}>
            <input style={S.input} value={cfg.outputDir} onChange={(e) => setCfgKey('outputDir', e.target.value)} placeholder={vi ? 'Mặc định: output' : 'Default: output'} />
          </Field>
        </section>
      </div>

      <div style={S.footer}>
        {error && <span style={{ color: 'var(--fail)' }}>{error}</span>}
        <button style={{ ...S.btnPrimary, opacity: charCount && !busy ? 1 : 0.5, cursor: charCount && !busy ? 'pointer' : 'not-allowed' }}
          disabled={!charCount || busy} onClick={onGenerate}>
          {busy ? (vi ? 'AI đang phân tích…' : 'AI analyzing…') : (vi ? 'Tạo kế hoạch (AI)' : 'Generate Content Plan')}
        </button>
      </div>
    </div>
  )
}

// ── Phase 2: review + edit plan ─────────────────────────────────────────────

interface VoiceCfg { lang: string; gender: 'female' | 'male'; engine: string }

function ReviewPhase({ vi, plan, setPlan, busy, error, voice, onBack, onApprove }: {
  vi: boolean; plan: ContentPlan; setPlan: (p: ContentPlan) => void
  busy: boolean; error: string | null; voice: VoiceCfg; onBack: () => void; onApprove: () => void
}) {
  function updateScene(i: number, patch: Partial<ContentScene>) {
    setPlan({ ...plan, scenes: plan.scenes.map((s, idx) => (idx === i ? { ...s, ...patch } : s)) })
  }
  function removeScene(i: number) {
    setPlan({ ...plan, scenes: plan.scenes.filter((_, idx) => idx !== i) })
  }
  function moveScene(i: number, dir: -1 | 1) {
    const j = i + dir
    if (j < 0 || j >= plan.scenes.length) return
    const next = [...plan.scenes]
    ;[next[i], next[j]] = [next[j], next[i]]
    setPlan({ ...plan, scenes: next })
  }
  function addScene() {
    setPlan({ ...plan, scenes: [...plan.scenes, { index: plan.scenes.length, role: 'explain', narration: '', emotion: 'normal', reading_speed: 1.0 }] })
  }

  const canRender = plan.scenes.some((s) => (s.narration || '').trim()) && !busy

  return (
    <div style={S.screen}>
      <Stepper vi={vi} step={2} />
      <div style={S.header}>
        <h1 style={S.h1}>{vi ? 'Duyệt kế hoạch AI' : 'Review AI Plan'}</h1>
        <p style={S.sub}>
          {plan.topic ? <b>{plan.topic}</b> : null}
          {plan.video_style ? ` · ${plan.video_style}` : ''}
          {' · '}{plan.scenes.length} {vi ? 'cảnh' : 'scenes'}
          {' · '}{vi ? 'Sửa lời kể / cảm xúc / thời lượng, thêm-xoá-đổi thứ tự cảnh trước khi render.' : 'Edit narration / emotion / duration, add-remove-reorder before rendering.'}
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {plan.scenes.map((s, i) => (
          <SceneRow key={i} vi={vi} scene={s} index={i} total={plan.scenes.length} voice={voice}
            onChange={(patch) => updateScene(i, patch)} onRemove={() => removeScene(i)} onMove={(d) => moveScene(i, d)} />
        ))}
        <button style={{ ...S.btnGhost, alignSelf: 'flex-start' }} onClick={addScene}>+ {vi ? 'Thêm cảnh' : 'Add scene'}</button>
      </div>

      <div style={S.footer}>
        <button style={S.btnGhost} onClick={onBack} disabled={busy}>{vi ? '← Quay lại kịch bản' : '← Back to script'}</button>
        {error && <span style={{ color: 'var(--fail)' }}>{error}</span>}
        <button style={{ ...S.btnPrimary, opacity: canRender ? 1 : 0.5, cursor: canRender ? 'pointer' : 'not-allowed' }}
          disabled={!canRender} onClick={onApprove}>
          {busy ? (vi ? 'Đang gửi…' : 'Starting…') : (vi ? 'Duyệt & Render' : 'Approve & Render')}
        </button>
      </div>
    </div>
  )
}

function SceneRow({ vi, scene, index, total, voice, onChange, onRemove, onMove }: {
  vi: boolean; scene: ContentScene; index: number; total: number; voice: VoiceCfg
  onChange: (patch: Partial<ContentScene>) => void; onRemove: () => void; onMove: (dir: -1 | 1) => void
}) {
  const [previewing, setPreviewing] = useState(false)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [dur, setDur] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const hasText = !!(scene.narration || '').trim()

  async function doPreview() {
    if (!hasText || previewing) return
    setPreviewErr(null); setPreviewing(true)
    try {
      const r = await previewNarration({
        text: (scene.narration || '').trim(),
        voice_language: voice.lang, voice_gender: voice.gender,
        tts_engine: voice.engine, reading_speed: scene.reading_speed ?? 1,
      })
      setDur(r.duration_sec)
      if (audioRef.current) audioRef.current.pause()
      const a = new Audio(BASE_URL + r.url)
      audioRef.current = a
      void a.play().catch(() => {})
    } catch (err) {
      setPreviewErr(err instanceof Error ? err.message : String(err))
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <section style={S.card}>
      <div style={S.cardHd}>
        <input style={{ ...S.input, fontWeight: 700, flex: 1 }} value={scene.scene_title || ''} placeholder={`${vi ? 'Cảnh' : 'Scene'} ${index + 1}`}
          onChange={(e) => onChange({ scene_title: e.target.value })} />
        <div style={{ display: 'flex', gap: 4 }}>
          <button style={{ ...S.iconBtn, color: hasText ? 'var(--accent-primary, #8b5cf6)' : undefined }} title={vi ? 'Nghe thử giọng' : 'Preview voice'}
            disabled={!hasText || previewing} onClick={doPreview}>{previewing ? '…' : '🔊'}</button>
          <button style={S.iconBtn} title="Up" disabled={index === 0} onClick={() => onMove(-1)}>↑</button>
          <button style={S.iconBtn} title="Down" disabled={index === total - 1} onClick={() => onMove(1)}>↓</button>
          <button style={{ ...S.iconBtn, color: 'var(--fail, #ef4444)' }} title="Delete" onClick={onRemove}>✕</button>
        </div>
      </div>
      <textarea style={{ ...S.textarea, minHeight: 70, marginBottom: 8 }} value={scene.narration}
        placeholder={vi ? 'Lời kể…' : 'Narration…'} onChange={(e) => onChange({ narration: e.target.value })} />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <label style={S.miniLabel}>{vi ? 'Cảm xúc' : 'Emotion'}
          <select style={S.inputSm} value={scene.emotion || 'normal'} onChange={(e) => onChange({ emotion: e.target.value })}>
            {EMOTIONS.map((e2) => <option key={e2} value={e2}>{e2}</option>)}
          </select>
        </label>
        <label style={S.miniLabel}>{vi ? 'Tốc độ' : 'Speed'}
          <input type="number" step={0.05} min={0.5} max={2} style={S.inputSm} value={scene.reading_speed ?? 1}
            onChange={(e) => onChange({ reading_speed: Number(e.target.value) || 1 })} />
        </label>
        <label style={S.miniLabel}>{vi ? 'Thời lượng (s)' : 'Dur (s)'}
          <input type="number" step={0.5} min={0} style={S.inputSm} value={scene.est_duration_sec ?? 0}
            onChange={(e) => onChange({ est_duration_sec: Number(e.target.value) || 0 })} />
        </label>
        <label style={{ ...S.miniLabel, flex: 1, minWidth: 200 }}>{vi ? 'Visual prompt' : 'Visual prompt'}
          <input style={S.inputSm} value={scene.visual_prompt || ''} onChange={(e) => onChange({ visual_prompt: e.target.value })}
            placeholder={vi ? 'Mô tả hình ảnh cho scene này…' : 'Image/video prompt for this scene…'} />
        </label>
      </div>
      {(dur != null || previewErr) && (
        <div style={{ fontSize: 11, marginTop: 6, color: previewErr ? 'var(--fail, #ef4444)' : 'var(--text-3, #999)' }}>
          {previewErr ? previewErr : `${vi ? 'Giọng ~' : 'Voice ~'}${(dur ?? 0).toFixed(1)}s`}
        </div>
      )}
    </section>
  )
}

// ── Phase 3: live monitor ───────────────────────────────────────────────────

function ContentMonitor({ jobId, onNew, vi }: { jobId: string; onNew: () => void; vi: boolean }) {
  const { stage, jobStatus, jobMessage, progress, liveParts, liveEvents, isTerminal, error } = useRenderSocket(jobId)
  const pct = progress?.overall_progress_percent ?? 0
  const ok = jobStatus === 'completed' || jobStatus === 'completed_with_errors'
  const planReady = useMemo(() => liveEvents.some((e) => (e as { event?: string }).event === 'content.plan.ready'), [liveEvents])

  return (
    <div style={S.screen}>
      <Stepper vi={vi} step={3} />
      <div style={S.header}>
        <h1 style={S.h1}>{vi ? 'Đang render…' : 'Rendering…'}</h1>
        <p style={S.sub}>{jobMessage || stage || ''}</p>
      </div>
      <section style={S.card}>
        <div style={S.cardHd}><span style={S.cardTitle}>{vi ? 'Tiến độ' : 'Progress'}</span><span style={S.count}>{pct}%</span></div>
        <div style={S.barTrack}><div style={{ ...S.barFill, width: `${pct}%` }} /></div>
        <div style={{ fontSize: 12, color: 'var(--text-3, #999)', marginTop: 6 }}>
          {vi ? 'Giai đoạn' : 'Stage'}: <b>{stage || '—'}</b>{planReady && <> · {vi ? 'kế hoạch sẵn sàng' : 'plan ready'}</>}
        </div>
      </section>
      {liveParts.length > 0 && (
        <section style={S.card}>
          <div style={S.cardHd}><span style={S.cardTitle}>{vi ? 'Cảnh' : 'Scenes'} ({liveParts.length})</span></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {liveParts.map((p) => (
              <div key={p.part_no} style={S.partRow}>
                <span>#{p.part_no}</span>
                <span style={{ flex: 1, color: 'var(--text-3, #999)' }}>{p.message || p.status}</span>
                <span style={{ color: statusColor(p.status) }}>{p.status} {p.progress_percent ? `${p.progress_percent}%` : ''}</span>
              </div>
            ))}
          </div>
        </section>
      )}
      {isTerminal && (
        <section style={{ ...S.card, borderColor: ok ? 'var(--ok, #22c55e)' : 'var(--fail, #ef4444)' }}>
          <div style={S.cardHd}>
            <span style={{ ...S.cardTitle, color: ok ? 'var(--ok, #22c55e)' : 'var(--fail, #ef4444)' }}>
              {ok ? (vi ? '✓ Hoàn thành' : '✓ Done') : (vi ? '✕ Thất bại' : '✕ Failed')}
            </span>
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-2, #ccc)' }}>{jobMessage || error || ''}</p>
          <button style={S.btnPrimary} onClick={onNew}>{vi ? 'Tạo video mới' : 'New content video'}</button>
        </section>
      )}
      {!isTerminal && <div style={{ marginTop: 12 }}><button style={S.btnGhost} onClick={onNew}>{vi ? 'Tạo cái khác' : 'Start another'}</button></div>}
    </div>
  )
}

// ── shared bits ─────────────────────────────────────────────────────────────

function Stepper({ vi, step }: { vi: boolean; step: 1 | 2 | 3 }) {
  const labels = vi ? ['Kịch bản', 'Duyệt kế hoạch', 'Render'] : ['Script', 'Review', 'Render']
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
      {labels.map((l, i) => {
        const n = (i + 1) as 1 | 2 | 3
        const active = n === step
        const done = n < step
        return (
          <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: active ? 700 : 500, color: active ? 'var(--accent-primary, #8b5cf6)' : done ? 'var(--text-2, #ccc)' : 'var(--text-3, #999)' }}>
            <span style={{ width: 20, height: 20, borderRadius: 10, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, background: active ? 'var(--accent-subtle, rgba(139,92,246,.18))' : 'transparent', border: '1px solid var(--border-subtle, #333)' }}>{done ? '✓' : n}</span>
            {l}{i < 2 && <span style={{ color: 'var(--text-3, #666)' }}>›</span>}
          </div>
        )
      })}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2, #ccc)', marginBottom: 6 }}>{label}</div>
      {children}
    </div>
  )
}

function statusColor(status: string): string {
  if (status === 'done') return 'var(--ok, #22c55e)'
  if (status === 'failed') return 'var(--fail, #ef4444)'
  if (status === 'rendering') return 'var(--accent-primary, #8b5cf6)'
  return 'var(--text-3, #999)'
}

function seg(on: boolean): React.CSSProperties {
  return {
    flex: 1, padding: '8px 10px', textAlign: 'center', cursor: 'pointer', borderRadius: 8, fontSize: 13, fontWeight: 600,
    border: '1px solid var(--border-subtle, #333)',
    background: on ? 'var(--accent-subtle, rgba(139,92,246,.18))' : 'transparent',
    color: on ? 'var(--accent-primary, #8b5cf6)' : 'var(--text-2, #ccc)',
  }
}

const S: Record<string, React.CSSProperties> = {
  screen: { padding: 'var(--space-6, 24px)', maxWidth: 980, margin: '0 auto', width: '100%' },
  header: { marginBottom: 20 },
  h1: { fontSize: 22, fontWeight: 700, margin: 0, color: 'var(--text-1, #fff)' },
  sub: { fontSize: 13, color: 'var(--text-3, #999)', marginTop: 6, maxWidth: 720, lineHeight: 1.5 },
  grid: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 16, alignItems: 'start' },
  card: { background: 'var(--surface-card, #17171c)', border: '1px solid var(--border-subtle, #2a2a30)', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardHd: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 12 },
  cardTitle: { fontSize: 14, fontWeight: 700, color: 'var(--text-1, #fff)' },
  count: { fontSize: 12, color: 'var(--text-3, #999)' },
  textarea: { width: '100%', minHeight: 220, resize: 'vertical', padding: 12, borderRadius: 8, border: '1px solid var(--border-subtle, #2a2a30)', background: 'var(--surface-input, #0f0f13)', color: 'var(--text-1, #fff)', fontSize: 14, lineHeight: 1.6, fontFamily: 'inherit', marginBottom: 10 },
  input: { padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border-subtle, #2a2a30)', background: 'var(--surface-input, #0f0f13)', color: 'var(--text-1, #fff)', fontSize: 13, minWidth: 0, flex: 1 },
  inputSm: { padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border-subtle, #2a2a30)', background: 'var(--surface-input, #0f0f13)', color: 'var(--text-1, #fff)', fontSize: 12, minWidth: 0, width: '100%' },
  miniLabel: { display: 'flex', flexDirection: 'column', gap: 3, fontSize: 11, color: 'var(--text-3, #999)', minWidth: 90 },
  iconBtn: { width: 28, height: 28, borderRadius: 6, cursor: 'pointer', border: '1px solid var(--border-subtle, #2a2a30)', background: 'transparent', color: 'var(--text-2, #ccc)', fontSize: 13 },
  segRow: { display: 'flex', gap: 6 },
  footer: { display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 16, marginTop: 16, flexWrap: 'wrap' },
  btnPrimary: { padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 700, color: '#fff', background: 'var(--brand-gradient, linear-gradient(135deg,#8b5cf6,#6366f1))' },
  btnGhost: { padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600, border: '1px solid var(--border-subtle, #2a2a30)', background: 'transparent', color: 'var(--text-2, #ccc)' },
  barTrack: { height: 8, borderRadius: 4, background: 'var(--surface-input, #0f0f13)', overflow: 'hidden' },
  barFill: { height: '100%', background: 'var(--brand-gradient, linear-gradient(90deg,#8b5cf6,#6366f1))', transition: 'width .3s ease' },
  partRow: { display: 'flex', gap: 10, alignItems: 'center', fontSize: 12, padding: '4px 0' },
}
