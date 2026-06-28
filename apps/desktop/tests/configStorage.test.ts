import { afterEach, expect, test } from "bun:test";
import { loadInitialConfig, saveConfig, STORAGE_KEY } from "@/api";

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

function installBrowserFallback() {
  const storage = new MemoryStorage();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage,
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {},
  });
  return storage;
}

afterEach(() => {
  Reflect.deleteProperty(globalThis, "localStorage");
  Reflect.deleteProperty(globalThis, "window");
});

test("persists browser fallback connection config", async () => {
  const storage = installBrowserFallback();

  const saved = await saveConfig({
    serverUrl: "http://127.0.0.1:6877/",
    apiKey: "ntrp_test",
  });

  expect(saved).toEqual({ serverUrl: "http://127.0.0.1:6877", apiKey: "ntrp_test" });
  expect(storage.getItem(STORAGE_KEY)).toBe(JSON.stringify(saved));
  expect(await loadInitialConfig()).toEqual(saved);
});
