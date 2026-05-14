import { fetchJson } from '../transport.js';

export const renderApi = {
  async submit(payload) {
    return fetchJson('/api/render', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async cancel(jobId) {
    return fetchJson(`/api/render/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    });
  },

  async getDraft() {
    return fetchJson('/api/render/draft');
  },

  async saveDraft(payload) {
    return fetchJson('/api/render/draft', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },

  async getSupportedPlatforms() {
    return fetchJson('/api/render/platforms');
  },

  async getCreatorTypes() {
    return fetchJson('/api/render/creator-types');
  },
};
