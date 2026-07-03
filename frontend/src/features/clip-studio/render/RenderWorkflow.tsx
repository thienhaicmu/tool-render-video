import { useState, useRef, useEffect } from 'react'
import './RenderWorkflow.css'
import type { Lang } from '../ClipStudio'
import { useRenderStore } from '@/stores/renderStore'
import { useUIStore } from '@/stores/uiStore'
import { useJobsStore } from '@/stores/jobsStore'
import { useRenderSocket } from '@/hooks/useRenderSocket'
import { prepareSource, cancelRender, cancelPrepareSource, retryRender, resumeRender } from '@/api/render'
import { getJob } from '@/api/jobs'
import type { PrepareSourceResponse } from '@/api/render'
import type { JobPart, QualityReport, PartRankResult } from '@/types/api'
import { useT, ERROR_KIND_KEY, ERROR_FIX_STEPS, inferErrorKind } from './i18n'
import type { CfgTab, Source } from './types'
import { RATIO_INFO } from './constants'
import { buildRenderPayload } from './buildRenderPayload'
import { payloadToConfig } from './payloadToConfig'
import { validateSources, validateConfig } from './validate'
import { useRenderConfig } from './useRenderConfig'
import { loadTerminalResults } from './loadResults'
import { parseSubmitError } from './submitError'
import { CreateHero } from './steps/CreateHero'
import { StepConfigure } from './steps/StepConfigure'
import { StepRendering } from './steps/StepRendering'
import { StepResults } from './steps/StepResults'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { confirmDialog } from '@/components/ui/ConfirmDialog'

