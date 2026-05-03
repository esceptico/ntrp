const { app, BrowserWindow, shell } = require("electron");
const path = require("node:path");

const isDev = Boolean(process.env.NTRP_DESKTOP_DEV_SERVER_URL);

function createWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 980,
    minHeight: 660,
    title: "ntrp",
    backgroundColor: "#0d0f10",
    titleBarStyle: "hiddenInset",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  if (isDev) {
    window.loadURL(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
  } else {
    window.loadFile(path.join(__dirname, "../dist/renderer/index.html"));
  }
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
