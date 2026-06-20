/**
 * AiSummaryCard — shows AI analysis summary for a completed job.
 * Renders only when ai_director_enabled is true in the payload.
 */

const MODE_COLORS: Record<string, string> = {
  local: '#6B7280',
  cloud: '#3B82F6',
  hybrid: 'var(--color-accent)',
}

const PROVIDER_MODEL_HINT: Record<string, string> = {
  gemini: 'gemini-2.5-flash',
  openai: 'gpt-4o',
  claude: 'claude-sonnet-4-6',
}

interface ParsedPayload {
  ai_director_enabled?: boolean
  ai_analysis_mode?: string
  ai_cloud_provider?: string
}

interface ParsedResult {
  output_rank_score?: number
  is_best_output?: boolean
  is_best_clip?: boolean
}

function parsePayload(json: string): ParsedPayload {
  try { return JSON.parse(json) as ParsedPayload } catch { return {} }
}

function parseResult(json: string): ParsedResult {
  try { return JSON.parse(json) as ParsedResult } catch { return {} }
}

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--color-success)'
  if (score >= 60) return '#F59E0B'
  return 'var(--color-text-secondary)'
}

export interface AiSummaryCardProps {
  payloadJson: string
  resultJson: string
}

export function AiSummaryCard({ payloadJson, resultJson }: AiSummaryCardProps) {
  const payload = parsePayload(payloadJson)
  const result = parseResult(resultJson)

  if (!payload.ai_director_enabled) return null

  const mode = (payload.ai_analysis_mode ?? 'hybrid') as string
  const provider = payload.ai_cloud_provider
  const modeColor = MODE_COLORS[mode] ?? 'var(--color-accent)'
  const rankScore = typeof result.output_rank_score === 'number' ? result.output_rank_score : null
  const modelHint = provider ? PROVIDER_MODEL_HINT[provider] : null

  return (
    <div
      style={{
        backgroundColor: 'rgba(108, 99, 255, 0.06)',
        border: '1px solid rgba(108, 99, 255, 0.15)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      {/* Section title + badges */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--color-text-secondary)',
            fontWeight: 'var(--font-weight-medium)' as unknown as number,
          }}
        >
          AI Analysis
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

      {/* Stats row */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--space-4)',
          flexWrap: 'wrap',
          fontSize: 'var(--font-size-xs)',
        }}
      >
        {rankScore !== null && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ color: 'var(--color-text-secondary)' }}>Best Score</span>
            <span
              style={{
                fontWeight: 'var(--font-weight-semibold)' as unknown as number,
                color: scoreColor(rankScore),
                fontSize: 'var(--font-size-base)',
              }}
            >
              {Math.round(rankScore)}
            </span>
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ color: 'var(--color-text-secondary)' }}>Mode</span>
          <span
            style={{
              color: modeColor,
              fontWeight: 'var(--font-weight-medium)' as unknown as number,
              textTransform: 'capitalize',
            }}
          >
            {mode}
          </span>
        </div>
        {provider && (mode === 'cloud' || mode === 'hybrid') && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={{ color: 'var(--color-text-secondary)' }}>Provider</span>
            <span style={{ color: 'var(--color-text-primary)', textTransform: 'capitalize' }}>
              {provider}
              {modelHint && (
                <span style={{ color: 'var(--color-text-secondary)', marginLeft: 4 }}>
                  ({modelHint})
                </span>
              )}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
