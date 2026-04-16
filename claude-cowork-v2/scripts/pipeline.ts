/**
 * pipeline.ts
 *
 * Main orchestrator for the Claude Cowork V2 pipeline.
 *
 * Executes these stages in order:
 *   1. Intake        — receive and persist the raw task
 *   2. Normalize     — transform raw prompt into structured NormalizedPrompt
 *   3. Validate      — schema-validate the normalized task
 *   4. Build Pack    — assemble the task pack markdown
 *   5. Execute       — run through the configured executor
 *   6. Collect       — enrich execution result with analysis
 *   7. Review        — evaluate execution against acceptance criteria
 *   8. Summarize     — generate final-summary.md
 *   9. Archive       — bundle all artifacts
 *  10. Finalize      — write pipeline completion event
 *
 * Usage:
 *   tsx scripts/pipeline.ts --file tasks/incoming/sample-task.json
 *   tsx scripts/pipeline.ts --task-id task_xyz123   (resume from existing intake)
 *
 * Each stage is wrapped in try/catch. Non-critical stage failures
 * are logged and recorded in stage_errors without stopping the pipeline.
 * Critical failures (normalization, execution) stop the pipeline and
 * still produce a partial artifact bundle for debugging.
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { generateRunId, generateSessionId, nowIso } from './ids.js';
import { intakeTask, loadRawTask } from './task-intake.js';
import { normalizePrompt } from './normalize-prompt.js';
import { buildTaskPack } from './build-task-pack.js';
import { runClaudeTask } from './run-claude-task.js';
import { collectResults } from './collect-results.js';
import { reviewTask } from './review-task.js';
import { generateFinalSummary } from './generate-final-summary.js';
import { archiveArtifacts } from './archive-artifacts.js';
import type {
  PipelineContext,
  RawTask,
  NormalizedPrompt,
  ExecutionResult,
  ReviewReport,
} from './types.js';

// ── Stage wrappers ────────────────────────────────────────────────────────────

/**
 * Wraps a pipeline stage. Logs entry/exit and catches non-critical errors.
 * Set `critical=true` to re-throw on failure (stops the pipeline).
 */
async function runStage<T>(
  name: string,
  ctx: PipelineContext,
  fn: () => Promise<T>,
  critical = false
): Promise<T | undefined> {
  const logger = createLogger(name, ctx.config, {
    task_id: ctx.task_id,
    run_id: ctx.run_id,
    session_id: ctx.session_id,
  });

  logger.debug(`Stage starting: ${name}`);

  try {
    const result = await fn();
    logger.debug(`Stage complete: ${name}`);
    return result;
  } catch (err) {
    const errorMsg = String(err);
    logger.error(`Stage failed: ${name}`, { error: errorMsg });
    ctx.stage_errors.push({ stage: name, error: errorMsg });

    if (critical) {
      throw new Error(`Critical stage "${name}" failed: ${errorMsg}`);
    }

    return undefined;
  }
}

// ── Pipeline update helpers ───────────────────────────────────────────────────

async function updateState(taskId: string, runId: string, status: string): Promise<void> {
  const statePath = path.resolve(process.cwd(), '.claude-cowork', 'state.json');
  try {
    const existing = await fs.readJson(statePath).catch(() => ({}));
    await fs.writeJson(
      statePath,
      {
        ...existing,
        last_run_at: nowIso(),
        last_task_id: taskId,
        last_run_id: runId,
        last_status: status,
      },
      { spaces: 2 }
    );
  } catch {
    // State file write failure is non-critical
  }
}

// ── Main pipeline ─────────────────────────────────────────────────────────────

