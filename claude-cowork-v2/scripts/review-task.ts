/**
 * review-task.ts
 *
 * Runs the review engine against an execution result.
 *
 * Reviewer modes:
 *   - mock          : Alias for deterministic (no LLM call)
 *   - deterministic : Rule-based review without LLM (always available)
 *   - openai_compat : Calls LLM provider for intelligent review
 *
 * The review engine always validates its output against
 * review-report.schema.json before persisting.
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { validateOrThrow } from './schema.js';
import { loadSystemPrompt, loadTemplate } from './prompt-loader.js';
import { nowIso } from './ids.js';
import type {
  ExecutionResult,
  NormalizedPrompt,
  ReviewReport,
  ReviewerProviderInterface,
  LLMCompletionOptions,
  LLMCompletionResult,
  AcceptanceCriterionResult,
  ReviewCheckpointResult,
  ReviewVerdict,
  PipelineConfig,
} from './types.js';

// ── Resilience helpers ────────────────────────────────────────────────────────

const LLM_TIMEOUT_MS = 60_000;
const LLM_BACKOFF_MS: readonly number[] = [0, 1_000, 2_000];

type ResilienceLogger = {
  event: (name: string, status: string, meta: Record<string, unknown>, message?: string) => void;
  warn: (message: string, meta?: Record<string, unknown>) => void;
};

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`LLM call timed out after ${ms}ms`)),
      ms
    );
  });
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timer !== undefined) clearTimeout(timer);
  });
}

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
    const delay = LLM_BACKOFF_MS[attempt - 1] ?? 2_000;
    if (delay > 0) await new Promise((res) => setTimeout(res, delay));

    try {
      const call = fn();
      return await (opts.timeoutMs != null ? withTimeout(call, opts.timeoutMs) : call);
    } catch (err) {
      lastError = err;
      const isTimeout = String(err).includes('timed out');

      if (attempt < opts.maxAttempts) {
        const eventName = isTimeout ? `${prefix}.timeout` : `${prefix}.retry`;
        opts.logger.event(eventName, 'failed', { attempt, component: opts.component }, String(err));
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

// ── Placeholder guard ─────────────────────────────────────────────────────────

function findUnresolvedPlaceholders(content: string): string[] {
  const matches = content.match(/\{\{[A-Z_]+\}\}/g);
  return matches ? [...new Set(matches)] : [];
}

// ── Reviewer provider adapters ────────────────────────────────────────────────

class MockReviewerProvider implements ReviewerProviderInterface {
  async complete(_options: LLMCompletionOptions): Promise<LLMCompletionResult> {
    // Only used when reviewer_provider is mock or deterministic —
    // buildLLMReview is never called in those paths.
    return { content: '{}', model: 'mock' };
  }
}

class OpenAICompatReviewerProvider implements ReviewerProviderInterface {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly model: string;

  constructor(config: Pick<PipelineConfig, 'reviewer_model' | 'reviewer_base_url'>) {
    const apiKey = process.env['REVIEWER_API_KEY'];
    if (!apiKey) {
      throw new Error(
        'REVIEWER_API_KEY environment variable is required for openai_compat reviewer.'
      );
    }
    this.apiKey = apiKey;
    this.baseUrl = config.reviewer_base_url ?? 'https://api.openai.com/v1';
    this.model = config.reviewer_model;
  }

  async complete(options: LLMCompletionOptions): Promise<LLMCompletionResult> {
    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: this.model,
        messages: options.messages,
        max_tokens: options.max_tokens ?? 4096,
        temperature: options.temperature ?? 0.1,
      }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Reviewer LLM request failed: ${response.status}\n${body}`);
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = (await response.json()) as any;
    const content = data?.choices?.[0]?.message?.content as string | undefined;

    if (!content) throw new Error('Reviewer LLM returned empty content');

    return {
      content,
      model: data?.model,
      usage: {
        input_tokens: data?.usage?.prompt_tokens,
        output_tokens: data?.usage?.completion_tokens,
      },
    };
  }
}

// ── Deterministic reviewer ────────────────────────────────────────────────────

/**
 * Rule-based reviewer that never calls an LLM.
 * Used for mock/deterministic modes and as a fallback when the LLM reviewer fails.
 */
