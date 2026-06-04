import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/api/client'
import {
  BLANK_CREATOR_CONTEXT,
  getCreatorContext,
  putCreatorContext,
  type CreatorContextPayload,
} from '@/api/creatorContext'

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
  background: 'var(--bg)',
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
            background: isConfigured ? 'rgba(0,200,150,.12)' : 'rgba(138,147,176,.10)',
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
                fontFamily: 'var(--fh)',
                letterSpacing: '.04em',
                border: '1px solid rgba(123,97,255,.4)',
                background: 'rgba(123,97,255,.10)',
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
                fontFamily: 'var(--fh)',
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

  return (
    <div style={{
      height: '100%', overflowY: 'auto', padding: '20px 24px',
      maxWidth: 520, margin: '0 auto',
      display: 'flex', flexDirection: 'column', gap: 24,
    }}>

      {/* Header */}
      <div>
        <div style={{ fontFamily: 'var(--fh)', fontSize: 16, fontWeight: 700, color: 'var(--text-1)', letterSpacing: '.5px' }}>
          CÀI ĐẶT
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>
          Thông tin hệ thống và quản lý bộ nhớ cache
        </div>
      </div>

      <CreatorContextSection />

      {loading ? (
        <div style={{ color: 'var(--text-3)', fontSize: 12 }}>Đang tải…</div>
      ) : info ? (
        <>
          {/* Cache section */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
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
                  fontFamily: 'var(--fh)', letterSpacing: '.04em',
                  border: '1px solid rgba(232,64,122,.4)', background: 'rgba(232,64,122,.08)',
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
          </div>

          {/* Database section */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Database</SectionTitle>
            <InfoRow label="Kích thước" value={`${info.database.size_mb} MB`} />
            <InfoRow label="Đường dẫn" value={info.database.path} />
          </div>

          {/* Jobs section */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Thống kê Job</SectionTitle>
            <InfoRow label="Tổng số job" value={info.jobs.total} />
            <InfoRow label="Hoàn thành" value={<span style={{ color: 'var(--ok)' }}>{info.jobs.completed}</span>} />
            <InfoRow label="Lỗi" value={<span style={{ color: 'var(--fail)' }}>{info.jobs.failed}</span>} />
            <InfoRow label="Đang chạy" value={<span style={{ color: 'var(--accent)' }}>{info.jobs.active}</span>} />
          </div>

          {/* Tips */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
            <SectionTitle>Hướng dẫn</SectionTitle>
            <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.8 }}>
              <div>• Cache lưu kết quả scene detection, transcription, motion path — tăng tốc render lại cùng video</div>
              <div>• Xóa cache nếu kết quả transcription/subtitle bị lỗi hoặc cần giải phóng dung lượng</div>
              <div>• Database <code>app.db</code> chứa toàn bộ lịch sử job — không xóa thủ công</div>
              <div>• Để tăng/giảm số job song song, đặt biến môi trường <code>MAX_CONCURRENT_JOBS</code></div>
            </div>
          </div>
        </>
      ) : (
        <div style={{ color: 'var(--fail)', fontSize: 12 }}>Không thể tải thông tin hệ thống</div>
      )}
    </div>
  )
}
