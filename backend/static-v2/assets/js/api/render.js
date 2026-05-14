import { fetchJson } from '../transport.js';

export const renderApi = {
  async prepareSource(payload) {
    return fetchJson('/api/render/prepare-source', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /* Returns a URL string — used directly in <video src="..."> */
  getPreviewVideoUrl(sessionId) {
    return `/api/render/preview-video/${encodeURIComponent(sessionId)}`;
  },

  async getPreviewTranscript(sessionId) {
    return fetchJson(`/api/render/preview-transcript/${encodeURIComponent(sessionId)}`);
  },

  async process(payload) {
    return fetchJson('/api/render/process', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async cancel(jobId) {
    return fetchJson(`/api/render/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    });
  },

  async retry(jobId) {
    return fetchJson(`/api/render/retry/${encodeURIComponent(jobId)}`, {
      method: 'POST',
    });
  },

  async resume(jobId) {
    return fetchJson(`/api/render/resume/${encodeURIComponent(jobId)}`, {
      method: 'POST',
    });
  },
};
