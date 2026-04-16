/**
 * run-claude-task.ts
 *
 * Executes a task pack through the configured executor.
 *
 * Executor modes:
 *   - claude_cli   : Real Claude Code CLI execution (production)
 *   - simulated    : Returns realistic mock output (local dev / CI)
 *   - dry_run      : Validates setup without execution
 *
 * The executor abstraction is designed so that plugging in the real
 * Claude CLI is a single-line change in ClaudeCliExecutor.execute().
 *
 * REAL CLI INTEGRATION POINT:
 *   See ClaudeCliExecutor below — search for "PRODUCTION PLUG-IN POINT"
 */

import fs from 'fs-extra';
import path from 'path';
import { execa } from 'execa';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { validateOrThrow } from './schema.js';
import { generateRunId, generateSessionId, nowIso } from './ids.js';
import type {
  ExecutionResult,
  ExecutorOptions,
  TaskExecutor,
  NormalizedPrompt,
  PipelineConfig,
} from './types.js';

// ── Resilience helpers ────────────────────────────────────────────────────────

const EXECUTOR_BACKOFF_MS: readonly number[] = [0, 1_000, 2_000];

type ResilienceLogger = {
  event: (name: string, status: string, meta: Record<string, unknown>, message?: string) => void;
  warn: (message: string, meta?: Record<string, unknown>) => void;
};

async function callWithRetry<T>(
  fn: () => Promise<T>,
  opts: {
    maxAttempts: number;
    component: string;
    timeoutMs?: number;
    eventPrefix?: string;
    logger: ResilienceLogger;
  }
): Promise<T> {
  const prefix = opts.eventPrefix ?? 'llm';
  let lastError: unknown;

  for (let attempt = 1; attempt <= opts.maxAttempts; attempt++) {
    const delay = EXECUTOR_BACKOFF_MS[attempt - 1] ?? 2_000;
    if (delay > 0) await new Promise((res) => setTimeout(res, delay));

    try {
      return await fn();
    } catch (err) {
      lastError = err;

      if (attempt < opts.maxAttempts) {
        opts.logger.event(`${prefix}.retry`, 'failed', { attempt, component: opts.component }, String(err));
        opts.logger.warn(`${opts.component}: attempt ${attempt} failed, retrying`, {
          attempt,
          error: String(err),
          component: opts.component,
        });
      } else {
        opts.logger.event(`${prefix}.failed`, 'failed', { attempt, component: opts.component }, String(err));
      }
    }
  }
  throw lastError;
}

// ── Executor implementations ──────────────────────────────────────────────────

/**
 * ClaudeCliExecutor
 *
 * PRODUCTION PLUG-IN POINT:
 * Replace the execa call below with the actual Claude Code CLI invocation.
 * The CLI contract is: `claude --task-file <path> [--session-id <id>]`
 * Adjust flags to match the Claude CLI version you are targeting.
 *
 * Claude Code CLI docs: https://docs.anthropic.com/claude-code
 */
class ClaudeCliExecutor implements TaskExecutor {
  constructor(private readonly config: PipelineConfig) {}

