/**
 * config.ts
 *
 * Loads, validates, and exports the runtime pipeline configuration.
 *
 * Priority order (highest → lowest):
 *   1. Environment variables (from process.env / .env file)
 *   2. .claude-cowork/config.json
 *   3. Built-in defaults
 *
 * The merged config is validated against pipeline-config.schema.json.
 * The process exits with code 1 on invalid config — fail fast.
 */

import path from 'path';
import fs from 'fs-extra';
import dotenv from 'dotenv';
import { createValidator } from './schema.js';
import type { PipelineConfig } from './types.js';

// Load .env from project root (silently ignore if absent)
dotenv.config({ path: path.resolve(process.cwd(), '.env') });

// ── Defaults ──────────────────────────────────────────────────────────────────

const DEFAULTS: PipelineConfig = {
  version: '2.0.0',
  project_name: 'unnamed-project',
  executor_mode: 'simulated',
  claude_cli_command: 'claude',
  normalizer_provider: 'mock',
  normalizer_model: 'claude-sonnet-4-6',
  reviewer_provider: 'mock',
  reviewer_model: 'claude-sonnet-4-6',
  log_level: 'info',
  artifact_root: 'artifacts',
  tasks_root: 'tasks',
  logs_root: 'logs',
  retention_days: 30,
  max_retries: 2,
  timeout_seconds: 300,
  doc_paths: [
    'docs/project-overview.md',
    'docs/architecture.md',
    'docs/coding-standards.md',
    'docs/prompt-rules.md',
  ],
};

// ── File config loader ────────────────────────────────────────────────────────

async function loadFileConfig(): Promise<Partial<PipelineConfig>> {
  const configPath = path.resolve(process.cwd(), '.claude-cowork', 'config.json');
  try {
    const raw = await fs.readFile(configPath, 'utf-8');
    return JSON.parse(raw) as Partial<PipelineConfig>;
  } catch {
    // Config file not required; use defaults
    return {};
  }
}

// ── Environment overlay ───────────────────────────────────────────────────────

function applyEnvOverrides(base: PipelineConfig): PipelineConfig {
  const env = process.env;
  return {
    ...base,
    ...(env['CLAUDE_EXECUTOR_MODE'] && {
      executor_mode: env['CLAUDE_EXECUTOR_MODE'] as PipelineConfig['executor_mode'],
    }),
    ...(env['CLAUDE_CLI_COMMAND'] && { claude_cli_command: env['CLAUDE_CLI_COMMAND'] }),
    ...(env['NORMALIZER_PROVIDER'] && {
      normalizer_provider: env['NORMALIZER_PROVIDER'] as PipelineConfig['normalizer_provider'], // validated by schema
    }),
    ...(env['NORMALIZER_MODEL'] && { normalizer_model: env['NORMALIZER_MODEL'] }),
    ...(env['NORMALIZER_BASE_URL'] && { normalizer_base_url: env['NORMALIZER_BASE_URL'] }),
    ...(env['REVIEWER_PROVIDER'] && {
      reviewer_provider: env['REVIEWER_PROVIDER'] as PipelineConfig['reviewer_provider'],
    }),
    ...(env['REVIEWER_MODEL'] && { reviewer_model: env['REVIEWER_MODEL'] }),
    ...(env['REVIEWER_BASE_URL'] && { reviewer_base_url: env['REVIEWER_BASE_URL'] }),
    ...(env['LOG_LEVEL'] && { log_level: env['LOG_LEVEL'] as PipelineConfig['log_level'] }),
    ...(env['ARTIFACT_ROOT'] && { artifact_root: env['ARTIFACT_ROOT'] }),
    ...(env['TASKS_ROOT'] && { tasks_root: env['TASKS_ROOT'] }),
    ...(env['LOGS_ROOT'] && { logs_root: env['LOGS_ROOT'] }),
    ...(env['PROJECT_NAME'] && { project_name: env['PROJECT_NAME'] }),
    ...(env['RETENTION_DAYS'] && { retention_days: Number(env['RETENTION_DAYS']) }),
    ...(env['MAX_RETRIES'] && { max_retries: Number(env['MAX_RETRIES']) }),
    ...(env['TIMEOUT_SECONDS'] && { timeout_seconds: Number(env['TIMEOUT_SECONDS']) }),
    // NOTE: API keys are intentionally NOT merged into config —
    // they are read directly in the provider adapters to avoid
    // any chance of them appearing in logs.
  };
}

// ── Public API ────────────────────────────────────────────────────────────────

let _config: PipelineConfig | null = null;

/**
 * Loads, merges, and validates the pipeline config.
 * Cached after first call. Call early in pipeline startup.
 */
export async function loadConfig(): Promise<PipelineConfig> {
  if (_config) return _config;

  const fileConfig = await loadFileConfig();
  const merged: PipelineConfig = applyEnvOverrides({ ...DEFAULTS, ...fileConfig });

  // Validate against schema
  const schemaPath = path.resolve(process.cwd(), 'schemas', 'pipeline-config.schema.json');

  try {
    const schemaRaw = await fs.readFile(schemaPath, 'utf-8');
    const schema = JSON.parse(schemaRaw);
    const validate = createValidator(schema);

    if (!validate(merged)) {
      console.error('[config] Invalid pipeline configuration:');
      console.error(JSON.stringify(validate.errors, null, 2));
      process.exit(1);
    }
  } catch (err) {
    // Schema file missing during bootstrap — warn but continue
    console.warn('[config] Warning: pipeline-config schema not found, skipping validation');
  }

  _config = merged;
  return merged;
}

/**
 * Returns the cached config. Must call loadConfig() first.
 * Throws if config has not been loaded yet.
 */
export function getConfig(): PipelineConfig {
  if (!_config) {
    throw new Error('Config not loaded. Call loadConfig() before getConfig().');
  }
  return _config;
}

/**
 * Returns an absolute path relative to project root.
 */
export function resolvePath(...segments: string[]): string {
  return path.resolve(process.cwd(), ...segments);
}
