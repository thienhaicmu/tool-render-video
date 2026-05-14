/* Electron/desktop bridge adapter.
   In a browser context (no window.electronAPI), all calls are no-ops or return null.
   In Electron renderer context, electronAPI is injected via contextBridge in preload.
*/

const api = (typeof window !== 'undefined' && window.electronAPI) || null;

export const desktopAdapter = {
  isDesktop: !!api,

  async pickVideoFile() {
    if (!api) return null;
    return api.pickVideoFile?.() ?? null;
  },

  async pickOutputDir() {
    if (!api) return null;
    return api.pickOutputDir?.() ?? null;
  },

  async getAppVersion() {
    if (!api) return null;
    return api.getAppVersion?.() ?? null;
  },

  onJobProgress(handler) {
    if (!api?.onJobProgress) return () => {};
    return api.onJobProgress(handler);
  },

  openExternal(url) {
    if (api?.openExternal) {
      api.openExternal(url);
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  },
};
