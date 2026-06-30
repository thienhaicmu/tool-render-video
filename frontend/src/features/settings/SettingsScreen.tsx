import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/api/client'
import {
  BLANK_CREATOR_CONTEXT,
  getCreatorContext,
  putCreatorContext,
  type CreatorContextPayload,
} from '@/api/creatorContext'
import {
  getDataRetention,
  putDataRetention,
} from '@/api/dataRetention'
import {
  getPerformance,
  putPerformance,
} from '@/api/performance'
import {
  getDefaultOutputDir,
  putDefaultOutputDir,
} from '@/api/outputDir'
import {
  clearRenderDefaults,
  getRenderDefaults,
  putRenderDefaults,
} from '@/api/renderDefaults'

interface CacheInfo {
  total_mb: number
  subdirs: Record<string, number>
  cache_dir: string
}

interface SystemInfo {
  cache: CacheInfo
  database: { path: string; size_mb: number }
  jobs: { total: number; completed: number; failed: number; active: number }
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 9, fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase',
      color: 'var(--text-3)', marginBottom: 10, paddingBottom: 6,
      borderBottom: '1px solid var(--border)',
    }}>
      {children}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '5px 0', fontSize: 12 }}>
      <span style={{ color: 'var(--text-3)' }}>{label}</span>
      <span style={{ color: 'var(--text-1)', fontWeight: 600, maxWidth: '60%', textAlign: 'right', wordBreak: 'break-all' }}>{value}</span>
    </div>
  )
}

// ── CreatorContext section ────────────────────────────────────────────────
// Sprint 3-FE: lets the user configure the channel persona the AI
// Director consumes. Backend persistence lives in routes/settings.py +
// db/creator_repo.py (nested in the existing creator_prefs.prefs_json blob).

function pillarsToCsv(pillars: string[]): string {
  return pillars.join(', ')
}

function pillarsFromCsv(csv: string): string[] {
  return csv
    .split(',')
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
}

function FormRow({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
      <label
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--text-2)',
          letterSpacing: '.02em',
        }}
      >
        {label}
      </label>
      {children}
      {hint ? (
        <div style={{ fontSize: 10, color: 'var(--text-3)', lineHeight: 1.4 }}>{hint}</div>
      ) : null}
    </div>
  )
}

const _inputStyle: React.CSSProperties = {
  padding: '7px 10px',
  fontSize: 12,
  borderRadius: 6,
  border: '1px solid var(--border)',
  // Bug fix 2026-06-15: was `var(--bg)` which is NOT defined in tokens.css
  // (only the prefixed prototype aliases --bg-base / --bg-card / etc. exist).
  // Inputs were rendering on the surrounding card's background instead of
  // the dedicated input surface.
  background: 'var(--surface-input)',
  color: 'var(--text-1)',
  fontFamily: 'inherit',
  outline: 'none',
}

