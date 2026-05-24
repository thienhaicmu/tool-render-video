import { useUIStore } from '../stores/uiStore'
import { translations, type TranslationKey } from './translations'

export function useI18n() {
  const lang = useUIStore((s) => s.lang)
  const setLang = useUIStore((s) => s.setLang)

  function t(key: TranslationKey): string {
    const dict = translations[lang] as Record<string, string>
    const fallback = translations.en as Record<string, string>
    return dict[key] ?? fallback[key] ?? key
  }

  return { t, lang, setLang }
}