// ── Root component ────────────────────────────────────────────────────────────
export function RenderWorkflow({ lang }: { lang: Lang }) {
  const t = useT(lang)
  // P2.2 - Create/Jobs model. The 4-step wizard is gone: 'create' merges the
  // old Source + Configure steps (hero drop zone when no source, Configure
  // once a file is added); 'monitor' and 'results' are job-centric views
  // reached from the queue dock / drawer / notifications / footer buttons.
  type View = 'create' | 'monitor' | 'results'
  const [view, setView]       = useState<View>('create')
  const [sources, setSources] = useState<Source[]>([])
  // Set after a successful submit - drives the "added to queue" banner on
  // the Create screen with a one-click jump to the job's monitor.
  const [lastQueuedJobId, setLastQueuedJobId] = useState<string | null>(null)

  const [prepareResult, setPrepareResult] = useState<PrepareSourceResponse | null>(null)
  const [isPreparing, setIsPreparing]     = useState(false)
  const [prepareError, setPrepareError]   = useState<string | null>(null)
  const prepareCancelledRef               = useRef(false)
  const prepareAbortRef                   = useRef<AbortController | null>(null)
  // isSubmitting locks the Start-Render button while a POST /api/render/process
  // is in flight. Without this, a double-click (or two clicks across a slow
  // network round-trip) submits two identical render jobs with different
  // UUIDs — backend's job_id dedup doesn't catch it because the IDs differ.
  // See bug investigation 2026-06-15 (jobs 68b83de8 + fab6af2b on same source).
  const [isSubmitting, setIsSubmitting]   = useState(false)

  const [cfgTab, setCfgTab] = useState<CfgTab>('ai')
  // Config state (defaults + localStorage draft + one-shot server-defaults
  // hydration + setCfgKey/applyPreset) lives in useRenderConfig — slice 2 of
  // the RenderWorkflow decomposition.
  const { cfg, setCfg, setCfgKey, applyPreset } = useRenderConfig()

  const [jobId, setJobId]               = useState<string | null>(null)
  const [submitError, setSubmitError]   = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)

  const [parts, setParts]                   = useState<JobPart[]>([])
  const [partScores, setPartScores]         = useState<Record<number, number>>({})
  const [partRanks, setPartRanks]           = useState<Record<number, PartRankResult>>({})
  const [qualityReports, setQualityReports] = useState<Record<number, QualityReport | null>>({})
  const [qualityLoadFailed, setQualityLoadFailed] = useState(false)
  const [partsLoading, setPartsLoading]     = useState(false)
  const [allDataLoaded, setAllDataLoaded]   = useState(false)
  const [isRetrying, setIsRetrying]         = useState(false)
  const [rawMsgOpen, setRawMsgOpen]         = useState(false)

  const { submitRender } = useRenderStore()
  const addNotification = useUIStore((s) => s.addNotification)
  const {
    stage, jobStatus, progress, jobMessage, isTerminal,
    isReconnecting: wsReconnecting,
    isPolling:      wsPolling,
    liveParts, liveEvents, recapPlan, error: wsError, errorKind,
  } = useRenderSocket(jobId)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Compose ↔ Monitor (Pha 4) ───────────────────────────────────────────────
  // The old broad "auto-reattach" effect forced Step 3 whenever ANY
  // background job was running (watching jobsStore.active), hijacking the
  // user out of composing the next render. It's removed: a running job is
  // now discoverable in the always-visible queue dock, and the Monitor opens
  // only on an EXPLICIT user action via uiStore.monitorJobId (dock / drawer /
  // notification click / 409-navigate).
  //
  // These refs were guards for that removed effect. They're still set by the
  // duplicate / new-render / send-to-render effects below; harmless no-ops
  // now, kept to avoid churning those working flows.
  const duplicateInProgressRef = useRef(false)
  const newRenderInProgressRef = useRef(false)
  const sendToRenderInProgressRef = useRef(false)

  // Pha 4 — open Monitor (Step 3) for a specific job on explicit request.
  // Compose state (sources / cfg) lives in separate useState and is
  // preserved — only `step` + `jobId` change, so the user can navigate
  // back to Configure with their work intact.
  const monitorJobId = useUIStore((s) => s.monitorJobId)
  const setMonitorJobId = useUIStore((s) => s.setMonitorJobId)
  useEffect(() => {
    if (!monitorJobId) return
    setJobId(monitorJobId)
    setView('monitor')
    setMonitorJobId(null)
  }, [monitorJobId, setMonitorJobId])

  // S3.2/S3.5 — consume newRenderRequest counter. On every increment,
  // reset Render Workflow state to a clean Step 1. Auto-reattach is
  // suppressed via the ref so an unrelated running render doesn't
  // hijack the user's intent.
  const newRenderRequest = useUIStore((s) => s.newRenderRequest)
  const prevNewRenderRequestRef = useRef(newRenderRequest)
  useEffect(() => {
    if (newRenderRequest === prevNewRenderRequestRef.current) return
    prevNewRenderRequestRef.current = newRenderRequest
    newRenderInProgressRef.current = true
    setJobId(null)
    setSources([])
    setPrepareResult(null)
    setPrepareError(null)
    setSubmitError(null)
    setParts([])
    setPartScores({})
    setPartRanks({})
    setQualityReports({})
    setQualityLoadFailed(false)
    setView('create')
    // Release the lock on the next microtask so future activeJob
    // updates can resume auto-reattach behaviour.
    queueMicrotask(() => { newRenderInProgressRef.current = false })
  }, [newRenderRequest])

  // S2.5 — consume duplicate seed: fetch old job payload, hydrate cfg +
  // source, jump to Step 2 so user can tweak before submitting a fresh
  // render. The seed is cleared immediately so a navigation back to
  // clip-studio doesn't re-apply stale state.
  const duplicateSeedJobId    = useUIStore((s) => s.duplicateSeedJobId)
  const setDuplicateSeedJobId = useUIStore((s) => s.setDuplicateSeedJobId)
  useEffect(() => {
    if (!duplicateSeedJobId) return
    const seedId = duplicateSeedJobId
    duplicateInProgressRef.current = true
    setDuplicateSeedJobId(null)

    ;(async () => {
      try {
        const job = await getJob(seedId)
        let payload: Record<string, unknown> = {}
        try {
          payload = job.payload_json ? JSON.parse(job.payload_json) : {}
        } catch {
          payload = {}
        }
        // P4.B — full inverse mapping. The old ad-hoc patch restored only
        // ~6 fields, silently resetting subtitles/narration/LLM/trim to
        // defaults while the user believed their settings were copied.
        setCfg((prev) => ({ ...prev, ...payloadToConfig(payload) }))

        // Pre-fill the source step. Best-effort: the original payload may
        // be a local file (source_video_path) or an edit session ID. Only
        // the local-file path is reusable for "duplicate" semantics; for
        // edit sessions we leave Step 1 empty so the user re-picks.
        const srcPath = payload.source_video_path as string | undefined
        if (srcPath) {
          setSources([{ value: srcPath }])
        }

        // Land on Create (Configure state - sources are pre-filled).
        setView('create')
      } catch {
        // Silent fallback: stay on Step 1 with whatever was already
        // pre-filled. Duplicate UX failures must not block the screen.
      } finally {
        duplicateInProgressRef.current = false
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duplicateSeedJobId])

  // Pha 1.1 — consume a Download→Render handoff. Reset the wizard to a
  // clean Step 1 with the downloaded file pre-filled as the source, then
  // clear the seed so navigating back to clip-studio doesn't re-apply it.
  // Lands on Step 1 (not Step 2) because the source still needs the
  // prepare-source probe that "Configure" triggers — same as a manual pick.
  const sendToRenderSourcePath    = useUIStore((s) => s.sendToRenderSourcePath)
  const setSendToRenderSourcePath = useUIStore((s) => s.setSendToRenderSourcePath)
  useEffect(() => {
    if (!sendToRenderSourcePath) return
    const path = sendToRenderSourcePath
    sendToRenderInProgressRef.current = true
    setSendToRenderSourcePath(null)
    setJobId(null)
    setPrepareResult(null)
    setPrepareError(null)
    setSubmitError(null)
    setParts([])
    setPartScores({})
    setPartRanks({})
    setQualityReports({})
    setQualityLoadFailed(false)
    setIsSubmitting(false)
    setSources([{ value: path }])
    setView('create')
    queueMicrotask(() => { sendToRenderInProgressRef.current = false })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sendToRenderSourcePath])

  useEffect(() => {
    if (!jobId || !isTerminal) return
    setQualityLoadFailed(false)
    setPartsLoading(true)
    setAllDataLoaded(false)
    // Terminal results fetch (parts + quality + ranking, each with a 12s
    // timeout) lives in loadTerminalResults — slice 3 of the decomposition.
    // Only fields that loaded within the timeout are applied.
    loadTerminalResults(jobId).then((r) => {
      if (r.parts) setParts(r.parts)
      if (r.quality) { setPartScores(r.quality.scores); setQualityReports(r.quality.reports) }
      if (r.qualityLoadFailed) setQualityLoadFailed(true)
      if (r.partRanks) setPartRanks(r.partRanks)
    }).finally(() => {
      setPartsLoading(false)
      setAllDataLoaded(true)
    })
  }, [jobId, isTerminal])

  // Auto-advance to results after completion (success + partial success).
  // Gated on allDataLoaded so parts/quality/ranking are ready before the step change.
  useEffect(() => {
    if (!isTerminal || view !== 'monitor' || !allDataLoaded) return
    const s = jobStatus ?? ''
    const skipAdvance = s === 'failed' || s === 'interrupted' || s === 'cancelled'
    if (skipAdvance) return
    const timer = setTimeout(() => setView('results'), 300)
    return () => clearTimeout(timer)
  }, [isTerminal, jobStatus, view, allDataLoaded])

  // E-2 — toast notification on job terminal
  useEffect(() => {
    if (!isTerminal || !jobId) return
    const s = jobStatus ?? ''
    const doneCount = progress?.completed_parts ?? 0
    if (s === 'completed' || s === 'completed_with_errors' || s === 'partial') {
      addNotification({
        type: 'success',
        title: 'Render complete',
        message: doneCount > 0 ? `${doneCount} clip${doneCount !== 1 ? 's' : ''} ready` : undefined,
        jobId, kind: 'render',
      })
    } else if (s === 'failed') {
      addNotification({ type: 'error', title: 'Render failed', message: jobMessage || undefined, jobId, kind: 'render' })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTerminal])

  // ── Source actions ──────────────────────────────────────────────────────────

  // S3.4 — drag-drop / picker callback that accepts multiple files and
  // appends them to the source list (deduping by path).
  function addSourcePaths(paths: string[]) {
    if (!paths.length) return
    setSources((prev) => {
      const seen = new Set(prev.map((s) => s.value))
      const additions = paths
        .map((p) => p.trim())
        .filter((p) => p && !seen.has(p))
        .map((p) => ({ value: p }))
      return [...prev, ...additions]
    })
  }

  // P2.2 - auto-prepare: the old "Configure ->" click is gone. As soon as a
  // source is added, probe it in the background (preview video, duration,
  // export dir). Configure renders immediately; prepareResult streams in.
  const preparedForRef = useRef<string | null>(null)
  useEffect(() => {
    const src = sources[0]
    if (!src) {
      preparedForRef.current = null
      setPrepareResult(null)
      setPrepareError(null)
      return
    }
    if (preparedForRef.current === src.value) return
    preparedForRef.current = src.value
    prepareCancelledRef.current = false
    const abort = new AbortController()
    prepareAbortRef.current = abort
    setIsPreparing(true)
    setPrepareError(null)
    setPrepareResult(null)
    ;(async () => {
      if (window.electronAPI?.pathExists) {
        const exists = await window.electronAPI.pathExists(src.value)
        if (exists === false) {
          setPrepareError(
            lang === 'VI'
              ? `File không tìm thấy: "${src.value}". Có thể bị đổi tên hoặc xoá.`
              : `File not found: "${src.value}". It may have been moved or deleted.`,
          )
          setIsPreparing(false)
          return
        }
      }
      try {
        const result = await prepareSource({
          source_mode: 'local',
          source_video_path: src.value,
        }, abort.signal)
        if (prepareCancelledRef.current) {
          cancelPrepareSource(result.session_id).catch(() => {})
          return
        }
        setPrepareResult(result)
        // Default SAVE FOLDER = parent of source video, NOT the backend temp
        // folder. Preserves user-typed value when manually overridden.
        const _srcPath = src.value || ''
        const _lastSep = Math.max(_srcPath.lastIndexOf('\\'), _srcPath.lastIndexOf('/'))
        const _parentDir = _lastSep > 0 ? _srcPath.slice(0, _lastSep) : ''
        setCfg((prev) => ({
          ...prev,
          outputDir: prev.outputDir?.trim() ? prev.outputDir : (_parentDir || result.export_dir || ''),
        }))
      } catch (e) {
        if (!prepareCancelledRef.current) {
          setPrepareError(e instanceof Error ? e.message : 'Failed to prepare source')
        }
      } finally {
        setIsPreparing(false)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sources])

  function handleChangeSource() {
    prepareCancelledRef.current = true
    prepareAbortRef.current?.abort()
    setSources([])
    setPrepareResult(null)
  }

  async function pickOutputDir() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) setCfgKey('outputDir', dir)
  }

  // ── Render actions ──────────────────────────────────────────────────────────

  const buildPayloadForSource = (srcValue: string) => buildRenderPayload(cfg, srcValue)

  async function handleStartRender() {
    if (isSubmitting) return  // hard guard against double-submit

    // ── Validation: same checks as before, mirrored from the backend so
    //    failures surface instantly without round-tripping. Sync checks are
    //    extracted into ./validate (unit-tested); the async Electron
    //    pathExists probe stays inline between them (order preserved). ──────
    const srcError = validateSources(sources, lang)
    if (srcError) { setSubmitError(srcError); return }
    if (window.electronAPI?.pathExists) {
      for (const s of sources) {
        const exists = await window.electronAPI.pathExists(s.value)
        if (exists === false) {
          setSubmitError(
            lang === 'VI'
              ? `File nguồn không còn tồn tại: ${s.value}`
              : `Source file no longer exists: ${s.value}`,
          )
          return
        }
      }
    }
    const cfgError = validateConfig(cfg, lang)
    if (cfgError) { setSubmitError(cfgError); return }
    setIsSubmitting(true)
    setSubmitError(null)
    setLastQueuedJobId(null)

    // ── S3.4 multi-source batch path. For len > 1, submit each source
    //    sequentially with the same cfg. First success becomes the
    //    attached jobId so the user lands on Step 3 monitoring it; the
    //    rest run in the background and appear in ActiveJobsDock.
    if (sources.length > 1) {
      const submitted: string[] = []
      const failed: string[] = []
      for (const s of sources) {
        try {
          const id = await submitRender(buildPayloadForSource(s.value))
          submitted.push(id)
        } catch {
          failed.push(s.value)
        }
      }
      addNotification({
        type: failed.length === 0 ? 'success' : (submitted.length === 0 ? 'error' : 'warning'),
        title: lang === 'VI'
          ? `Đã queue ${submitted.length}/${sources.length} render`
          : `Queued ${submitted.length}/${sources.length} renders`,
        message: failed.length > 0
          ? (lang === 'VI'
            ? `${failed.length} job submit thất bại — kiểm tra file path`
            : `${failed.length} jobs failed to submit — check paths`)
          : undefined,
        duration: 6000,
      })
      // Pha 4 — Add-to-Queue: jobs run in the background (queue dock);
      // return Compose to a clean Step 1 instead of pinning to the first
      // job's monitor. cfg kept; sources cleared.
      if (submitted.length > 0) {
        setSources([]); setPrepareResult(null); setPrepareError(null)
        setParts([]); setPartScores({}); setPartRanks({})
        setQualityReports({}); setQualityLoadFailed(false)
        setJobId(null)
        setLastQueuedJobId(submitted[0])
      }
      setIsSubmitting(false)
      return
    }

    // ── Single-source path.
    const src = sources[0]
    const payload = buildPayloadForSource(src.value)
    try {
      const newJobId = await submitRender(payload)
      // Pha 4 — "Add to Queue": the job runs in the background (visible in
      // the queue dock); return Compose to a clean Step 1 so the user can
      // start the next render immediately instead of being pinned to the
      // monitor. cfg is kept for convenience; the source is cleared.
      addNotification({
        type: 'success',
        title: lang === 'VI' ? 'Đã thêm vào hàng đợi' : 'Added to queue',
        message: lang === 'VI'
          ? 'Theo dõi ở thanh hàng đợi phía dưới.'
          : 'Track it in the queue bar below.',
        duration: 5000,
      })
      setSources([]); setPrepareResult(null); setPrepareError(null)
      setParts([]); setPartScores({}); setPartRanks({})
      setQualityReports({}); setQualityLoadFailed(false)
      setJobId(null)
      setLastQueuedJobId(newJobId)
      setIsSubmitting(false)
    } catch (e) {
      // Message + 409 dedup-id parsing lives in parseSubmitError (slice 4a);
      // the navigate/toast state machine stays here. On 409 dedup, jump
      // straight to the already-running job's monitor — re-using it is what
      // the user wants 99% of the time (they can still cancel from there).
      const { message, dedupJobId } = parseSubmitError(e)
      if (dedupJobId) {
        setJobId(dedupJobId)
        setView('monitor')
        setIsSubmitting(false)
        addNotification({
          type: 'info',
          title: lang === 'VI' ? 'Mở job đang chạy' : 'Opened active job',
          message: lang === 'VI'
            ? 'Job render cho source này đang chạy — đã chuyển sang màn theo dõi.'
            : 'A render for this source is already running — switched to monitor view.',
          duration: 5000,
        })
      } else {
        setSubmitError(message)
        setIsSubmitting(false)  // re-enable on failure so user can retry
      }
    }
  }

  async function handleCancelRender() {
    if (!jobId || isCancelling) return
    setIsCancelling(true)
    try {
      await cancelRender(jobId)
    } catch { /* ignore */ }
    finally { setIsCancelling(false) }
  }

  async function handleRetryRender() {
    if (!jobId || isRetrying) return
    setIsRetrying(true)
    try {
      const res = await retryRender(jobId)
      setJobId(res.job_id)
      setParts([]); setPartScores({}); setQualityReports({}); setQualityLoadFailed(false)
      setView('monitor')
    } catch { /* stay on current view */ }
    finally { setIsRetrying(false) }
  }

  async function handleResumeRender() {
    if (!jobId || isRetrying) return
    setIsRetrying(true)
    try {
      const res = await resumeRender(jobId)
      setJobId(res.job_id)
      setParts([]); setPartScores({}); setQualityReports({}); setQualityLoadFailed(false)
      setView('monitor')
    } catch { /* stay on current view */ }
    finally { setIsRetrying(false) }
  }

  // N2: re-render the same source with the same Configure step settings.
  // Keeps sources + cfg + prepareResult; only resets the live job-tracking
  // state. Jumps to Step 2 (Configure) so the user can optionally tweak a
  // setting before clicking Start Render — feels safer than skipping
  // straight to submit. The Source step is skipped entirely because the
  // file pick + prepare-source from the original flow already validated
  // the same source.
  function handleRerenderSameConfig() {
    setView('create')
    setJobId(null)
    setParts([])
    setPartScores({})
    setPartRanks({})
    setQualityReports({})
    setQualityLoadFailed(false)
    setAllDataLoaded(false)
    setIsSubmitting(false)
    setSubmitError(null)
  }

  async function handleNewRender() {
    // Bug #8 fix: if there's still an active render in the queue (running or
    // queued), starting a new flow only sets the user up for an HTTP 409 at
    // submit time. Confirm + offer monitor instead. The user can still
    // proceed if they explicitly want to (e.g. they're going to pick a
    // DIFFERENT source — server dedup keys on source path, not just any
    // active job). Reads the shared jobs store rather than firing its own
    // /api/jobs/history GET (the store is polled at 4 s so `active` is
    // at most that stale, which is fine for a confirmation dialog).
    try {
      const active = useJobsStore.getState().active
      if (active) {
        // P0.4 — in-app 3-way dialog. The old window.confirm crammed
        // "open monitor" vs "start new" into OK/Cancel prose.
        const jobLabel = active.title || active.job_id.slice(0, 8)
        const choice = await confirmDialog({
          title: lang === 'VI' ? 'Vẫn còn render đang chạy' : 'A render is still running',
          message: lang === 'VI'
            ? `"${jobLabel}" đang chạy. Bạn muốn mở màn theo dõi job đó, hay bắt đầu một render mới?`
            : `"${jobLabel}" is in progress. Open its monitor, or start a new render anyway?`,
          buttons: [
            { id: 'monitor', label: lang === 'VI' ? 'Mở monitor' : 'Open monitor', variant: 'primary' },
            { id: 'new',     label: lang === 'VI' ? 'Render mới' : 'New render' },
            { id: 'cancel',  label: lang === 'VI' ? 'Đóng' : 'Cancel' },
          ],
        })
        if (choice === 'monitor') {
          setJobId(active.job_id)
          setView('monitor')
          return
        }
        if (choice !== 'new') return  // dismissed / cancel — do nothing
        // User chose to proceed — fall through and start fresh. Backend dedup
        // will still block if they pick the same source path; that's now
        // handled by the 409→navigate path in handleStartRender.
      }
    } catch {
      // backend unreachable — proceed with reset; user will discover the
      // issue when they try to submit.
    }
    setView('create'); setSources([]); setJobId(null)
    setPrepareResult(null); setParts([]); setPartScores({}); setQualityReports({})
    // Reset submit guard so the next Start-Render click is accepted.
    // Without this the button stays disabled after returning from Result.
    setIsSubmitting(false)
    setSubmitError(null)
  }

  const doneParts = parts.filter(p => p.status === 'done')

  // P2.2 - "added to queue" banner shown on the Create screen after submit.
  const queuedInfo = lastQueuedJobId ? (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ color: 'var(--ok)' }}>{'\u2713'} {t.rwQueued}</span>
      <button
        className="btn-xs"
        onClick={() => {
          const id = lastQueuedJobId
          setLastQueuedJobId(null)
          setJobId(id)
          setView('monitor')
        }}
      >
        {t.rwQueuedView}
      </button>
    </span>
  ) : null

  return (
    <div className="rw-root">
      {/* ── CREATE — empty state: hero drop zone ─────────────────────────── */}
      {view === 'create' && sources.length === 0 && (
        <CreateHero
          lang={lang}
          prepareError={prepareError}
          queuedInfo={queuedInfo}
          onAddPaths={addSourcePaths}
          onBrowse={() => {
            void (async () => {
              const picked = await window.electronAPI?.pickVideoFile?.()
              if (picked) addSourcePaths([picked])
              else fileInputRef.current?.click()
            })()
          }}
        />
      )}

      {/* ── CREATE — configure state (source added) ──────────────────────── */}
      {view === 'create' && sources.length > 0 && (
        <div className="step-screen active">
            {/* Sprint 5.7 per-step ErrorBoundary: a render error inside Step 2
                no longer takes down the whole workflow. User stays on the
                page and can navigate to other steps. */}
            <ErrorBoundary>
              <StepConfigure
                cfg={cfg} cfgTab={cfgTab} setCfgTab={setCfgTab}
                setCfgKey={setCfgKey} applyPreset={applyPreset}
                sources={sources} prepareResult={prepareResult}
                pickOutputDir={pickOutputDir} onChangeSource={handleChangeSource} t={t}
              />
            </ErrorBoundary>
            <div className="screen-footer">
              <button className="btn-back" onClick={handleChangeSource}>{t.cfgChangeSource}</button>
              <div className="screen-footer-info">
                {submitError
                  ? <span style={{ color: 'var(--fail)' }}>{submitError}</span>
                  : prepareError
                  ? <span style={{ color: 'var(--fail)' }}>{prepareError}</span>
                  : isPreparing
                  ? <span style={{ color: 'var(--text-3)' }}>{t.rwProbing}</span>
                  : queuedInfo
                }
              </div>
              <button
                className="btn-next"
                disabled={isSubmitting}
                onClick={handleStartRender}
              >
                {isSubmitting ? (lang === 'VI' ? 'Đang gửi…' : 'Starting…') : t.btnStartRender}
              </button>
            </div>
        </div>
      )}

      {/* ── MONITOR — job-centric live view ──────────────────────────────── */}
      {view === 'monitor' && (
        <div className="step-screen active">
            <ErrorBoundary>
              <StepRendering
                jobId={jobId}
                stage={stage ?? ''}
                jobStatus={jobStatus ?? ''}
                progress={progress}
                jobMessage={jobMessage ?? ''}
                isTerminal={isTerminal}
                liveParts={liveParts}
                liveEvents={liveEvents}
                recapPlan={recapPlan}
                wsError={wsError}
                wsReconnecting={wsReconnecting}
                wsPolling={wsPolling}
                t={t}
                aspectRatio={RATIO_INFO[cfg.ratio].api}
                aiAnalysisMode={cfg.llmEnabled ? 'cloud' : 'local'}
                aiCloudProvider={cfg.aiProvider}
              />
            </ErrorBoundary>
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setView('create')}>{t.btnConfig}</button>
              <div className="screen-footer-info" style={{ gap: '12px' }}>
                {isTerminal ? (() => {
                  const s = jobStatus ?? ''
                  if (s === 'failed' || s === 'interrupted')
                    return <span style={{ color: 'var(--fail)' }}>{s === 'interrupted' ? t.rndInterrupted : t.rndFailed}</span>
                  if (s === 'cancelled')
                    return <span style={{ color: 'var(--text-3)' }}>{t.rndCancelled}</span>
                  if (s === 'completed_with_errors')
                    return <span style={{ color: 'var(--warn)' }}>{t.rndPartial}</span>
                  return <span style={{ color: 'var(--ok)' }}>{t.rndComplete}</span>
                })() : wsReconnecting
                  ? <span style={{ color: 'var(--warn)', fontSize: '11px' }}>↻ {t.rndWsReconnecting}</span>
                  : wsError
                  ? <span style={{ color: 'var(--warn)', fontSize: '11px' }}>{t.rndWsError}</span>
                  : <span style={{ color: 'var(--accent)' }}>{t.rndInProgress}</span>
                }
              </div>
              {isTerminal ? (
                (() => {
                  // S5-hotfix — refine the displayed error using both
                  // the backend kind and the raw message, so cancelled
                  // jobs don't read as "Failed — retry" and so AI key
                  // failures get actionable hints.
                  const displayKind = inferErrorKind(jobStatus ?? '', jobMessage ?? '', errorKind)
                  const isCancelled = displayKind === 'CANCELLED' || jobStatus === 'cancelled'
                  return (
                <>
                  {(jobStatus === 'failed' || jobStatus === 'cancelled') && displayKind && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{
                        fontSize: 11,
                        color: isCancelled ? 'var(--text-2)' : 'var(--error, #e74c3c)',
                        fontWeight: 700, marginBottom: 6,
                      }}>
                        {t[ERROR_KIND_KEY[displayKind]] as string}
                      </div>
                      <ul style={{ margin: '0 0 6px 14px', padding: 0, fontSize: 11, color: 'var(--text-2)', lineHeight: 1.6 }}>
                        {ERROR_FIX_STEPS[displayKind].map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                      {jobMessage && (
                        <div>
                          <button
                            onClick={() => setRawMsgOpen(o => !o)}
                            style={{ fontSize: 10, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
                          >
                            {rawMsgOpen ? 'Hide detail' : 'Show raw error'}
                          </button>
                          {rawMsgOpen && (
                            <pre style={{
                              marginTop: 6, padding: '6px 8px', borderRadius: 5,
                              background: 'rgba(0,0,0,.35)', fontSize: 10, color: 'var(--text-2)',
                              whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 120, overflowY: 'auto',
                            }}>
                              {jobMessage}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {(jobStatus === 'failed' || jobStatus === 'cancelled') && (
                      <button className="btn-back" onClick={handleRetryRender} disabled={isRetrying}>
                        {isRetrying ? '…' : t.btnRetry}
                      </button>
                    )}
                    {(jobStatus === 'interrupted') && (
                      <button className="btn-back" onClick={handleResumeRender} disabled={isRetrying}>
                        {isRetrying ? '…' : t.btnResume}
                      </button>
                    )}
                    <button className="btn-next" onClick={() => setView('results')}>{t.btnViewResults}</button>
                  </div>
                </>
                  )
                })()
              ) : (
                <button
                  className="btn-cancel"
                  onClick={handleCancelRender}
                  disabled={isCancelling || jobStatus === 'cancelling'}
                >
                  {(isCancelling || jobStatus === 'cancelling') ? t.btnCancelling : t.btnCancelRender}
                </button>
              )}
            </div>
        </div>
      )}

      {/* ── RESULTS — job-centric results view ───────────────────────────── */}
      {view === 'results' && (
        <div className="step-screen active">
            <ErrorBoundary>
              <StepResults
                jobId={jobId} parts={parts} partScores={partScores} partRanks={partRanks}
                qualityReports={qualityReports} qualityLoadFailed={qualityLoadFailed}
                loading={partsLoading} t={t}
                aspectRatio={RATIO_INFO[cfg.ratio].api}
                jobStatus={jobStatus ?? ''}
                jobMessage={jobMessage ?? ''}
                onRetry={handleRetryRender} isRetrying={isRetrying}
                aiAnalysisMode={cfg.llmEnabled ? 'cloud' : 'local'}
                aiCloudProvider={cfg.aiProvider}
                goal={'auto'}
              />
            </ErrorBoundary>
            <div className="screen-footer">
              <button className="btn-back" onClick={() => setView('monitor')}>{t.btnBackRendering}</button>
              <div className="screen-footer-info" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                {doneParts.length > 0
                  ? <><span style={{ color: 'var(--ok)' }}>✓ </span><span>{t.resClipsReady(doneParts.length)}</span></>
                  : <span>{t.stepRes}</span>
                }
                {/* N1 (audit 2026-06-15): one-click open of the output folder
                    via shell:openPath IPC. Only shows when the job actually
                    has an output_dir written. */}
                {cfg.outputDir && (
                  <button
                    onClick={() => { window.electronAPI?.openPath?.(cfg.outputDir) }}
                    title={cfg.outputDir}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '6px 12px', borderRadius: 999,
                      background: 'var(--surface-card-hover)',
                      border: '1px solid var(--border-default)',
                      color: 'var(--text-primary)', fontSize: 12, fontWeight: 500,
                      cursor: 'pointer',
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>
                    </svg>
                    {lang === 'VI' ? 'Mở thư mục' : 'Open folder'}
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {/* N2 (audit 2026-06-15): re-render the same source with the
                    same config — saves the user from walking Source →
                    Configure again when iterating on a video. */}
                <button
                  className="btn-back"
                  onClick={handleRerenderSameConfig}
                  disabled={!sources.length || isSubmitting}
                  title={lang === 'VI' ? 'Render lại cùng cấu hình' : 'Re-render with same config'}
                >
                  ↻ {lang === 'VI' ? 'Render lại' : 'Render again'}
                </button>
                <button className="btn-next" onClick={handleNewRender}>{t.btnNewRender}</button>
              </div>
            </div>
        </div>
      )}

      <input
        ref={fileInputRef} type="file" accept="video/*" multiple style={{ display: 'none' }}
        onChange={(e) => {
          const files = Array.from(e.target.files || [])
          const paths = files
            .map((f) => (f as File & { path?: string }).path || f.name)
            .filter((p) => p && p.length > 0)
          if (paths.length) addSourcePaths(paths)
          // Allow re-picking the same file by resetting the input.
          e.target.value = ''
        }}
      />
    </div>
  )
}
