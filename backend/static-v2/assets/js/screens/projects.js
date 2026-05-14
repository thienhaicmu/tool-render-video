/* projectsScreen — UI-R5B IA wrapper.
   Routes /projects (no jobId) → libraryScreen (history/all renders).
   Routes /projects/:jobId → resultsScreen (ranked clip review).
   Both screens are reused without any logic changes — this wrapper only
   dispatches based on whether a jobId param is present.
   UI-R5D will rebuild this into a unified creative project archive.
*/

import { libraryScreen } from './library.js';
import { resultsScreen } from './results.js';

export async function mount(el, params) {
  const jobId = params?.[0];
  if (jobId) {
    return resultsScreen.mount(el, [jobId]);
  }
  return libraryScreen.mount(el, params ?? []);
}

export const projectsScreen = { mount };