function CreatorContextSection() {
  const [payload, setPayload] = useState<CreatorContextPayload>(BLANK_CREATOR_CONTEXT)
  const [pillarsCsv, setPillarsCsv] = useState<string>('')
  const [isConfigured, setIsConfigured] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)
  const [saving, setSaving] = useState<boolean>(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const env = await getCreatorContext()
      setPayload(env.creator_context)
      setPillarsCsv(pillarsToCsv(env.creator_context.content_pillars))
      setIsConfigured(env.is_configured)
    } catch {
      setPayload(BLANK_CREATOR_CONTEXT)
      setPillarsCsv('')
      setIsConfigured(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
  }, [fetch])

  function updateField<K extends keyof CreatorContextPayload>(
    key: K,
    value: CreatorContextPayload[K],
  ) {
    setPayload((prev) => ({ ...prev, [key]: value }))
    setSaveResult(null)
  }

  async function handleSave() {
    setSaving(true)
    setSaveResult(null)
    try {
      const body: CreatorContextPayload = {
        ...payload,
        content_pillars: pillarsFromCsv(pillarsCsv),
      }
      const env = await putCreatorContext(body)
      setPayload(env.creator_context)
      setPillarsCsv(pillarsToCsv(env.creator_context.content_pillars))
      setIsConfigured(env.is_configured)
      setSaveResult(env.is_configured ? 'Đã lưu' : 'Đã xoá cấu hình')
    } catch {
      setSaveResult('Lưu thất bại')
    } finally {
      setSaving(false)
    }
  }

  async function handleClear() {
    if (!window.confirm('Xoá toàn bộ cấu hình Creator Context?')) return
    setSaving(true)
    setSaveResult(null)
    try {
      const env = await putCreatorContext(BLANK_CREATOR_CONTEXT)
      setPayload(env.creator_context)
      setPillarsCsv('')
      setIsConfigured(env.is_configured)
      setSaveResult('Đã xoá cấu hình')
    } catch {
      setSaveResult('Xoá thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      data-testid="creator-context-section"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: '16px 18px',
      }}
    >
      <SectionTitle>
        Creator Context{' '}
        <span
          style={{
            marginLeft: 8,
            fontSize: 9,
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: 4,
            background: isConfigured ? 'rgba(var(--ok-rgb),.12)' : 'rgba(var(--text-rgb),.10)',
            color: isConfigured ? 'var(--ok)' : 'var(--text-3)',
            letterSpacing: '.04em',
          }}
        >
          {isConfigured ? 'ĐÃ CẤU HÌNH' : 'CHƯA CẤU HÌNH'}
        </span>
      </SectionTitle>

      {loading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Đang tải…</div>
      ) : (
        <>
          <FormRow label="Tên kênh" hint="Tên hiển thị của kênh / creator">
            <input
              data-testid="cc-channel-name"
              type="text"
              value={payload.channel_name}
              onChange={(e) => updateField('channel_name', e.target.value)}
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="Brand voice" hint="viral · educational · entertaining · authentic">
            <input
              data-testid="cc-brand-voice"
              type="text"
              value={payload.brand_voice}
              onChange={(e) => updateField('brand_voice', e.target.value)}
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="Target audience" hint="us · eu · jp · vn · global">
            <input
              data-testid="cc-target-audience"
              type="text"
              value={payload.target_audience}
              onChange={(e) => updateField('target_audience', e.target.value)}
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="Content pillars" hint="Cách nhau bằng dấu phẩy (ví dụ: recipe, tutorial, review)">
            <input
              data-testid="cc-content-pillars"
              type="text"
              value={pillarsCsv}
              onChange={(e) => {
                setPillarsCsv(e.target.value)
                setSaveResult(null)
              }}
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="Market" hint="Mã thị trường — viết tắt (vn / us / ...)">
            <input
              data-testid="cc-market"
              type="text"
              value={payload.market}
              onChange={(e) => updateField('market', e.target.value)}
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="Language" hint="BCP-47 (vi / en / ja / ...)">
            <input
              data-testid="cc-language"
              type="text"
              value={payload.language}
              onChange={(e) => updateField('language', e.target.value)}
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="Editorial brief" hint="Mô tả ngắn về phong cách, tông giọng, ưu tiên biên tập">
            <textarea
              data-testid="cc-notes"
              value={payload.notes}
              onChange={(e) => updateField('notes', e.target.value)}
              rows={3}
              style={{ ..._inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
            />
          </FormRow>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
            <button
              data-testid="cc-save"
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '6px 16px',
                borderRadius: 7,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: 'var(--font-family-base)',
                letterSpacing: '.04em',
                border: '1px solid rgba(var(--accent-rgb),.4)',
                background: 'rgba(var(--accent-rgb),.10)',
                color: 'var(--accent)',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.5 : 1,
              }}
            >
              {saving ? 'Đang lưu…' : 'Lưu'}
            </button>
            <button
              data-testid="cc-clear"
              onClick={handleClear}
              disabled={saving || !isConfigured}
              style={{
                padding: '6px 16px',
                borderRadius: 7,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: 'var(--font-family-base)',
                letterSpacing: '.04em',
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--text-3)',
                cursor: saving || !isConfigured ? 'not-allowed' : 'pointer',
                opacity: saving || !isConfigured ? 0.5 : 1,
              }}
            >
              Xoá cấu hình
            </button>
            {saveResult ? (
              <span data-testid="cc-status" style={{ fontSize: 11, color: 'var(--text-3)' }}>
                {saveResult}
              </span>
            ) : null}
          </div>

          <div style={{ marginTop: 12, fontSize: 10, color: 'var(--text-3)', lineHeight: 1.5 }}>
            AI Director đọc CreatorContext ở mỗi render để bias hướng chọn clip phù hợp với
            phong cách kênh. Để trống tất cả ô = không cấu hình → AI hoạt động như trước.
          </div>
        </>
      )}
    </div>
  )
}