function buildDeterministicReview(
  normalized: NormalizedPrompt,
  result: ExecutionResult
): ReviewReport {
  const isSimulated = result.status === 'simulated' || result.status === 'dry_run';
  const isSuccess = result.status === 'success' || isSimulated;

  const criteriaResults: AcceptanceCriterionResult[] = normalized.acceptance_criteria.map(
    (criterion) => ({
      criterion,
      met: isSimulated ? 'not_verifiable' : isSuccess ? 'not_verifiable' : 'no',
      evidence: isSimulated
        ? 'Execution was simulated — criteria cannot be verified without real output.'
        : isSuccess
          ? 'Execution succeeded. Manual verification required for this criterion.'
          : 'Execution failed. Criterion not met.',
    })
  );

  const checkpointResults: ReviewCheckpointResult[] = normalized.review_checkpoints.map(
    (checkpoint) => ({
      checkpoint,
      passed: isSuccess,
      notes: isSimulated
        ? 'Simulated execution — checkpoint cannot be verified automatically.'
        : isSuccess
          ? 'Execution completed. Manual checkpoint verification recommended.'
          : 'Execution failed. Checkpoint not assessable.',
    })
  );

  const scopeFitScore = isSimulated ? 7 : isSuccess ? 8 : 3;
  const safetyScore =
    isSimulated
      ? 9
      : isSuccess && (result.risks ?? []).length === 0
        ? 9
        : isSuccess
          ? 7
          : 4;
  const loggingScore = isSimulated ? 6 : isSuccess ? 7 : 5;
  const overallScore = parseFloat(
    ((scopeFitScore + safetyScore + loggingScore) / 3).toFixed(1)
  );

  let verdict: ReviewVerdict;
  if (result.status === 'failed') {
    verdict = 'rejected';
  } else if (overallScore >= 8) {
    verdict = 'accepted';
  } else if (overallScore >= 6) {
    verdict = 'accepted_with_followup';
  } else {
    verdict = 'changes_requested';
  }

  return {
    schema_version: '2.0',
    task_id: result.task_id,
    run_id: result.run_id,
    reviewed_at: nowIso(),
    reviewer_mode: 'deterministic',
    verdict,
    scope_fit_score: scopeFitScore,
    safety_score: safetyScore,
    logging_score: loggingScore,
    overall_score: overallScore,
    acceptance_criteria_results: criteriaResults,
    review_checkpoint_results: checkpointResults,
    scope_assessment: isSimulated
      ? 'Execution was simulated. Scope assessment is heuristic only.'
      : isSuccess
        ? 'Execution completed without errors. Scope compliance assumed but requires manual verification.'
        : 'Execution failed. Scope was not demonstrably achieved.',
    safety_assessment:
      (result.risks ?? []).length === 0
        ? 'No risk flags detected in execution output.'
        : `Risk flags detected: ${(result.risks ?? []).join('; ')}`,
    logging_assessment: isSimulated
      ? 'Cannot assess logging quality on simulated output.'
      : 'Manual review of implementation logs recommended.',
    followup_tasks:
      verdict === 'accepted_with_followup'
        ? [
            'Manual verification of acceptance criteria recommended',
            'Run integration tests if not already executed',
          ]
        : [],
    blocking_issues:
      verdict === 'rejected'
        ? [`Execution status: ${result.status}`, result.error ?? 'Unknown error']
        : [],
    summary: `Deterministic review complete. Execution status: ${result.status}. Verdict: ${verdict}. Overall score: ${overallScore}/10.`,
    recommendations: [
      'Switch to reviewer_provider=openai_compat for intelligent LLM-based code review.',
      'Ensure acceptance criteria are verifiable from executor output.',
      ...(result.followups ?? []),
    ],
  };
}

// ── LLM-based reviewer ────────────────────────────────────────────────────────

/**
 * Formats a list for inclusion in an LLM prompt.
 */
function promptList(items: string[]): string {
  if (items.length === 0) return '_(none)_';
  return items.map((i) => `- ${i}`).join('\n');
}

/**
 * Builds the LLM reviewer prompt and calls the provider.
 * All data is injected via TypeScript string interpolation.
 * The review-task.md template is loaded as a static closing instruction
 * (it contains no {{...}} placeholders) and appended verbatim.
 */
