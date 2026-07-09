/**
 * StoryStudio — dedicated Story-to-Video workflow (render_format="story").
 *
 * Four phases (thin orchestrator; phases live in sibling files, mirroring the
 * Content Studio structure):
 *   input      — paste a chapter + config → "Analyze" (POST /api/story/analyze)
 *   bible      — review characters/environments + generate reference sheets
 *   storyboard — review + edit scenes → shots → "Approve & Render"
 *                (submitRender with story_plan_override = the edited storyboard)
 *   done       — render started, link to History
 *
 * Reuses the Content Studio design language (cs- classes via StoryStudio.css +
 * shared SectionCard/Field/RatioPreview) and the shared render engine.
 */
import { useEffect, useState, type ReactNode } from 'react'
import './StoryStudio.css'
import type { RenderRequest } from '@/types/api'
import { useI18n } from '../../i18n/useI18n'
import { useRenderStore } from '../../stores/renderStore'
import { useUIStore } from '../../stores/uiStore'
import { RATIO_INFO } from '../clip-studio/render/constants'
import { getDefaultOutputDir } from '../../api/outputDir'
import { analyzeChapter, planStoryboard, type StoryBible, type StoryPlan } from '../../api/story'
import { DEFAULT_STORY_CFG, VOICE_LOCALE, type StoryConfig, type StoryPhase } from './types'
import { InputPhase } from './InputPhase'
import { BiblePhase } from './BiblePhase'
import { StoryboardPhase } from './StoryboardPhase'

const STEP_INDEX: Record<StoryPhase | 'done', 1 | 2 | 3 | 4> = { input: 1, bible: 2, storyboard: 3, done: 4 }

function StoryStepper({ vi, step }: { vi: boolean; step: 1 | 2 | 3 | 4 }) {
  const labels = vi ? ['Chương', 'Nhân vật', 'Storyboard', 'Render'] : ['Chapter', 'Characters', 'Storyboard', 'Render']
  return (
    <div className="cs-stepper">
      {labels.map((l, i) => {
        const n = (i + 1) as 1 | 2 | 3 | 4
        const cls = `cs-step${n === step ? ' is-active' : ''}${n < step ? ' is-done' : ''}`
        return (
          <div key={l} className={cls}>
            <span className="cs-step-dot">{n < step ? '✓' : n}</span>
            {l}{i < labels.length - 1 && <span className="cs-step-sep">›</span>}
          </div>
        )
      })}
    </div>
  )
}