export async function runPipeline(rawTaskInput: {
  raw_task?: RawTask;
  task_id?: string;
}): Promise<PipelineContext> {
  const config = await loadConfig();
  const run_id = generateRunId();
  const session_id = generateSessionId();

  // ── Stage 1: Intake ─────────────────────────────────────────────────────────
  let rawTask: RawTask;

  if (rawTaskInput.raw_task) {
    rawTask = rawTaskInput.raw_task;
  } else if (rawTaskInput.task_id) {
    rawTask = await loadRawTask(rawTaskInput.task_id);
  } else {
    throw new Error('runPipeline requires either raw_task or task_id');
  }

  const ctx: PipelineContext = {
    task_id: rawTask.task_id,
    run_id,
    session_id,
    config,
    raw_task: rawTask,
    started_at: nowIso(),
    status: 'completed',
    stage_errors: [],
  };

  const logger = createLogger('pipeline', config, {
    task_id: ctx.task_id,
    run_id,
    session_id,
  });

  logger.info('Pipeline starting', {
    task_id: ctx.task_id,
    run_id,
    session_id,
    executor_mode: config.executor_mode,
    normalizer_provider: config.normalizer_provider,
    reviewer_provider: config.reviewer_provider,
  });

  try {
    // ── Stage 2: Normalize ────────────────────────────────────────────────────
    const normalized = await runStage<NormalizedPrompt>(
      'normalize',
      ctx,
      () => normalizePrompt(rawTask, run_id, session_id),
      true // critical — pipeline cannot continue without normalization
    );

    if (!normalized) {
      throw new Error('Normalization returned no result');
    }

    ctx.normalized = normalized;

    // ── Stage 3: Build task pack ──────────────────────────────────────────────
    const taskPack = await runStage(
      'build-task-pack',
      ctx,
      () => buildTaskPack(normalized, run_id, session_id),
      true // critical — executor needs the task pack
    );

    if (!taskPack) {
      throw new Error('Task pack build returned no result');
    }

    ctx.task_pack_path = taskPack.task_pack_path;

    // ── Stage 4: Execute ──────────────────────────────────────────────────────
    const executionResult = await runStage<ExecutionResult>(
      'execute',
      ctx,
      () =>
        runClaudeTask(normalized, taskPack.task_pack_path, taskPack.task_pack_content, run_id, session_id),
      true // critical — no result to review without execution
    );

    if (!executionResult) {
      throw new Error('Execution returned no result');
    }

    ctx.execution_result = executionResult;

    // ── Stage 5: Collect results ──────────────────────────────────────────────
    const enrichedResult = await runStage<ExecutionResult>(
      'collect-results',
      ctx,
      () => collectResults(executionResult, normalized),
      false // non-critical — enrichment is best-effort
    );

    if (enrichedResult) {
      ctx.execution_result = enrichedResult;
    }

    const finalResult = ctx.execution_result!;

    // ── Stage 6: Review ───────────────────────────────────────────────────────
    const review = await runStage<ReviewReport>(
      'review',
      ctx,
      () => reviewTask(normalized, finalResult),
      false // non-critical — a failed review is still useful data
    );

    const fallbackReview: ReviewReport = {
      schema_version: '2.0',
      task_id: ctx.task_id,
      run_id,
      reviewed_at: nowIso(),
      reviewer_mode: 'deterministic',
      verdict: 'changes_requested',
      scope_fit_score: 0,
      safety_score: 0,
      logging_score: 0,
      overall_score: 0,
      acceptance_criteria_results: [],
      scope_assessment: 'Review stage failed — see stage_errors.',
      safety_assessment: 'Review stage failed.',
      logging_assessment: 'Review stage failed.',
      summary: 'Review could not be completed due to a pipeline error.',
      recommendations: ['Investigate review stage failure in pipeline logs.'],
    };

    ctx.review_report = review ?? fallbackReview;

    // ── Stage 7: Generate final summary ───────────────────────────────────────
    let finalSummaryMd = '';
    await runStage(
      'generate-final-summary',
      ctx,
      async () => {
        finalSummaryMd = await generateFinalSummary(
          normalized,
          finalResult,
          ctx.review_report!
        );
      },
      false
    );

    // ── Stage 8: Archive artifacts ────────────────────────────────────────────
    const manifest = await runStage(
      'archive',
      ctx,
      () =>
        archiveArtifacts({
          normalized,
          result: finalResult,
          review: ctx.review_report!,
          final_summary_md: finalSummaryMd,
          pipeline_status: ctx.stage_errors.length === 0 ? 'completed' : 'partial',
        }),
      false
    );

    if (manifest) {
      ctx.artifact_manifest = manifest;
    }

    // ── Stage 9: Finalize ─────────────────────────────────────────────────────
    ctx.completed_at = nowIso();
    ctx.status = ctx.stage_errors.length === 0 ? 'completed' : 'partial';

    logger.event('pipeline.completed', 'completed', {
      task_id: ctx.task_id,
      run_id,
      pipeline_status: ctx.status,
      execution_status: finalResult.status,
      review_verdict: ctx.review_report?.verdict,
      stage_errors: ctx.stage_errors.length,
      artifact_root: manifest?.artifact_root,
    });

    logger.info(
      `Pipeline complete. Verdict: ${ctx.review_report?.verdict ?? 'unknown'}. ` +
        `Status: ${ctx.status}. Artifacts: ${manifest?.artifact_root ?? 'not archived'}`,
      { stage_errors: ctx.stage_errors }
    );
  } catch (err) {
    const errorMsg = String(err);
    ctx.status = 'failed';
    ctx.completed_at = nowIso();

    logger.event('pipeline.failed', 'failed', { stage_errors: ctx.stage_errors }, errorMsg);
    logger.error('Pipeline failed at a critical stage', { error: errorMsg });

    // Attempt partial archive for debugging
    if (ctx.normalized && ctx.execution_result) {
      try {
        await archiveArtifacts({
          normalized: ctx.normalized,
          result: ctx.execution_result,
          review: ctx.review_report ?? {
            schema_version: '2.0',
            task_id: ctx.task_id,
            run_id,
            reviewed_at: nowIso(),
            reviewer_mode: 'deterministic',
            verdict: 'rejected',
            scope_fit_score: 0,
            safety_score: 0,
            logging_score: 0,
            overall_score: 0,
            acceptance_criteria_results: [],
            scope_assessment: 'Pipeline failed.',
            safety_assessment: 'Pipeline failed.',
            logging_assessment: 'Pipeline failed.',
            summary: `Pipeline failed: ${errorMsg}`,
            recommendations: ['Investigate pipeline.failed event in logs.'],
          },
          final_summary_md: `# Pipeline Failed\n\nError: ${errorMsg}\n`,
          pipeline_status: 'failed',
        });
        logger.info('Partial artifact bundle saved for debugging');
      } catch (archiveErr) {
        logger.error('Could not save partial artifact bundle', { error: String(archiveErr) });
      }
    }
  }

  await updateState(ctx.task_id, run_id, ctx.status);
  return ctx;
}

