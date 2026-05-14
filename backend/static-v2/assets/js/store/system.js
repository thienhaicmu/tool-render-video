import { createStore } from './create-store.js';
import { systemApi } from '../api/system.js';

const store = createStore({
  health: null,
  executionMode: 'balanced',
  appVersion: null,
  backendReady: false,
  error: null,
});

async function init() {
  try {
    const [health, mode] = await Promise.allSettled([
      systemApi.getHealth(),
      systemApi.getExecutionMode(),
    ]);

    const update = { backendReady: true };

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
}

async function refresh() {
  try {
    const health = await systemApi.getHealth();
    store.set({ health, backendReady: true, error: null });
  } catch (err) {
    store.set({ backendReady: false, error: err.message });
  }
}

export const systemStore = { ...store, init, refresh };
