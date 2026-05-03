const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ntrpDesktop", {
  version: () => process.versions.electron,
  config: {
    get: () => ipcRenderer.invoke("config:get"),
    set: config => ipcRenderer.invoke("config:set", config),
  },
});
