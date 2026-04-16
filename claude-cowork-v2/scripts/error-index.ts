/**
 * error-index.ts
 *
 * Manages the error candidate index for the bug-log workflow.
 *
 * Primary storage: .claude-cowork/error-index.json
 * Fallback:        dynamic scan of logs/errors/** when index is absent/stale
 *
 * This module is intentionally standalone — it does NOT import from
 * capture-error.ts to avoid circular dependencies.
 *
 * Public API:
 *   loadOrBuildIndex()                    — load or rebuild the full index
 *   appendToIndex(entry)                  — add one entry and persist
 *   resolveBestCandidate(index, filters)  — smart relevance selection
 */

import fs from 'fs-extra';
import path from 'path';
import { nowIso } from './ids.js';

// ── Types ─────────────────────────────────────────────────────────────────────

/** One entry in the error index — one captured error event. */
export interface ErrorIndexEntry {
  error_id: string;
  session_id: string;
  task_id: string;
  run_id: string;
  component: string;
  action: string;
  timestamp: string;           // ISO 8601 UTC
  error_name: string;
  error_message: string;       // first 200 chars — safe for display
  error_log_path: string;      // relative to project root, forward slashes
  bug_prompt_path: string;     // relative to project root, forward slashes
}

/** The full index file shape. */
export interface ErrorIndex {
  version: '2.0';
  updated_at: string;
  entries: ErrorIndexEntry[];  // ordered newest-first
}

/** Filters accepted by resolveBestCandidate(). */
export interface CandidateFilters {
  session_id?: string;
  task_id?: string;
  component?: string;
  error_id?: string;   // exact match — bypasses all other filters
  latest?: boolean;    // force newest entry, ignore other filters
}

// ── Paths ─────────────────────────────────────────────────────────────────────

const INDEX_PATH = path.resolve(process.cwd(), '.claude-cowork', 'error-index.json');
const LOGS_ERRORS_DIR = path.resolve(process.cwd(), 'logs', 'errors');

// ── Index I/O ─────────────────────────────────────────────────────────────────

/** Load the index from disk. Returns null if file is absent or unreadable. */
async function loadIndexFile(): Promise<ErrorIndex | null> {
  if (!(await fs.pathExists(INDEX_PATH))) return null;
  try {
    const raw = await fs.readFile(INDEX_PATH, 'utf-8');
    const parsed = JSON.parse(raw) as ErrorIndex;
    if (!Array.isArray(parsed.entries)) return null;
    return parsed;
  } catch {
    return null;
  }
}

/** Persist the index to disk. */
async function saveIndexFile(index: ErrorIndex): Promise<void> {
  await fs.ensureDir(path.dirname(INDEX_PATH));
  await fs.writeFile(INDEX_PATH, JSON.stringify(index, null, 2), 'utf-8');
}

// ── Filesystem scan (fallback / rebuild) ─────────────────────────────────────

/**
 * Scan logs/errors/<session_id>/*-error.json and build a fresh index.
 * Used when no index file exists yet (e.g. errors captured by V1).
 */
