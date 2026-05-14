import { createStore } from './create-store.js';
import { openJobStream } from '../transport.js';
import { normalizeJob } from '../entities/job.js';
import { normalizePartList } from '../entities/part.js';

const store = createStore({
  jobId: null,
  job: null,
  parts: [],
  summary: null,
  connected: false,
  error: null,
});

let _closeStream = null;

function _handleMessage(data) {
  const update = {};
  if (data.job)     update.job     = normalizeJob(data.job);
  if (data.parts)   update.parts   = normalizePartList(data.parts);
  if (data.summary) update.summary = data.summary;
  if (Object.keys(update).length) store.set(update);
}

function start(jobId) {
  stop();
  store.set({ jobId, job: null, parts: [], summary: null, connected: true, error: null });

  _closeStream = openJobStream(jobId, {
    onMessage: _handleMessage,
    onError:   err => store.set({ error: err?.message ?? 'stream error' }),
    onClose:   () => store.set({ connected: false }),
  });
}

function stop() {
  if (_closeStream) { _closeStream(); _closeStream = null; }
  store.set({ connected: false });
}

function clear() {
  stop();
  store.reset();
}

export const monitorStore = { ...store, start, stop, clear };
