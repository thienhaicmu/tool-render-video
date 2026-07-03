import { BASE_URL } from '@/api/client'

export function getPartThumbnailUrl(jobId: string, partNo: number): string {
  return `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/thumbnail?t=0.5&w=320`
}

export function getPartMediaUrl(jobId: string, partNo: number): string {
  return `${BASE_URL}/api/render/jobs/${encodeURIComponent(jobId)}/parts/${partNo}/media`
}

export function fmtDuration(secs: number): string {
  const m = Math.floor(secs / 60)
  const s = Math.round(secs % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

// WP3 — accessible switch: same `.tog` visual, now keyboard-operable with a
// screen-reader role. Behaviour + styling unchanged.
export function Tog({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div
      role="switch"
      aria-checked={checked}
      tabIndex={0}
      className={`tog${checked ? ' on' : ''}`}
      onClick={() => onChange(!checked)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChange(!checked) }
      }}
    />
  )
}