// OutputDirSection (audit 2026-06-15): backend endpoints
// /api/settings/output-dir (GET + PUT) existed since Sprint 3 but there
// was no FE form to set the default. Until now creators only got their
// output_dir saved as a side-effect of the first POST /render/process —
// they couldn't pre-configure it. With the gear icon now wired to
// Settings (N4), this section is the obvious place to add it.
function OutputDirSection() {
  const [path, setPath] = useState<string>('')
  const [isConfigured, setIsConfigured] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)
  const [saving, setSaving] = useState<boolean>(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  const fetchValue = useCallback(async () => {
    setLoading(true)
    try {
      const env = await getDefaultOutputDir()
      setPath(env.path || '')
      setIsConfigured(env.is_configured)
    } catch {
      setPath('')
      setIsConfigured(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchValue() }, [fetchValue])

  async function handlePick() {
    const dir = await window.electronAPI?.pickDirectory?.()
    if (dir) {
      setPath(dir)
      setSaveResult(null)
    }
  }

  async function handleSave() {
    setSaving(true)
    setSaveResult(null)
    try {
      const env = await putDefaultOutputDir(path.trim() || null)
      setPath(env.path || '')
      setIsConfigured(env.is_configured)
      setSaveResult(env.is_configured ? 'Đã lưu' : 'Đã xoá mặc định')
    } catch {
      setSaveResult('Lưu thất bại')
    } finally {
      setSaving(false)
    }
  }

  async function handleClear() {
    if (!window.confirm('Xoá thư mục lưu mặc định?')) return
    setSaving(true)
    setSaveResult(null)
    try {
      const env = await putDefaultOutputDir(null)
      setPath('')
      setIsConfigured(env.is_configured)
      setSaveResult('Đã xoá mặc định')
    } catch {
      setSaveResult('Xoá thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: '16px 18px',
      }}
    >
      <SectionTitle>
        Thư mục lưu mặc định{' '}
        <span
          style={{
            marginLeft: 8,
            fontSize: 9,
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: 4,
            background: isConfigured ? 'rgba(var(--ok-rgb),.12)' : 'rgba(var(--text-rgb),.10)',
            color: isConfigured ? 'var(--ok)' : 'var(--text-3)',
            letterSpacing: '.04em',
          }}
        >
          {isConfigured ? 'ĐÃ CẤU HÌNH' : 'CHƯA CẤU HÌNH'}
        </span>
      </SectionTitle>
      {loading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Đang tải…</div>
      ) : (
        <>
          <FormRow
            label="Thư mục output"
            hint="Render mới sẽ dùng thư mục này nếu Configure không đặt thư mục riêng."
          >
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                type="text"
                value={path}
                onChange={(e) => { setPath(e.target.value); setSaveResult(null) }}
                placeholder="D:\Output\Channel"
                style={{ ..._inputStyle, flex: 1 }}
              />
              <button
                onClick={handlePick}
                style={{
                  padding: '0 12px',
                  borderRadius: 6,
                  fontSize: 11,
                  fontWeight: 600,
                  border: '1px solid var(--border)',
                  background: 'var(--bg-hover)',
                  color: 'var(--text-1)',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                Chọn…
              </button>
            </div>
          </FormRow>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '6px 16px',
                borderRadius: 7,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: 'var(--font-family-base)',
                letterSpacing: '.04em',
                border: '1px solid rgba(var(--accent-rgb),.4)',
                background: 'rgba(var(--accent-rgb),.10)',
                color: 'var(--accent)',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.5 : 1,
              }}
            >
              {saving ? 'Đang lưu…' : 'Lưu'}
            </button>
            <button
              onClick={handleClear}
              disabled={saving || !isConfigured}
              style={{
                padding: '6px 16px',
                borderRadius: 7,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: 'var(--font-family-base)',
                letterSpacing: '.04em',
                border: '1px solid var(--border)',
                background: 'transparent',
                color: 'var(--text-3)',
                cursor: saving || !isConfigured ? 'not-allowed' : 'pointer',
                opacity: saving || !isConfigured ? 0.5 : 1,
              }}
            >
              Xoá mặc định
            </button>
            {saveResult ? (
              <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{saveResult}</span>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}


// Batch 10R (MT-7 UI): Settings section for the job-retention auto-prune
// setting (backend wiring shipped in Batch 10A as ST-12). Keeps the
// same shape as CreatorContextSection so reviewers can diff them.
function DataRetentionSection() {
  const [days, setDays] = useState<number>(0)
  const [isConfigured, setIsConfigured] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)
  const [saving, setSaving] = useState<boolean>(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const env = await getDataRetention()
      setDays(env.data_retention.job_retention_days)
      setIsConfigured(env.is_configured)
    } catch {
      setDays(0)
      setIsConfigured(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
  }, [fetch])

  async function handleSave() {
    setSaving(true)
    setSaveResult(null)
    try {
      const env = await putDataRetention({ job_retention_days: days })
      setDays(env.data_retention.job_retention_days)
      setIsConfigured(env.is_configured)
      setSaveResult(
        env.data_retention.job_retention_days === 0
          ? 'Đã tắt auto-prune'
          : `Sẽ xóa job cũ hơn ${env.data_retention.job_retention_days} ngày`,
      )
    } catch {
      setSaveResult('Lưu thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      data-testid="data-retention-section"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: '16px 18px',
      }}
    >
      <SectionTitle>
        Data Retention{' '}
        <span
          style={{
            marginLeft: 8,
            fontSize: 9,
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: 4,
            background: isConfigured && days > 0
              ? 'rgba(var(--ok-rgb),.12)'
              : 'rgba(var(--text-rgb),.10)',
            color: isConfigured && days > 0 ? 'var(--ok)' : 'var(--text-3)',
            letterSpacing: '.04em',
          }}
        >
          {isConfigured && days > 0 ? `AUTO-PRUNE ${days}D` : 'TẮT'}
        </span>
      </SectionTitle>

      {loading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Đang tải…</div>
      ) : (
        <>
          <FormRow
            label="Số ngày giữ job"
            hint="0 = không xóa tự động · 1-365 = xóa job hoàn thành/lỗi cũ hơn N ngày"
          >
            <input
              data-testid="dr-job-retention-days"
              type="number"
              min={0}
              max={365}
              value={days}
              onChange={(e) => {
                const raw = parseInt(e.target.value || '0', 10)
                const clamped = isNaN(raw) ? 0 : Math.max(0, Math.min(365, raw))
                setDays(clamped)
                setSaveResult(null)
              }}
              style={_inputStyle}
            />
          </FormRow>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
            <button
              data-testid="dr-save"
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '6px 16px',
                borderRadius: 7,
                fontSize: 11,
                fontWeight: 700,
                fontFamily: 'var(--font-family-base)',
                letterSpacing: '.04em',
                border: '1px solid rgba(var(--accent-rgb),.4)',
                background: 'rgba(var(--accent-rgb),.10)',
                color: 'var(--accent)',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.5 : 1,
              }}
            >
              {saving ? 'Đang lưu…' : 'Lưu'}
            </button>
            {saveResult ? (
              <span data-testid="dr-status" style={{ fontSize: 11, color: 'var(--text-3)' }}>
                {saveResult}
              </span>
            ) : null}
          </div>

          <div style={{ marginTop: 12, fontSize: 10, color: 'var(--text-3)', lineHeight: 1.5 }}>
            Job đang chạy / chờ KHÔNG bao giờ bị xóa. Chỉ áp dụng cho các job đã hoàn thành,
            lỗi, hủy hoặc bị gián đoạn. Kiểm tra mỗi 30 phút (chu kỳ dọn dẹp định kỳ).
          </div>
        </>
      )}
    </div>
  )
}


function PerformanceSection() {
  const [hwdecode, setHwdecode] = useState<boolean>(false)
  const [qsv, setQsv] = useState<boolean>(false)
  const [loading, setLoading] = useState<boolean>(true)
  const [saving, setSaving] = useState<boolean>(false)
  const [saveResult, setSaveResult] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const env = await getPerformance()
      setHwdecode(env.performance.hwdecode)
      setQsv(env.performance.qsv)
    } catch {
      setHwdecode(false)
      setQsv(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  async function save(next: { hwdecode: boolean; qsv: boolean }) {
    setSaving(true)
    setSaveResult(null)
    setHwdecode(next.hwdecode)   // optimistic
    setQsv(next.qsv)
    try {
      const env = await putPerformance(next)
      setHwdecode(env.performance.hwdecode)
      setQsv(env.performance.qsv)
      setSaveResult('Đã lưu — áp dụng cho lần render tới')
    } catch {
      setSaveResult('Lưu thất bại')
      fetch()
    } finally {
      setSaving(false)
    }
  }

  const Toggle = ({ on, onClick }: { on: boolean; onClick: () => void }) => (
    <button
      onClick={onClick}
      disabled={saving}
      style={{
        width: 52, height: 26, borderRadius: 99, border: '1px solid var(--border)',
        background: on ? 'rgba(var(--accent-rgb),.25)' : 'rgba(var(--text-rgb),.08)',
        position: 'relative', cursor: saving ? 'not-allowed' : 'pointer',
        transition: 'background .15s', flexShrink: 0,
      }}
      aria-pressed={on}
    >
      <span style={{
        position: 'absolute', top: 2, left: on ? 28 : 2, width: 20, height: 20, borderRadius: '50%',
        background: on ? 'var(--accent)' : 'var(--text-3)', transition: 'left .15s',
      }} />
    </button>
  )

  const Row = ({ label, hint, on, onToggle, warn }: {
    label: string; hint: string; on: boolean; onToggle: () => void; warn?: boolean
  }) => (
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 0', borderTop: '1px solid var(--border)' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{label}</div>
        <div style={{ fontSize: 10, color: warn ? 'var(--warn, #d6a200)' : 'var(--text-3)', lineHeight: 1.5, marginTop: 2 }}>{hint}</div>
      </div>
      <Toggle on={on} onClick={onToggle} />
    </div>
  )

  return (
    <div data-testid="performance-section" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
      <SectionTitle>Hiệu năng / Tốc độ render</SectionTitle>
      {loading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Đang tải…</div>
      ) : (
        <>
          <Row
            label="Tăng tốc giải mã (iGPU)"
            hint="Giải mã video nguồn bằng iGPU thay vì CPU — nhanh hơn, CHẤT LƯỢNG GIỮ NGUYÊN (giải mã không mất mát). Tự rớt về CPU nếu lỗi."
            on={hwdecode}
            onToggle={() => save({ hwdecode: !hwdecode, qsv })}
          />
          <Row
            label="Encode bằng iGPU — QSV (nhanh nhất)"
            hint="Encode trên iGPU thay vì CPU x264 — NHANH NHẤT, nhưng chất lượng giảm nhẹ so với x264. Khuyên chỉ bật khi xuất để đăng social/YouTube."
            on={qsv}
            onToggle={() => save({ hwdecode, qsv: !qsv })}
            warn
          />
          {saveResult ? (
            <div data-testid="perf-status" style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 10 }}>{saveResult}</div>
          ) : null}
          <div style={{ marginTop: 10, fontSize: 10, color: 'var(--text-3)', lineHeight: 1.5 }}>
            Render đã tự chạy đa luồng CPU. Hai tùy chọn trên dùng iGPU Intel để nhanh hơn nữa; tắt cả hai = giữ chất lượng x264 tối đa.
          </div>
        </>
      )}
    </div>
  )
}


