/* Download API wrappers.
   Contract source: docs/FRONTEND_CONTRACT_PACKET_V1.md §9
   POST /api/download/process    — create download batch job
   POST /api/download/retry/{id} — retry failed download items
   GET  /api/jobs/{id}           — fetch current job status
*/

import { fetchJson } from '../transport.js';

export const downloadApi = {
  async processDownload(payload) {
    return fetchJson('/api/download/process', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async retryDownload(jobId, partNumbers = []) {
    return fetchJson(`/api/download/retry/${encodeURIComponent(jobId)}`, {
      method: 'POST',
      body: JSON.stringify({ part_numbers: partNumbers }),
    });
  },

  async getDownloadJob(jobId) {
    return fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
  },
};
