/* createScreen — UI-R5B IA wrapper.
   Shows sourceScreen (Import phase) when no prepare-source session exists,
   or studioScreen (Brief phase) when a session is ready.
   Both screens are reused without any logic changes — this wrapper only
   routes between them based on draftStore state.
   UI-R5C will rebuild this into a unified single-surface workspace.
*/

import { draftStore }  from '../store/draft.js';
import { sourceScreen } from './source.js';
import { studioScreen } from './studio.js';

export async function mount(el, params) {
  const { draft } = draftStore.getState();
  if (draft.editSessionId) {
    return studioScreen.mount(el, params);
  }
  return sourceScreen.mount(el, params);
}

export const createScreen = { mount };
