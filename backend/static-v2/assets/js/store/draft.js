import { createStore } from './create-store.js';
import { renderApi } from '../api/render.js';

const DEFAULTS = {
  sourceFile:    '',
  outputDir:     '',
  platform:      'youtube',
  creatorType:   'solo_creator',
  executionMode: 'balanced',
  aiEnabled:     true,
  qualityPreset: 'standard',
  subtitleStyle: null,
  cameraStyle:   null,
  segmentMode:   null,
};

const store = createStore({
  draft: { ...DEFAULTS },
  dirty: false,
  saving: false,
  error: null,
});

function patch(partial) {
  const { draft } = store.getState();
  store.set({ draft: { ...draft, ...partial }, dirty: true });
}

function reset() {
  store.set({ draft: { ...DEFAULTS }, dirty: false, error: null });
}

async function save() {
  const { draft } = store.getState();
  store.set({ saving: true, error: null });
  try {
    await renderApi.saveDraft(draft);
    store.set({ saving: false, dirty: false });
  } catch (err) {
    store.set({ saving: false, error: err.message });
  }
}

async function loadRemote() {
  try {
    const remote = await renderApi.getDraft();
    if (remote) {
      store.set({ draft: { ...DEFAULTS, ...remote }, dirty: false });
    }
  } catch { /* no remote draft is fine */ }
}

function buildPayload() {
  return { ...store.getState().draft };
}

export const draftStore = { ...store, patch, reset, save, loadRemote, buildPayload };
