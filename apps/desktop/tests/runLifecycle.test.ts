import { expect, test } from "bun:test";
import type { State } from "../src/store/index.ts";
import {
  reduceApprovalRequested,
  reduceRunCompleted,
  reduceRunFailed,
  reduceRunStarted,
  reduceRunStatus,
} from "../src/store/run-lifecycle.ts";

function lifecycleState(overrides: Partial<State> = {}): State {
  return {
    currentSessionId: "session-1",
    running: false,
    currentRunId: null,
    activeRunSessionIds: new Set(),
    unreadDoneSessionIds: new Set(),
    pendingApprovals: [],
    reviewingApprovalToolId: null,
    queuedMessages: [],
    pendingResume: null,
    stoppingRunId: null,
    terminalRunIds: new Set(),
    ...overrides,
  } as State;
}

test("run start enters running state and tracks the active session", () => {
  const patch = reduceRunStarted(lifecycleState(), {
    runId: "run-1",
    sessionId: "session-1",
  });

  expect(patch.running).toBe(true);
  expect(patch.currentRunId).toBe("run-1");
  expect(patch.activeRunSessionIds?.has("session-1")).toBe(true);
});

test("terminal run cannot be resurrected by stale status poll", () => {
  const initial = lifecycleState({
    running: true,
    currentRunId: "run-1",
    activeRunSessionIds: new Set(["session-1"]),
  });
  const running = {
    ...initial,
    ...reduceRunCompleted(initial, { runId: "run-1", sessionId: "session-1" }),
  };

  const stale = {
    ...running,
    ...reduceRunStatus(running, {
      activeRuns: [{ runId: "run-1", sessionId: "session-1", status: "running" }],
    }),
  };

  expect(stale.running).toBe(false);
  expect(stale.currentRunId).toBeNull();
  expect(stale.activeRunSessionIds.has("session-1")).toBe(false);
});

test("terminal status poll clears the current run", () => {
  const running = lifecycleState({
    running: true,
    currentRunId: "run-1",
    activeRunSessionIds: new Set(["session-1"]),
  });

  const terminal = {
    ...running,
    ...reduceRunStatus(running, {
      activeRuns: [{ runId: "run-1", sessionId: "session-1", status: "completed" }],
    }),
  };

  expect(terminal.running).toBe(false);
  expect(terminal.currentRunId).toBeNull();
  expect(terminal.activeRunSessionIds.has("session-1")).toBe(false);
  expect(terminal.terminalRunIds.has("run-1")).toBe(true);

  const stale = {
    ...terminal,
    ...reduceRunStatus(terminal, {
      activeRuns: [{ runId: "run-1", sessionId: "session-1", status: "running" }],
    }),
  };

  expect(stale.running).toBe(false);
  expect(stale.currentRunId).toBeNull();
  expect(stale.activeRunSessionIds.has("session-1")).toBe(false);
});

test("missing current run in status poll clears known active run", () => {
  const running = lifecycleState({
    running: true,
    currentRunId: "run-1",
    activeRunSessionIds: new Set(["session-1"]),
  });

  const stale = {
    ...running,
    ...reduceRunStatus(running, { activeRuns: [] }),
  };

  expect(stale.running).toBe(false);
  expect(stale.currentRunId).toBeNull();
  expect(stale.activeRunSessionIds.has("session-1")).toBe(false);
});

test("empty status poll does not clear optimistic run before server run id", () => {
  const optimistic = lifecycleState({
    running: true,
    currentRunId: null,
    activeRunSessionIds: new Set(["session-1"]),
  });

  const state = {
    ...optimistic,
    ...reduceRunStatus(optimistic, { activeRuns: [] }),
  };

  expect(state.running).toBe(true);
  expect(state.currentRunId).toBeNull();
});

test("terminal status poll clears optimistic current run and cannot be resurrected", () => {
  const optimistic = lifecycleState({
    running: true,
    currentRunId: null,
    activeRunSessionIds: new Set(["session-1"]),
  });

  const terminal = {
    ...optimistic,
    ...reduceRunStatus(optimistic, {
      activeRuns: [{ runId: "run-1", sessionId: "session-1", status: "completed" }],
    }),
  };

  expect(terminal.running).toBe(false);
  expect(terminal.currentRunId).toBeNull();
  expect(terminal.activeRunSessionIds.has("session-1")).toBe(false);
  expect(terminal.terminalRunIds.has("run-1")).toBe(true);

  const staleStarted = {
    ...terminal,
    ...reduceRunStarted(terminal, { runId: "run-1", sessionId: "session-1" }),
  };

  expect(staleStarted.running).toBe(false);
  expect(staleStarted.currentRunId).toBeNull();
  expect(staleStarted.activeRunSessionIds.has("session-1")).toBe(false);
  expect(staleStarted.terminalRunIds.has("run-1")).toBe(true);
});

test("terminal current run clears queued composer messages", () => {
  const running = lifecycleState({
    running: true,
    currentRunId: "run-1",
    activeRunSessionIds: new Set(["session-1"]),
    queuedMessages: [
      {
        clientId: "queued-1",
        text: "use mcp",
        status: "pending",
        enqueuedAt: 1,
      },
    ],
  });

  const patch = reduceRunFailed(running, { runId: "run-1", sessionId: "session-1" });

  expect(patch.queuedMessages).toEqual([]);
});

test("stopping a stale run does not clear a newer active run", () => {
  const patch = reduceRunCompleted(
    lifecycleState({ running: true, currentRunId: "run-new" }),
    { runId: "run-old", sessionId: "session-1" },
  );

  expect(patch.running).toBeUndefined();
  expect(patch.currentRunId).toBeUndefined();
  expect(patch.terminalRunIds?.has("run-old")).toBe(true);
});

test("failed optimistic send from another session does not clear current run", () => {
  const state = lifecycleState({
    currentSessionId: "session-2",
    running: true,
    currentRunId: null,
    activeRunSessionIds: new Set(["session-1", "session-2"]),
  });

  const patch = reduceRunFailed(state, { runId: null, sessionId: "session-1" });

  expect(patch.running).toBeUndefined();
  expect(patch.currentRunId).toBeUndefined();
  expect(patch.activeRunSessionIds?.has("session-1")).toBe(false);
  expect(patch.activeRunSessionIds?.has("session-2")).toBe(true);
});

test("approval requests survive run status refresh", () => {
  const approved = {
    ...lifecycleState({ running: true, currentRunId: "run-1" }),
    ...reduceApprovalRequested(lifecycleState({ running: true, currentRunId: "run-1" }), {
      toolId: "tool-1",
      toolName: "Edit",
      status: "pending",
    }),
  };

  const patch = reduceRunStatus(approved, {
    activeRuns: [{ runId: "run-1", sessionId: "session-1", status: "running" }],
  });

  expect(patch.pendingApprovals).toBeUndefined();
});
