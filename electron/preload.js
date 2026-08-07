const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jutsuUI', {
  minimizeWindow: () => ipcRenderer.invoke('window-minimize'),
  toggleMaximizeWindow: () => ipcRenderer.invoke('window-toggle-maximize'),
  closeWindow: () => ipcRenderer.invoke('window-close'),
  isWindowMaximized: () => ipcRenderer.invoke('window-is-maximized'),
  pickSourceFile: () => ipcRenderer.invoke('pick-source-file'),
  pickFolder: (title) => ipcRenderer.invoke('pick-folder', title),
  pickVaultFile: () => ipcRenderer.invoke('pick-vault-file'),
  openPath: (targetPath) => ipcRenderer.invoke('open-path', targetPath),
  loadSettings: () => ipcRenderer.invoke('load-settings'),
  saveSettings: (settings) => ipcRenderer.invoke('save-settings', settings),
  checkJutsuAvailable: () => ipcRenderer.invoke('check-jutsu-available'),
  checkSetupStatus: () => ipcRenderer.invoke('check-setup-status'),
  runSetup: () => ipcRenderer.invoke('run-setup'),
  runJutsu: (options) => ipcRenderer.invoke('run-jutsu', options),
  runCompare: (options) => ipcRenderer.invoke('run-compare', options),
  cancelRun: () => ipcRenderer.invoke('cancel-run'),
  readProgress: (workdir) => ipcRenderer.invoke('read-progress', workdir),
  suggestMaxWorkers: () => ipcRenderer.invoke('suggest-max-workers'),
  onLog: (callback) => {
    const listener = (_event, chunk) => callback(chunk);
    ipcRenderer.on('jutsu-log', listener);
    return () => ipcRenderer.removeListener('jutsu-log', listener);
  },
  onSetupLog: (callback) => {
    const listener = (_event, chunk) => callback(chunk);
    ipcRenderer.on('setup-log', listener);
    return () => ipcRenderer.removeListener('setup-log', listener);
  },
});
