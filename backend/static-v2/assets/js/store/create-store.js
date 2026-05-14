/* Minimal reactive store factory.
   Usage:
     const store = createStore({ count: 0 });
     const unsub = store.subscribe(state => console.log(state));
     store.set({ count: 1 });
     store.update(s => ({ ...s, count: s.count + 1 }));
     unsub();
*/

export function createStore(initialState) {
  let state = { ...initialState };
  const listeners = new Set();

  function getState() {
    return state;
  }

  function set(partial) {
    state = { ...state, ...partial };
    listeners.forEach(fn => fn(state));
  }

  function update(updater) {
    set(updater(state));
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  function reset() {
    set({ ...initialState });
  }

  return { getState, set, update, subscribe, reset };
}
