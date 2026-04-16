/**
 * task-intake.ts
 *
 * Handles raw task submission.
 *
 * Usage (standalone):
 *   tsx scripts/task-intake.ts --prompt "Fix the login bug" --by "alice"
 *   tsx scripts/task-intake.ts --file tasks/incoming/my-task.json
 *
 * Programmatic usage:
 *   const task = await intakeTask({ raw_prompt: "...", submitted_by: "alice" });
 */

import fs from 'fs-extra';
import path from 'path';
import { loadConfig } from './config.js';
import { generateTaskId, nowIso } from './ids.js';
import { createLogger } from './logger.js';
import { validateOrThrow } from './schema.js';
import type { RawTask } from './types.js';

// ── Core function ─────────────────────────────────────────────────────────────

export interface IntakeInput {
  raw_prompt: string;
  submitted_by?: string;
  priority?: RawTask['priority'];
  labels?: string[];
  target_branch?: string;
  project_hint?: string;
}

/**
 * Creates a validated RawTask from intake input and persists it to disk.
 * Returns the RawTask with its assigned task_id.
 */
export async function intakeTask(input: IntakeInput): Promise<RawTask> {
  const config = await loadConfig();

  const task_id = generateTaskId();
  const run_id = task_id; // At intake, task_id == first run_id
  const session_id = task_id;

  const logger = createLogger('task-intake', config, { task_id, run_id, session_id });

  const task: RawTask = {
    task_id,
    submitted_at: nowIso(),
    submitted_by: input.submitted_by ?? 'unknown',
    raw_prompt: input.raw_prompt.trim(),
    priority: input.priority ?? 'normal',
    ...(input.labels && { labels: input.labels }),
    ...(input.target_branch && { target_branch: input.target_branch }),
    ...(input.project_hint && { project_hint: input.project_hint }),
  };

  // Validate against schema
  await validateOrThrow<RawTask>('task.schema.json', task, 'task-intake');

  // Persist to tasks/incoming/
  const incomingDir = path.resolve(process.cwd(), config.tasks_root, 'incoming');
  await fs.ensureDir(incomingDir);
  const taskPath = path.join(incomingDir, `${task_id}.json`);
  await fs.writeJson(taskPath, task, { spaces: 2 });

  logger.event('task.received', 'completed', {
    task_id,
    submitted_by: task.submitted_by,
    priority: task.priority,
    prompt_length: task.raw_prompt.length,
    path: taskPath,
  });

  logger.info(`Task received and persisted: ${task_id}`, { path: taskPath });
  return task;
}

/**
 * Loads an existing raw task from disk by task_id.
 */
export async function loadRawTask(task_id: string): Promise<RawTask> {
  const config = await loadConfig();
  const taskPath = path.resolve(
    process.cwd(),
    config.tasks_root,
    'incoming',
    `${task_id}.json`
  );

  try {
    const raw = await fs.readJson(taskPath);
    return await validateOrThrow<RawTask>('task.schema.json', raw, 'loadRawTask');
  } catch (err) {
    throw new Error(`Failed to load raw task ${task_id}: ${String(err)}`);
  }
}

// ── CLI entry point ───────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  // Handle --file <path> to intake an existing JSON file
  const fileIdx = args.indexOf('--file');
  if (fileIdx !== -1 && args[fileIdx + 1]) {
    const filePath = path.resolve(process.cwd(), args[fileIdx + 1]);
    const raw = await fs.readJson(filePath);

    if (typeof raw.raw_prompt !== 'string') {
      console.error('Error: JSON file must contain a "raw_prompt" string field.');
      process.exit(1);
    }

    const task = await intakeTask({
      raw_prompt: raw.raw_prompt,
      submitted_by: raw.submitted_by,
      priority: raw.priority,
      labels: raw.labels,
      target_branch: raw.target_branch,
      project_hint: raw.project_hint,
    });

    console.log(`\nTask created: ${task.task_id}`);
    return;
  }

  // Handle --prompt "..." --by "..." flags
  const promptIdx = args.indexOf('--prompt');
  const byIdx = args.indexOf('--by');

  if (promptIdx !== -1 && args[promptIdx + 1]) {
    const task = await intakeTask({
      raw_prompt: args[promptIdx + 1],
      submitted_by: byIdx !== -1 ? args[byIdx + 1] : 'cli-user',
    });
    console.log(`\nTask created: ${task.task_id}`);
    return;
  }

  console.error('Usage:');
  console.error('  tsx scripts/task-intake.ts --prompt "Your request" --by "your-name"');
  console.error('  tsx scripts/task-intake.ts --file tasks/incoming/sample-task.json');
  process.exit(1);
}

// Run only when called directly
if (process.argv[1]?.endsWith('task-intake.ts')) {
  main().catch((err) => {
    console.error('[task-intake] Fatal error:', err);
    process.exit(1);
  });
}
