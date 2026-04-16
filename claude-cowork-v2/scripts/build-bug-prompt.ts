#!/usr/bin/env ts-node
/**
 * build-bug-prompt.ts — V3
 *
 * Generates a structured bug-fix prompt artifact (.md) from an error record.
 * Writes the artifact and back-patches bug_prompt_path into the error JSON.
 *
 * Usage:
 *   ts-node scripts/build-bug-prompt.ts --id <error_id>
 *   ts-node scripts/build-bug-prompt.ts          # uses last-error pointer
 *
 * Output:
 *   .claude-cowork/bug-prompts/<error_id>.md
 *   (also patches .claude-cowork/errors/<error_id>.json with bug_prompt_path)
 */

import * as fs   from 'fs';
import * as path from 'path';

import { ErrorRecord, buildPromptContent, computeBugSignature } from './error-ranking';

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const ROOT        = path.resolve(__dirname, '..');
const COWORK_DIR  = path.join(ROOT, '.claude-cowork');
const ERRORS_DIR  = path.join(COWORK_DIR, 'errors');
const PROMPTS_DIR = path.join(COWORK_DIR, 'bug-prompts');
const LAST_PATH   = path.join(COWORK_DIR, 'last-error.json');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ensureDir(dir: string): void {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function parseArgs(argv: string[]): Record<string, string> {
  const args: Record<string, string> = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const key = argv[i].slice(2);
      args[key] = argv[i + 1] ?? '';
      i++;
    }
  }
  return args;
}

function loadRecord(error_id: string): ErrorRecord {
  const p = path.join(ERRORS_DIR, `${error_id}.json`);
  if (!fs.existsSync(p)) {
    throw new Error(`Error record not found: ${p}`);
  }
  const record = JSON.parse(fs.readFileSync(p, 'utf8')) as ErrorRecord;
  // Ensure bug_signature is populated for records that predate V3
  if (!record.bug_signature) {
    record.bug_signature = computeBugSignature(record);
  }
  return record;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main(): void {
  const args = parseArgs(process.argv.slice(2));

  let error_id = args['id'];
  if (!error_id) {
    if (!fs.existsSync(LAST_PATH)) {
      console.error('No --id provided and no last-error.json found.');
      process.exit(1);
    }
    const last = JSON.parse(fs.readFileSync(LAST_PATH, 'utf8')) as { error_id: string };
    error_id = last.error_id;
    if (!error_id) {
      console.error('last-error.json does not contain a valid error_id.');
      process.exit(1);
    }
  }

  const record  = loadRecord(error_id);
  const content = buildPromptContent(record);

  ensureDir(PROMPTS_DIR);
  const prompt_path    = path.join(PROMPTS_DIR, `${error_id}.md`);
  fs.writeFileSync(prompt_path, content, 'utf8');

  // Back-patch bug_prompt_path into the error record
  const relative_path = path.relative(ROOT, prompt_path).replace(/\\/g, '/');
  record.bug_prompt_path = relative_path;
  fs.writeFileSync(
    path.join(ERRORS_DIR, `${error_id}.json`),
    JSON.stringify(record, null, 2),
    'utf8',
  );

  process.stdout.write(prompt_path + '\n');
}

main();
