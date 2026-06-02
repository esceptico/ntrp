import { afterEach, expect, test } from "bun:test";
import { apiWithConfig, compactSessionApi, listProjectsApi } from "../src/api.ts";
import { runBuiltinCommand } from "../src/actions/builtins.ts";
import { getState, setState } from "../src/store/index.ts";

const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;

afterEach(() => {
  (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
});

test("compactSessionApi uses an extended timeout", async () => {
  let request: { path: string; method?: string; body?: string; timeout?: number } | null = null;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, req: typeof request) => {
          request = req;
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: { status: "compacted" },
            text: "",
          };
        },
      },
    },
  };

  await compactSessionApi({ serverUrl: "http://localhost:6877", apiKey: "" }, "sess-1");

  expect(request).toEqual({
    path: "/compact",
    method: "POST",
    body: JSON.stringify({ session_id: "sess-1" }),
    timeout: 600_000,
  });
});

test("standard API calls use the default timeout", async () => {
  let request: { path: string; method?: string; body?: string; timeout?: number } | null = null;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, req: typeof request) => {
          request = req;
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: [],
            text: "",
          };
        },
      },
    },
  };

  await listProjectsApi({ serverUrl: "http://localhost:6877", apiKey: "" });

  expect(request).toEqual({
    path: "/projects",
    method: "GET",
    body: undefined,
    timeout: 60_000,
  });
});

test("desktop API bridge rejects when the renderer timeout elapses", async () => {
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => new Promise(() => {}),
      },
    },
  };

  let error: unknown = null;
  try {
    await apiWithConfig({ serverUrl: "http://localhost:6877", apiKey: "" }, "/slow", {
      timeout: 5,
    } as RequestInit & { timeout: number });
  } catch (e) {
    error = e;
  }

  expect(error).toBeInstanceOf(Error);
  expect((error as Error).message).toBe("Request timed out for GET /slow");
});

test("compact command does not reload or claim success when compaction is below threshold", async () => {
  const requests: string[] = [];
  setState({
    config: { serverUrl: "http://localhost:6877", apiKey: "" },
    currentSessionId: "sess-1",
    messages: new Map(),
    order: [],
  });
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, req: { path: string }) => {
          requests.push(req.path);
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: { status: "not_needed", message: "Context below compaction threshold" },
            text: "",
          };
        },
      },
    },
  };

  await runBuiltinCommand("compact", "");

  expect(requests).toEqual(["/compact"]);
  const notices = getState().order.map((id) => getState().messages.get(id)?.content);
  expect(notices).toContain("Context below compaction threshold");
  expect(notices).not.toContain("Context compacted.");
});
