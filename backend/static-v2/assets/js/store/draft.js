import { createStore } from './create-store.js';
import { buildRenderRequest } from '../entities/render-request.js';

const DEFAULTS = {
  // Source (set by prepare-source)
  sourceMode:      'youtube',
  youtubeUrl:      '',
  sourceVideoPath: '',
  editSessionId:   null,
  sessionTitle:    null,
  sessionDuration: null,
  outputDir:       '',

  // Clip setup
  aspectRatio:     '9:16',
  minPartSec:      15,
  maxPartSec:      60,
  maxExportParts:  5,

  // Subtitle
  subtitleEnabled: true,
  subtitleStyle:   'viral_bold',

  // Camera
  reframeMode:     'center',
  motionAwareCrop: false,

  // AI
  aiEnabled:          false,
  aiInfluenceEnabled: false,
  aiExecutionMode:    'balanced',

  // Render
  renderProfile: 'quality',
};

const store = createStore({
  draft: { ...DEFAULTS },
  dirty: false,
  error: null,
});

function patch(partial) {
  const { draft } = store.getState();
  store.set({ draft: { ...draft, ...partial }, dirty: true });
}

/* Called after prepare-source succeeds. */
function setSession(session) {
  const { draft } = store.getState();
  store.set({
    draft: {
      ...draft,
      editSessionId:   session.sessionId,
      sessionTitle:    session.title    ?? null,
      sessionDuration: session.duration ?? null,
    },
    dirty: true,
  });
}

function clearSession() {
  const { draft } = store.getState();
  store.set({
    draft: { ...draft, editSessionId: null, sessionTitle: null, sessionDuration: null },
  });
}

function reset() {
  store.set({ draft: { ...DEFAULTS }, dirty: false, error: null });
}

function buildPayload() {
  return buildRenderRequest(store.getState().draft);
}

export const draftStore = { ...store, patch, setSession, clearSession, reset, buildPayload };