export function StoryStudio() {
  const { lang } = useI18n()
  const vi = lang === 'vi'
  const { submitRender } = useRenderStore()
  const setActivePanel = useUIStore((s) => s.setActivePanel)

  const [phase, setPhase] = useState<StoryPhase>('input')
  const [chapter, setChapter] = useState('')
  const [cfg, setCfg] = useState<StoryConfig>(DEFAULT_STORY_CFG)
  const [bible, setBible] = useState<StoryBible | null>(null)
  const [plan, setPlan] = useState<StoryPlan | null>(null)
  const [estTotal, setEstTotal] = useState(0)
  const [jobId, setJobId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const setKey = <K extends keyof StoryConfig>(k: K, v: StoryConfig[K]) => setCfg((c) => ({ ...c, [k]: v }))
  const hasPicker = typeof window !== 'undefined' && !!window.electronAPI?.pickDirectory

  // Prefill the save folder from the saved default (never clobber a user choice).
  useEffect(() => {
    void getDefaultOutputDir()
      .then((r) => { if (r.is_configured && r.path) setCfg((c) => (c.outputDir ? c : { ...c, outputDir: r.path! })) })
      .catch(() => {})
  }, [])

  async function pickOutputDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setKey('outputDir', dir)
  }

  function fail(e: unknown) { setError(e instanceof Error ? e.message : String(e)) }

  async function onAnalyze() {
    if (!chapter.trim() || busy) return
    setBusy(true); setError(null)
    try {
      const r = await analyzeChapter({
        chapter_text: chapter.trim(), language: cfg.language,
        series_id: cfg.seriesId || undefined, chapter_no: cfg.chapterNo || undefined,
      })
      setBible(r.bible)
      setPhase('bible')
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  async function onPlan() {
    if (busy) return
    setBusy(true); setError(null)
    try {
      const r = await planStoryboard({
        chapter_text: chapter.trim(), language: cfg.language, art_style: cfg.artStyle || undefined,
        series_id: cfg.seriesId || undefined, chapter_no: cfg.chapterNo || undefined,
        aspect_ratio: RATIO_INFO[cfg.ratio].api, reading_pace: cfg.readingPace, bible,
      })
      if (!r.plan?.scenes?.length) {
        setError(vi ? 'AI không dựng được storyboard. Kiểm tra API key / thử lại.' : 'AI produced no storyboard. Check API key / retry.')
      } else {
        setPlan(r.plan)
        setEstTotal(r.estimated_total_sec || 0)
        setPhase('storyboard')
      }
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  function buildPayload(p: StoryPlan): RenderRequest {
    // Reindex densely so per-shot temp files never collide after edits.
    const reindexed: StoryPlan = {
      ...p,
      scenes: p.scenes.map((sc, i) => ({ ...sc, index: i, shots: sc.shots.map((sh, j) => ({ ...sh, index: j })) })),
    }
    return {
      source_mode: 'local',
      source_video_path: '',
      render_format: 'story',
      content_script: chapter.trim(),
      story_plan_override: JSON.stringify(reindexed),
      story_series_id: cfg.seriesId.trim() || undefined,
      story_chapter_no: cfg.chapterNo || undefined,
      story_art_style: cfg.artStyle.trim() || undefined,
      story_reading_pace: cfg.readingPace,
      voice_language: VOICE_LOCALE[cfg.language],
      aspect_ratio: RATIO_INFO[cfg.ratio].api,
      add_subtitle: cfg.subEnabled,
      subtitle_style: cfg.subStyle,
      highlight_per_word: cfg.subEnabled && cfg.wordByWord ? true : undefined,
      content_ai_budget: cfg.aiBudget > 0 ? cfg.aiBudget : undefined,
      output_dir: cfg.outputDir.trim(),
    }
  }

  async function onRender() {
    if (!plan || busy) return
    setError(null)
    if (!cfg.outputDir.trim()) { setError(vi ? 'Chưa chọn thư mục lưu video.' : 'Pick a save folder first.'); return }
    setBusy(true)
    try {
      const exists = await window.electronAPI?.pathExists?.(cfg.outputDir.trim())
      if (exists === false) {
        setError(vi ? `Thư mục lưu không tồn tại: ${cfg.outputDir.trim()}` : `Save folder does not exist: ${cfg.outputDir.trim()}`)
        setBusy(false); return
      }
      const id = await submitRender(buildPayload(plan))
      setJobId(id)
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  function reset() {
    setPhase('input'); setChapter(''); setBible(null); setPlan(null); setEstTotal(0)
    setJobId(null); setError(null)
  }

  const step = STEP_INDEX[jobId ? 'done' : phase]

  return (
    <>
      <div className="cs-screen" style={{ paddingBottom: 0 }}>
        <StoryStepper vi={vi} step={step} />
      </div>

      {jobId ? (
        <div className="cs-screen">
          <section className="cs-card">
            <div className="cs-card-hd"><span className="cs-card-title">🎬 {vi ? 'Đã bắt đầu render' : 'Render started'}</span></div>
            <div className="cs-hint" style={{ marginBottom: 12 }}>{vi ? 'Job' : 'Job'}: <code>{jobId}</code></div>
            <div className="cs-row" style={{ gap: 8 }}>
              <Btn primary onClick={() => setActivePanel('library')}>{vi ? 'Xem tiến độ trong Lịch sử →' : 'Track in History →'}</Btn>
              <Btn onClick={reset}>{vi ? 'Chương mới' : 'New chapter'}</Btn>
            </div>
          </section>
        </div>
      ) : phase === 'input' ? (
        <InputPhase vi={vi} chapter={chapter} setChapter={setChapter} cfg={cfg} setKey={setKey}
          busy={busy} error={error} onAnalyze={onAnalyze} hasPicker={hasPicker} pickOutputDir={pickOutputDir} />
      ) : phase === 'bible' && bible ? (
        <BiblePhase vi={vi} bible={bible} setBible={setBible} cfg={cfg} busy={busy} error={error}
          onBack={() => setPhase('input')} onNext={onPlan} />
      ) : phase === 'storyboard' && plan ? (
        <StoryboardPhase vi={vi} plan={plan} setPlan={setPlan} estTotal={estTotal} busy={busy} error={error}
          onBack={() => setPhase('bible')} onRender={onRender} />
      ) : null}
    </>
  )
}

// Tiny local button wrapper to keep the done card self-contained.
function Btn({ primary, onClick, children }: { primary?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button className={primary ? 'cs-cta' : ''} onClick={onClick}
      style={primary ? undefined : { background: 'transparent', border: '1px solid var(--border,#333)', color: 'inherit', padding: '8px 14px', borderRadius: 8, cursor: 'pointer' }}>
      {children}
    </button>
  )
}
