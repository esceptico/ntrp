const { app, BrowserWindow, ipcMain, nativeTheme, safeStorage, session, shell } = require("electron");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const { fileURLToPath } = require("node:url");

const isDev = Boolean(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
const configFileName = "config.json";

const defaultConfig = {
  serverUrl: "http://localhost:6877",
  apiKey: "",
};
const eventStreams = new Map();

function configPath() {
  return path.join(app.getPath("userData"), configFileName);
}

function rendererIndexPath() {
  return path.join(__dirname, "../dist/renderer/index.html");
}

function originOf(value) {
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

function isTrustedSender(event) {
  const frameUrl = event.senderFrame?.url ?? "";
  return isTrustedRendererUrl(frameUrl);
}

function isTrustedRendererUrl(frameUrl) {
  if (isDev) return originOf(frameUrl) === originOf(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
  if (!frameUrl.startsWith("file://")) return false;
  try {
    return path.normalize(fileURLToPath(frameUrl)) === path.normalize(rendererIndexPath());
  } catch {
    return false;
  }
}

function assertTrustedSender(event) {
  if (!isTrustedSender(event)) throw new Error("Untrusted IPC sender");
}

function normalizeConfig(input) {
  const serverUrl = typeof input?.serverUrl === "string" ? input.serverUrl.trim().replace(/\/$/, "") : "";
  return {
    serverUrl: serverUrl || defaultConfig.serverUrl,
    apiKey: typeof input?.apiKey === "string" ? input.apiKey.trim() : "",
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

function normalizeApiRequest(input) {
  const method = typeof input?.method === "string" ? input.method.toUpperCase() : "GET";
  const allowedMethods = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
  if (!allowedMethods.has(method)) throw new Error(`Unsupported API method: ${method}`);

  const requestPath = typeof input?.path === "string" ? input.path : "";
  if (!requestPath.startsWith("/") || requestPath.startsWith("//")) {
    throw new Error("API path must be relative to the configured server");
  }

  return {
    method,
    path: requestPath,
    body: typeof input?.body === "string" ? input.body : undefined,
    timeout: Number.isFinite(input?.timeout) ? Number(input.timeout) : 30_000,
  };
}

function apiHeaders(config, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (config.apiKey) headers.Authorization = `Bearer ${config.apiKey}`;
  return headers;
}

async function apiRequest(configInput, requestInput, signal) {
  const config = normalizeConfig(configInput);
  const request = normalizeApiRequest(requestInput);
  const controller = new AbortController();
  const timeoutId = request.timeout > 0 ? setTimeout(() => controller.abort(), request.timeout) : null;
  const signals = [controller.signal];
  if (signal) signals.push(signal);

  try {
    const response = await fetch(new URL(request.path, config.serverUrl), {
      method: request.method,
      headers: apiHeaders(config, request.body),
      body: request.body,
      signal: AbortSignal.any(signals),
    });
    const contentType = response.headers.get("content-type") ?? "";
    const text = await response.text();
    let data = null;
    if (contentType.includes("application/json") && text) {
      data = JSON.parse(text);
    }
    return {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
      contentType,
      data,
      text,
    };
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

async function streamEvents(connectionId, webContents, configInput, sessionId, signal) {
  const config = normalizeConfig(configInput);
  try {
    const response = await fetch(
      new URL(`/chat/events/${encodeURIComponent(sessionId)}?stream=true`, config.serverUrl),
      {
        headers: apiHeaders(config),
        signal,
      },
    );
    if (!response.ok || !response.body) {
      throw new Error(`event stream failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (!signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const event = JSON.parse(line.slice(6));
          if (!webContents.isDestroyed()) {
            webContents.send("events:data", { connectionId, event });
          }
        } catch {
          // Ignore non-JSON keepalive events.
        }
      }
    }
  } catch (error) {
    if (!signal.aborted && !webContents.isDestroyed()) {
      webContents.send("events:data", {
        connectionId,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  } finally {
    eventStreams.delete(connectionId);
  }
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 980,
    minHeight: 660,
    title: "ntrp",
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#100f0f" : "#ece9e0",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 18 },
    vibrancy: "sidebar",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  window.webContents.on("will-navigate", (event, url) => {
    if (!isTrustedRendererUrl(url)) event.preventDefault();
  });

  if (isDev) {
    window.loadURL(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
  } else {
    window.loadFile(rendererIndexPath());
  }
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });

  ipcMain.handle("config:get", event => {
    assertTrustedSender(event);
    return readConfig();
  });
  ipcMain.handle("config:set", (event, config) => {
    assertTrustedSender(event);
    return writeConfig(config);
  });
  ipcMain.handle("api:request", (event, config, request) => {
    assertTrustedSender(event);
    return apiRequest(config, request);
  });
  ipcMain.handle("events:connect", (event, config, sessionId) => {
    assertTrustedSender(event);
    const connectionId = crypto.randomUUID();
    const controller = new AbortController();
    eventStreams.set(connectionId, controller);
    void streamEvents(connectionId, event.sender, config, sessionId, controller.signal);
    return connectionId;
  });
  ipcMain.handle("events:disconnect", (event, connectionId) => {
    assertTrustedSender(event);
    eventStreams.get(connectionId)?.abort();
    eventStreams.delete(connectionId);
  });
  ipcMain.handle("shell:open-path", async (event, targetPath) => {
    assertTrustedSender(event);
    if (typeof targetPath !== "string" || targetPath.length === 0) return "Invalid path";
    // shell.openPath returns "" on success, an error string otherwise.
    return shell.openPath(targetPath);
  });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
