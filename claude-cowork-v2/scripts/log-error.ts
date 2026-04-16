/**
 * log-error.ts  (v2)
 *
 * CLI entry point for the runtime bug-log workflow.
 * Intelligently selects the most relevant bug-fix prompt rather than
 * blindly using the latest error.
 *
 * ── USAGE ─────────────────────────────────────────────────────────────────────
 *
 *   npm run log_error                         → print best-match bug-fix prompt
 *   npm run log_error:run                     → send best-match prompt to Claude CLI
 *
 *   tsx scripts/log-error.ts [flags]
 *
 * ── FLAGS ─────────────────────────────────────────────────────────────────────
 *
 *   (none)                   print best-match prompt (smart selection)
 *   --run                    send best-match prompt to Claude CLI
 *   --list                   list recent error candidates; do not run anything
 *   --latest                 force-select the newest error, skip smart matching
 *   --id      <error_id>     select exact error by ID
 *   --session <session_id>   prefer errors from this session
 *   --task    <task_id>      narrow to this task within session
 *   --component <name>       narrow to this component
 *
 * ── SELECTION PRIORITY ────────────────────────────────────────────────────────
 *
 *   1. --id    → exact match (bypass all other filters)
 *   2. --latest → force newest entry
 *   3. session  → use --session, or infer from newest entry's session
 *   4. task     → narrow with --task (best-effort; ignored if empty)
 *   5. component → narrow with --component (best-effort; ignored if empty)
 *   6. tiebreak → newest timestamp among final candidates
 *
 * ── FAILURES ──────────────────────────────────────────────────────────────────
 *
 *   - Exits 1 with clear message if no error candidates exist
 *   - Exits 1 if the selected prompt file is missing
 *   - Exits 1 if Claude CLI cannot be launched
 */

import fs from 'fs-extra';
import path from 'path';
import { execa } from 'execa';
import dotenv from 'dotenv';
import {
  loadOrBuildIndex,
  resolveBestCandidate,
  type ErrorIndexEntry,
  type CandidateFilters,
} from './error-index.js';

// Load .env for CLAUDE_CLI_COMMAND override
dotenv.config({ path: path.resolve(process.cwd(), '.env') });

// ── Constants ─────────────────────────────────────────────────────────────────

const LIST_MAX = 10;   // max entries shown by --list
const SEP = '─'.repeat(76);

// ── Claude CLI resolution ─────────────────────────────────────────────────────

function resolveClaudeCommand(): string {
  if (process.env['CLAUDE_CLI_COMMAND']) return process.env['CLAUDE_CLI_COMMAND'];
  try {
    const cfgPath = path.resolve(process.cwd(), '.claude-cowork', 'config.json');
    const raw = fs.readFileSync(cfgPath, 'utf-8');
    const cfg = JSON.parse(raw) as Record<string, unknown>;
    if (typeof cfg['claude_cli_command'] === 'string' && cfg['claude_cli_command']) {
      return cfg['claude_cli_command'];
    }
  } catch { /* fall through */ }
  return 'claude';
}

// ── Arg parser ────────────────────────────────────────────────────────────────

interface ParsedArgs {
  run: boolean;
  list: boolean;
  latest: boolean;
  id?: string;
  session?: string;
  task?: string;
  component?: string;
}

function parseArgs(argv: string[]): ParsedArgs {
  const args = argv.slice(2);
  const get = (flag: string): string | undefined => {
    const i = args.indexOf(flag);
    return i !== -1 && i + 1 < args.length ? args[i + 1] : undefined;
  };
  return {
    run:       args.includes('--run'),
    list:      args.includes('--list'),
    latest:    args.includes('--latest'),
    id:        get('--id'),
    session:   get('--session'),
    task:      get('--task'),
    component: get('--component'),
  };
}

// ── Prompt loading ────────────────────────────────────────────────────────────

async function loadPromptContent(entry: ErrorIndexEntry): Promise<string> {
  if (!entry.bug_prompt_path) {
    process.stderr.write(
      `[log-error] Bug prompt was not generated for error '${entry.error_id}'.\n` +
      `  Regenerate: tsx scripts/build-bug-prompt.ts ${entry.error_log_path}\n`
    );
    process.exit(1);
  }

  const promptPath = path.resolve(process.cwd(), entry.bug_prompt_path);
  if (!(await fs.pathExists(promptPath))) {
    process.stderr.write(
      `[log-error] Bug prompt file not found on disk.\n` +
      `  Error ID  : ${entry.error_id}\n` +
      `  Expected  : ${promptPath}\n` +
      `  Regenerate: tsx scripts/build-bug-prompt.ts ${entry.error_log_path}\n`
    );
    process.exit(1);
  }

  try {
    return await fs.readFile(promptPath, 'utf-8');
  } catch (err) {
    process.stderr.write(`[log-error] Cannot read bug prompt file: ${String(err)}\n`);
    process.exit(1);
  }
}

// ── Display helpers ───────────────────────────────────────────────────────────

function formatEntryShort(entry: ErrorIndexEntry, rank: number, isBest: boolean): string {
  const badge = isBest ? '  ← selected' : '';
  const ts = entry.timestamp.replace('T', ' ').replace('.000Z', ' UTC').replace(/\.\d+Z$/, ' UTC');
  const msg = entry.error_message.length > 80
    ? entry.error_message.slice(0, 77) + '...'
    : entry.error_message;

  return (
    `  #${rank}  ${entry.error_id}${badge}\n` +
    `       Session  : ${entry.session_id}\n` +
    `       Task     : ${entry.task_id}\n` +
    `       Component: ${entry.component}\n` +
    `       Time     : ${ts}\n` +
    `       Error    : ${entry.error_name}: ${msg}\n`
  );
}

