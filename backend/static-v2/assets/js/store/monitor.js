import { createStore } from './create-store.js';
import { subscribeJob } from '../transport.js';
import { normalizeJob } from '../entities/job.js';
import { normalizePartList } from '../entities/part.js';
import { jobsApi } from '../api/jobs.js';

const store = createStore({
  jobId:         null,
  job:           null,
  parts:         [],
  summary:       null,
  transportMode: 'connecting',
  terminal:      false,
  terminalStatus: null,
  queueStatus:   null,
  logs:          null,
  logsLoading:   false,
  error:         null,
});

let _subscription = null;

function _handleUpdate(data) {
  const update = {};
  if (data.job)     update.job     = normalizeJob(data.job);
  if (data.parts)   update.parts   = normalizePartList(data.parts);
  if (data.summary) update.summary = data.summary;
  if (data._transport) update.transportMode = data._transport;
  if (Object.keys(update).length) store.set(update);
}

function start(jobId) {
  stop();
  store.set({
    jobId, job: null, parts: [], summary: null,
    transportMode: 'connecting', terminal: false, terminalStatus: null,
    logs: null, error: null,
  });

  _subscription = subscribeJob(jobId, {
    onUpdate: _handleUpdate,
    onTerminal(status) {
      store.set({ terminal: true, terminalStatus: status });
      // Authoritative final fetch
      jobsApi.get(jobId)
        .then(raw => { if (raw) store.set({ job: normalizeJob(raw) }); })
        .catch(() => {});
    },
    onTransportChange(mode) {
      store.set({ transportMode: mode });
    },
  });
}

function stop() {
  if (_subscription) { _subscription.unsubscribe(); _subscription = null; }
  store.set({ transportMode: 'connecting' });
}

async function loadLogs(lines = 120) {
  const { jobId } = store.getState();
  if (!jobId) return;
  store.set({ logsLoading: true });
  try {
    const data = await jobsApi.getLogs(jobId, lines);
    store.set({ logs: data?.items ?? [], logsLoading: false });
  } catch {
    store.set({ logs: [], logsLoading: false });
  }
}

function clear() {
  stop();
  store.reset();
}

export const monitorStore = { ...store, start, stop, clear, loadLogs };
