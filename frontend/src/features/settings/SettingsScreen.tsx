import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '@/api/client'

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
