/**
 * error-ranking.ts — V3
 *
 * Core ranking module for bug candidate prioritisation.
 * Computes a deterministic priority score per error record using:
 *   severity + frequency + recency + context relevance boosts
 *
 * Weights (highest to lowest influence):
 *   severity      critical=100 | high=70 | medium=40 | low=10
 *   frequency     repeated errors add +10..+30
 *   recency       recent errors add +0..+20
 *   context       session/task/component boosts +4..+8
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export interface ErrorRecord {
  error_id: string;
  session_id: string;
  task_id: string;
  run_id: string;
  component: string;
  action: string;
  timestamp: string;         // ISO-8601
  error_name: string;
  error_message: string;
  severity?: Severity;       // stored if classified at capture time
  bug_signature?: string;    // stored if computed at capture time
  frequency_count?: number;  // stored from index at capture time
  bug_prompt_path?: string;  // relative path to .md artifact
}

export interface ScoredCandidate extends ErrorRecord {
  severity: Severity;
  bug_signature: string;
  frequency_count: number;
  scores: ScoreBreakdown;
}

export interface ScoreBreakdown {
  severity_score: number;
  frequency_score: number;
  recency_score: number;
  session_boost: number;
  task_boost: number;
  component_boost: number;
  total: number;
}

export interface RankingContext {
  session_id?: string;
  task_id?: string;
  component?: string;
}

// ---------------------------------------------------------------------------
// Severity classification
// ---------------------------------------------------------------------------

const SEVERITY_SCORES: Record<Severity, number> = {
  critical: 100,
  high: 70,
  medium: 40,
  low: 10,
};

/**
 * Classifies an error's severity from available metadata.
 * Explicit `severity` field wins; otherwise heuristics are applied.
 */
export function classifyErrorSeverity(record: Partial<ErrorRecord>): Severity {
  if (record.severity && isValidSeverity(record.severity)) return record.severity;

  const name    = (record.error_name    ?? '').toLowerCase();
  const msg     = (record.error_message ?? '').toLowerCase();
  const action  = (record.action        ?? '').toLowerCase();
  const comp    = (record.component     ?? '').toLowerCase();

  // Critical: crash, data-loss, security, fatal pipeline failure
  if (
    name.includes('fatal')          ||
    name.includes('segfault')       ||
    name.includes('unhandledrejection') ||
    msg.includes('process crashed') ||
    msg.includes('data corruption') ||
    msg.includes('segmentation fault') ||
    msg.includes('out of memory')   ||
    msg.includes('security')        ||
    action.includes('crash')
  ) return 'critical';

  // High: core feature broken — download, render, stream, send, repeated 5xx-like
  if (
    name.includes('error')           ||
    name.includes('exception')       ||
    msg.includes('download failed')  ||
    msg.includes('render failed')    ||
    msg.includes('stream failed')    ||
    msg.includes('send failed')      ||
    msg.includes('failed to extract') ||
    msg.includes('econnrefused')     ||
    msg.includes('enotfound')        ||
    msg.includes('etimedout')        ||
    msg.includes('timeout')          ||
    msg.includes('status 5')         ||
    action.includes('download')      ||
    action.includes('render')        ||
    action.includes('upload')        ||
    comp.includes('pipeline')
  ) return 'high';

  // Low: cosmetic, deprecated, debug/logging only
  if (
    name.includes('warning')     ||
    name.includes('deprecation') ||
    msg.includes('deprecated')   ||
    msg.includes('warn:')        ||
    action.includes('log')       ||
    action.includes('debug')
  ) return 'low';

  // Default fallback
  return 'medium';
}

export function isValidSeverity(v: unknown): v is Severity {
  return v === 'critical' || v === 'high' || v === 'medium' || v === 'low';
}

// ---------------------------------------------------------------------------
// Bug signature (fingerprint for frequency grouping)
// ---------------------------------------------------------------------------

/**
 * Produces a normalised fingerprint from component + action + error_name +
 * error_message (with IDs/numbers/paths stripped).
 * Used to group repeated occurrences of the same logical bug.
 */
export function computeBugSignature(record: Partial<ErrorRecord>): string {
  const component  = slug(record.component  ?? 'unknown');
  const action     = slug(record.action     ?? 'unknown');
  const error_name = slug(record.error_name ?? 'unknown');

  const normalised_msg = (record.error_message ?? '')
    .toLowerCase()
    .replace(/[a-f0-9-]{8,}/g, 'ID')   // UUIDs, hex IDs
    .replace(/\d{4,}/g, 'N')            // long numbers
    .replace(/(?:\/|\\)[^\s]*/g, 'PATH') // file/url paths
    .replace(/https?:\/\/[^\s]*/g, 'URL')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 100);

  return `${component}::${action}::${error_name}::${normalised_msg}`;
}