function printHeader(entry: ErrorIndexEntry, matchReason: string): void {
  process.stdout.write(
    `\n${SEP}\n` +
    ` Bug Fix Prompt\n` +
    `${SEP}\n` +
    `  Error ID  : ${entry.error_id}\n` +
    `  Session   : ${entry.session_id}\n` +
    `  Task      : ${entry.task_id}\n` +
    `  Component : ${entry.component}\n` +
    `  Timestamp : ${entry.timestamp}\n` +
    `  Matched by: ${matchReason}\n` +
    `  Prompt    : ${entry.bug_prompt_path}\n` +
    `${SEP}\n\n`
  );
}

// ── Commands ──────────────────────────────────────────────────────────────────

async function cmdList(
  filters: CandidateFilters,
  _args: ParsedArgs
): Promise<void> {
  const index = await loadOrBuildIndex();

  if (index.entries.length === 0) {
    process.stdout.write('[log-error] No error candidates found in index.\n');
    process.stdout.write('  Run the pipeline or call captureError() from a failing stage.\n');
    return;
  }

  const { result: best, warnings } = resolveBestCandidate(index, filters);

  for (const w of warnings) {
    process.stderr.write(`[log-error] warning: ${w}\n`);
  }

  const shown = index.entries.slice(0, LIST_MAX);
  const bestId = best?.entry.error_id ?? null;

  process.stdout.write(
    `\n${SEP}\n` +
    ` Recent Error Candidates  (${shown.length} of ${index.entries.length})\n` +
    `${SEP}\n`
  );

  shown.forEach((entry, i) => {
    process.stdout.write(formatEntryShort(entry, i + 1, entry.error_id === bestId));
    if (i < shown.length - 1) process.stdout.write('\n');
  });

  process.stdout.write(`${SEP}\n`);

  if (best) {
    process.stdout.write(
      `\n  Selected: ${best.entry.error_id}  (${best.match_reason})\n` +
      `  Run with: npm run log_error:run\n\n`
    );
  }
}

async function cmdPrint(
  filters: CandidateFilters,
  _args: ParsedArgs
): Promise<void> {
  const index = await loadOrBuildIndex();
  const { result, warnings } = resolveBestCandidate(index, filters);

  for (const w of warnings) {
    process.stderr.write(`[log-error] warning: ${w}\n`);
  }

  if (!result) {
    process.stderr.write(
      `[log-error] No error candidates found.\n` +
      `  Run the pipeline or call captureError() from a failing stage.\n` +
      `  Use --list to see available errors.\n`
    );
    process.exit(1);
  }

  const content = await loadPromptContent(result.entry);
  printHeader(result.entry, result.match_reason);
  process.stdout.write(content);
  process.stdout.write('\n');
}

async function cmdRun(
  filters: CandidateFilters,
  _args: ParsedArgs
): Promise<void> {
  const index = await loadOrBuildIndex();
  const { result, warnings } = resolveBestCandidate(index, filters);

  for (const w of warnings) {
    process.stderr.write(`[log-error] warning: ${w}\n`);
  }

  if (!result) {
    process.stderr.write(
      `[log-error] No error candidates found — nothing to send to Claude CLI.\n` +
      `  Run the pipeline or call captureError() from a failing stage.\n` +
      `  Use --list to see available errors.\n`
    );
    process.exit(1);
  }

  const content = await loadPromptContent(result.entry);
  const claudeCmd = resolveClaudeCommand();

  process.stderr.write(
    `[log-error] Sending bug-fix prompt to Claude CLI...\n` +
    `  Error ID  : ${result.entry.error_id}\n` +
    `  Session   : ${result.entry.session_id}\n` +
    `  Component : ${result.entry.component}\n` +
    `  Matched by: ${result.match_reason}\n` +
    `  Command   : ${claudeCmd} --print\n` +
    `  Prompt    : ${result.entry.bug_prompt_path}\n\n`
  );

  let exitCode = 0;
  try {
    const proc = execa(claudeCmd, ['--print'], {
      input: content,
      reject: false,
      timeout: 600_000,
    });
    proc.stdout?.pipe(process.stdout);
    proc.stderr?.pipe(process.stderr);
    const res = await proc;
    exitCode = res.exitCode ?? 0;
  } catch (err) {
    const msg = String(err);
    if (msg.includes('ENOENT')) {
      process.stderr.write(
        `[log-error] Claude CLI not found: '${claudeCmd}'\n` +
        `  Install Claude Code CLI or set CLAUDE_CLI_COMMAND in .env\n`
      );
    } else {
      process.stderr.write(`[log-error] Claude CLI invocation failed: ${msg}\n`);
    }
    process.exit(1);
  }

  if (exitCode !== 0) {
    process.stderr.write(`[log-error] Claude CLI exited with code ${exitCode}\n`);
    process.exit(exitCode);
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const parsed = parseArgs(process.argv);

  const filters: CandidateFilters = {
    error_id:   parsed.id,
    session_id: parsed.session,
    task_id:    parsed.task,
    component:  parsed.component,
    latest:     parsed.latest,
  };

  if (parsed.list) {
    await cmdList(filters, parsed);
  } else if (parsed.run) {
    await cmdRun(filters, parsed);
  } else {
    await cmdPrint(filters, parsed);
  }
}

main().catch((err: unknown) => {
  process.stderr.write(`[log-error] Fatal: ${String(err)}\n`);
  process.exit(1);
});
