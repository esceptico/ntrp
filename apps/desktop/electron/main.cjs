const { app, BrowserWindow, ipcMain, safeStorage, shell } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");

const isDev = Boolean(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
const configFileName = "config.json";

const defaultConfig = {
  serverUrl: "http://localhost:6877",
  apiKey: "",
};

function configPath() {
  return path.join(app.getPath("userData"), configFileName);
}

function normalizeConfig(input) {
  const serverUrl = typeof input?.serverUrl === "string" ? input.serverUrl.trim().replace(/\/$/, "") : "";
  return {
    serverUrl: serverUrl || defaultConfig.serverUrl,
    apiKey: typeof input?.apiKey === "string" ? input.apiKey : "",
  };
}

async function encryptSecret(value) {
  if (!value) return { encoding: "empty", value: "" };
  if (typeof safeStorage.encryptStringAsync === "function" && typeof safeStorage.isAsyncEncryptionAvailable === "function") {
    const available = await safeStorage.isAsyncEncryptionAvailable();
    if (available) {
      const encrypted = await safeStorage.encryptStringAsync(value);
      return { encoding: "safeStorage", value: encrypted.toString("base64") };
    }
  }
  if (safeStorage.isEncryptionAvailable()) {
    const encrypted = safeStorage.encryptString(value);
    return { encoding: "safeStorage", value: encrypted.toString("base64") };
  }
  return { encoding: "plain", value };
}

async function decryptSecret(secret) {
  if (!secret || secret.encoding === "empty") return "";
  if (secret.encoding === "plain") return typeof secret.value === "string" ? secret.value : "";
  if (secret.encoding !== "safeStorage" || typeof secret.value !== "string") return "";
  const encrypted = Buffer.from(secret.value, "base64");
  if (typeof safeStorage.decryptStringAsync === "function" && typeof safeStorage.isAsyncEncryptionAvailable === "function") {
    const available = await safeStorage.isAsyncEncryptionAvailable();
    if (available) return safeStorage.decryptStringAsync(encrypted);
  }
  if (safeStorage.isEncryptionAvailable()) return safeStorage.decryptString(encrypted);
  return "";
}

async function readConfig() {
  try {
    const raw = JSON.parse(await fs.readFile(configPath(), "utf8"));
    return normalizeConfig({
      serverUrl: raw.serverUrl,
      apiKey: await decryptSecret(raw.apiKey),
    });
  } catch {
    return defaultConfig;
  }
}

async function writeConfig(config) {
  const normalized = normalizeConfig(config);
  await fs.mkdir(path.dirname(configPath()), { recursive: true });
  await fs.writeFile(
    configPath(),
    JSON.stringify(
      {
        serverUrl: normalized.serverUrl,
        apiKey: await encryptSecret(normalized.apiKey),
      },
      null,
      2,
    ),
    "utf8",
  );
  return normalized;
}

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
  ipcMain.handle("config:get", () => readConfig());
  ipcMain.handle("config:set", (_event, config) => writeConfig(config));

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
