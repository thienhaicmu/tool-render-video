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
});

