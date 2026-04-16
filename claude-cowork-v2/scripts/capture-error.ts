/**
 * capture-error.ts
 *
 * Reusable runtime error capture utility.
 *
 * Accepts structured error context, writes a typed JSON error log to:
 *   logs/errors/<session_id>/<timestamp>-error.json
 *
 * Then calls build-bug-prompt to generate the fix prompt, and updates:
 *   .claude-cowork/last-error.json
 *
 * ── HOOK POINT ────────────────────────────────────────────────────────────────
 * To wire this into the existing pipeline, call captureError() inside the
 * catch block of any stage that throws a critical error. Example in pipeline.ts:
 *
 *   } catch (err: unknown) {
 *     await captureError({
 *       error: err,
 *       component: 'pipeline',
 *       action: 'run_stage',
 *       session_id: ctx.session_id,
 *       task_id: ctx.task_id,
 *       run_id: ctx.run_id,
 *       suspected_flow: ['pipeline.ts → runStage → ...'],
 *     });
 *     throw err;
 *   }
 * ─────────────────────────────────────────────────────────────────────────────
 *
 * SECURITY: Never include secrets, API keys, tokens, or PII in any field.
 * The input_summary field is caller-controlled — sanitize before passing.
 */

import fs from 'fs-extra';
import path from 'path';
import { nowIso } from './ids.js';
import { buildBugPrompt } from './build-bug-prompt.js';
import { appendToIndex } from './error-index.js';
import type { ErrorIndexEntry } from './error-index.js';

// ── Types ─────────────────────────────────────────────────────────────────────

/** Caller-supplied context for a runtime error. */
export interface ErrorContext {
  /** The raw error value (Error instance or unknown throw). */
  error: unknown;
  /** Logical component where the error occurred (e.g. "video-download-service"). */
  component: string;
  /** Specific action being performed (e.g. "download_and_stream_video"). */
  action: string;
  /** Session ID from the active pipeline context. */
  session_id: string;
  /** Task ID if known; defaults to "unknown". */
  task_id?: string;
  /** Run ID if known; defaults to "unknown". */
  run_id?: string;
  /**
   * Safe serializable summary of the inputs at the time of failure.
   * Do NOT include secrets, API keys, or raw user credentials.
   */
  input_summary?: Record<string, unknown>;
  /** File paths relevant to this error (source files, config, etc.). */
  related_files?: string[];
  /** Ordered list of function/module steps suspected to be in the call chain. */
  suspected_flow?: string[];
}

/** The structured JSON error log written to disk. */
export interface ErrorLog {
  error_id: string;
  session_id: string;
  task_id: string;
  run_id: string;
  timestamp: string;
  component: string;
  action: string;
  status: 'failed';
  error_name: string;
  error_message: string;
  stack_trace: string;
  input_summary: Record<string, unknown>;
  related_files: string[];
  suspected_flow: string[];
}

/** Return value of captureError(). */
export interface CapturedError {
  error_id: string;
  error_log_path: string;
  bug_prompt_path: string;
}

/** Shape of .claude-cowork/last-error.json */
export interface LastErrorPointer {
  latest_error_id: string;
  latest_error_path: string;
  latest_bug_prompt_path: string;
  session_id: string;
  task_id: string;
  run_id: string;
  updated_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Generate a timestamp-based error ID.
 * Format: err_YYYYMMDD_HHmmss  (e.g. err_20260416_221501)
 * Uses UTC to ensure consistent IDs across timezones.
 */
function generateErrorId(now: Date): string {
  const iso = now.toISOString(); // "2026-04-16T22:15:01.000Z"
  const dateStr = iso.slice(0, 10).replace(/-/g, ''); // "20260416"
  const timeStr = iso.slice(11, 19).replace(/:/g, ''); // "221501"
  return `err_${dateStr}_${timeStr}`;
}

/**
 * Generate the timestamp prefix used in the filename.
 * Format: YYYYMMDD_HHmmss
 */
function generateTimestampPrefix(now: Date): string {
  const iso = now.toISOString();
  const dateStr = iso.slice(0, 10).replace(/-/g, '');
  const timeStr = iso.slice(11, 19).replace(/:/g, '');
  return `${dateStr}_${timeStr}`;
}

/**
 * Safely extract a string name from an unknown error value.
 */
function extractErrorName(err: unknown): string {
  if (err instanceof Error) return err.name || 'Error';
  if (typeof err === 'object' && err !== null) {
    const cast = err as Record<string, unknown>;
    if (typeof cast['name'] === 'string') return cast['name'];
    if (typeof cast['code'] === 'string') return cast['code'];
  }
  return 'UnknownError';
}

/**
 * Safely extract a human-readable message from an unknown error value.
 */
function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message || String(err);
  if (typeof err === 'object' && err !== null) {
    const cast = err as Record<string, unknown>;
    if (typeof cast['message'] === 'string') return cast['message'];
  }
  return String(err);
}

