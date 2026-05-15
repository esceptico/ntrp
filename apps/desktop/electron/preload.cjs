const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("ntrpDesktop", {
  version: () => process.versions.electron,
  app: {
    reload: () => ipcRenderer.invoke("app:reload"),
    quit: () => ipcRenderer.invoke("app:quit"),
  },
  config: {
    get: () => ipcRenderer.invoke("config:get"),
    set: config => ipcRenderer.invoke("config:set", config),
  },
  api: {
    request: (config, request) => ipcRenderer.invoke("api:request", config, request),
  },
  events: {
    connect: (config, sessionId, afterSeq) => ipcRenderer.invoke("events:connect", config, sessionId, afterSeq),
    disconnect: connectionId => ipcRenderer.invoke("events:disconnect", connectionId),
    onData: callback => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("events:data", listener);
      return () => ipcRenderer.off("events:data", listener);
    },
  },
  shell: {
    openPath: path => ipcRenderer.invoke("shell:open-path", path),
  },
  clipboard: {
    writeText: text => ipcRenderer.invoke("clipboard:write", text),
  },
  quickCapture: {
    submit: message => ipcRenderer.invoke("quick:submit", message),
    close: () => ipcRenderer.invoke("quick:close"),
    setShortcut: accelerator => ipcRenderer.invoke("quick:setShortcut", accelerator),
    onMessage: callback => {
      const listener = (_event, message) => callback(message);
      ipcRenderer.on("quick:message", listener);
      return () => ipcRenderer.off("quick:message", listener);
    },
  },
});
