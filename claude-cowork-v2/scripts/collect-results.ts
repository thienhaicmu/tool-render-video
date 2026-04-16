/**
 * collect-results.ts
 *
 * Collects and summarizes execution results.
 * In a full production system this stage would:
 *   - Parse Claude CLI structured output (JSON lines, tool calls, etc.)
 *   - Resolve file diffs and classify changes
 *   - Detect risk patterns (auth changes, schema changes, etc.)
 *   - Write a normalized ExecutionResult
 *
 * Currently it loads the raw execution result and enriches it
 * with any additional analysis that can be done without re-running
 * the executor.
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import type { ExecutionResult, NormalizedPrompt } from './types.js';

// ── Risk pattern detection ────────────────────────────────────────────────────

const RISK_PATTERNS: Array<{ pattern: RegExp; flag: string }> = [
  { pattern: /auth|jwt|token|session|password|secret/i, flag: 'Possible auth/secret modification' },
  { pattern: /migrate|migration|schema|alter table|drop table/i, flag: 'Database schema change detected' },
  { pattern: /rm -rf|shutil\.rmtree|os\.remove|unlink/i, flag: 'Destructive file operation pattern' },
  { pattern: /eval\(|exec\(|subprocess/i, flag: 'Dynamic code execution pattern' },
  { pattern: /CORS|cors_origins|Access-Control/i, flag: 'CORS configuration change' },
];

function detectRisks(content: string): string[] {
  const flags: string[] = [];
  for (const { pattern, flag } of RISK_PATTERNS) {
    if (pattern.test(content)) {
      flags.push(flag);
    }
  }
  return flags;
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Enriches an execution result with additional analysis.
 * Returns the updated ExecutionResult.
 */
export async function collectResults(
  result: ExecutionResult,
  normalized: NormalizedPrompt
): Promise<ExecutionResult> {
  const config = await loadConfig();

  const logger = createLogger('collect-results', config, {
    task_id: result.task_id,
    run_id: result.run_id,
    session_id: result.session_id,
  });

  logger.info('Collecting and enriching execution results', { run_id: result.run_id });

  // Attempt to read stdout for risk analysis
  let stdoutContent = result.stdout_excerpt ?? '';
  if (result.stdout_path) {
    try {
      const full = await fs.readFile(result.stdout_path, 'utf-8');
      stdoutContent = full.slice(0, 8000); // Analyze first 8KB
    } catch {
      // Best-effort
    }
  }

  // Detect risks from stdout content
  const detectedRisks = detectRisks(stdoutContent + (result.summary ?? ''));
  const combinedRisks = [
    ...(result.risks ?? []),
    ...detectedRisks.filter((r) => !(result.risks ?? []).includes(r)),
  ];

  // Cross-reference expected deliverables against the execution summary
  const deliverablesMissing: string[] = [];
  for (const deliverable of normalized.expected_deliverables) {
    // Simple heuristic: if a deliverable is mentioned in stdout, it's likely done
    const mentioned = stdoutContent.toLowerCase().includes(
      deliverable.toLowerCase().slice(0, 20)
    );
    if (!mentioned && result.status !== 'simulated' && result.status !== 'dry_run') {
      deliverablesMissing.push(deliverable);
    }
  }

  const enriched: ExecutionResult = {
    ...result,
    risks: combinedRisks,
    followups: [
      ...(result.followups ?? []),
      ...(deliverablesMissing.length > 0
        ? [`Verify these deliverables: ${deliverablesMissing.join(', ')}`]
        : []),
    ],
  };

  // Update the persisted execution result with enriched data
  const resultDir = path.resolve(process.cwd(), config.tasks_root, 'execution-results');
  const resultPath = path.join(resultDir, `${result.task_id}-${result.run_id}.json`);
  await fs.writeJson(resultPath, enriched, { spaces: 2 });

  logger.info('Result collection complete', {
    detected_risks: detectedRisks.length,
    deliverables_missing: deliverablesMissing.length,
  });

  return enriched;
}
