import { afterEach, expect, test } from "bun:test";
import { compactSessionApi, getKnowledgeSummaryApi } from "../src/api.ts";
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

test("knowledge requests use the default API timeout", async () => {
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
            data: { surfaces: [], next_actions: [], policy_version: "test" },
            text: "",
          };
        },
      },
    },
  };

  await getKnowledgeSummaryApi({ serverUrl: "http://localhost:6877", apiKey: "" });

  expect(request).toEqual({
    path: "/knowledge/summary",
    method: "GET",
    body: undefined,
    timeout: 60_000,
  });
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
