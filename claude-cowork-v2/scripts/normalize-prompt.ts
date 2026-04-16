/**
 * normalize-prompt.ts
 *
 * Transforms a raw task into a fully structured NormalizedPrompt.
 *
 * Pipeline:
 *   1. Load raw task from disk
 *   2. Build normalization prompt (system + docs + few-shots + raw task)
 *   3. Call LLM via provider adapter (mock | openai_compat)
 *   4. Parse JSON response
 *   5. Validate against normalized-prompt.schema.json
 *   6. Persist to tasks/normalized/
 *   7. Write prompt log + normalization event
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { validateOrThrow } from './schema.js';
import { loadSystemPrompt, loadFewShots } from './prompt-loader.js';
import { buildDocContext } from './doc-loader.js';
import { nowIso } from './ids.js';
import type {
  RawTask,
  NormalizedPrompt,
  NormalizationError,
  NormalizerProviderInterface,
  LLMCompletionOptions,
  LLMCompletionResult,
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

// ── Provider adapters ─────────────────────────────────────────────────────────

/**
 * MockNormalizerProvider — returns a deterministic normalized task.
 * Used in tests and local development to avoid real LLM calls.
 */
class MockNormalizerProvider implements NormalizerProviderInterface {
  async complete(options: LLMCompletionOptions): Promise<LLMCompletionResult> {
    // Extract raw prompt from the user message for mock context
    const userMsg = options.messages.find((m) => m.role === 'user')?.content ?? '';
    const promptMatch = userMsg.match(/## Raw Request\s+```\s*([\s\S]+?)```/);
    const rawPrompt = promptMatch?.[1]?.trim() ?? 'No raw prompt found';
    const taskId =
      userMsg.match(/Set task_id to:\s*([\w_]+)/)?.[1] ??
      userMsg.match(/## Task ID\s+([\w_]+)/)?.[1] ??
      'task_mock_fallback';

    const normalized: NormalizedPrompt = {
      schema_version: '2.0',
      task_id: taskId,
      task_type: 'feature',
      title: `[MOCK] ${rawPrompt.slice(0, 60)}`,
      objective: `[MOCK] Complete the following engineering task: ${rawPrompt.slice(0, 120)}`,
      business_context:
        '[MOCK] This task was submitted for automated processing. ' +
        'Replace with real business context in production.',
      project_context_needed: ['docs/architecture.md', 'docs/coding-standards.md'],
      scope_in: [
        '[MOCK] Primary implementation file — identify from raw prompt',
        '[MOCK] Test file for the modified component',
      ],
      scope_out: [
        '[MOCK] Unrelated modules not mentioned in the request',
        '[MOCK] Infrastructure and deployment configuration',
      ],
      constraints: [
        '[MOCK] Must not break existing tests',
        '[MOCK] Must follow the coding standards in docs/coding-standards.md',
      ],
      assumptions: [
        '[MOCK] The codebase is in a clean state before execution',
        '[MOCK] The relevant test suite is available and runnable',
      ],
      related_files: [],
      acceptance_criteria: [
        '[MOCK] The primary objective is demonstrably achieved',
        '[MOCK] All existing tests continue to pass',
        '[MOCK] Code changes conform to coding-standards.md',
      ],
      logging_requirements: ['[MOCK] Log entry and exit of modified functions at INFO level'],
      review_checkpoints: [
        '[MOCK] Verify the change does not alter unrelated behavior',
        '[MOCK] Verify logging requirements are met',
      ],
      expected_deliverables: [
        '[MOCK] Modified source file(s)',
        '[MOCK] Updated or new test file(s)',
      ],
      risk_flags: ['[MOCK] No real risk analysis performed — this is a mock normalization'],
      estimated_complexity: 'small',
      raw_task_ref: `tasks/incoming/${taskId}.json`,
      normalized_at: nowIso(),
      normalizer_model: 'mock',
      normalizer_provider: 'mock',
    };

    return {
      content: JSON.stringify(normalized, null, 2),
      model: 'mock',
      usage: { input_tokens: 0, output_tokens: 0 },
    };
  }
}

/**
 * OpenAICompatibleNormalizerProvider — calls any OpenAI-compatible endpoint.
 * Works with Anthropic Claude via their OpenAI-compatible API.
 *
 * Required env vars:
 *   NORMALIZER_API_KEY
 *   NORMALIZER_BASE_URL  (e.g. https://api.anthropic.com/v1)
 */
class OpenAICompatNormalizerProvider implements NormalizerProviderInterface {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly model: string;

  constructor(config: Pick<PipelineConfig, 'normalizer_model' | 'normalizer_base_url'>) {
    const apiKey = process.env['NORMALIZER_API_KEY'];
    if (!apiKey) {
      throw new Error(
        'NORMALIZER_API_KEY environment variable is required for openai_compat provider. ' +
          'Never put API keys in config files.'
      );
    }
    this.apiKey = apiKey;
    this.baseUrl = config.normalizer_base_url ?? 'https://api.openai.com/v1';
    this.model = config.normalizer_model;
  }

  async complete(options: LLMCompletionOptions): Promise<LLMCompletionResult> {
    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
        // Anthropic-specific headers (ignored by non-Anthropic endpoints)
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
      throw new Error(
        `Normalizer LLM request failed: ${response.status} ${response.statusText}\n${body}`
      );
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = (await response.json()) as any;
    const content = data?.choices?.[0]?.message?.content as string | undefined;

    if (!content) {
      throw new Error('Normalizer LLM returned empty content');
    }

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

// ── Provider factory ──────────────────────────────────────────────────────────

function createNormalizerProvider(config: PipelineConfig): NormalizerProviderInterface {
  switch (config.normalizer_provider) {
    case 'mock':
      return new MockNormalizerProvider();
    case 'openai_compat':
      return new OpenAICompatNormalizerProvider(config);
    default: {
      // TypeScript exhaustive check
      const _: never = config.normalizer_provider;
      throw new Error(`Unknown normalizer provider: ${String(_)}`);
    }
  }
}

// ── Prompt builder ────────────────────────────────────────────────────────────

async function buildNormalizationPrompt(
  rawTask: RawTask,
  config: PipelineConfig
): Promise<LLMCompletionOptions> {
  const [systemPrompt, fewShots, docContext] = await Promise.all([
    loadSystemPrompt('prompt-normalizer-system'),
    loadFewShots('normalize-examples'),
    buildDocContext(config),
  ]);

  const userMessage = `
## Task ID
${rawTask.task_id}

## Raw Request

\`\`\`
${rawTask.raw_prompt}
\`\`\`

## Submitter
${rawTask.submitted_by}

## Priority
${rawTask.priority ?? 'normal'}

## Project Context (from docs)

${docContext}

## Few-Shot Examples (for calibration)

${fewShots}

---

Produce a single JSON object that is a valid NormalizedPrompt.
Set task_id to: ${rawTask.task_id}
Set raw_task_ref to: tasks/incoming/${rawTask.task_id}.json
Set normalized_at to: ${nowIso()}

If the request lacks sufficient context to normalize, return:
{
  "error": "insufficient_context",
  "message": "...",
  "questions": ["..."]
}

Output ONLY the JSON object. No markdown code fences. No commentary.
`.trim();

  return {
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ],
    max_tokens: 4096,
    temperature: 0.1,
  };
}

// ── JSON extraction ───────────────────────────────────────────────────────────

function extractJson(raw: string): unknown {
  // Strip markdown code fences if the LLM included them despite instructions
  const stripped = raw
    .replace(/^```(?:json)?\s*/m, '')
    .replace(/\s*```$/m, '')
    .trim();

  try {
    return JSON.parse(stripped);
  } catch {
    throw new Error(`LLM response is not valid JSON:\n${raw.slice(0, 500)}`);
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

export async function normalizePrompt(
  rawTask: RawTask,
  overrideRunId?: string,
  overrideSessionId?: string
): Promise<NormalizedPrompt> {
  const config = await loadConfig();
  const run_id = overrideRunId ?? rawTask.task_id;
  const session_id = overrideSessionId ?? rawTask.task_id;

  const logger = createLogger('normalize-prompt', config, {
    task_id: rawTask.task_id,
    run_id,
    session_id,
  });

  logger.info('Starting prompt normalization', { task_id: rawTask.task_id });

  // 1. Build prompt
  const promptOptions = await buildNormalizationPrompt(rawTask, config);

  // 2. Write prompt log (for debugging and quality review)
  const promptLogDir = path.resolve(process.cwd(), config.logs_root, 'prompts');
  await fs.ensureDir(promptLogDir);
  const promptLogPath = path.join(promptLogDir, `${rawTask.task_id}-normalize.json`);
  await fs.writeJson(
    promptLogPath,
    {
      task_id: rawTask.task_id,
      logged_at: nowIso(),
      stage: 'normalize',
      messages: promptOptions.messages,
      // SECURITY: No secrets or API keys in this log
    },
    { spaces: 2 }
  );

  // 3. Call LLM provider with retry + timeout
  const provider = createNormalizerProvider(config);

  let llmResult: LLMCompletionResult;
  try {
    logger.debug('Calling normalizer LLM', {
      provider: config.normalizer_provider,
      max_attempts: config.max_retries + 1,
    });
    llmResult = await callWithRetry(
      () => provider.complete(promptOptions),
      {
        maxAttempts: config.max_retries + 1,
        component: 'normalize-prompt',
        timeoutMs: LLM_TIMEOUT_MS,
        logger,
      }
    );
  } catch (err) {
    logger.event('task.validation.failed', 'failed', {}, `Normalizer LLM call failed: ${String(err)}`);
    throw new Error(`Normalization LLM call failed: ${String(err)}`);
  }

  // 4. Parse response
  const parsed = extractJson(llmResult.content);

  // 5. Check for normalization refusal
  const maybeError = parsed as Partial<NormalizationError>;
  if (maybeError.error) {
    const errMsg =
      `Normalization refused: ${maybeError.error} — ${maybeError.message}` +
      (maybeError.questions ? `\nQuestions:\n${maybeError.questions.join('\n')}` : '');

    logger.event('task.validation.failed', 'failed', { refusal: maybeError }, errMsg);
    throw new Error(errMsg);
  }

  // 6. Validate against schema
  const normalized = await validateOrThrow<NormalizedPrompt>(
    'normalized-prompt.schema.json',
    parsed,
    'normalize-prompt'
  );

  // 7. Persist to tasks/normalized/
  const normalizedDir = path.resolve(process.cwd(), config.tasks_root, 'normalized');
  await fs.ensureDir(normalizedDir);
  const normalizedPath = path.join(normalizedDir, `${rawTask.task_id}.json`);
  await fs.writeJson(normalizedPath, normalized, { spaces: 2 });

  logger.event('task.normalized', 'completed', {
    task_id: rawTask.task_id,
    task_type: normalized.task_type,
    complexity: normalized.estimated_complexity,
    model: llmResult.model,
    output_tokens: llmResult.usage?.output_tokens,
    path: normalizedPath,
  });

  logger.info(`Normalization complete: ${rawTask.task_id}`, {
    title: normalized.title,
    task_type: normalized.task_type,
  });

  return normalized;
}

/**
 * Loads an existing normalized task from disk.
 */
export async function loadNormalizedTask(task_id: string): Promise<NormalizedPrompt> {
  const config = await loadConfig();
  const p = path.resolve(process.cwd(), config.tasks_root, 'normalized', `${task_id}.json`);

  try {
    const raw = await fs.readJson(p);
    return await validateOrThrow<NormalizedPrompt>(
      'normalized-prompt.schema.json',
      raw,
      'loadNormalizedTask'
    );
  } catch (err) {
    throw new Error(`Failed to load normalized task ${task_id}: ${String(err)}`);
  }
}
