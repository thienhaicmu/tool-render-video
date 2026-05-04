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
});

