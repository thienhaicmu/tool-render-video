/* Electron/desktop bridge adapter.
   In a browser context (no window.electronAPI), all calls are no-ops or safe
   fallbacks. Never crashes if preload is missing or API methods are absent.
*/

const api = (typeof window !== 'undefined' && window.electronAPI) || null;

export const desktopAdapter = {
  isDesktop: !!api,

  /* True only when a native folder picker is wired up via IPC. */
  get folderPickerAvailable() {
    return !!(api?.pickOutputDir);
  },

  /* True only when a native file picker is wired up via IPC. */
  get filePickerAvailable() {
    return !!(api?.pickVideoFile);
  },

  async pickVideoFile() {
    if (!api?.pickVideoFile) return null;
    try {
      return await api.pickVideoFile();
    } catch (err) {
      console.warn('[desktop-adapter] pickVideoFile failed:', err);
      return null;
    }
  },

  async pickOutputDir() {
    if (!api?.pickOutputDir) return null;
    try {
      return await api.pickOutputDir();
    } catch (err) {
      console.warn('[desktop-adapter] pickOutputDir failed:', err);
      return null;
    }
  },

  async getAppVersion() {
    if (!api?.getAppVersion) return null;
    try {
      return await api.getAppVersion();
    } catch {
      return null;
    }
  },

  onJobProgress(handler) {
    if (!api?.onJobProgress) return () => {};
    try {
      return api.onJobProgress(handler);
    } catch {
      return () => {};
    }
  },

  openExternal(url) {
    if (api?.openExternal) {
      try { api.openExternal(url); } catch { window.open(url, '_blank', 'noopener,noreferrer'); }
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  },
};