function slug(s: string): string {
  return s.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
}

// ---------------------------------------------------------------------------
// Individual score components
// ---------------------------------------------------------------------------

export function severityScore(s: Severity): number {
  return SEVERITY_SCORES[s];
}

export function frequencyScore(count: number): number {
  if (count <= 1) return 0;
  if (count <= 2) return 10;
  if (count <= 5) return 20;
  return 30;
}

export function recencyScore(timestamp: string): number {
  const ageMs  = Date.now() - new Date(timestamp).getTime();
  const ageMin = ageMs / 60_000;
  if (ageMin <=   5) return 20;
  if (ageMin <=  30) return 15;
  if (ageMin <= 120) return 10;
  if (ageMin <= 1440) return 5;   // within 24 h
  return 0;
}

// ---------------------------------------------------------------------------
// Prompt content builder (shared template — single source of truth)
// ---------------------------------------------------------------------------

/**
 * Builds the markdown content for a bug-fix prompt artifact.
 * Used by both build-bug-prompt.ts (generation) and log-error.ts (regeneration).
 */
export function buildPromptContent(r: ErrorRecord): string {
  const freq_note =
    (r.frequency_count ?? 1) > 1
      ? `\n> **Note:** This error has occurred **${r.frequency_count} times** — it is a repeated bug.`
      : '';

  const signature = r.bug_signature ?? computeBugSignature(r);

  return `# Bug Fix Request

## Error Summary

| Field           | Value |
|-----------------|-------|
| **error_id**    | \`${r.error_id}\` |
| **severity**    | ${r.severity ?? classifyErrorSeverity(r)} |
| **component**   | ${r.component} |
| **action**      | ${r.action} |
| **error_name**  | ${r.error_name} |
| **frequency**   | ${r.frequency_count ?? 1}× |
| **timestamp**   | ${r.timestamp} |
| **session_id**  | ${r.session_id} |
| **task_id**     | ${r.task_id} |
| **run_id**      | ${r.run_id} |
${freq_note}

## Error Message

\`\`\`
${r.error_message}
\`\`\`

## Bug Signature

\`\`\`
${signature}
\`\`\`

## Fix Instructions

You are an expert software engineer. Perform the following steps:

1. Identify the **root cause** of the error described above.
2. Locate the relevant source file(s) in component \`${r.component}\`, action \`${r.action}\`.
3. Propose and apply a minimal, targeted fix.
4. Do **not** refactor unrelated code.
5. Do **not** add unnecessary comments or type annotations.
6. After applying the fix, briefly explain what caused the error and what was changed.

Focus only on fixing this specific bug. Be surgical.
`;
}

// ---------------------------------------------------------------------------
// Full ranking
// ---------------------------------------------------------------------------

/**
 * Ranks error records from highest to lowest priority.
 *
 * @param records         Raw error records loaded from disk
 * @param context         Current session/task/component for relevance boosts
 * @param signatureCounts Map<bug_signature, total_count> from error-index
 */
export function rankCandidates(
  records: ErrorRecord[],
  context: RankingContext,
  signatureCounts: Map<string, number>,
): ScoredCandidate[] {
  const scored: ScoredCandidate[] = records.map((r) => {
    const severity      = classifyErrorSeverity(r);
    const bug_signature = r.bug_signature ?? computeBugSignature(r);
    const frequency_count =
      signatureCounts.get(bug_signature) ??
      r.frequency_count ??
      1;

    const sev_score   = severityScore(severity);
    const freq_score  = frequencyScore(frequency_count);
    const rec_score   = recencyScore(r.timestamp);

    const session_boost   = context.session_id   && r.session_id === context.session_id   ? 8 : 0;
    const task_boost      = context.task_id       && r.task_id    === context.task_id      ? 6 : 0;
    const component_boost = context.component     && r.component  === context.component    ? 4 : 0;

    const total =
      sev_score + freq_score + rec_score +
      session_boost + task_boost + component_boost;

    return {
      ...r,
      severity,
      bug_signature,
      frequency_count,
      scores: {
        severity_score:   sev_score,
        frequency_score:  freq_score,
        recency_score:    rec_score,
        session_boost,
        task_boost,
        component_boost,
        total,
      },
    };
  });

  // Primary sort: total score descending; tiebreak: timestamp descending
  return scored.sort((a, b) => {
    if (b.scores.total !== a.scores.total) return b.scores.total - a.scores.total;
    return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
  });
}