/**
 * Safely extract a stack trace string from an unknown error value.
 */
function extractStackTrace(err: unknown): string {
  if (err instanceof Error && err.stack) return err.stack;
  return '(no stack trace available)';
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Capture a runtime error: write the structured log, generate a fix prompt,
 * and update the last-error pointer.
 *
 * Safe to call from any catch block — never throws; if internal I/O fails
 * the error is written to stderr and the function returns null.
 */
export async function captureError(ctx: ErrorContext): Promise<CapturedError | null> {
  try {
    const now = new Date();
    const error_id = generateErrorId(now);
    const timestamp_prefix = generateTimestampPrefix(now);
    const timestamp = now.toISOString();

    const task_id = ctx.task_id ?? 'unknown';
    const run_id = ctx.run_id ?? 'unknown';

    // ── Build the error log ─────────────────────────────────────────────────

    const errorLog: ErrorLog = {
      error_id,
      session_id: ctx.session_id,
      task_id,
      run_id,
      timestamp,
      component: ctx.component,
      action: ctx.action,
      status: 'failed',
      error_name: extractErrorName(ctx.error),
      error_message: extractErrorMessage(ctx.error),
      stack_trace: extractStackTrace(ctx.error),
      input_summary: ctx.input_summary ?? {},
      related_files: ctx.related_files ?? [],
      suspected_flow: ctx.suspected_flow ?? [],
    };

    // ── Write error log to disk ─────────────────────────────────────────────

    const logsDir = path.resolve(process.cwd(), 'logs', 'errors', ctx.session_id);
    await fs.ensureDir(logsDir);
    const errorLogFilename = `${timestamp_prefix}-error.json`;
    const errorLogPath = path.join(logsDir, errorLogFilename);
    await fs.writeFile(errorLogPath, JSON.stringify(errorLog, null, 2), 'utf-8');

    // ── Generate bug-fix prompt ─────────────────────────────────────────────

    const bugPromptPath = await buildBugPrompt(errorLog);

    // ── Update error index (V2 smart selection) ────────────────────────────

    const errorLogRel = path.relative(process.cwd(), errorLogPath).replace(/\\/g, '/');
    const bugPromptRel = path.relative(process.cwd(), bugPromptPath).replace(/\\/g, '/');

    const indexEntry: ErrorIndexEntry = {
      error_id,
      session_id: ctx.session_id,
      task_id,
      run_id,
      component: ctx.component,
      action: ctx.action,
      timestamp,
      error_name: errorLog.error_name,
      error_message: errorLog.error_message.slice(0, 200),
      error_log_path: errorLogRel,
      bug_prompt_path: bugPromptRel,
    };
    await appendToIndex(indexEntry);

    // ── Update last-error pointer (V1 backward compat) ──────────────────────

    const pointerDir = path.resolve(process.cwd(), '.claude-cowork');
    await fs.ensureDir(pointerDir);
    const pointer: LastErrorPointer = {
      latest_error_id: error_id,
      latest_error_path: errorLogRel,
      latest_bug_prompt_path: bugPromptRel,
      session_id: ctx.session_id,
      task_id,
      run_id,
      updated_at: nowIso(),
    };
    await fs.writeFile(
      path.join(pointerDir, 'last-error.json'),
      JSON.stringify(pointer, null, 2),
      'utf-8'
    );

    return {
      error_id,
      error_log_path: errorLogPath,
      bug_prompt_path: bugPromptPath,
    };
  } catch (internalErr) {
    // captureError must never crash the caller
    process.stderr.write(
      `[capture-error] INTERNAL ERROR — could not persist error log: ${String(internalErr)}\n`
    );
    return null;
  }
}
