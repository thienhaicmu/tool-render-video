import { fetchJson } from '../transport.js';

export const jobsApi = {
  async list(params) {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetchJson(`/api/jobs${qs}`);
  },

  async get(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
  },

  async getParts(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/parts`);
  },

  async getLogs(jobId, lines = 120) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/logs?lines=${lines}`);
  },

  async getQueueStatus() {
    return fetchJson('/api/jobs/queue/status');
  },

  async delete(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`, {
      method: 'DELETE',
    });
  },

  async getHistory() {
    return fetchJson('/api/jobs/history');
  },
};
