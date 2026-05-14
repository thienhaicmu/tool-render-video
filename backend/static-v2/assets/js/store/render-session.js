/* Global render session store — tracks the active render across all routes.
   Synced from monitorStore on every update.
   Shell subscribes to drive the persistent render bar.
   Active = queued | running. Terminal = completed | failed | interrupted | completed_with_errors.
*/

import { createStore } from './create-store.js';

const ACTIVE_STATUSES = new Set(['queued', 'running']);

const _initial = {
  jobId:           null,
  status:          null,
  progressPercent: 0,
  stage:           '',
  doneParts:       0,
  totalParts:      0,
  transportMode:   'connecting',
  active:          false,
};

const store = createStore({ ..._initial });

/* Called by monitorStore after every state mutation. */
function sync(monitorState) {
  const { jobId, job, summary, transportMode, terminalStatus, terminal } = monitorState;

  const status          = terminal
    ? (terminalStatus ?? job?.status ?? null)
    : (job?.status ?? null);
  const progressPercent = Math.min(100, job?.progressPercent ?? summary?.overall_progress_percent ?? 0);
  const stage           = job?.stage ?? summary?.current_stage ?? '';
  const doneParts       = summary?.completed_parts ?? 0;
  const totalParts      = summary?.total_parts ?? 0;
  const active          = !terminal && status != null && ACTIVE_STATUSES.has(status);

  store.set({ jobId, status, progressPercent, stage, doneParts, totalParts, transportMode, active });
}

function clear() {
  store.reset();
}

export const renderSessionStore = { ...store, sync, clear };
