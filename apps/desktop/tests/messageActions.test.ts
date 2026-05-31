import { beforeEach, expect, test } from "bun:test";
import { enqueueMessage, stopRun } from "../src/actions/messages.ts";
import { getState, setState } from "../src/store/index.ts";

type CapturedRequest = { path: string; method: string; body?: string };

function mockBridge(requests: CapturedRequest[]) {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: CapturedRequest) => {
          requests.push(request);
          return { ok: true, contentType: "application/json", data: {} };
        },
      },
    },
    setTimeout,
    clearTimeout,
  };
  return () => {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  };
}

const SESSION_ROW = {
  session_id: "session-1",
  started_at: "2026-05-30T00:00:00Z",
  last_activity: "2026-05-30T00:00:00Z",
  name: "chan",
  message_count: 3,
  session_type: "channel" as const,
  active_run_id: "run-bg",
};

test("stopRun cancels a backgrounded/automation run by session even when currentRunId is null", async () => {
  const requests: CapturedRequest[] = [];
  const restore = mockBridge(requests);
  try {
    setState({
      config: { serverUrl: "http://x", apiKey: "" },
      currentSessionId: "session-1",
      currentRunId: null,
      running: true,
      sessions: [SESSION_ROW],
      activeRunSessionIds: new Set(["session-1"]),
      messages: new Map(),
      order: [],
    });

    await stopRun();

    expect(requests).toHaveLength(1);
    expect(requests[0].path).toBe("/cancel");
    const body = JSON.parse(requests[0].body ?? "{}");
    // Resolved from the session's active_run_id instead of no-op'ing on the
    // null currentRunId — this is the Stop-button fix.
    expect(body.run_id).toBe("run-bg");
  } finally {
    restore();
  }
});

test("stopRun falls back to session_id when no run id is known at all", async () => {
  const requests: CapturedRequest[] = [];
  const restore = mockBridge(requests);
  try {
    setState({
      config: { serverUrl: "http://x", apiKey: "" },
      currentSessionId: "session-1",
      currentRunId: null,
      running: true,
      sessions: [{ ...SESSION_ROW, active_run_id: null }],
      activeRunSessionIds: new Set(["session-1"]),
      messages: new Map(),
      order: [],
    });

    await stopRun();

    expect(requests).toHaveLength(1);
    const body = JSON.parse(requests[0].body ?? "{}");
    expect(body.session_id).toBe("session-1"); // server resolves the active run
    expect(body.run_id).toBeUndefined();
  } finally {
    restore();
  }
});

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