export async function buildIndexFromScan(): Promise<ErrorIndex> {
  const entries: ErrorIndexEntry[] = [];

  if (!(await fs.pathExists(LOGS_ERRORS_DIR))) {
    return { version: '2.0', updated_at: nowIso(), entries: [] };
  }

  // Each sub-directory is a session_id
  const sessionDirs = await fs.readdir(LOGS_ERRORS_DIR);
  for (const sessionId of sessionDirs) {
    const sessionDir = path.join(LOGS_ERRORS_DIR, sessionId);
    const stat = await fs.stat(sessionDir).catch(() => null);
    if (!stat?.isDirectory()) continue;

    const files = await fs.readdir(sessionDir);
    for (const filename of files) {
      if (!filename.endsWith('-error.json')) continue;
      const filePath = path.join(sessionDir, filename);
      try {
        const raw = await fs.readFile(filePath, 'utf-8');
        const log = JSON.parse(raw) as Record<string, unknown>;

        // Require the minimum fields needed to be a valid index entry
        if (
          typeof log['error_id'] !== 'string' ||
          typeof log['timestamp'] !== 'string'
        ) continue;

        const errorId = log['error_id'] as string;
        const promptRelPath = `artifacts/bug-prompts/${errorId}-fix-bug.md`;
        const promptAbs = path.resolve(process.cwd(), promptRelPath);
        const promptExists = await fs.pathExists(promptAbs);

        entries.push({
          error_id:       errorId,
          session_id:     typeof log['session_id'] === 'string' ? log['session_id'] : sessionId,
          task_id:        typeof log['task_id'] === 'string'    ? log['task_id']    : 'unknown',
          run_id:         typeof log['run_id'] === 'string'     ? log['run_id']     : 'unknown',
          component:      typeof log['component'] === 'string'  ? log['component']  : 'unknown',
          action:         typeof log['action'] === 'string'     ? log['action']     : 'unknown',
          timestamp:      log['timestamp'] as string,
          error_name:     typeof log['error_name'] === 'string'    ? log['error_name']    : 'UnknownError',
          error_message:  typeof log['error_message'] === 'string' ? (log['error_message'] as string).slice(0, 200) : '',
          error_log_path: path.relative(process.cwd(), filePath).replace(/\\/g, '/'),
          bug_prompt_path: promptExists ? promptRelPath : '',
        });
      } catch {
        // Skip unreadable or malformed files silently
      }
    }
  }

  // Sort newest-first
  entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  return { version: '2.0', updated_at: nowIso(), entries };
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Load the index from disk, or build it from a filesystem scan if absent.
 * Always returns a valid ErrorIndex (never throws).
 */
export async function loadOrBuildIndex(): Promise<ErrorIndex> {
  const loaded = await loadIndexFile();
  if (loaded) return loaded;

  // No index file — build from scan (V1 backward compat)
  const built = await buildIndexFromScan();
  // Persist it for next time, best-effort
  saveIndexFile(built).catch(() => undefined);
  return built;
}

/**
 * Append one entry to the index and persist.
 * Called by capture-error.ts immediately after writing the error log.
 * Deduplicates by error_id (idempotent).
 */
export async function appendToIndex(entry: ErrorIndexEntry): Promise<void> {
  const index = await loadOrBuildIndex();

  // Remove any existing entry with the same error_id (re-capture idempotency)
  const filtered = index.entries.filter((e) => e.error_id !== entry.error_id);

  // Prepend (newest-first ordering)
  const updated: ErrorIndex = {
    version: '2.0',
    updated_at: nowIso(),
    entries: [entry, ...filtered],
  };

  await saveIndexFile(updated);
}

// ── Relevance resolution ──────────────────────────────────────────────────────

/** Result type returned by resolveBestCandidate — includes which filters were used. */
export interface ResolvedCandidate {
  entry: ErrorIndexEntry;
  /** How the candidate was matched: 'exact-id' | 'latest' | 'session+task+component' | etc. */
  match_reason: string;
}

/**
 * Select the most relevant error candidate from the index.
 *
 * Priority order (descending):
 *   1. --id <error_id>        → exact match, skip all other logic
 *   2. --latest               → newest entry by timestamp
 *   3. Session filter         → use provided --session, or infer from newest entry
 *   4. Task filter            → narrow to --task within session group
 *   5. Component filter       → narrow to --component within task group
 *   6. Timestamp tiebreak     → newest among final group
 *
 * Each narrowing step is best-effort: if it would yield zero results,
 * the previous broader set is retained (with a warning message appended).
 *
 * Returns null if the index is empty or no candidates survive filtering.
 */
export function resolveBestCandidate(
  index: ErrorIndex,
  filters: CandidateFilters
): { result: ResolvedCandidate | null; warnings: string[] } {
  const warnings: string[] = [];
  const all = index.entries;

  if (all.length === 0) {
    return { result: null, warnings };
  }

  // ── 1. Exact ID match ─────────────────────────────────────────────────────
  if (filters.error_id) {
    const found = all.find((e) => e.error_id === filters.error_id);
    if (!found) {
      warnings.push(`No error found with id '${filters.error_id}'.`);
      return { result: null, warnings };
    }
    return { result: { entry: found, match_reason: 'exact-id' }, warnings };
  }

  // ── 2. Force latest ───────────────────────────────────────────────────────
  if (filters.latest) {
    // all is already sorted newest-first
    return { result: { entry: all[0]!, match_reason: 'latest' }, warnings };
  }

  // ── 3. Session filter ─────────────────────────────────────────────────────
  let sessionId = filters.session_id;
  if (!sessionId) {
    // Infer: session of the newest entry
    sessionId = all[0]!.session_id;
  }

  let candidates = all.filter((e) => e.session_id === sessionId);
  if (candidates.length === 0) {
    warnings.push(`No errors found for session '${sessionId}'. Falling back to all entries.`);
    candidates = all;
  }
  const matchParts: string[] = [`session=${sessionId}`];

  // ── 4. Task filter ────────────────────────────────────────────────────────
  if (filters.task_id) {
    const narrowed = candidates.filter((e) => e.task_id === filters.task_id);
    if (narrowed.length === 0) {
      warnings.push(
        `No errors found for task '${filters.task_id}' within session '${sessionId}'. ` +
        `Ignoring task filter.`
      );
    } else {
      candidates = narrowed;
      matchParts.push(`task=${filters.task_id}`);
    }
  }

  // ── 5. Component filter ───────────────────────────────────────────────────
  if (filters.component) {
    const narrowed = candidates.filter(
      (e) => e.component.toLowerCase() === filters.component!.toLowerCase()
    );
    if (narrowed.length === 0) {
      warnings.push(
        `No errors found for component '${filters.component}' within current group. ` +
        `Ignoring component filter.`
      );
    } else {
      candidates = narrowed;
      matchParts.push(`component=${filters.component}`);
    }
  }

  // ── 6. Newest among final group (candidates already sorted newest-first) ──
  const best = candidates[0]!;
  return {
    result: { entry: best, match_reason: matchParts.join(', ') },
    warnings,
  };
}