export function SettingsScreen() {
  const [info, setInfo] = useState<SystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [clearing, setClearing] = useState(false)
  const [clearResult, setClearResult] = useState<string | null>(null)

  const fetchInfo = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiFetch<SystemInfo>('/api/render/system-info')
      setInfo(data)
    } catch {
      // silently fail — non-critical
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchInfo() }, [fetchInfo])

  async function handleClearCache() {
    if (!window.confirm('Xóa toàn bộ cache render? Các render tiếp theo sẽ chậm hơn lần đầu.')) return
    setClearing(true)
    setClearResult(null)
    try {
      const res = await apiFetch<{ deleted_files: number; freed_mb: number }>('/api/render/cache/clear', { method: 'POST' })
      setClearResult(`Đã xóa ${res.deleted_files} file · giải phóng ${res.freed_mb} MB`)
      await fetchInfo()
    } catch {
      setClearResult('Xóa cache thất bại')
    } finally {
      setClearing(false)
    }
  }

  // S2.2 IA refactor: section anchors + a sticky left rail for fast
  // scanning. Existing form components are unchanged — each is wrapped
  // in a section that the nav can scrollIntoView({behavior:'smooth'}).
  // Order intentionally matches the FE-facing mental model:
  //   1. Creator    — who is rendering
  //   2. Defaults   — render workflow form pre-fill (NEW S2.3)
  //   3. Output     — where files go
  //   4. Retention  — when to prune
  //   5. Storage    — cache + db
  //   6. Stats      — system stats + help
  return (
    <div style={{
      height: '100%', overflowY: 'auto',
      display: 'grid',
      gridTemplateColumns: 'minmax(180px, 220px) 1fr',
      gap: 24,
      padding: '20px 24px',
    }}>
      <SettingsNav />

      <div style={{
        display: 'flex', flexDirection: 'column', gap: 24,
        maxWidth: 560, minWidth: 0,
      }}>
        {/* Header */}
        <div>
          <div style={{ fontFamily: 'var(--font-family-base)', fontSize: 16, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.5px' }}>
            CÀI ĐẶT
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>
            Tùy chỉnh creator, defaults render, output, storage và thống kê hệ thống
          </div>
        </div>

        <section id="settings-creator">
          <CreatorContextSection />
        </section>

        <section id="settings-defaults">
          <RenderDefaultsSection />
        </section>

        <section id="settings-output">
          <OutputDirSection />
        </section>

        <section id="settings-retention">
          <DataRetentionSection />
        </section>

        <section id="settings-performance">
          <PerformanceSection />
        </section>

      {loading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Đang tải…</div>
      ) : info ? (
        <>
          {/* Cache section */}
          <section id="settings-storage" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Render Cache</SectionTitle>
            <InfoRow label="Tổng dung lượng" value={`${info.cache.total_mb} MB`} />
            {Object.entries(info.cache.subdirs).map(([name, mb]) => (
              <InfoRow key={name} label={`  ${name}`} value={`${mb} MB`} />
            ))}
            <InfoRow label="Thư mục" value={info.cache.cache_dir} />

            <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
              <button
                onClick={handleClearCache}
                disabled={clearing}
                style={{
                  padding: '6px 16px', borderRadius: 7, fontSize: 11, fontWeight: 700,
                  fontFamily: 'var(--font-family-base)', letterSpacing: '.04em',
                  border: '1px solid rgba(var(--fail-rgb),.4)', background: 'rgba(var(--fail-rgb),.08)',
                  color: 'var(--fail)', cursor: clearing ? 'not-allowed' : 'pointer',
                  opacity: clearing ? .5 : 1,
                }}
              >
                {clearing ? 'Đang xóa…' : 'Xóa cache'}
              </button>
              {clearResult && (
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{clearResult}</span>
              )}
            </div>
          </section>

          {/* Database section */}
          <section id="settings-database" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Database</SectionTitle>
            <InfoRow label="Kích thước" value={`${info.database.size_mb} MB`} />
            <InfoRow label="Đường dẫn" value={info.database.path} />
          </section>

          {/* Jobs section */}
          <section id="settings-stats" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Thống kê Job</SectionTitle>
            <InfoRow label="Tổng số job" value={info.jobs.total} />
            <InfoRow label="Hoàn thành" value={<span style={{ color: 'var(--ok)' }}>{info.jobs.completed}</span>} />
            <InfoRow label="Lỗi" value={<span style={{ color: 'var(--fail)' }}>{info.jobs.failed}</span>} />
            <InfoRow label="Đang chạy" value={<span style={{ color: 'var(--accent)' }}>{info.jobs.active}</span>} />
          </section>

          {/* Tips */}
          <section id="settings-help" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Hướng dẫn</SectionTitle>
            <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.8 }}>
              <div>• Cache lưu kết quả scene detection, transcription, motion path — tăng tốc render lại cùng video</div>
              <div>• Xóa cache nếu kết quả transcription/subtitle bị lỗi hoặc cần giải phóng dung lượng</div>
              <div>• Database <code>app.db</code> chứa toàn bộ lịch sử job — không xóa thủ công</div>
              <div>• Để tăng/giảm số job song song, đặt biến môi trường <code>MAX_CONCURRENT_JOBS</code></div>
            </div>
          </section>
        </>
      ) : (
        <div style={{ color: 'var(--fail)', fontSize: 12 }}>Không thể tải thông tin hệ thống</div>
      )}
      </div>
    </div>
  )
}

