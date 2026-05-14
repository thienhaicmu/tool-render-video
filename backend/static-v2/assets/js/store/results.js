import { createStore } from './create-store.js';
import { jobsApi } from '../api/jobs.js';
import { normalizeJob } from '../entities/job.js';
import { normalizePartList } from '../entities/part.js';
import { parseResultPackage } from '../entities/result-package.js';

const store = createStore({
  jobId:             null,
  job:               null,
  parts:             [],
  result:            null,
  selectedClipIndex: null,
  loading:           false,
  error:             null,
});

async function load(jobId) {
  store.set({
    jobId, job: null, parts: [], result: null,
    selectedClipIndex: null, loading: true, error: null,
  });
  try {
    const [jobRaw, partsRaw] = await Promise.all([
      jobsApi.get(jobId),
      jobsApi.getParts(jobId).catch(() => ({ items: [] })),
    ]);
    const job    = normalizeJob(jobRaw);
    const parts  = normalizePartList(partsRaw);
    const result = parseResultPackage(jobId, job?.resultRaw);

    store.set({ job, parts, result, loading: false });

    // Auto-select best clip
    if (result?.ranking?.length > 0) {
      const bestIdx = result.ranking.findIndex(c => c.isBest);
      store.set({ selectedClipIndex: bestIdx >= 0 ? bestIdx : 0 });
    }
  } catch (err) {
    store.set({ loading: false, error: err.message });
  }
}

function selectClip(index) {
  store.set({ selectedClipIndex: index });
}

function getSelectedClip() {
  const { result, selectedClipIndex } = store.getState();
  if (!result || selectedClipIndex === null) return null;
  return result.ranking[selectedClipIndex] ?? null;
}

export const resultsStore = { ...store, load, selectClip, getSelectedClip };
