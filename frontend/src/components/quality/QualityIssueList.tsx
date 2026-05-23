/**
 * QualityIssueList — renders a list of QualityIssue[], grouped by severity.
 */
import React from 'react'
import { Badge } from '../ui/Badge'
import type { QualityIssue } from '../../types/api'
import type { BadgeVariant } from '../ui/Badge'

export interface QualityIssueListProps {
  issues: QualityIssue[]
}

const SEVERITY_ORDER: QualityIssue['severity'][] = ['critical', 'error', 'warning', 'info']

const SEVERITY_VARIANT: Record<QualityIssue['severity'], BadgeVariant> = {
  critical: 'error',
  error:    'error',
  warning:  'warning',
  info:     'info',
}

const SEVERITY_LABEL: Record<QualityIssue['severity'], string> = {
  critical: 'Critical',
  error:    'Error',
  warning:  'Warning',
  info:     'Info',
}

export function QualityIssueList({ issues }: QualityIssueListProps) {
  if (issues.length === 0) {
    return (
      <p style={emptyStyle}>No quality issues found.</p>
    )
  }

  // Group by severity
  const grouped = SEVERITY_ORDER.reduce<Record<string, QualityIssue[]>>((acc, sev) => {
    const items = issues.filter((i) => i.severity === sev)
    if (items.length > 0) acc[sev] = items
    return acc
  }, {})

  return (
    <div style={containerStyle}>
      {SEVERITY_ORDER.filter((sev) => grouped[sev]).map((sev) => (
        <section key={sev} style={groupStyle}>
          <div style={groupHeaderStyle}>
            <Badge variant={SEVERITY_VARIANT[sev]} size="sm">
              {SEVERITY_LABEL[sev]}
            </Badge>
            <span style={countStyle}>{grouped[sev].length}</span>
          </div>

          <ul style={listStyle}>
            {grouped[sev].map((issue, idx) => (
              <li key={`${issue.code}_${idx}`} style={issueItemStyle}>
                <div style={issueHeaderStyle}>
                  <code style={codeStyle}>{issue.code}</code>
                  <span style={confidenceStyle}>
                    {Math.round(issue.confidence * 100)}% confidence
                  </span>
                </div>
                <p style={messageStyle}>{issue.message}</p>
                {issue.recommended_action && (
                  <p style={actionStyle}>→ {issue.recommended_action}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-4)',
}

const emptyStyle: React.CSSProperties = {
  color: 'var(--color-success)',
  fontSize: 'var(--font-size-sm)',
}

const groupStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2)',
}

const groupHeaderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
}

const countStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-disabled)',
}

const listStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2)',
  listStyle: 'none',
}

const issueItemStyle: React.CSSProperties = {
  backgroundColor: 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)',
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-1)',
}

const issueHeaderStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
}

const codeStyle: React.CSSProperties = {
  fontFamily: 'var(--font-family-mono)',
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-accent)',
}

const confidenceStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-disabled)',
}

const messageStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-primary)',
}

const actionStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-secondary)',
  fontStyle: 'italic',
}
