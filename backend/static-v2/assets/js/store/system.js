import { createStore } from './create-store.js';
import { systemApi } from '../api/system.js';

const store = createStore({
  health:        null,
  executionMode: 'balanced',
  appVersion:    null,
  backendReady:  false,
  error:         null,
});

let _healthTimer = null;

async function init() {
  try {
    const [health, mode] = await Promise.allSettled([
      systemApi.getHealth(),
      systemApi.getExecutionMode(),
    ]);

    const update = { backendReady: true, error: null };

    if (health.status === 'fulfilled') {
      update.health = health.value;
    }

    if (mode.status === 'fulfilled') {
      update.executionMode = mode.value?.mode ?? mode.value?.execution_mode ?? 'balanced';
    }

    store.set(update);
  } catch (err) {
    store.set({ backendReady: false, error: err.message });
  }

  // Periodic health watch: recheck every 30s when backend is unavailable,
  // every 60s when ready (to detect disconnects without hammering the backend)
  _startHealthWatch();
}

async function refresh() {
  try {
    const health = await systemApi.getHealth();
    store.set({ health, backendReady: true, error: null });
  } catch (err) {
    store.set({ backendReady: false, error: err.message });
  }
}

function _startHealthWatch() {
  if (_healthTimer) return;
  _healthTimer = setInterval(async () => {
    const { backendReady } = store.getState();
    try {
      await systemApi.getHealth();
      if (!backendReady) store.set({ backendReady: true, error: null });
    } catch {
      if (backendReady) store.set({ backendReady: false });
    }
  }, 30_000);
}

export const systemStore = { ...store, init, refresh };
