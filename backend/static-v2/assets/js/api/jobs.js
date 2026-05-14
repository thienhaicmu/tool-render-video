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

  async getResult(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/result`);
  },

  async getSummary(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/summary`);
  },

  async delete(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`, {
      method: 'DELETE',
    });
  },
};
