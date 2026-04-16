/**
 * generate-final-summary.ts
 *
 * Produces the human-readable final-summary.md for a completed pipeline run.
 * This document is the primary deliverable for engineering team review.
 *
 * It combines:
 *   - Task metadata and objective
 *   - Execution outcome
 *   - Review verdict and scores
 *   - Acceptance criteria results
 *   - Recommendations and follow-ups
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { loadTemplate } from './prompt-loader.js';
import { nowIso } from './ids.js';
import type {
  NormalizedPrompt,
  ExecutionResult,
  ReviewReport,
} from './types.js';

// ── Markdown helpers ──────────────────────────────────────────────────────────

function badge(verdict: string): string {
  const map: Record<string, string> = {
    accepted: '✅ ACCEPTED',
    accepted_with_followup: '⚠️ ACCEPTED WITH FOLLOW-UP',
    changes_requested: '🔄 CHANGES REQUESTED',
    rejected: '❌ REJECTED',
  };
  return map[verdict] ?? verdict.toUpperCase();
}

function statusBadge(status: string): string {
  const map: Record<string, string> = {
    success: '✅ SUCCESS',
    simulated: '🟡 SIMULATED',
    dry_run: '⚪ DRY RUN',
    partial: '⚠️ PARTIAL',
    failed: '❌ FAILED',
    timeout: '⏱️ TIMEOUT',
  };
  return map[status] ?? status.toUpperCase();
}

function scoreBar(score: number): string {
  const filled = Math.round(score);
  return '█'.repeat(filled) + '░'.repeat(10 - filled) + ` ${score}/10`;
}

function criteriaTable(criteria: ReviewReport['acceptance_criteria_results']): string {
  if (criteria.length === 0) return '_(no acceptance criteria recorded)_';
  const header = '| Criterion | Met | Evidence |\n|---|---|---|';
  const rows = criteria.map((c) => {
    const icon =
      c.met === 'yes' ? '✅' : c.met === 'partial' ? '⚠️' : c.met === 'no' ? '❌' : '❓';
    return `| ${c.criterion.slice(0, 60)} | ${icon} ${c.met} | ${c.evidence.slice(0, 80)} |`;
  });
  return [header, ...rows].join('\n');
}

function bulletList(items: string[], emptyText: string): string {
  if (!items || items.length === 0) return emptyText;
  return items.map((i) => `- ${i}`).join('\n');
}

function filesChangedList(
  files: ExecutionResult['files_changed']
): string {
  if (!files || files.length === 0) return '_(none reported)_';
  return files.map((f) => `- [\`${f.operation}\`] \`${f.path}\``).join('\n');
}

function blockingIssuesSection(issues: string[] | undefined): string {
  if (!issues || issues.length === 0) return '';
  return `## ❌ Blocking Issues\n\n${issues.map((i) => `- ${i}`).join('\n')}`;
}

// ── Unresolved placeholder guard ──────────────────────────────────────────────

function findUnresolvedPlaceholders(content: string): string[] {
  const matches = content.match(/\{\{[A-Z_]+\}\}/g);
  return matches ? [...new Set(matches)] : [];
}

// ── Summary builder ───────────────────────────────────────────────────────────

async function buildSummaryMarkdown(
  normalized: NormalizedPrompt,
  result: ExecutionResult,
  review: ReviewReport
): Promise<string> {
  const template = await loadTemplate('final-summary');

  // All variable names must match final-summary.md exactly.
  // Add new variables here when adding them to the template.
  const rendered = template
    .replace('{{TITLE}}', normalized.title)
    .replace('{{TASK_ID}}', normalized.task_id)
    .replace(/\{\{RUN_ID\}\}/g, result.run_id)                          // appears twice in template
    .replace('{{TASK_TYPE}}', normalized.task_type)
    .replace('{{COMPLEXITY}}', normalized.estimated_complexity)
    .replace('{{GENERATED_AT}}', nowIso())
    .replace('{{OBJECTIVE}}', normalized.objective)
    .replace('{{BUSINESS_CONTEXT}}', normalized.business_context)
    .replace('{{EXECUTION_STATUS}}', statusBadge(result.status))
    .replace('{{EXECUTOR_MODE}}', result.executor_mode)
    .replace('{{DURATION_MS}}', `${result.duration_ms}ms`)
    .replace('{{EXIT_CODE}}', result.exit_code != null ? String(result.exit_code) : 'n/a')
    .replace('{{EXECUTION_SUMMARY}}', result.summary ?? '_(no summary provided)_')
    .replace('{{FILES_CHANGED}}', filesChangedList(result.files_changed))
    .replace('{{RISKS}}', bulletList(result.risks ?? [], '_(none detected)_'))
    .replace('{{VERDICT_BADGE}}', badge(review.verdict))
    .replace('{{OVERALL_SCORE}}', scoreBar(review.overall_score))
    .replace('{{SCOPE_FIT_SCORE}}', scoreBar(review.scope_fit_score))
    .replace('{{SAFETY_SCORE}}', scoreBar(review.safety_score))
    .replace('{{LOGGING_SCORE}}', scoreBar(review.logging_score))
    .replace('{{CRITERIA_TABLE}}', criteriaTable(review.acceptance_criteria_results))
    .replace('{{SCOPE_ASSESSMENT}}', review.scope_assessment)
    .replace('{{SAFETY_ASSESSMENT}}', review.safety_assessment)
    .replace('{{LOGGING_ASSESSMENT}}', review.logging_assessment)
    .replace('{{REVIEW_SUMMARY}}', review.summary)
    .replace('{{RECOMMENDATIONS}}', bulletList(review.recommendations ?? [], '_(none)_'))
    .replace('{{FOLLOWUP_TASKS}}', bulletList((review.followup_tasks ?? []).map((t) => `[ ] ${t}`), '_(none)_'))
    .replace('{{BLOCKING_ISSUES}}', blockingIssuesSection(review.blocking_issues))
    .replace('{{SESSION_ID}}', result.session_id);

  // Fail fast: any surviving {{...}} means a template/renderer mismatch.
  const unresolved = findUnresolvedPlaceholders(rendered);
  if (unresolved.length > 0) {
    throw new Error(
      `Final summary template has unresolved placeholders after rendering: ${unresolved.join(', ')}. ` +
        'Align final-summary.md variable names with generate-final-summary.ts.'
    );
  }

  return rendered;
}

// ── Main export ───────────────────────────────────────────────────────────────

export async function generateFinalSummary(
  normalized: NormalizedPrompt,
  result: ExecutionResult,
  review: ReviewReport
): Promise<string> {
  const config = await loadConfig();

  const logger = createLogger('generate-final-summary', config, {
    task_id: normalized.task_id,
    run_id: result.run_id,
    session_id: result.session_id,
  });

  logger.info('Generating final summary', { task_id: normalized.task_id });

  const markdown = await buildSummaryMarkdown(normalized, result, review);

  // Persist to artifacts/<task_id>/<run_id>/final-summary.md
  // (also written during archive — this is an intermediate write)
  const artifactDir = path.resolve(
    process.cwd(),
    config.artifact_root,
    normalized.task_id,
    result.run_id
  );
  await fs.ensureDir(artifactDir);

  const summaryPath = path.join(artifactDir, 'final-summary.md');
  await fs.writeFile(summaryPath, markdown, 'utf-8');

  logger.info(`Final summary written: ${summaryPath}`);

  return markdown;
}