// ── S2.2 IA refactor — section nav rail ───────────────────────────────
//
// Sticky left rail listing every section anchor. Click → smooth-scrolls
// to the matching `<section id="...">`. No active-section highlight in
// v1 (would require an IntersectionObserver) — kept minimal so the rail
// is purely a faster jump table.

const _NAV_ITEMS: Array<{ id: string; label: string }> = [
  { id: 'settings-creator',   label: 'Creator' },
  { id: 'settings-defaults',  label: 'Render Defaults' },
  { id: 'settings-output',    label: 'Output' },
  { id: 'settings-retention', label: 'Data Retention' },
  { id: 'settings-storage',   label: 'Cache' },
  { id: 'settings-database',  label: 'Database' },
  { id: 'settings-stats',     label: 'Thống kê' },
  { id: 'settings-help',      label: 'Hướng dẫn' },
]

function SettingsNav() {
  function scrollTo(id: string) {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  return (
    <nav style={{
      position: 'sticky', top: 0, alignSelf: 'flex-start',
      display: 'flex', flexDirection: 'column', gap: 2,
      paddingTop: 38,
    }}>
      <div style={{
        fontSize: 9, fontWeight: 700, letterSpacing: '.1em',
        color: 'var(--text-3)', textTransform: 'uppercase',
        marginBottom: 6, paddingLeft: 8,
      }}>
        Mục
      </div>
      {_NAV_ITEMS.map((it) => (
        <button
          key={it.id}
          onClick={() => scrollTo(it.id)}
          style={{
            textAlign: 'left',
            padding: '6px 8px',
            border: 'none',
            background: 'transparent',
            color: 'var(--text-2)',
            fontSize: 12,
            borderRadius: 6,
            cursor: 'pointer',
            transition: 'background-color 0.12s ease',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-card-hover)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
        >
          {it.label}
        </button>
      ))}
    </nav>
  )
}

// ── S2.3 — render defaults form ───────────────────────────────────────
//
// Persists user preset defaults via /api/settings/render-defaults so the
// Configure step of the render workflow can auto-fill (S2.4 consumes
// this on Step 2 mount). Field choices match the canonical lists in
// features/clip-studio/render/constants.ts so the saved defaults round-
// trip 1:1 with what the render form accepts.

const _DEFAULTS_ASPECT_OPTIONS = ['9:16', '3:4', '4:5', '1:1', '16:9']
const _DEFAULTS_PRESET_OPTIONS = [
  { value: 'viral',   label: 'VIRAL SHORT (TikTok)' },
  { value: 'gaming',  label: 'GAMING HYPE (YT Short)' },
  { value: 'clean',   label: 'CLEAN STORY (Reels)' },
  { value: 'podcast', label: 'PODCAST CLIP' },
]
const _DEFAULTS_SUB_STYLE_OPTIONS = [
  { value: 'opus_pop',        label: 'Pop' },
  { value: 'capcut_box',      label: 'Box' },
  { value: 'punch_green',     label: 'Punch' },
  { value: 'karaoke_clean',   label: 'Karaoke' },
  { value: 'smooth_premiere', label: 'Smooth' },
]
const _DEFAULTS_LLM_OPTIONS = [
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'claude', label: 'Anthropic Claude' },
]
const _DEFAULTS_VOICE_PROVIDER_OPTIONS = [
  { value: 'xtts',       label: 'XTTS (local)' },
  { value: 'elevenlabs', label: 'ElevenLabs (cloud)' },
  { value: 'edge',       label: 'Edge TTS' },
]

function RenderDefaultsSection() {
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [isConfigured, setIsConfigured] = useState(false)

  const [aspectRatio, setAspectRatio] = useState('')
  const [preset, setPreset] = useState('')
  const [voiceProvider, setVoiceProvider] = useState('')
  const [voiceId, setVoiceId] = useState('')
  const [subtitleStyle, setSubtitleStyle] = useState('')
  const [llmProvider, setLlmProvider] = useState('')

  // Initial load — mirror the existing pattern in CreatorContextSection.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const env = await getRenderDefaults()
        if (cancelled) return
        setIsConfigured(env.is_configured)
        setAspectRatio(env.render_defaults.aspect_ratio || '')
        setPreset(env.render_defaults.preset || '')
        setVoiceProvider(env.render_defaults.voice_provider || '')
        setVoiceId(env.render_defaults.voice_id || '')
        setSubtitleStyle(env.render_defaults.subtitle_style || '')
        setLlmProvider(env.render_defaults.llm_provider || '')
      } catch {
        // Silently fall back to defaults — non-critical.
      } finally {
        if (!cancelled) setLoaded(true)
      }
    })()
    return () => { cancelled = true }
  }, [])

  async function handleSave() {
    setSaving(true)
    setSaveMsg(null)
    try {
      const env = await putRenderDefaults({
        aspect_ratio:   aspectRatio   || null,
        preset:         preset        || null,
        voice_provider: voiceProvider || null,
        voice_id:       voiceId.trim() || null,
        subtitle_style: subtitleStyle || null,
        llm_provider:   llmProvider   || null,
      })
      setIsConfigured(env.is_configured)
      setSaveMsg(env.is_configured ? 'Đã lưu defaults' : 'Đã xóa defaults')
    } catch {
      setSaveMsg('Lưu thất bại — kiểm tra log')
    } finally {
      setSaving(false)
    }
  }

  async function handleClear() {
    if (!window.confirm('Xóa toàn bộ render defaults? Step 2 sẽ trở lại trắng.')) return
    setSaving(true)
    setSaveMsg(null)
    try {
      await clearRenderDefaults()
      setAspectRatio('')
      setPreset('')
      setVoiceProvider('')
      setVoiceId('')
      setSubtitleStyle('')
      setLlmProvider('')
      setIsConfigured(false)
      setSaveMsg('Đã xóa defaults')
    } catch {
      setSaveMsg('Xóa thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '16px 18px',
    }}>
      <SectionTitle>
        Render Defaults
        {isConfigured && (
          <span style={{
            marginLeft: 8,
            fontSize: 9, fontWeight: 700, letterSpacing: '.04em',
            color: 'var(--ok)',
          }}>
            • ĐÃ CẤU HÌNH
          </span>
        )}
      </SectionTitle>

      {!loaded ? (
        <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Đang tải…</div>
      ) : (
        <>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 12, lineHeight: 1.5 }}>
            Mỗi field tùy chọn — bỏ trống nghĩa "không có defaults, hỏi user mỗi render".
          </div>

          <FormRow label="Aspect ratio" hint="Tỉ lệ output mặc định">
            <select
              value={aspectRatio}
              onChange={(e) => setAspectRatio(e.target.value)}
              style={_inputStyle}
            >
              <option value="">— (không default)</option>
              {_DEFAULTS_ASPECT_OPTIONS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </FormRow>

          <FormRow label="Preset" hint="Template style mặc định">
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value)}
              style={_inputStyle}
            >
              <option value="">— (không default)</option>
              {_DEFAULTS_PRESET_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </FormRow>

          <FormRow label="Subtitle style" hint="Style phụ đề mặc định">
            <select
              value={subtitleStyle}
              onChange={(e) => setSubtitleStyle(e.target.value)}
              style={_inputStyle}
            >
              <option value="">— (không default)</option>
              {_DEFAULTS_SUB_STYLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </FormRow>

          <FormRow label="Voice provider" hint="Engine TTS mặc định">
            <select
              value={voiceProvider}
              onChange={(e) => setVoiceProvider(e.target.value)}
              style={_inputStyle}
            >
              <option value="">— (không default)</option>
              {_DEFAULTS_VOICE_PROVIDER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </FormRow>

          <FormRow label="Voice ID" hint="ID giọng cụ thể (vd: rachel_v2). Để trống nếu chưa có preference.">
            <input
              type="text"
              value={voiceId}
              onChange={(e) => setVoiceId(e.target.value)}
              placeholder="rachel_v2 / vi-VN-HoaiMyNeural / …"
              style={_inputStyle}
            />
          </FormRow>

          <FormRow label="LLM provider" hint="Provider cho AI Director mặc định">
            <select
              value={llmProvider}
              onChange={(e) => setLlmProvider(e.target.value)}
              style={_inputStyle}
            >
              <option value="">— (không default)</option>
              {_DEFAULTS_LLM_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </FormRow>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '6px 16px', borderRadius: 7, fontSize: 11, fontWeight: 700,
                fontFamily: 'var(--font-family-base)', letterSpacing: '.04em',
                border: '1px solid var(--accent)', background: 'var(--accent)',
                color: '#fff', cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? .5 : 1,
              }}
            >
              {saving ? 'Đang lưu…' : 'Lưu defaults'}
            </button>
            <button
              onClick={handleClear}
              disabled={saving || !isConfigured}
              style={{
                padding: '6px 12px', borderRadius: 7, fontSize: 11, fontWeight: 600,
                fontFamily: 'var(--font-family-base)', letterSpacing: '.04em',
                border: '1px solid var(--border)', background: 'transparent',
                color: 'var(--text-2)',
                cursor: (saving || !isConfigured) ? 'not-allowed' : 'pointer',
                opacity: (saving || !isConfigured) ? .5 : 1,
              }}
            >
              Xóa hết
            </button>
            {saveMsg && (
              <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{saveMsg}</span>
            )}
          </div>
        </>
      )}
    </div>
  )
}
