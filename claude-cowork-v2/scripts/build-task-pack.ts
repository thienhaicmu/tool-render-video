/**
 * build-task-pack.ts
 *
 * Assembles the task pack — a structured markdown document sent to
 * the Claude Code executor. The task pack is the only artifact the
 * executor sees; the raw prompt is never forwarded.
 *
 * The task pack is built from:
 *   - The normalized task (all structured fields)
 *   - The execution-task.md template
 *   - Relevant doc context (project_context_needed)
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { createLogger } from './logger.js';
import { loadTemplate } from './prompt-loader.js';
import { loadProjectContextDocs, assembleDocContext } from './doc-loader.js';
import { nowIso } from './ids.js';
import type { NormalizedPrompt } from './types.js';

// ── Builder ───────────────────────────────────────────────────────────────────

/**
 * Renders a markdown list from an array of strings.
 */
function mdList(items: string[]): string {
  if (items.length === 0) return '_(none specified)_';
  return items.map((i) => `- ${i}`).join('\n');
}

/**
 * Detects any remaining {{PLACEHOLDER}} tokens in the rendered output.
 * Returns an array of unresolved variable names, or empty array if clean.
 */
function findUnresolvedPlaceholders(content: string): string[] {
  const matches = content.match(/\{\{[A-Z_]+\}\}/g);
  return matches ? [...new Set(matches)] : [];
}

/**
 * Builds the task pack markdown from a normalized task and doc context.
 * Throws if any template variable remains unresolved after rendering.
 */
async function renderTaskPack(
  normalized: NormalizedPrompt,
  run_id: string,
  docContext: string
): Promise<string> {
  const template = await loadTemplate('execution-task');

  // Replace all template variables — must match execution-task.md exactly.
  // Variable names here are the source of truth; the template must use the same names.
  const pack = template
    .replace('{{TASK_ID}}', normalized.task_id)
    .replace('{{TITLE}}', normalized.title)
    .replace('{{RUN_ID}}', run_id)
    .replace('{{GENERATED_AT}}', nowIso())
    .replace('{{COMPLEXITY}}', normalized.estimated_complexity)
    .replace('{{TASK_TYPE}}', normalized.task_type)
    .replace('{{OBJECTIVE}}', normalized.objective)
    .replace('{{BUSINESS_CONTEXT}}', normalized.business_context)
    .replace('{{DOC_CONTEXT}}', docContext)
    .replace('{{SCOPE_IN}}', mdList(normalized.scope_in))
    .replace('{{SCOPE_OUT}}', mdList(normalized.scope_out))
    .replace('{{CONSTRAINTS}}', mdList(normalized.constraints))
    .replace('{{ASSUMPTIONS}}', mdList(normalized.assumptions))
    .replace('{{RELATED_FILES}}', mdList(normalized.related_files))
    .replace('{{ACCEPTANCE_CRITERIA}}', mdList(normalized.acceptance_criteria))
    .replace('{{LOGGING_REQUIREMENTS}}', mdList(normalized.logging_requirements))
    .replace('{{EXPECTED_DELIVERABLES}}', mdList(normalized.expected_deliverables))
    .replace('{{RISK_FLAGS}}', mdList(normalized.risk_flags ?? []))
    .replace('{{REVIEW_CHECKPOINTS}}', mdList(normalized.review_checkpoints));

  // Fail fast: any surviving {{...}} means a template/renderer mismatch.
  const unresolved = findUnresolvedPlaceholders(pack);
  if (unresolved.length > 0) {
    throw new Error(
      `Task pack template has unresolved placeholders after rendering: ${unresolved.join(', ')}. ` +
        'Align execution-task.md variable names with build-task-pack.ts.'
    );
  }

  return pack;
}

// ── Main export ───────────────────────────────────────────────────────────────

export interface TaskPackResult {
  task_pack_path: string;
  task_pack_content: string;
}

export async function buildTaskPack(
  normalized: NormalizedPrompt,
  run_id: string,
  session_id: string
): Promise<TaskPackResult> {
  const config = await loadConfig();

  const logger = createLogger('build-task-pack', config, {
    task_id: normalized.task_id,
    run_id,
    session_id,
  });

  logger.info('Building task pack', { task_id: normalized.task_id });

  // Load project context docs specified in the normalized task
  const docs = await loadProjectContextDocs(normalized.project_context_needed);
  const loadedDocs = docs.filter((d) => d.loaded);
  const missingDocs = docs.filter((d) => !d.loaded);

  if (missingDocs.length > 0) {
    logger.warn('Some project context docs could not be loaded', {
      missing: missingDocs.map((d) => d.path),
    });
  }

  // Guard: if project_context_needed was non-empty but ALL docs failed to load,
  // treat it as an error — the executor would run with no project context.
  if (normalized.project_context_needed.length > 0 && loadedDocs.length === 0) {
    throw new Error(
      `All ${normalized.project_context_needed.length} requested project context docs ` +
        `failed to load: ${missingDocs.map((d) => d.path).join(', ')}. ` +
        'The executor cannot run without project context. Verify doc_paths in config and docs/ directory.'
    );
  }

  const docContext =
    loadedDocs.length > 0
      ? assembleDocContext(docs)
      : '_(no project context docs were specified for this task)_';

  // Render the task pack — throws on unresolved placeholders
  const taskPackContent = await renderTaskPack(normalized, run_id, docContext);

  // Persist to tasks/taskpacks/
  const taskPackDir = path.resolve(process.cwd(), config.tasks_root, 'taskpacks');
  await fs.ensureDir(taskPackDir);
  const taskPackPath = path.join(taskPackDir, `${normalized.task_id}.md`);
  await fs.writeFile(taskPackPath, taskPackContent, 'utf-8');

  logger.event('task.packaged', 'completed', {
    task_id: normalized.task_id,
    task_pack_path: taskPackPath,
    doc_count: loadedDocs.length,
    doc_missing_count: missingDocs.length,
    task_pack_length: taskPackContent.length,
  });

  logger.info(`Task pack written: ${taskPackPath}`);

  return { task_pack_path: taskPackPath, task_pack_content: taskPackContent };
}

/**
 * Loads an existing task pack from disk.
 */
export async function loadTaskPack(task_id: string): Promise<string> {
  const config = await loadConfig();
  const p = path.resolve(process.cwd(), config.tasks_root, 'taskpacks', `${task_id}.md`);

  try {
    return await fs.readFile(p, 'utf-8');
  } catch {
    throw new Error(`Task pack not found for task ${task_id}: ${p}`);
  }
}
