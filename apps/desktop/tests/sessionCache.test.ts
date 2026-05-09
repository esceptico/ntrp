import { beforeEach, expect, test } from "bun:test";
import { getState, setState, useStore } from "../src/store.js";
import type { UiMessage } from "../src/store.js";

function blank() {
  setState({
    currentSessionId: null,
    messages: new Map(),
    order: [],
    historyLoadedFor: null,
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
  s.appendMessage(userMessage("a-1", "hello A"));
  s.setCurrentRunId("run-A");
  s.setRunning(true);
  setState({ historyLoadedFor: "A" });

  s.setCurrentSession("B");

  const cached = getState().sessionCache.get("A");
  expect(cached).toBeDefined();
  expect(cached!.order).toEqual(["a-1"]);
  expect(cached!.currentRunId).toBe("run-A");
  expect(cached!.running).toBe(true);
  expect(cached!.historyLoadedFor).toBe("A");
});

test("switching back hydrates cached state", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.appendMessage(userMessage("a-1", "hello A"));
  setState({ historyLoadedFor: "A" });

  s.setCurrentSession("B");
  // B is fresh and has no cache yet — global slots are blank.
  expect(getState().messages.size).toBe(0);
  expect(getState().historyLoadedFor).toBeNull();

  s.setCurrentSession("A");
  // Restored from cache: messages and historyLoadedFor come back.
  expect(getState().messages.get("a-1")?.content).toBe("hello A");
  expect(getState().historyLoadedFor).toBe("A");
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

test("resetCancellingQueuedMessages flips cancelling back to pending", () => {
  const s = getState();
  s.setCurrentSession("A");
  s.addQueuedMessage({ clientId: "cid-1", text: "a", status: "cancelling", enqueuedAt: 0 });
  s.addQueuedMessage({ clientId: "cid-2", text: "b", status: "pending", enqueuedAt: 0 });
  s.resetCancellingQueuedMessages();
  expect(getState().queuedMessages.map((q) => q.status)).toEqual(["pending", "pending"]);
});
