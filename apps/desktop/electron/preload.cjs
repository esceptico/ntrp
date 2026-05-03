const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("ntrpDesktop", {
  version: () => process.versions.electron,
});
