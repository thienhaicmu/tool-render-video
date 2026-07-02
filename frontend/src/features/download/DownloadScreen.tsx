/**
 * DownloadScreen — P0.3 (frontend redesign): the sidebar "Download" panel.
 *
 * Previously this panel mounted features/downloader/DownloaderScreen — a
 * weaker, parallel implementation of the same backend downloader (no cookie
 * management, no staged list, no Send-to-Render). That screen is deleted;
 * this wrapper mounts the canonical DownloadTab (the one inside Clip
 * Studio) so both entry points share one implementation.
 *
 * DownloadTab speaks 'EN' | 'VI' while uiStore.lang is 'en' | 'vi' — same
 * mapping ClipStudio.tsx does.
 */
import { useUIStore } from '@/stores/uiStore'
import { DownloadTab } from '../clip-studio/download/DownloadTab'
import type { Lang } from '../clip-studio/ClipStudio'

export function DownloadScreen() {
  const uiLang = useUIStore((s) => s.lang)
  const lang: Lang = uiLang === 'vi' ? 'VI' : 'EN'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <DownloadTab lang={lang} />
    </div>
  )
}
