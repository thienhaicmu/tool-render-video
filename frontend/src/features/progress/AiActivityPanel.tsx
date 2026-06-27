/**
 * AiActivityPanel — shows AI Director activity during active rendering.
 * Renders only when ai_director_enabled is true in the payload.
 */
import type { RenderStage } from '../../types/enums'

// `satisfies` validates every member is a real backend stage (C1) without
// widening the Set's runtime/`.has(string)` ergonomics.
const AI_ANALYZING_STAGE_LIST = [
  'analyzing',
  'segment_building',
  'transcribing_full',
  'scene_detection',
] as const satisfies readonly RenderStage[]
const AI_ANALYZING_STAGES = new Set<string>(AI_ANALYZING_STAGE_LIST)

const MODE_COLORS: Record<string, string> = {
  local: '#6B7280',
  cloud: '#3B82F6',
  hybrid: 'var(--color-accent)',
}

const MODE_SUBSTEP: Record<string, string> = {
  local: '◉ Local scoring',
  cloud: '◉ Cloud analysis',
  hybrid: '◉ Local → Cloud → Merge',
}

const AI_KEYWORDS = [
  'ai', 'director', 'analyz', 'scor', 'rank', 'cloud', 'hybrid',
  'model', 'infer', 'llm', 'gemini', 'openai', 'claude',
]

function isAiMessage(text: string): boolean {
  const lower = text.toLowerCase()
  return AI_KEYWORDS.some((kw) => lower.includes(kw))
}

interface ParsedPayload {
  ai_director_enabled?: boolean
  ai_analysis_mode?: string
  ai_cloud_provider?: string
}

function parsePayload(payloadJson: string): ParsedPayload {
  try {
    return JSON.parse(payloadJson) as ParsedPayload
  } catch {
    return {}
  }
}

export interface AiActivityPanelProps {
  payloadJson: string
  currentStage: string | null
  messages: string[]
}

export function AiActivityPanel({ payloadJson, currentStage, messages }: AiActivityPanelProps) {
  const payload = parsePayload(payloadJson)

  if (!payload.ai_director_enabled) return null

  const mode = (payload.ai_analysis_mode ?? 'hybrid') as string
  const provider = payload.ai_cloud_provider
  const modeColor = MODE_COLORS[mode] ?? 'var(--color-accent)'
  const isAnalyzing = currentStage !== null && AI_ANALYZING_STAGES.has(currentStage)

  // Find the most recent AI-related message
  let currentMsg = ''
  for (let i = messages.length - 1; i >= 0; i--) {
    if (isAiMessage(messages[i])) {
      currentMsg = messages[i]
      break
    }
  }

  return (
    <div
      style={{
        backgroundColor: 'rgba(108, 99, 255, 0.08)',
        border: '1px solid rgba(108, 99, 255, 0.2)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      {/* Title row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {/* Activity indicator */}
        <span
          className={isAnalyzing ? 'ai-dot-pulse' : undefined}
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: isAnalyzing ? 'var(--color-accent)' : 'var(--color-text-secondary)',
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: 'var(--font-size-xs)',
            fontWeight: 'var(--font-weight-semibold)' as unknown as number,
            color: 'var(--color-text-primary)',
          }}
        >
          AI Director
        </span>
        {/* Mode badge */}
        <span
          style={{
            fontSize: 'var(--font-size-xs)',
            backgroundColor: modeColor === 'var(--color-accent)'
              ? 'var(--color-accent-muted)'
              : `${modeColor}22`,
            color: modeColor,
            borderRadius: 'var(--radius-sm)',
            padding: '1px 6px',
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
            textTransform: 'capitalize' as const,
          }}
        >
          {mode}
        </span>
        {/* Provider badge — only for cloud/hybrid */}
        {provider && (mode === 'cloud' || mode === 'hybrid') && (
          <span
            style={{
              fontSize: 'var(--font-size-xs)',
              backgroundColor: 'rgba(59, 130, 246, 0.15)',
              color: '#3B82F6',
              borderRadius: 'var(--radius-sm)',
              padding: '1px 6px',
              fontWeight: 'var(--font-weight-medium)' as unknown as number,
              textTransform: 'capitalize' as const,
            }}
          >
            {provider}
          </span>
        )}
      </div>

      {/* Sub-step when analyzing */}
      {isAnalyzing && (
        <div
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-accent)',
            opacity: 0.85,
          }}
        >
          {MODE_SUBSTEP[mode] ?? '◉ Analyzing'}
        </div>
      )}

      {/* Most recent AI-related message */}
      {currentMsg && (
        <div
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            wordBreak: 'break-word',
          }}
        >
          {currentMsg}
        </div>
      )}
    </div>
  )
}