async function buildLLMReview(
  normalized: NormalizedPrompt,
  result: ExecutionResult,
  provider: ReviewerProviderInterface,
  model: string
): Promise<ReviewReport> {
  const [systemPrompt, reviewInstruction] = await Promise.all([
    loadSystemPrompt('reviewer-system'),
    loadTemplate('review-task'),
  ]);

  // Guard: review-task.md must be a static instruction with no unresolved placeholders.
  const unresolvedInTemplate = findUnresolvedPlaceholders(reviewInstruction);
  if (unresolvedInTemplate.length > 0) {
    throw new Error(
      `review-task.md contains unresolved placeholders: ${unresolvedInTemplate.join(', ')}. ` +
        'The review template must be a static instruction block with no {{...}} variables.'
    );
  }

  const filesChanged = (result.files_changed ?? [])
    .map((f) => `- [${f.operation}] ${f.path}`)
    .join('\n') || '_(none reported)_';

  const userMessage = `
## Task Specification

**Task ID**: ${result.task_id}
**Run ID**: ${result.run_id}

### Objective
${normalized.objective}

### Business Context
${normalized.business_context}

### Scope In
${promptList(normalized.scope_in)}

### Scope Out
${promptList(normalized.scope_out)}

### Constraints
${promptList(normalized.constraints)}

### Related Files
${promptList(normalized.related_files)}

### Acceptance Criteria
${promptList(normalized.acceptance_criteria)}

### Logging Requirements
${promptList(normalized.logging_requirements)}

### Review Checkpoints
${promptList(normalized.review_checkpoints)}

### Expected Deliverables
${promptList(normalized.expected_deliverables)}

---

## Execution Result

**Status**: ${result.status}
**Executor Mode**: ${result.executor_mode}
**Duration**: ${result.duration_ms}ms
**Exit Code**: ${result.exit_code != null ? String(result.exit_code) : 'n/a'}

### Summary
${result.summary ?? '_(no summary)_'}

### Files Changed
${filesChanged}

### Risks Detected by Executor
${promptList(result.risks ?? [])}

### Follow-ups from Executor
${promptList(result.followups ?? [])}

### Stdout Excerpt
\`\`\`
${result.stdout_excerpt ?? '_(no output)_'}
\`\`\`

### Stderr Excerpt
\`\`\`
${result.stderr_excerpt ?? '_(none)_'}
\`\`\`

---

${reviewInstruction}

Set task_id to: ${result.task_id}
Set run_id to: ${result.run_id}
Set reviewer_model to: ${model}
Set reviewed_at to: ${nowIso()}
`.trim();

  const llmResult = await provider.complete({
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ],
    max_tokens: 4096,
    temperature: 0.1,
  });

  // Strip markdown fences if the model included them despite instructions
  const stripped = llmResult.content
    .replace(/^```(?:json)?\s*/m, '')
    .replace(/\s*```$/m, '')
    .trim();

  let parsed: unknown;
  try {
    parsed = JSON.parse(stripped);
  } catch {
    throw new Error(`Reviewer LLM returned invalid JSON:\n${stripped.slice(0, 500)}`);
  }

  return parsed as ReviewReport;
}

// ── Provider factory ──────────────────────────────────────────────────────────

function createReviewerProvider(config: PipelineConfig): ReviewerProviderInterface {
  switch (config.reviewer_provider) {
    case 'mock':
    case 'deterministic':
      return new MockReviewerProvider();
    case 'openai_compat':
      return new OpenAICompatReviewerProvider(config);
    default: {
      const _: never = config.reviewer_provider;
      throw new Error(`Unknown reviewer provider: ${String(_)}`);
    }
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

export async function reviewTask(
  normalized: NormalizedPrompt,
  result: ExecutionResult
): Promise<ReviewReport> {
  const config = await loadConfig();

  const logger = createLogger('review-task', config, {
    task_id: result.task_id,
    run_id: result.run_id,
    session_id: result.session_id,
  });

  logger.event('task.review.started', 'started', {
    reviewer_provider: config.reviewer_provider,
    task_id: result.task_id,
    execution_status: result.status,
  });

  let review: ReviewReport;

  try {
    if (
      config.reviewer_provider === 'mock' ||
      config.reviewer_provider === 'deterministic'
    ) {
      review = buildDeterministicReview(normalized, result);
    } else {
      // LLM path — retry with backoff, fall back to deterministic on exhaustion
      const provider = createReviewerProvider(config);
      try {
        review = await callWithRetry(
          () => buildLLMReview(normalized, result, provider, config.reviewer_model),
          {
            maxAttempts: config.max_retries + 1,
            component: 'review-task',
            timeoutMs: LLM_TIMEOUT_MS,
            logger,
          }
        );
      } catch (llmErr) {
        logger.warn('LLM reviewer failed after all retries, falling back to deterministic', {
          error: String(llmErr),
        });
        review = buildDeterministicReview(normalized, result);
      }
    }

    // Schema validation — catches both LLM output mismatches and deterministic bugs
    await validateOrThrow<ReviewReport>('review-report.schema.json', review, 'review-task');
  } catch (err) {
    const errorMsg = String(err);
    logger.error('Review generation failed', { error: errorMsg });
    // Produce a minimal valid review so the pipeline can still archive artifacts
    review = buildDeterministicReview(normalized, {
      ...result,
      status: 'failed',
      error: errorMsg,
    });
    // Validate the fallback too — if this throws, the bug is in buildDeterministicReview
    await validateOrThrow<ReviewReport>('review-report.schema.json', review, 'review-task-fallback');
  }

  // Persist to tasks/reviews/ and logs/reviews/
  const reviewsDir = path.resolve(process.cwd(), config.tasks_root, 'reviews');
  const logsReviewDir = path.resolve(process.cwd(), config.logs_root, 'reviews');
  await fs.ensureDir(reviewsDir);
  await fs.ensureDir(logsReviewDir);

  const reviewPath = path.join(reviewsDir, `${result.task_id}-${result.run_id}.json`);
  const logsPath = path.join(logsReviewDir, `${result.task_id}-${result.run_id}.json`);

  await fs.writeJson(reviewPath, review, { spaces: 2 });
  await fs.writeJson(logsPath, review, { spaces: 2 });

  logger.event('task.review.completed', 'completed', {
    verdict: review.verdict,
    overall_score: review.overall_score,
    scope_fit_score: review.scope_fit_score,
    safety_score: review.safety_score,
    logging_score: review.logging_score,
    reviewer_mode: review.reviewer_mode,
    review_path: reviewPath,
  });

  return review;
}
