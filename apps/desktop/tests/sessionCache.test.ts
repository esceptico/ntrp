import { beforeEach, expect, test } from "bun:test";
import { loadHistory } from "../src/actions/history.ts";
import { switchSession } from "../src/actions/sessions.ts";
import { getState, setState, useStore } from "../src/store/index.ts";
import type { UiMessage } from "../src/store/index.ts";
import { createInitialSessionViewState } from "../src/store/session-view.ts";

function blank() {
  setState({
    sessionView: createInitialSessionViewState(),
    currentSessionId: null,
    messages: new Map(),
    order: [],
    historyLoadedFor: null,
    historyReloadingFor: null,
    historyHasMoreBefore: false,
    historyHasMoreAfter: false,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
    running: false,
    currentRunId: null,
    activeActivityId: null,
    sessionCache: new Map(),
    pendingApprovals: [],
    reviewingApprovalToolId: null,
    compacting: false,
    lastCompaction: null,
    sourceFocus: null,
    editingId: null,
    queuedMessages: [],
  });
}

function userMessage(id: string, content: string): UiMessage {
  return { id, role: "user", content };
}

beforeEach(blank);

test("switching sessions snapshots outgoing state into cache", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.setHistory([userMessage("a-1", "hello A")]);
  s.setCurrentRunId("run-A");
  s.setRunning(true);

  s.setCurrentSession("B");

  const cached = getState().sessionCache.get("A");
  expect(cached).toBeDefined();
  expect(cached!.order).toEqual(["a-1"]);
  expect(cached!.currentRunId).toBe("run-A");
  expect(cached!.running).toBe(true);
  expect(cached!.historyLoadedFor).toBe("A");
  expect(cached!.sessionView.historyLoadedFor).toBe("A");
});

test("switching back hydrates cached state", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.setHistory([userMessage("a-1", "hello A")]);

  s.setCurrentSession("B");
  // B is fresh and has no cache yet — global slots are blank.
  expect(getState().messages.size).toBe(0);
  expect(getState().historyLoadedFor).toBeNull();

  s.setCurrentSession("A");
  // Restored from cache: the preview comes back, but canonical history
  // still has to reload before live tail can open.
  expect(getState().messages.get("a-1")?.content).toBe("hello A");
  expect(getState().historyLoadedFor).toBeNull();
  expect(getState().sessionView.historyPhase).toBe("cached-preview");
  expect(getState().sessionView.canonicalHistoryRequired).toBe(true);
});

