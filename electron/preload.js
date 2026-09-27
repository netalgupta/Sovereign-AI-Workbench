/** The only bridge between the setup/splash pages and the main process. */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('sovereign', {
  info: () => ipcRenderer.invoke('setup:info'),
  chooseDir: (current) => ipcRenderer.invoke('setup:chooseDir', current),
  freeBytes: (dir) => ipcRenderer.invoke('setup:freeBytes', dir),
  install: (dir) => ipcRenderer.invoke('setup:run', dir),
  launch: () => ipcRenderer.invoke('setup:launch'),
  recentLog: () => ipcRenderer.invoke('app:log'),
  openLogFolder: () => ipcRenderer.invoke('app:openLogFolder'),
  onProgress: (fn) => ipcRenderer.on('setup:progress', (_e, msg) => fn(msg)),
  onLog: (fn) => ipcRenderer.on('log', (_e, line) => fn(line)),
  onStatus: (fn) => ipcRenderer.on('status', (_e, text) => fn(text)),
  onFailed: (fn) => ipcRenderer.on('failed', (_e, info) => fn(info)),
})
