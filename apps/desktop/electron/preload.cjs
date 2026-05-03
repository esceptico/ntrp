const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ntrpDesktop", {
  version: () => process.versions.electron,
  config: {
    get: () => ipcRenderer.invoke("config:get"),
    set: config => ipcRenderer.invoke("config:set", config),
  },
  api: {
    request: (config, request) => ipcRenderer.invoke("api:request", config, request),
  },
  events: {
    connect: (config, sessionId) => ipcRenderer.invoke("events:connect", config, sessionId),
    disconnect: connectionId => ipcRenderer.invoke("events:disconnect", connectionId),
    onData: callback => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("events:data", listener);
      return () => ipcRenderer.off("events:data", listener);
    },
  },
});
