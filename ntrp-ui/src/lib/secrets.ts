import { secrets } from "bun";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

const SERVICE = "ntrp";
const SERVER_URL_KEY = "server-url";
const API_KEY_KEY = "api-key";

const SETTINGS_DIR = path.join(os.homedir(), ".ntrp");
const SETTINGS_FILE = path.join(SETTINGS_DIR, "settings.json");

export interface Credentials {
  serverUrl: string | null;
  apiKey: string | null;
}

async function isKeychainAvailable(): Promise<boolean> {
  if (process.env.NTRP_SKIP_KEYCHAIN === "1") return false;
  try {
    await secrets.get({ service: SERVICE, name: API_KEY_KEY });
    return true;
  } catch {
    return false;
  }
}

function readSettingsFile(): Record<string, unknown> {
  try {
    if (fs.existsSync(SETTINGS_FILE)) {
      const data = fs.readFileSync(SETTINGS_FILE, "utf-8");
      const parsed = JSON.parse(data);
      if (typeof parsed === "object" && parsed !== null) return parsed;
    }
  } catch {}
  return {};
}

function writeSettingsFile(settings: Record<string, unknown>): void {
  try {
    if (!fs.existsSync(SETTINGS_DIR)) {
      fs.mkdirSync(SETTINGS_DIR, { recursive: true });
    }
    fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2), { mode: 0o600 });
  } catch {}
}

function getFallbackCredentials(): Credentials {
  const settings = readSettingsFile();
  const connection = settings.connection as Record<string, string> | undefined;
  return {
    serverUrl: connection?.serverUrl ?? null,
    apiKey: connection?.apiKey ?? null,
  };
}

export async function getCredentials(): Promise<Credentials> {
  const keychain = await isKeychainAvailable();

  if (keychain) {
    // Migrate from settings file if needed
    const fallback = getFallbackCredentials();
    if (fallback.apiKey || fallback.serverUrl) {
      if (fallback.apiKey) {
        try { await secrets.set({ service: SERVICE, name: API_KEY_KEY, value: fallback.apiKey }); } catch {}
      }
      if (fallback.serverUrl) {
        try { await secrets.set({ service: SERVICE, name: SERVER_URL_KEY, value: fallback.serverUrl }); } catch {}
      }
      // Remove from settings file
      const settings = readSettingsFile();
      delete (settings as Record<string, unknown>).connection;
      writeSettingsFile(settings);
    }

    try {
      return {
        serverUrl: await secrets.get({ service: SERVICE, name: SERVER_URL_KEY }),
        apiKey: await secrets.get({ service: SERVICE, name: API_KEY_KEY }),
      };
    } catch {
      return getFallbackCredentials();
    }
  }

  return getFallbackCredentials();
}

export async function setCredentials(serverUrl: string, apiKey: string): Promise<void> {
  const keychain = await isKeychainAvailable();

  if (keychain) {
    try {
      await secrets.delete({ service: SERVICE, name: API_KEY_KEY }).catch(() => {});
      await secrets.set({ service: SERVICE, name: API_KEY_KEY, value: apiKey });
      await secrets.delete({ service: SERVICE, name: SERVER_URL_KEY }).catch(() => {});
      await secrets.set({ service: SERVICE, name: SERVER_URL_KEY, value: serverUrl });
      return;
    } catch {}
  }

  // Fallback: store in settings file
  const settings = readSettingsFile();
  settings.connection = { serverUrl, apiKey };
  writeSettingsFile(settings);
}

export async function deleteCredentials(): Promise<void> {
  const keychain = await isKeychainAvailable();

  if (keychain) {
    await secrets.delete({ service: SERVICE, name: API_KEY_KEY }).catch(() => {});
    await secrets.delete({ service: SERVICE, name: SERVER_URL_KEY }).catch(() => {});
  }

  const settings = readSettingsFile();
  delete (settings as Record<string, unknown>).connection;
  writeSettingsFile(settings);
}
