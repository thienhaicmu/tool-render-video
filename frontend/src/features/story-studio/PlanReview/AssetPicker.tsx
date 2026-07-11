/**
 * AssetPicker — modal to pick a library asset (character/background) in Review (AL4).
 *
 * Lists indexed assets (GET /api/story/assets) filtered by kind (fixed by the caller)
 * + region/genre/search; picking one calls onPick(asset) so the parent assigns it to
 * the plan (character → render.masters, background → render.visual_assets) — the render
 * then uses it directly instead of calling AI (library-first, AL3).
 */
import { useEffect, useState } from 'react'
import { listStoryAssets, scanStoryAssets, storyAssetImageUrl, type StoryAsset } from '../../../api/storyAssets'

const REGIONS = ['', 'cn', 'jp', 'ko', 'vi', 'eu', 'us'] as const
const GENRES = ['', 'wuxia', 'ngontinh', 'horror', 'fantasy', 'codai', 'hiendai'] as const

export function AssetPicker({ vi, kind, region: region0 = '', genre: genre0 = '', onPick, onClose }: {
  vi: boolean
  kind: string
  region?: string
  genre?: string
  onPick: (asset: StoryAsset) => void
  onClose: () => void
}) {
  const [region, setRegion] = useState(region0)
  const [genre, setGenre] = useState(genre0)
  const [q, setQ] = useState('')
  const [assets, setAssets] = useState<StoryAsset[]>([])
  const [busy, setBusy] = useState(false)
  const [scanMsg, setScanMsg] = useState('')

  const load = () => {
    setBusy(true)
    void listStoryAssets({ kind, region, genre, q })
      .then((r) => setAssets(r.assets || []))
      .catch(() => setAssets([]))
      .finally(() => setBusy(false))
  }
  useEffect(load, [kind, region, genre, q])   // eslint-disable-line react-hooks/exhaustive-deps

  async function rescan() {
    setScanMsg(vi ? 'Đang quét…' : 'Scanning…')
    try {
      const r = await scanStoryAssets()
      setScanMsg(vi ? `Đã quét: ${r.indexed} asset` : `Indexed: ${r.indexed}`)
      load()
    } catch { setScanMsg(vi ? '⚠ Lỗi quét' : '⚠ Scan failed') }
  }

  const kindLabel = kind === 'background' ? (vi ? 'nền' : 'backgrounds')
    : kind === 'object' ? (vi ? 'đồ vật' : 'objects') : (vi ? 'nhân vật' : 'characters')

  return (
    <div className="st-console-backdrop" onMouseDown={onClose}>
      <div className="st-asset-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="st-asset-head">
          <strong>{vi ? `Kho ${kindLabel}` : `${kindLabel} library`}</strong>
          <button type="button" className="st-icon-btn" onClick={onClose} title="Close">✕</button>
        </div>
        <div className="st-asset-filters">
          <select className="st-select st-select--sm" value={region} onChange={(e) => setRegion(e.target.value)}>
            {REGIONS.map((r) => <option key={r} value={r}>{r || (vi ? 'mọi vùng' : 'all regions')}</option>)}
          </select>
          <select className="st-select st-select--sm" value={genre} onChange={(e) => setGenre(e.target.value)}>
            {GENRES.map((g) => <option key={g} value={g}>{g || (vi ? 'mọi thể loại' : 'all genres')}</option>)}
          </select>
          <input className="st-input st-input--sm" value={q} placeholder={vi ? 'Tìm…' : 'Search…'}
            onChange={(e) => setQ(e.target.value)} />
          <button type="button" className="st-btn st-btn--sm" onClick={rescan}>{vi ? '↻ Quét kho' : '↻ Rescan'}</button>
          <span className="st-muted st-asset-scanmsg">{scanMsg}</span>
        </div>
        {busy && <div className="st-muted st-asset-empty">{vi ? 'Đang tải…' : 'Loading…'}</div>}
        {!busy && assets.length === 0 && (
          <div className="st-muted st-asset-empty">
            {vi ? 'Kho trống. Sinh ảnh theo docs/asset_library_prompts.md, lưu vào asset_library rồi bấm "Quét kho".'
                : 'Empty. Generate images (docs/asset_library_prompts.md), save into asset_library, then "Rescan".'}
          </div>
        )}
        <div className="st-asset-grid">
          {assets.map((a) => (
            <button key={a.id} type="button" className="st-asset-card"
              onClick={() => { onPick(a); onClose() }} title={a.slug}>
              <div className="st-asset-thumb"
                style={{ background: a.transparent ? 'repeating-conic-gradient(#c8c8c8 0% 25%, #fff 0% 50%) 50% / 12px 12px' : 'var(--bg-panel)' }}>
                <img src={storyAssetImageUrl(a.id)} alt={a.slug} loading="lazy" />
              </div>
              <span className="st-asset-name">{a.name || a.slug}</span>
              <span className="st-asset-meta st-muted">{[a.region, a.genre].filter(Boolean).join('·')}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
