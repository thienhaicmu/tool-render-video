const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  pickDirectory: async () => {
    try {
      const picked = await ipcRenderer.invoke('dialog:pickDirectory');
      return String(picked || '');
    } catch (_) {
      return '';
    }
  },
  openFolderPicker: async () => {
    try {
      const picked = await ipcRenderer.invoke('open-folder-picker');
      return picked || null;
    } catch (_) {
      return null;
    }
  },
  /* ── Source / output pickers (used by desktop-adapter.js) ── */
  pickVideoFile: async () => {
    try {
      const picked = await ipcRenderer.invoke('pick-video-file');
      return picked || null;
    } catch (_) {
      return null;
    }
  },
  pickOutputDir: async () => {
    try {
      const picked = await ipcRenderer.invoke('open-folder-picker');
      return picked || null;
    } catch (_) {
      return null;
    }
  },
  getAppVersion: async () => {
    try {
      return await ipcRenderer.invoke('app:getVersion');
    } catch (_) {
      return null;
    }
  },
  onJobProgress: (handler) => {
    try {
      const listener = (_event, data) => handler(data);
      ipcRenderer.on('job-progress', listener);
      return () => ipcRenderer.removeListener('job-progress', listener);
    } catch (_) {
      return () => {};
    }
  },
  pathExists: async (targetPath) => {
    try {
      return await ipcRenderer.invoke('path:exists', String(targetPath || ''));
    } catch (_) {
      return null;
    }
  },
  openPath: async (targetPath) => {
    try {
      return await ipcRenderer.invoke('shell:openPath', String(targetPath || ''));
    } catch (e) {
      return e?.message || String(e || 'Unable to open path');
    }
  },
  openBrowserProfile: async (opts) => {
    try {
      return await ipcRenderer.invoke('open-browser-profile', opts || {});
    } catch (e) {
      return { ok: false, error: e?.message || String(e || 'IPC error') };
    }
  },
  onBootStatus: (cb) => {
    ipcRenderer.on('boot-status', (_event, msg) => cb(msg));
  },
  onBootVersion: (cb) => {
    ipcRenderer.on('boot-version', (_event, ver) => cb(ver));
  },
});

