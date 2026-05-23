/**
 * AIChip — AI phase indicator chip.
 * Source: docs/design/components.md component #6
 */
export type AIChipVariant = 'applied' | 'advisory' | 'skipped' | 'unavailable'

export interface AIChipProps {
  variant: AIChipVariant
  label?: string
}

interface ChipConfig {
  defaultLabel: string
  iconColor: string
  textColor: string
  bg: string
  border?: string
}

const CHIP_CONFIG: Record<AIChipVariant, ChipConfig> = {
  applied: {
    defaultLabel: 'AI Applied',
    iconColor: 'var(--ai-active)',
    textColor: 'var(--ai-active)',
    bg: 'var(--ai-subtle)',
  },
  advisory: {
    defaultLabel: 'AI Advisory',
    iconColor: 'color-mix(in srgb, var(--ai-active) 60%, transparent)',
    textColor: 'color-mix(in srgb, var(--ai-active) 60%, transparent)',
    bg: 'color-mix(in srgb, var(--ai-subtle) 60%, transparent)',
  },
  skipped: {
    defaultLabel: 'AI Skipped',
    iconColor: 'var(--text-tertiary)',
    textColor: 'var(--text-tertiary)',
    bg: 'var(--surface-card)',
  },
  unavailable: {
    defaultLabel: 'AI Unavailable',
    iconColor: 'var(--text-disabled)',
    textColor: 'var(--text-disabled)',
    bg: 'transparent',
  },
}

export function AIChip({ variant, label }: AIChipProps) {
  const config = CHIP_CONFIG[variant]
  const displayLabel = label ?? config.defaultLabel

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        height: '20px',
        padding: '0 6px',
        borderRadius: 'var(--radius-sm)',
        backgroundColor: config.bg,
        fontSize: 'var(--text-xs)',
        fontWeight: 'var(--weight-medium)' as unknown as number,
        color: config.textColor,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          fontSize: '12px',
          color: config.iconColor,
          lineHeight: 1,
          flexShrink: 0,
        }}
        aria-hidden="true"
      >
        ⚡
      </span>
      {displayLabel}
    </span>
  )
}
