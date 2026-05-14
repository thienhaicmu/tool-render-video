import { createStore } from './create-store.js';
import { systemApi } from '../api/system.js';
import { normalizeSessionList } from '../entities/source-session.js';

const store = createStore({
  sessions: [],
  activeSessionId: null,
  loading: false,
  error: null,
});

async function load() {
  store.set({ loading: true, error: null });
  try {
    const raw = await systemApi.getSessions();
    const sessions = normalizeSessionList(Array.isArray(raw) ? raw : raw?.sessions ?? []);
    store.set({ sessions, loading: false });
  } catch (err) {
    store.set({ loading: false, error: err.message });
  }
}

function setActive(sessionId) {
  store.set({ activeSessionId: sessionId });
}

function getActive() {
  const { sessions, activeSessionId } = store.getState();
  return sessions.find(s => s.id === activeSessionId) ?? null;
}

export const sessionStore = { ...store, load, setActive, getActive };
