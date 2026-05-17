const { app, BrowserWindow, clipboard, globalShortcut, ipcMain, nativeTheme, safeStorage, screen, session, shell } = require("electron");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const { fileURLToPath } = require("node:url");

const isDev = Boolean(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
const configFileName = "config.json";

// App icon. macOS dev: dock picks up the PNG via app.dock.setIcon below
// (Electron's dock.setIcon is more reliable with a high-res PNG than an
// .icns). Windows/Linux dev: BrowserWindow `icon` is enough. In a
// packaged build the bundle's own icon (set by electron-builder) takes
// over.
const ICON_DIR = path.join(__dirname, "icons");
const ICON_PATH = process.platform === "win32"
  ? path.join(ICON_DIR, "icon.ico")
  : path.join(ICON_DIR, "icon.png");

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

function apiNetworkErrorResponse(error, request) {
  const cause = error && typeof error === "object" ? error.cause : null;
  const code = cause && typeof cause === "object" && "code" in cause ? cause.code : null;
  const suffix = code ? ` (${code})` : "";
  return {
    ok: false,
    status: 0,
    statusText: "Network Error",
    contentType: "text/plain",
    data: null,
    text: `Network error for ${request.method} ${request.path}${suffix}`,
  };
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
  } catch (error) {
    return apiNetworkErrorResponse(error, request);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

function eventStreamUrl(config, sessionId, afterSeq) {
  const params = new URLSearchParams({ stream: "true" });
  if (typeof afterSeq === "number" && Number.isFinite(afterSeq)) {
    params.set("after_seq", String(afterSeq));
  }
  return new URL(`/chat/events/${encodeURIComponent(sessionId)}?${params.toString()}`, config.serverUrl);
}

async function streamEvents(connectionId, webContents, configInput, sessionId, afterSeq, signal) {
  const config = normalizeConfig(configInput);
  try {
    const response = await fetch(eventStreamUrl(config, sessionId, afterSeq), {
      headers: apiHeaders(config),
      signal,
    });
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

let mainWindow = null;
let quickWindow = null;
/** Currently registered accelerator string, or null if none. Tracked so
 *  we can unregister cleanly before re-registering a new chord, and so
 *  duplicate-set calls become no-ops. */
let registeredShortcut = null;
/** Whether the quick-capture window was summoned with ntrp already in
 *  the foreground (i.e. the main window had focus). Drives the
 *  "dismiss" path: if we came in from another app, on Esc/blur we
 *  deactivate ntrp so focus returns to that app rather than popping
 *  the main window forward. */
let quickSummonedFromForeground = false;

const DEFAULT_QUICK_SHORTCUT = "CommandOrControl+Shift+Space";

/** Register the quick-capture global shortcut, replacing whatever was
 *  previously bound. Pass an empty string / nullish value to clear.
 *  Returns true on success (or successful clear), false if the OS
 *  refused the registration (another app owns the chord). */
function setQuickShortcut(accelerator) {
  const target = accelerator || "";
  // Idempotent: if the renderer pushes the same chord we already hold,
  // skip the unregister/register dance entirely. Avoids a momentary
  // window where the chord isn't bound at all.
  if (registeredShortcut === (target || null)) return true;
  if (registeredShortcut) {
    globalShortcut.unregister(registeredShortcut);
    registeredShortcut = null;
  }
  if (!target) {
    // eslint-disable-next-line no-console
    console.log("[ntrp] quick-capture shortcut: disabled");
    return true;
  }
  try {
    const ok = globalShortcut.register(target, showQuickWindow);
    if (ok) {
      registeredShortcut = target;
      // eslint-disable-next-line no-console
      console.log(`[ntrp] quick-capture shortcut: bound ${target}`);
      return true;
    }
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn(`[ntrp] quick-capture shortcut: bind threw for ${target}:`, error);
    return false;
  }
  // eslint-disable-next-line no-console
  console.warn(`[ntrp] quick-capture shortcut: OS refused ${target} (another app already owns it?)`);
  return false;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 980,
    minHeight: 660,
    title: "ntrp",
    icon: ICON_PATH,
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#100f0f" : "#ece9e0",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 18, y: 18 },
    vibrancy: "sidebar",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!isTrustedRendererUrl(url)) event.preventDefault();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  mainWindow.on("enter-full-screen", () => {
    mainWindow?.webContents.send("window:fullscreen-changed", true);
  });
  mainWindow.on("leave-full-screen", () => {
    mainWindow?.webContents.send("window:fullscreen-changed", false);
  });

  if (isDev) {
    mainWindow.loadURL(process.env.NTRP_DESKTOP_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(rendererIndexPath());
  }
}

/** Quick-capture window: a frameless, always-on-top floating composer
 *  summoned by the global shortcut. Loads the same renderer bundle but
 *  with the `#quick-capture` hash so main.tsx mounts QuickCapture
 *  instead of the full App. Hidden (not destroyed) on blur/submit so
 *  re-summoning is instant. */
function createQuickWindow() {
  if (quickWindow && !quickWindow.isDestroyed()) return quickWindow;

  quickWindow = new BrowserWindow({
    width: 620,
    height: 68,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    skipTaskbar: true,
    show: false,
    alwaysOnTop: true,
    fullscreenable: false,
    // No vibrancy here — combining it with `transparent: true` produced
    // a visible dark frame around the card on macOS (the vibrancy layer
    // showed through wherever the renderer was transparent). We want
    // the card itself to be the entire visible surface.
    hasShadow: false,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  // Floats across all spaces / above fullscreen apps on macOS. Without
  // this the window is invisible if the user is in a fullscreen Chrome
  // tab when they hit the shortcut.
  quickWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  quickWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });

  // Auto-hide on blur — Spotlight feel. User can re-summon with the
  // shortcut without paying the load cost since the window persists.
  // Routes through dismissQuickWindow so focus yields back to the
  // user's previous app instead of popping the main window forward.
  quickWindow.on("blur", () => {
    dismissQuickWindow();
  });

  quickWindow.on("closed", () => {
    quickWindow = null;
  });

  if (isDev) {
    const devUrl = process.env.NTRP_DESKTOP_DEV_SERVER_URL;
    quickWindow.loadURL(`${devUrl}#quick-capture`);
  } else {
    quickWindow.loadFile(rendererIndexPath(), { hash: "quick-capture" });
  }

  return quickWindow;
}

function showQuickWindow() {
  const win = createQuickWindow();
  if (win.isVisible()) {
    dismissQuickWindow();
    return;
  }
  // Snapshot the foreground state BEFORE we show our window — once we
  // call win.show() ntrp becomes the focused app and we lose that
  // signal. We compare focus identity rather than just BrowserWindow
  // presence: the main window might be open but unfocused (user was
  // in another app), which is the case where we want Esc to NOT pop
  // the main window forward.
  const focused = BrowserWindow.getFocusedWindow();
  quickSummonedFromForeground = focused === mainWindow && focused !== null;

  // Horizontally centered on the display that currently owns the
  // cursor; vertically biased toward the bottom of the work area so
  // the composer sits near where the user's reading attention is
  // (and out of the way of any top-of-screen menus / browser tabs).
  // ~78% from the top leaves enough margin below for the window's
  // shadow without crowding the dock.
  const cursorPoint = screen.getCursorScreenPoint();
  const display = screen.getDisplayNearestPoint(cursorPoint);
  const { x: dx, y: dy, width: dw, height: dh } = display.workArea;
  const [ww, wh] = win.getSize();
  const x = Math.round(dx + (dw - ww) / 2);
  const y = Math.round(dy + dh * 0.78 - wh);
  win.setPosition(x, y);
  win.show();
  win.focus();
}

/** Hide the quick window WITHOUT bringing the main window forward.
 *  Used for Esc/blur cancels — the user explicitly decided not to
 *  send anything, so we don't want ntrp to suddenly become the
 *  foreground app. On macOS, `app.hide()` yields focus to whatever
 *  the previous app was. We only invoke it when the quick window was
 *  summoned from outside ntrp; if the user was already in the main
 *  window, hiding the whole app would be jarring. */
function dismissQuickWindow() {
  if (!quickWindow || quickWindow.isDestroyed() || !quickWindow.isVisible()) return;
  quickWindow.hide();
  if (process.platform === "darwin" && !quickSummonedFromForeground) {
    // app.hide is the cleanest "give focus back" on macOS — there's no
    // way to deactivate without hiding ntrp's other windows. If the
    // main window was already hidden / minimized, this is a no-op for
    // it. If it happened to be visible in another space, it'll be
    // hidden too — that's the trade-off for proper focus restoration.
    app.hide();
  }
}

app.whenReady().then(() => {
  // macOS shows the bundle icon for packaged apps; in `electron .` dev
  // mode the dock would otherwise show the generic Electron icon.
  if (process.platform === "darwin" && app.dock) {
    app.dock.setIcon(ICON_PATH);
  }

  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });

  ipcMain.handle("app:reload", event => {
    assertTrustedSender(event);
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) win.reload();
  });
  ipcMain.handle("app:quit", event => {
    assertTrustedSender(event);
    app.quit();
  });
  ipcMain.handle("window:isFullScreen", event => {
    assertTrustedSender(event);
    const win = BrowserWindow.fromWebContents(event.sender);
    return win?.isFullScreen() ?? false;
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
  ipcMain.handle("events:connect", (event, config, sessionId, afterSeq) => {
    assertTrustedSender(event);
    const connectionId = crypto.randomUUID();
    const controller = new AbortController();
    eventStreams.set(connectionId, controller);
    void streamEvents(connectionId, event.sender, config, sessionId, afterSeq, controller.signal);
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
  ipcMain.handle("clipboard:write", (event, text) => {
    assertTrustedSender(event);
    if (typeof text !== "string") return false;
    clipboard.writeText(text);
    return true;
  });

  // Hide the floating composer (called from QuickCapture on Escape or
  // any explicit dismiss). Hiding rather than destroying keeps the next
  // summon snappy. Routed through dismissQuickWindow so focus yields
  // back to the user's previous app instead of popping ntrp forward.
  ipcMain.handle("quick:close", event => {
    assertTrustedSender(event);
    dismissQuickWindow();
  });

  // Submit a message from the quick-capture window. We forward it to the
  // main window over IPC so the renderer can call its existing
  // createSession + sendMessage actions (with the store, the SSE
  // subscription, etc. already wired). Side-effect: bring main window
  // forward so the user immediately sees the session that starts.
  ipcMain.handle("quick:submit", (event, message) => {
    assertTrustedSender(event);
    if (typeof message !== "string" || !message.trim()) return false;
    if (quickWindow && !quickWindow.isDestroyed()) quickWindow.hide();
    if (!mainWindow || mainWindow.isDestroyed()) {
      createWindow();
      // Defer the dispatch until the renderer has mounted and registered
      // its listener, otherwise the message gets sent into the void.
      mainWindow.webContents.once("did-finish-load", () => {
        mainWindow.webContents.send("quick:message", message);
      });
    } else {
      mainWindow.webContents.send("quick:message", message);
    }
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
    return true;
  });

  createWindow();

  // Allow the renderer to bind/unbind the global quick-capture chord.
  // Returns true on success so the Settings UI can surface "already in
  // use" errors without polling. The renderer is the source of truth
  // for the user's chosen accelerator (it lives in localStorage prefs);
  // we just hold the OS registration here.
  ipcMain.handle("quick:setShortcut", (event, accelerator) => {
    assertTrustedSender(event);
    if (accelerator != null && typeof accelerator !== "string") return false;
    return setQuickShortcut(accelerator);
  });

  // Start with the default chord so the shortcut works even before the
  // renderer mounts and pushes the user's preference. Renderer will
  // overwrite this on boot if they've customized it.
  if (!setQuickShortcut(DEFAULT_QUICK_SHORTCUT)) {
    // eslint-disable-next-line no-console
    console.warn(`[ntrp] failed to register default global shortcut ${DEFAULT_QUICK_SHORTCUT} — already in use?`);
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("will-quit", () => {
  // Release the global shortcut so other apps can claim it after we exit.
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

// In dev mode the parent script (scripts/dev.mjs) sends SIGTERM/SIGINT to
// kill the Electron child during reloads. Without an explicit handler, the
// process dies before Chromium flushes pending localStorage writes — so any
// settings the user just toggled are lost on the next launch. Routing the
// signal through `app.quit()` runs the proper shutdown sequence (graceful
// renderer teardown + storage flush) before exiting.
process.on("SIGTERM", () => app.quit());
process.on("SIGINT", () => app.quit());
