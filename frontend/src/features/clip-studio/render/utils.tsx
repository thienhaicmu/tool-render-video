import { BASE_URL } from '../../../api/client'

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

export function Tog({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return <div className={`tog${checked ? ' on' : ''}`} onClick={() => onChange(!checked)} />
}