  async execute(opts: ExecutorOptions): Promise<ExecutionResult> {
    const startMs = Date.now();
    const started_at = nowIso();

    const stdoutPath = path.resolve(
      process.cwd(),
      this.config.logs_root,
      'executions',
      `${opts.run_id}-stdout.txt`
    );
    const stderrPath = path.resolve(
      process.cwd(),
      this.config.logs_root,
      'executions',
      `${opts.run_id}-stderr.txt`
    );

    await fs.ensureDir(path.dirname(stdoutPath));

    let exitCode: number | null = null;
    let stdoutExcerpt = '';
    let stderrExcerpt = '';
    let status: ExecutionResult['status'] = 'success';
    let errorMsg: string | null = null;
    let summary = '';

    try {
      // ─────────────────────────────────────────────────────────────────────
      // PRODUCTION EXECUTION
      //
      // Pipes the task pack to Claude Code CLI via stdin in non-interactive
      // (--print) mode. JSON output is requested so we can extract the result
      // text cleanly.
      //
      // CLI flags:
      //   --print              Non-interactive; exits after producing one response.
      //   --output-format json Emits a single JSON object to stdout.
      //
      // Additional flags you may want per CLI version:
      //   --no-auto-updates    Suppress update-check noise on stdout.
      //   --dangerously-skip-permissions  CI environments without interactive approval.
      //
      // The task pack content is provided via stdin (input option). This avoids
      // OS argument-length limits and keeps shell-escaping concerns out of the path.
      // ─────────────────────────────────────────────────────────────────────

      const cliResult = await execa(
        this.config.claude_cli_command,
        ['--print', '--output-format', 'json'],
        {
          input: opts.task_pack_content,         // task pack piped via stdin
          timeout: opts.timeout_seconds * 1000,
          reject: false,                         // never throw on non-zero exit
        }
      );

      exitCode = cliResult.exitCode ?? null;
      const rawStdout = cliResult.stdout ?? '';
      const rawStderr = cliResult.stderr ?? '';

      await fs.writeFile(stdoutPath, rawStdout, 'utf-8');
      await fs.writeFile(stderrPath, rawStderr, 'utf-8');

      stdoutExcerpt = rawStdout.slice(0, 4000);
      stderrExcerpt = rawStderr.slice(0, 2000);

      if (exitCode === 0) {
        // Try to parse the structured JSON response from --output-format json.
        // Shape: { type, subtype, is_error, result, session_id, cost_usd, duration_api_ms, num_turns }
        try {
          const parsed = JSON.parse(rawStdout) as Record<string, unknown>;
          if (parsed['is_error'] === true) {
            status = 'failed';
            const errText = typeof parsed['result'] === 'string' ? parsed['result'] : 'Unknown CLI error';
            errorMsg = errText.slice(0, 500);
            summary = `Claude CLI reported an error: ${errorMsg}`;
          } else {
            status = 'success';
            const resultText = typeof parsed['result'] === 'string' ? parsed['result'] : '';
            summary = resultText.slice(0, 500) || 'Claude CLI completed successfully.';
          }
        } catch {
          // CLI did not return valid JSON (older version or flag not supported).
          // Fall back to treating any exit-0 as success with raw stdout as summary.
          status = 'success';
          summary = rawStdout.slice(0, 500) || 'Claude CLI completed successfully.';
        }
      } else {
        status = 'failed';
        errorMsg = rawStderr.slice(0, 500) || `Claude CLI exited with code ${exitCode}`;
        summary = `Claude CLI exited with code ${exitCode}. See stderr for details.`;
      }
    } catch (err) {
      // execa itself threw — typically ENOENT (CLI not found) or ETIMEDOUT.
      errorMsg = String(err);
      status = 'failed';
      summary = `Claude CLI invocation failed: ${errorMsg}`;
      await fs.writeFile(stderrPath, errorMsg, 'utf-8').catch(() => undefined);
    }

    return {
      schema_version: '2.0',
      task_id: opts.task_id,
      run_id: opts.run_id,
      session_id: opts.session_id,
      started_at,
      completed_at: nowIso(),
      duration_ms: Date.now() - startMs,
      status,
      executor_mode: 'claude_cli',
      summary,
      files_read: [],
      files_changed: [],
      stdout_excerpt: stdoutExcerpt,
      stderr_excerpt: stderrExcerpt,
      stdout_path: stdoutPath,
      stderr_path: stderrPath,
      exit_code: exitCode,
      risks: [],
      followups: [],
      raw_output_ref: stdoutPath,
      error: errorMsg,
    };
  }
}

/**
 * SimulatedExecutor
 *
 * Returns a realistic mock result without executing anything.
 * Used during local development and in CI environments where
 * real Claude CLI is not authenticated.
 */
