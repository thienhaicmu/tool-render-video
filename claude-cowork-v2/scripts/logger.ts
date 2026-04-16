/**
 * logger.ts
 *
 * Structured JSON logger for the Claude Cowork pipeline.
 *
 * Every log entry is a NDJSON line written to stdout AND optionally
 * to a rotating log file. The structured format ensures compatibility
 * with log aggregation tools (Datadog, Loki, CloudWatch, etc.).
 *
 * SECURITY: Never log secrets, API keys, or PII.
 * Pass only metadata that is safe for an audit trail.
 */

import fs from 'fs-extra';
import path from 'path';
import type { StructuredEvent, EventName, LogLevel, PipelineConfig } from './types.js';

// ── Level ordering ────────────────────────────────────────────────────────────

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

// ── Logger implementation ─────────────────────────────────────────────────────

export class Logger {
  private readonly component: string;
  private readonly config: Pick<PipelineConfig, 'log_level' | 'logs_root'>;
  private readonly task_id: string;
  private readonly run_id: string;
  private readonly session_id: string;

  constructor(
    component: string,
    config: Pick<PipelineConfig, 'log_level' | 'logs_root'>,
    ids: { task_id: string; run_id: string; session_id: string }
  ) {
    this.component = component;
    this.config = config;
    this.task_id = ids.task_id;
    this.run_id = ids.run_id;
    this.session_id = ids.session_id;
  }

  // ── Private helpers ─────────────────────────────────────────────────────────

  private shouldLog(level: LogLevel): boolean {
    return LEVEL_ORDER[level] >= LEVEL_ORDER[this.config.log_level];
  }

  private write(level: LogLevel, message: string, meta?: Record<string, unknown>): void {
    if (!this.shouldLog(level)) return;

    const entry = {
      timestamp: new Date().toISOString(),
      level,
      component: this.component,
      task_id: this.task_id,
      run_id: this.run_id,
      session_id: this.session_id,
      message,
      ...meta,
    };

    // Always write to stdout as NDJSON
    process.stdout.write(JSON.stringify(entry) + '\n');

    // Persist to log file asynchronously (best-effort)
    this.appendToFile(entry).catch(() => {
      // Intentionally silent — log file write failure must not crash the pipeline
    });
  }

  private async appendToFile(entry: Record<string, unknown>): Promise<void> {
    const date = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    const logDir = path.join(this.config.logs_root, 'events');
    const logPath = path.join(logDir, `${date}.ndjson`);
    await fs.ensureDir(logDir);
    await fs.appendFile(logPath, JSON.stringify(entry) + '\n', 'utf-8');
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  debug(message: string, meta?: Record<string, unknown>): void {
    this.write('debug', message, meta);
  }

  info(message: string, meta?: Record<string, unknown>): void {
    this.write('info', message, meta);
  }

  warn(message: string, meta?: Record<string, unknown>): void {
    this.write('warn', message, meta);
  }

  error(message: string, meta?: Record<string, unknown>): void {
    this.write('error', message, meta);
  }

  /**
   * Logs a structured pipeline event conforming to the event taxonomy.
   * Use this for all pipeline state transitions.
   */
  event(
    event_name: EventName,
    status: StructuredEvent['status'],
    meta?: Record<string, unknown>,
    error?: string
  ): void {
    const level: LogLevel =
      status === 'failed' ? 'error' : status === 'info' ? 'debug' : 'info';

    const eventEntry: StructuredEvent = {
      timestamp: new Date().toISOString(),
      task_id: this.task_id,
      run_id: this.run_id,
      session_id: this.session_id,
      component: this.component,
      event_name,
      actor: 'pipeline',
      status,
      metadata: meta,
      error,
    };

    this.write(level, event_name, eventEntry as unknown as Record<string, unknown>);

    // Also write to the events log specifically
    this.appendEventLog(eventEntry).catch(() => {
      // Best-effort
    });
  }

  private async appendEventLog(event: StructuredEvent): Promise<void> {
    const logDir = path.join(this.config.logs_root, 'events');
    const logPath = path.join(logDir, `${this.task_id}-events.ndjson`);
    await fs.ensureDir(logDir);
    await fs.appendFile(logPath, JSON.stringify(event) + '\n', 'utf-8');
  }
}

/**
 * Creates a logger for a pipeline component.
 */
export function createLogger(
  component: string,
  config: Pick<PipelineConfig, 'log_level' | 'logs_root'>,
  ids: { task_id: string; run_id: string; session_id: string }
): Logger {
  return new Logger(component, config, ids);
}
