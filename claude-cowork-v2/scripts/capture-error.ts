#!/usr/bin/env ts-node
/**
 * capture-error.ts — V3
 *
 * Captures a runtime error, classifies severity, writes a structured JSON
 * record, and updates the error-index for frequency tracking.
 *
 * Usage:
 *   ts-node scripts/capture-error.ts \
 *     --session   <session_id>  \
 *     --task      <task_id>     \
 *     --run       <run_id>      \
 *     --component <component>   \
 *     --action    <action>      \
 *     --error-name <ErrorClass> \
 *     --message   "error text"  \
 *     [--severity critical|high|medium|low]
 *
 * Outputs the captured error_id to stdout so callers can chain
 * into build-bug-prompt.ts.
 *
 * Storage layout:
 *   .claude-cowork/errors/<error_id>.json
 *   .claude-cowork/error-index.json
 *   .claude-cowork/last-error.json
 */

import * as fs   from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

import {
  classifyErrorSeverity,
  computeBugSignature,
  isValidSeverity,
  ErrorRecord,
} from './error-ranking';

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const ROOT        = path.resolve(__dirname, '..');
const COWORK_DIR  = path.join(ROOT, '.claude-cowork');
const ERRORS_DIR  = path.join(COWORK_DIR, 'errors');
const INDEX_PATH  = path.join(COWORK_DIR, 'error-index.json');
const LAST_PATH   = path.join(COWORK_DIR, 'last-error.json');

// ---------------------------------------------------------------------------
// Error index schema
// ---------------------------------------------------------------------------

interface SignatureEntry {
  count: number;
  first_seen_at: string;
  last_seen_at: string;
  error_ids: string[];
}

interface ErrorIndex {
  signatures: Record<string, SignatureEntry>;
  last_error_id: string | null;
  updated_at: string;
}

function loadIndex(): ErrorIndex {
  if (!fs.existsSync(INDEX_PATH)) {
    return { signatures: {}, last_error_id: null, updated_at: new Date().toISOString() };
  }
  try {
    return JSON.parse(fs.readFileSync(INDEX_PATH, 'utf8')) as ErrorIndex;
  } catch {
    return { signatures: {}, last_error_id: null, updated_at: new Date().toISOString() };
  }
}

function saveIndex(index: ErrorIndex): void {
  ensureDir(COWORK_DIR);
  index.updated_at = new Date().toISOString();
  fs.writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2), 'utf8');
}

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

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main(): void {
  const args = parseArgs(process.argv.slice(2));

  const session_id   = args['session']    ?? 'unknown';
  const task_id      = args['task']       ?? 'unknown';
  const run_id       = args['run']        ?? 'unknown';
  const component    = args['component']  ?? 'unknown';
  const action       = args['action']     ?? 'unknown';
  const error_name   = args['error-name'] ?? 'UnknownError';
  const error_message = args['message']   ?? '';
  const severity_override = args['severity'];

  const timestamp  = new Date().toISOString();
  const error_id   = crypto.randomUUID();

  const partial: Partial<ErrorRecord> = {
    component,
    action,
    error_name,
    error_message,
    severity: isValidSeverity(severity_override) ? severity_override : undefined,
  };

  const severity      = classifyErrorSeverity(partial);
  const bug_signature = computeBugSignature(partial);

  // Update index
  const index = loadIndex();
  const entry: SignatureEntry = index.signatures[bug_signature] ?? {
    count: 0,
    first_seen_at: timestamp,
    last_seen_at:  timestamp,
    error_ids:     [],
  };
  entry.count++;
  entry.last_seen_at = timestamp;
  entry.error_ids.push(error_id);
  index.signatures[bug_signature] = entry;
  index.last_error_id = error_id;

  const frequency_count = entry.count;

  // Compose record
  const record: ErrorRecord = {
    error_id,
    session_id,
    task_id,
    run_id,
    component,
    action,
    timestamp,
    error_name,
    error_message,
    severity,
    bug_signature,
    frequency_count,
    bug_prompt_path: undefined,
  };

  // Write error file
  ensureDir(ERRORS_DIR);
  const error_path = path.join(ERRORS_DIR, `${error_id}.json`);
  fs.writeFileSync(error_path, JSON.stringify(record, null, 2), 'utf8');

  // Write last-error pointer
  ensureDir(COWORK_DIR);
  fs.writeFileSync(LAST_PATH, JSON.stringify({ error_id, timestamp, bug_signature }, null, 2), 'utf8');

  // Save index
  saveIndex(index);

  // Output error_id for chaining
  process.stdout.write(error_id + '\n');
}

main();
