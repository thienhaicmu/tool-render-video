/**
 * build-bug-prompt.ts
 *
 * Generates a ready-to-run fix-bug prompt artifact from a structured error log.
 *
 * Template:  prompts/templates/fix-bug.md  ({{PLACEHOLDER}} tokens)
 * Output:    artifacts/bug-prompts/<error-id>-fix-bug.md
 *
 * Can be called:
 *   - Programmatically from capture-error.ts (after writing the error log)
 *   - Standalone via CLI: tsx scripts/build-bug-prompt.ts <error-log-path>
 */

import fs from 'fs-extra';
import path from 'path';
import type { ErrorLog } from './capture-error.js';

// ── Template rendering ────────────────────────────────────────────────────────

const TEMPLATE_PATH = path.resolve(
  process.cwd(),
  'prompts',
  'templates',
  'fix-bug.md'
);

const OUTPUT_DIR = path.resolve(process.cwd(), 'artifacts', 'bug-prompts');

/**
 * Replace all occurrences of {{KEY}} in the template with the supplied value.
 * If a placeholder is not found in the substitutions map it is replaced with
 * "(not provided)" so the output is always fully rendered.
 */
function renderTemplate(template: string, subs: Record<string, string>): string {
  return template.replace(/\{\{([A-Z0-9_]+)\}\}/g, (_match, key: string) => {
    return subs[key] ?? '(not provided)';
  });
}

/**
 * Format a string[] as a Markdown bullet list, or a fallback message if empty.
 */
function bulletList(items: string[], emptyMsg = '(none specified)'): string {
  if (items.length === 0) return emptyMsg;
  return items.map((item) => `- \`${item}\``).join('\n');
}

/**
 * Safely serialize an object as indented JSON, with a fallback.
 */
function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Build a bug-fix prompt from an ErrorLog.
 * Saves the rendered prompt to artifacts/bug-prompts/<error-id>-fix-bug.md.
 * Returns the absolute path of the generated file.
 */
export async function buildBugPrompt(errorLog: ErrorLog): Promise<string> {
  // Load template
  let template: string;
  try {
    template = await fs.readFile(TEMPLATE_PATH, 'utf-8');
  } catch (err) {
    throw new Error(
      `[build-bug-prompt] Cannot read template at ${TEMPLATE_PATH}: ${String(err)}`
    );
  }

  // Build substitution map — every {{PLACEHOLDER}} in the template
  const subs: Record<string, string> = {
    ERROR_ID:       errorLog.error_id,
    SESSION_ID:     errorLog.session_id,
    TASK_ID:        errorLog.task_id,
    RUN_ID:         errorLog.run_id,
    TIMESTAMP:      errorLog.timestamp,
    COMPONENT:      errorLog.component,
    ACTION:         errorLog.action,
    ERROR_NAME:     errorLog.error_name,
    ERROR_MESSAGE:  errorLog.error_message,
    STACK_TRACE:    errorLog.stack_trace || '(no stack trace available)',
    INPUT_SUMMARY:  safeJson(errorLog.input_summary),
    RELATED_FILES:  bulletList(errorLog.related_files),
    SUSPECTED_FLOW: bulletList(errorLog.suspected_flow),
  };

  const rendered = renderTemplate(template, subs);

  // Detect unresolved placeholders (template/renderer mismatch guard)
  const unresolved = [...rendered.matchAll(/\{\{[A-Z0-9_]+\}\}/g)].map((m) => m[0]);
  if (unresolved.length > 0) {
    throw new Error(
      `[build-bug-prompt] Unresolved placeholders in fix-bug.md: ${unresolved.join(', ')}`
    );
  }

  // Write output
  await fs.ensureDir(OUTPUT_DIR);
  const outputFilename = `${errorLog.error_id}-fix-bug.md`;
  const outputPath = path.join(OUTPUT_DIR, outputFilename);
  await fs.writeFile(outputPath, rendered, 'utf-8');

  return outputPath;
}

// ── Standalone CLI ────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const [, , errorLogArg] = process.argv;
  if (!errorLogArg) {
    process.stderr.write('Usage: tsx scripts/build-bug-prompt.ts <path-to-error-log.json>\n');
    process.exit(1);
  }

  const errorLogPath = path.resolve(process.cwd(), errorLogArg);
  let raw: string;
  try {
    raw = await fs.readFile(errorLogPath, 'utf-8');
  } catch {
    process.stderr.write(`[build-bug-prompt] Cannot read error log: ${errorLogPath}\n`);
    process.exit(1);
  }

  let errorLog: ErrorLog;
  try {
    errorLog = JSON.parse(raw) as ErrorLog;
  } catch {
    process.stderr.write(`[build-bug-prompt] Error log is not valid JSON: ${errorLogPath}\n`);
    process.exit(1);
  }

  const outputPath = await buildBugPrompt(errorLog);
  process.stdout.write(`Bug prompt written to: ${outputPath}\n`);
}

// Run when invoked directly
const isMain = process.argv[1] !== undefined &&
  path.resolve(process.argv[1]).includes('build-bug-prompt');

if (isMain) {
  main().catch((err: unknown) => {
    process.stderr.write(`[build-bug-prompt] Fatal: ${String(err)}\n`);
    process.exit(1);
  });
}