test("switchSession preserves cached preview until canonical history replaces it", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const requests: string[] = [];
  let resolveRequest: ((value: unknown) => void) | null = null;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: { path: string }) => {
          requests.push(request.path);
          return await new Promise((resolve) => {
            resolveRequest = resolve;
          });
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    const s = getState();
    s.setConfig({ serverUrl: "http://localhost:6877", apiKey: "" });
    s.setCurrentSession("A");
    s.setHistory([userMessage("a-1", "cached A")]);
    s.setRunning(true);
    s.setCurrentRunId("run-A");
    s.setCurrentSession("B");

    const switching = switchSession("A");

    expect(requests).toEqual(["/session/history?session_id=A"]);
    expect(getState().messages.get("a-1")?.content).toBe("cached A");
    expect(getState().running).toBe(true);
    expect(getState().currentRunId).toBe("run-A");
    expect(getState().historyLoadedFor).toBeNull();
    expect(getState().historyReloadingFor).toBe("A");
    expect(getState().sessionView.historyPhase).toBe("loading-history");

    resolveRequest?.({
      ok: true,
      status: 200,
      statusText: "OK",
      contentType: "application/json",
      data: {
        messages: [
          {
            id: "server-a-1",
            role: "user",
            content: "canonical A",
          },
        ],
        active_run_id: null,
      },
      text: "",
    });
    await switching;

    expect(getState().messages.get("server-a-1")?.content).toBe("canonical A");
    expect(getState().messages.has("a-1")).toBe(false);
    expect(getState().historyLoadedFor).toBe("A");
    expect(getState().historyReloadingFor).toBeNull();
    expect(getState().sessionView.canonicalHistoryRequired).toBe(false);
    expect(getState().running).toBe(false);
    expect(getState().currentRunId).toBeNull();
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("older replace history response cannot override newer response", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const requests: string[] = [];
  const resolvers: Array<(value: unknown) => void> = [];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: { path: string }) => {
          requests.push(request.path);
          return await new Promise((resolve) => {
            resolvers.push(resolve);
          });
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    const s = getState();
    s.setConfig({ serverUrl: "http://localhost:6877", apiKey: "" });
    s.setCurrentSession("A");

    const older = loadHistory("A");
    const newer = loadHistory("A");

    expect(requests).toEqual([
      "/session/history?session_id=A",
      "/session/history?session_id=A",
    ]);
    expect(getState().historyReloadingFor).toBe("A");

    resolvers[1]?.({
      ok: true,
      status: 200,
      statusText: "OK",
      contentType: "application/json",
      data: {
        messages: [
          {
            id: "server-a-new",
            role: "user",
            content: "new canonical A",
          },
        ],
        active_run_id: null,
      },
      text: "",
    });
    await newer;

    resolvers[0]?.({
      ok: true,
      status: 200,
      statusText: "OK",
      contentType: "application/json",
      data: {
        messages: [
          {
            id: "server-a-old",
            role: "user",
            content: "old canonical A",
          },
        ],
        active_run_id: "old-run",
      },
      text: "",
    });
    await older;

    expect(getState().messages.get("server-a-new")?.content).toBe("new canonical A");
    expect(getState().messages.has("server-a-old")).toBe(false);
    expect(getState().historyLoadedFor).toBe("A");
    expect(getState().historyReloadingFor).toBeNull();
    expect(getState().running).toBe(false);
    expect(getState().currentRunId).toBeNull();
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("re-selecting current session is a no-op for view state", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.appendMessage(userMessage("a-1", "live"));
  const liveMessages = getState().messages;

  s.setCurrentSession("A");
  // Same reference — no clobber from a stale cache snapshot.
  expect(getState().messages).toBe(liveMessages);
});

test("running state persists across switches", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.setRunning(true);
  s.setCurrentRunId("run-A");

  s.setCurrentSession("B");
  expect(getState().running).toBe(false);
  expect(getState().currentRunId).toBeNull();

  s.setCurrentSession("A");
  expect(getState().running).toBe(true);
  expect(getState().currentRunId).toBe("run-A");
});

test("queued messages persist across switches", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.addQueuedMessage({
    clientId: "cid-1",
    text: "follow-up",
    status: "pending",
    enqueuedAt: 0,
  });
  s.setCurrentSession("B");
  expect(getState().queuedMessages).toEqual([]);
  s.setCurrentSession("A");
  expect(getState().queuedMessages).toHaveLength(1);
  expect(getState().queuedMessages[0].clientId).toBe("cid-1");
});

test("history reload clears queued messages that are already persisted", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.addQueuedMessage({
    clientId: "cid-1",
    text: "follow-up",
    status: "pending",
    enqueuedAt: 0,
  });

  s.setHistory([userMessage("cid-1", "follow-up")]);

  expect(getState().queuedMessages).toEqual([]);
});

test("resetCancellingQueuedMessages flips cancelling back to pending", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.addQueuedMessage({ clientId: "cid-1", text: "a", status: "cancelling", enqueuedAt: 0 });
  s.addQueuedMessage({ clientId: "cid-2", text: "b", status: "pending", enqueuedAt: 0 });
  s.resetCancellingQueuedMessages();
  expect(getState().queuedMessages.map((q) => q.status)).toEqual(["pending", "pending"]);
});
