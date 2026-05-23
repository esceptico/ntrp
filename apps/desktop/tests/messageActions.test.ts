import { beforeEach, expect, test } from "bun:test";
import { enqueueMessage } from "../src/actions/messages.ts";
import { getState, setState } from "../src/store/index.ts";

beforeEach(() => {
  setState({
    config: { serverUrl: "http://localhost:6877", apiKey: "" },
    currentSessionId: "session-1",
    messages: new Map(),
    order: [],
    running: false,
    currentRunId: null,
    activeRunSessionIds: new Set(),
    queuedMessages: [],
    pendingApprovals: [],
  });
});

test("enqueueMessage promotes stale queued submit when server starts a new run", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const requests: unknown[] = [];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: unknown) => {
          requests.push(request);
          return {
            ok: true,
            contentType: "application/json",
            data: { run_id: "run-new", session_id: "session-1" },
          };
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      running: true,
      currentRunId: "run-stale",
      activeRunSessionIds: new Set(["session-1"]),
    });

    await enqueueMessage("use mcp");

    const state = getState();
    expect(requests).toHaveLength(1);
    expect(state.queuedMessages).toEqual([]);
    expect(state.running).toBe(true);
    expect(state.currentRunId).toBe("run-new");
    expect(state.order).toHaveLength(1);
    expect(state.messages.get(state.order[0])?.role).toBe("user");
    expect(state.messages.get(state.order[0])?.content).toBe("use mcp");
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("enqueueMessage removes queue card when enqueue request fails", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => {
          throw new Error("request failed");
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      running: true,
      currentRunId: "run-1",
      activeRunSessionIds: new Set(["session-1"]),
    });

    await enqueueMessage("use mcp");

    const state = getState();
    expect(state.queuedMessages).toEqual([]);
    expect(state.order).toHaveLength(1);
    expect(state.messages.get(state.order[0])?.role).toBe("error");
    expect(state.messages.get(state.order[0])?.content).toBe("request failed");
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});
