import { createStore } from './create-store.js';
import { jobsApi } from '../api/jobs.js';
import { parseResultPackage } from '../entities/result-package.js';

const store = createStore({
  jobId: null,
  result: null,
  selectedPartIndex: null,
  loading: false,
  error: null,
});

async function load(jobId) {
  store.set({ jobId, result: null, loading: true, error: null, selectedPartIndex: null });
  try {
    const raw = await jobsApi.getResult(jobId);
    const result = parseResultPackage(raw);
    store.set({ result, loading: false });
  } catch (err) {
    store.set({ loading: false, error: err.message });
  }
}

function selectPart(index) {
  store.set({ selectedPartIndex: index });
}

function getSelectedPart() {
  const { result, selectedPartIndex } = store.getState();
  if (!result || selectedPartIndex === null) return null;
  return result.parts[selectedPartIndex] ?? null;
}

export const resultsStore = { ...store, load, selectPart, getSelectedPart };
