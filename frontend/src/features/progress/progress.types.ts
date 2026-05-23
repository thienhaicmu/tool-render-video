/**
 * progress.types.ts — types for the live job progress feature module.
 */

/** Connection status displayed by ConnectionStatusBadge */
export type ConnectionStatus = 'connecting' | 'live' | 'reconnecting' | 'disconnected' | 'terminal'

/** Max messages to keep in the log */
export const MAX_LOG_MESSAGES = 5
