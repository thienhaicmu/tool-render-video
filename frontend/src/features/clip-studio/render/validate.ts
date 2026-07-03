/**
 * validate — pure, synchronous submit-time input checks (god-file slice 1).
 *
 * Extracted verbatim from RenderWorkflow.handleStartRender so the validation
 * is unit-testable in isolation (the component itself has no working test
 * harness). Behaviour + exact messages are preserved; the async Electron
 * pathExists check stays in the component between these two, so call order is:
 *   validateSources → (electron pathExists) → validateConfig.
 */
import type { ConfigState, Source } from './types'

export type RwLang = 'EN' | 'VI'

/** Source-list checks (run before the async pathExists probe). */
export function validateSources(sources: Source[], lang: RwLang): string | null {
  if (sources.length === 0) {
    return lang === 'VI' ? 'Chưa chọn file nguồn.' : 'No source file selected.'
  }
  for (const s of sources) {
    if (!(s.value || '').trim()) {
      return lang === 'VI' ? 'File nguồn rỗng.' : 'A source file path is empty.'
    }
  }
  return null
}

/** Config checks (run after the async pathExists probe). */
export function validateConfig(cfg: ConfigState, lang: RwLang): string | null {
  if (!(cfg.outputDir || '').trim()) {
    return lang === 'VI' ? 'Chưa chọn thư mục lưu (Save folder).' : 'Save folder is empty.'
  }
  if (cfg.minSec > cfg.maxSec) {
    return lang === 'VI'
      ? `Min clip duration (${cfg.minSec}s) lớn hơn max (${cfg.maxSec}s).`
      : `Min clip duration (${cfg.minSec}s) is greater than max (${cfg.maxSec}s).`
  }
  if (cfg.outputCount < 1) {
    return lang === 'VI' ? 'Số clip xuất ra phải ≥ 1.' : 'Output count must be ≥ 1.'
  }
  return null
}