class SimulatedExecutor implements TaskExecutor {
  async execute(opts: ExecutorOptions): Promise<ExecutionResult> {
    const started_at = nowIso();

    // Simulate processing time
    await new Promise((res) => setTimeout(res, 200));

    const completed_at = nowIso();

    // Extract task title from task pack for realistic summary
    const titleMatch = opts.task_pack_content.match(/# Task Pack: (.+)/);
    const title = titleMatch?.[1] ?? opts.task_id;

    return {
      schema_version: '2.0',
      task_id: opts.task_id,
      run_id: opts.run_id,
      session_id: opts.session_id,
      started_at,
      completed_at,
      duration_ms: Date.now() - new Date(started_at).getTime(),
      status: 'simulated',
      executor_mode: 'simulated',
      summary: `[SIMULATED] Task "${title}" processed. No real changes made.`,
      files_read: ['[SIMULATED] Relevant source files would be read here'],
      files_changed: [
        {
          path: '[SIMULATED] path/to/modified/file.ts',
          operation: 'modified',
          lines_added: 42,
          lines_removed: 8,
        },
      ],
      stdout_excerpt:
        '[SIMULATED] Claude Code executor output would appear here.\n' +
        'In production, this contains the actual CLI stdout.',
      stderr_excerpt: '',
      exit_code: 0,
      risks: [
        '[SIMULATED] This is simulated output. Switch CLAUDE_EXECUTOR_MODE=claude_cli for real execution.',
      ],
      followups: ['[SIMULATED] Add real executor output analysis here.'],
      error: null,
    };
  }
}

/**
 * DryRunExecutor
 *
 * Validates that the task pack is well-formed and the executor
 * is configured correctly, without actually running anything.
 */
class DryRunExecutor implements TaskExecutor {
  async execute(opts: ExecutorOptions): Promise<ExecutionResult> {
    const started_at = nowIso();
    const completed_at = nowIso();

    return {
      schema_version: '2.0',
      task_id: opts.task_id,
      run_id: opts.run_id,
      session_id: opts.session_id,
      started_at,
      completed_at,
      duration_ms: 0,
      status: 'dry_run',
      executor_mode: 'dry_run',
      summary:
        '[DRY RUN] Task pack validated. No execution performed. ' +
        `Task pack is ${opts.task_pack_content.length} bytes.`,
      files_read: [],
      files_changed: [],
      exit_code: null,
      risks: [],
      followups: ['Switch CLAUDE_EXECUTOR_MODE to claude_cli or simulated to run for real.'],
      error: null,
    };
  }
}

// ── Executor factory ──────────────────────────────────────────────────────────

function createExecutor(config: PipelineConfig): TaskExecutor {
  switch (config.executor_mode) {
    case 'claude_cli':
      return new ClaudeCliExecutor(config);
    case 'simulated':
      return new SimulatedExecutor();
    case 'dry_run':
      return new DryRunExecutor();
    default: {
      const _: never = config.executor_mode;
      throw new Error(`Unknown executor mode: ${String(_)}`);
    }
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

export async function runClaudeTask(
  normalized: NormalizedPrompt,
  task_pack_path: string,
  task_pack_content: string,
  existingRunId?: string,
  existingSessionId?: string
): Promise<ExecutionResult> {
  const config = await loadConfig();
  const run_id = existingRunId ?? generateRunId();
  const session_id = existingSessionId ?? generateSessionId();

  const logger = createLogger('run-claude-task', config, {
    task_id: normalized.task_id,
    run_id,
    session_id,
  });

  logger.event('task.execution.started', 'started', {
    executor_mode: config.executor_mode,
    task_pack_path,
    task_id: normalized.task_id,
    run_id,
  });

  const executor = createExecutor(config);

  // Only retry for claude_cli — simulated and dry_run are deterministic and need no retry.
  const maxAttempts = config.executor_mode === 'claude_cli' ? config.max_retries + 1 : 1;

  const executorOpts = {
    task_id: normalized.task_id,
    run_id,
    session_id,
    task_pack_path,
    task_pack_content,
    timeout_seconds: config.timeout_seconds,
    config,
  };

  let result: ExecutionResult;

  try {
    result = await callWithRetry(
      () => executor.execute(executorOpts),
      {
        maxAttempts,
        component: 'run-claude-task',
        eventPrefix: 'executor',
        logger,
      }
    );
  } catch (err) {
    const errorMsg = String(err);

    logger.event('task.execution.failed', 'failed', { run_id }, errorMsg);

    // Build a failed execution result so the pipeline can still archive artifacts
    result = {
      schema_version: '2.0',
      task_id: normalized.task_id,
      run_id,
      session_id,
      started_at: nowIso(),
      completed_at: nowIso(),
      duration_ms: 0,
      status: 'failed',
      executor_mode: config.executor_mode,
      summary: `Execution failed: ${errorMsg}`,
      error: errorMsg,
    };
  }

  // Validate result against schema
  await validateOrThrow<ExecutionResult>(
    'execution-log.schema.json',
    result,
    'run-claude-task'
  );

  // Persist execution result
  const resultDir = path.resolve(process.cwd(), config.tasks_root, 'execution-results');
  await fs.ensureDir(resultDir);
  const resultPath = path.join(resultDir, `${normalized.task_id}-${run_id}.json`);
  await fs.writeJson(resultPath, result, { spaces: 2 });

  const eventName =
    result.status === 'failed' ? 'task.execution.failed' : 'task.execution.completed';
  const eventStatus = result.status === 'failed' ? 'failed' : 'completed';

  logger.event(eventName, eventStatus, {
    run_id,
    status: result.status,
    executor_mode: result.executor_mode,
    duration_ms: result.duration_ms,
    files_changed: result.files_changed?.length ?? 0,
    result_path: resultPath,
  });

  return result;
}