// ── CLI entry point ───────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  const fileIdx = args.indexOf('--file');
  const taskIdIdx = args.indexOf('--task-id');
  const promptIdx = args.indexOf('--prompt');
  const byIdx = args.indexOf('--by');

  let rawTask: RawTask | undefined;
  let task_id: string | undefined;

  if (fileIdx !== -1 && args[fileIdx + 1]) {
    // Load task from a JSON file
    const filePath = path.resolve(process.cwd(), args[fileIdx + 1]);
    const raw = await fs.readJson(filePath);
    rawTask = await intakeTask({
      raw_prompt: raw.raw_prompt,
      submitted_by: raw.submitted_by,
      priority: raw.priority,
      labels: raw.labels,
      target_branch: raw.target_branch,
      project_hint: raw.project_hint,
    });
  } else if (taskIdIdx !== -1 && args[taskIdIdx + 1]) {
    // Resume from existing intake
    task_id = args[taskIdIdx + 1];
  } else if (promptIdx !== -1 && args[promptIdx + 1]) {
    // Quick prompt from CLI flag
    rawTask = await intakeTask({
      raw_prompt: args[promptIdx + 1],
      submitted_by: byIdx !== -1 && args[byIdx + 1] ? args[byIdx + 1] : 'cli-user',
    });
  } else {
    console.error('Usage:');
    console.error('  tsx scripts/pipeline.ts --file tasks/incoming/sample-task.json');
    console.error('  tsx scripts/pipeline.ts --task-id task_abc123');
    console.error('  tsx scripts/pipeline.ts --prompt "Your request" --by "your-name"');
    process.exit(1);
  }

  const ctx = await runPipeline({ raw_task: rawTask, task_id });

  console.log('\n════════════════════════════════════════════');
  console.log(`Task ID:    ${ctx.task_id}`);
  console.log(`Run ID:     ${ctx.run_id}`);
  console.log(`Status:     ${ctx.status}`);
  console.log(`Verdict:    ${ctx.review_report?.verdict ?? 'n/a'}`);
  console.log(`Score:      ${ctx.review_report?.overall_score ?? 'n/a'}/10`);
  console.log(`Artifacts:  ${ctx.artifact_manifest?.artifact_root ?? 'not archived'}`);
  if (ctx.stage_errors.length > 0) {
    console.log(`\nStage errors (${ctx.stage_errors.length}):`);
    ctx.stage_errors.forEach((e) => console.log(`  [${e.stage}] ${e.error}`));
  }
  console.log('════════════════════════════════════════════\n');

  process.exit(ctx.status === 'failed' ? 1 : 0);
}

if (process.argv[1]?.endsWith('pipeline.ts')) {
  main().catch((err) => {
    console.error('[pipeline] Fatal error:', err);
    process.exit(1);
  });
}
