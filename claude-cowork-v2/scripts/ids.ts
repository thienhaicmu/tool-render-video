/**
 * ids.ts
 *
 * Deterministic, collision-resistant ID generation using the standard
 * crypto module. No external ULID/UUID library required.
 */

import { randomBytes } from 'crypto';

/**
 * Generates a URL-safe random ID using crypto.randomBytes.
 * Format: <prefix>_<timestamp_base36><random_base36>
 *
 * Example: task_lk2j4m7p8xqr9s0t
 */
export function generateId(prefix: string): string {
  const timestamp = Date.now().toString(36);
  const random = randomBytes(8).toString('hex');
  return `${prefix}_${timestamp}${random}`;
}

export function generateTaskId(): string {
  return generateId('task');
}

export function generateRunId(): string {
  return generateId('run');
}

export function generateSessionId(): string {
  return generateId('sess');
}

/**
 * Returns the current ISO 8601 timestamp.
 */
export function nowIso(): string {
  return new Date().toISOString();
}
