import { fetchJson } from '../transport.js';

export const systemApi = {
  async getHealth() {
    return fetchJson('/api/health');
  },

  async getSystemInfo() {
    return fetchJson('/api/system/info');
  },

  async getExecutionMode() {
    return fetchJson('/api/system/execution-mode');
  },

  async getSessions() {
    return fetchJson('/api/sessions');
  },

  async getSession(sessionId) {
    return fetchJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
  },
};
