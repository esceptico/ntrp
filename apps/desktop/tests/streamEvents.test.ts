import { beforeEach, expect, test } from "bun:test";
import {
  eventStreamUrl,
  forgetEventSeqForSession,
  handleIncomingServerEvent,
  handleServerEvent,
  lastEventSeqForSession,
  resetEventSeqStateForTest,
  resetReplayGapReloadStateForTest,
  resetStreamStateForTest,
} from "../src/hooks/useEvents.js";
import { historyMessagesToUi, loadHistory, stopRun } from "../src/actions.js";
import { getState, setState } from "../src/store.js";

beforeEach(() => {
  resetStreamStateForTest();
  resetEventSeqStateForTest();
  resetReplayGapReloadStateForTest();
  setState({
    messages: new Map(),
    order: [],
    activeActivityId: null,
    running: false,
    currentRunId: null,
    currentSessionId: null,
    error: null,
  });
});

test("continues assistant content by message id without moving prior text below tools", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1" });
  handleServerEvent({ type: "TEXT_MESSAGE_START", message_id: "assistant-1" });
  handleServerEvent({ type: "TEXT_MESSAGE_CONTENT", message_id: "assistant-1", delta: "hello" });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-1",
    tool_call_name: "ReadFile",
    description: "read app",
  });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-1" });
  handleServerEvent({ type: "TEXT_MESSAGE_CONTENT", message_id: "assistant-1", delta: " world" });

  const state = getState();
  const assistantIds = state.order.filter((id) => state.messages.get(id)?.role === "assistant");
  const roles = state.order.map((id) => state.messages.get(id)?.role);

  expect(assistantIds).toEqual(["assistant-1"]);
  expect(state.messages.get("assistant-1")?.content).toBe("hello world");
  expect(roles).toEqual(["assistant", "activity"]);
});

test("ignores duplicate same-session replay events without duplicating text or tools", () => {
  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "run-1",
    session_id: "sequence-session-1",
    seq: 1,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_START",
    message_id: "assistant-seq-1",
    session_id: "sequence-session-1",
    seq: 2,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-seq-1",
    delta: "hello",
    session_id: "sequence-session-1",
    seq: 3,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-seq-1",
    delta: " duplicate",
    session_id: "sequence-session-1",
    seq: 3,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-seq-1",
    delta: " older",
    session_id: "sequence-session-1",
    seq: 2,
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-seq-1",
    tool_call_name: "ReadFile",
    session_id: "sequence-session-1",
    seq: 4,
  });
  handleServerEvent({
    type: "TOOL_CALL_END",
    tool_call_id: "tool-seq-1",
    session_id: "sequence-session-1",
    seq: 5,
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-seq-1",
    tool_call_name: "ReadFile",
    session_id: "sequence-session-1",
    seq: 4,
  });
  handleServerEvent({
    type: "TOOL_CALL_END",
    tool_call_id: "tool-seq-1",
    session_id: "sequence-session-1",
    seq: 5,
  });

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");

  expect(state.messages.get("assistant-seq-1")?.content).toBe("hello");
  expect(state.messages.get(activityId!)?.activity?.items.map((item) => item.id)).toEqual([
    "tool-seq-1",
  ]);
});

test("accepts higher sequence events for the same session", () => {
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-seq-2",
    delta: "first",
    session_id: "sequence-session-2",
    seq: 10,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-seq-2",
    delta: " second",
    session_id: "sequence-session-2",
    seq: 11,
  });

  expect(getState().messages.get("assistant-seq-2")?.content).toBe("first second");
});

test("accepts the same sequence number for a different session", () => {
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-session-a",
    delta: "A",
    session_id: "sequence-session-a",
    seq: 1,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-session-b",
    delta: "B",
    session_id: "sequence-session-b",
    seq: 1,
  });

  const state = getState();
  expect(state.messages.get("assistant-session-a")?.content).toBe("A");
  expect(state.messages.get("assistant-session-b")?.content).toBe("B");
});

test("resetStreamStateForTest keeps sequence tracking across reconnect-style resets", () => {
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-reset-seq",
    delta: "first",
    session_id: "sequence-reset-session",
    seq: 12,
  });

  resetStreamStateForTest();

  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-reset-seq",
    delta: " duplicate",
    session_id: "sequence-reset-session",
    seq: 12,
  });

  expect(getState().messages.get("assistant-reset-seq")?.content).toBe("first");
});

test("forgetEventSeqForSession lets a discarded projection replay the same sequenced event", () => {
  const event = {
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-forget-seq",
    delta: "restored",
    session_id: "sequence-forget-session",
    seq: 12,
  } as const;

  handleServerEvent(event);
  setState({ messages: new Map(), order: [], activeActivityId: null });
  forgetEventSeqForSession("sequence-forget-session");
  handleServerEvent(event);

  expect(getState().messages.get("assistant-forget-seq")?.content).toBe("restored");
});

test("event stream URL includes after_seq once a session sequence is known", () => {
  const config = { serverUrl: "http://localhost:6877", apiKey: "" };

  expect(eventStreamUrl(config, "url-session")).toBe(
    "http://localhost:6877/chat/events/url-session?stream=true",
  );

  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "run-url",
    session_id: "url-session",
    seq: 23,
  });

  expect(eventStreamUrl(config, "url-session")).toBe(
    "http://localhost:6877/chat/events/url-session?stream=true&after_seq=23",
  );
  expect(eventStreamUrl(config, "other-url-session")).toBe(
    "http://localhost:6877/chat/events/other-url-session?stream=true",
  );
});

test("loadHistory seeds event cursor from active stream checkpoint", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: {
            messages: [],
            active_run_id: "run-active",
            stream_checkpoint_seq: 44,
            page: { has_more_before: false, has_more_after: false },
          },
          text: "",
        }),
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "active-replay-session",
    });

    await loadHistory("active-replay-session");

    expect(lastEventSeqForSession("active-replay-session")).toBe(44);
    expect(eventStreamUrl(getState().config, "active-replay-session")).toBe(
      "http://localhost:6877/chat/events/active-replay-session?stream=true&after_seq=44",
    );
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("active history renders checkpointed tools as in-progress work", () => {
  const items = historyMessagesToUi(
    [
      {
        role: "user",
        content: "do work",
        id: "user-1",
        message_id: "user-1",
        seq: 1,
        created_at: "2026-05-08T12:00:00.000Z",
      },
      {
        role: "assistant",
        content: "",
        id: "assistant-1",
        message_id: "assistant-1",
        seq: 2,
        tool_calls: [{ id: "tool-1", name: "Research", arguments: "{}" }],
      },
    ],
    "run-active",
  );

  const user = items.find((item) => item.id === "user-1");
  const activity = items.find((item) => item.role === "activity");

  expect(user?.turn?.endedAt).toBeNull();
  expect(activity?.activity?.label).toBe("Calling");
  expect(activity?.activity?.done).toBe(false);
});

test("marks replayed assistant stream messages as static history", () => {
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-replay-1",
    delta: "already streamed",
    session_id: "replay-session",
    seq: 10,
    replay: true,
  });

  const message = getState().messages.get("assistant-replay-1");

  expect(message?.content).toBe("already streamed");
  expect(message?.sourceIndex).toBe(10);
  expect(message?.sourceMessageId).toBe("assistant-replay-1");
});

test("marks replayed activity messages as static history", () => {
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-replay-1",
    tool_call_name: "ReadFile",
    description: "read file",
    session_id: "replay-session",
    seq: 11,
    replay: true,
  });
  handleServerEvent({
    type: "TOOL_CALL_END",
    tool_call_id: "tool-replay-1",
    session_id: "replay-session",
    seq: 12,
    replay: true,
  });

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  const message = state.messages.get(activityId!);

  expect(message?.activity?.items.map((item) => item.id)).toEqual(["tool-replay-1"]);
  expect(message?.sourceIndex).toBe(12);
  expect(message?.sourceMessageId).toBe("tool-replay-1");
});

test("RUN_STARTED reopens a history turn that loaded as completed", () => {
  setState({
    messages: new Map([
      [
        "user-1",
        {
          id: "user-1",
          role: "user",
          content: "do work",
          turn: { startedAt: 1, endedAt: 2, durationMs: 1 },
        },
      ],
    ]),
    order: ["user-1"],
  });

  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1", seq: 1 });

  expect(getState().messages.get("user-1")?.turn?.endedAt).toBeNull();
  expect(getState().messages.get("user-1")?.turn?.durationMs).toBeNull();
});

test("exposes the last event sequence for bridge reconnects", () => {
  expect(lastEventSeqForSession("bridge-session")).toBeUndefined();

  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "run-bridge",
    session_id: "bridge-session",
    seq: 44,
  });

  expect(lastEventSeqForSession("bridge-session")).toBe(44);
});

test("stream_reset clears transient buffers and schedules one history reload", async () => {
  setState({ currentSessionId: "reset-session" });
  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "run-reset",
    session_id: "reset-session",
    seq: 1,
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-reset",
    tool_call_name: "ReadFile",
    session_id: "reset-session",
    seq: 2,
  });

  const resetEvent = {
    type: "stream_reset",
    reason: "replay_gap",
    session_id: "reset-session",
    seq: 3,
  } as const;

  let releaseReload!: () => void;
  const reloadGate = new Promise<void>((resolve) => {
    releaseReload = resolve;
  });
  const reloads: string[] = [];
  const firstReload = handleIncomingServerEvent(resetEvent, async (sessionId) => {
    reloads.push(sessionId);
    await reloadGate;
  });
  const secondReload = handleIncomingServerEvent(resetEvent, async (sessionId) => {
    reloads.push(sessionId);
  });

  const tailEvent = {
    type: "TOOL_CALL_END",
    tool_call_id: "tool-reset",
    session_id: "reset-session",
    seq: 4,
  } as const;
  const tailApply = handleIncomingServerEvent(tailEvent);

  expect(lastEventSeqForSession("reset-session")).toBeUndefined();
  expect(getState().activeActivityId).toBeNull();
  expect(getState().order).toEqual([]);
  expect(secondReload).toBeNull();

  releaseReload();
  await firstReload;
  await tailApply;

  expect(lastEventSeqForSession("reset-session")).toBe(4);
  expect(reloads).toEqual(["reset-session"]);
});

test("stream_reset drops queued tail events after session navigation", async () => {
  setState({ currentSessionId: "reset-session" });
  const resetEvent = {
    type: "stream_reset",
    reason: "replay_gap",
    session_id: "reset-session",
    seq: 3,
  } as const;

  let releaseReload!: () => void;
  const reloadGate = new Promise<void>((resolve) => {
    releaseReload = resolve;
  });
  const resetReload = handleIncomingServerEvent(resetEvent, async () => {
    await reloadGate;
  });
  const tailApply = handleIncomingServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "tail-message",
    delta: "tail",
    session_id: "reset-session",
    seq: 4,
  });

  setState({ currentSessionId: "other-session" });
  releaseReload();
  await resetReload;
  await tailApply;

  expect(lastEventSeqForSession("reset-session")).toBeUndefined();
  expect(getState().order).toEqual([]);
});

test("stream_reset keeps tail blocked when history reload fails", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  setState({ currentSessionId: "reset-session" });
  const resetEvent = {
    type: "stream_reset",
    reason: "replay_gap",
    session_id: "reset-session",
    seq: 3,
  } as const;

  const resetReload = handleIncomingServerEvent(resetEvent, async () => {
    throw new Error("reload failed");
  });
  const queuedTail = handleIncomingServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "tail-message",
    delta: "tail",
    session_id: "reset-session",
    seq: 4,
  });
  await resetReload;
  await queuedTail;
  handleIncomingServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "late-tail-message",
    delta: "late tail",
    session_id: "reset-session",
    seq: 5,
  });

  expect(lastEventSeqForSession("reset-session")).toBeUndefined();
  expect(getState().order).toEqual([]);
  expect(getState().error).toBe("reload failed");

  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: { messages: [], active_run_id: null },
          text: "",
        }),
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    await loadHistory("reset-session");
    handleIncomingServerEvent({
      type: "TEXT_MESSAGE_CONTENT",
      message_id: "recovered-message",
      delta: "recovered",
      session_id: "reset-session",
      seq: 5,
    });

    expect(lastEventSeqForSession("reset-session")).toBe(5);
    expect(getState().messages.get("recovered-message")?.content).toBe("recovered");
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("stopRun clears running state after successful cancel request", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const requests: Array<{ path: string; method: string; body?: string }> = [];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: { path: string; method: string; body?: string }) => {
          requests.push(request);
          return {
            ok: true,
            status: 202,
            statusText: "Accepted",
            contentType: "application/json",
            data: { status: "cancelling" },
            text: "",
          };
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      running: true,
      currentRunId: "run-1",
    });

    await stopRun();

    expect(requests).toEqual([
      { path: "/cancel", method: "POST", body: JSON.stringify({ run_id: "run-1" }) },
    ]);
    expect(getState().running).toBe(false);
    expect(getState().currentRunId).toBeNull();
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("stopRun clears running state when server no longer knows the run", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: false,
          status: 404,
          statusText: "Not Found",
          contentType: "application/json",
          data: { detail: "Run not found" },
          text: "",
        }),
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      running: true,
      currentRunId: "run-stale",
    });

    await stopRun();

    expect(getState().running).toBe(false);
    expect(getState().currentRunId).toBeNull();
    expect(getState().order).toEqual([]);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("stale run_cancelled does not clear a newer active run", () => {
  setState({ running: true, currentRunId: "run-new" });

  handleServerEvent({ type: "run_cancelled", run_id: "run-old", timestamp: 1 });

  expect(getState().running).toBe(true);
  expect(getState().currentRunId).toBe("run-new");
});

test("loadHistory restores currentRunId for active sessions", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: { messages: [], active_run_id: "active-run-1" },
          text: "",
        }),
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "active-session",
      running: false,
      currentRunId: null,
    });

    await loadHistory("active-session");

    expect(getState().running).toBe(true);
    expect(getState().currentRunId).toBe("active-run-1");
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("keeps tool results when result arrives before delayed burst item renders", async () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1", timestamp: 1 });
  handleServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-1", tool_call_name: "ReadFile", timestamp: 2 });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-1", timestamp: 3 });
  handleServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-2", tool_call_name: "ListFiles", timestamp: 4 });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-2", timestamp: 5 });
  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    tool_call_id: "tool-2",
    name: "ListFiles",
    content: "second result",
    preview: "second result",
    timestamp: 6,
  });

  await new Promise((resolve) => setTimeout(resolve, 80));

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  expect(activityId).toBeTruthy();
  const item = state.messages.get(activityId!)?.activity?.items.find((it) => it.id === "tool-2");
  expect(item?.result).toBe("second result");
});

test("merges duplicate buffered tool result patches before delayed render", async () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1", timestamp: 1 });
  handleServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-1", tool_call_name: "ReadFile", timestamp: 2 });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-1", timestamp: 3 });
  handleServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-2", tool_call_name: "ListFiles", timestamp: 4 });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-2", timestamp: 5 });
  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    tool_call_id: "tool-2",
    name: "ListFiles",
    content: "first result",
    preview: "first result",
    is_error: true,
    duration_ms: 25,
    timestamp: 6,
  });
  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    tool_call_id: "tool-2",
    name: "ListFiles",
    content: "second result",
    preview: "second result",
    timestamp: 7,
  });

  await new Promise((resolve) => setTimeout(resolve, 80));

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  expect(activityId).toBeTruthy();
  const item = state.messages.get(activityId!)?.activity?.items.find((it) => it.id === "tool-2");
  expect(item?.result).toBe("second result");
  expect(item?.error).toBe(true);
  expect(item?.durationMs).toBe(25);
});

test("updates an agent activity item from task lifecycle events", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1", timestamp: 1 });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "call-research",
    tool_call_name: "research",
    kind: "agent",
    description: "research(task='event systems')",
    timestamp: 2,
  });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "call-research", timestamp: 3 });
  handleServerEvent({
    type: "task_started",
    run_id: "run-1",
    task_id: "call-research",
    parent_tool_call_id: "call-research",
    name: "Research",
    summary: "event systems",
    depth: 1,
    timestamp: 4,
  });
  handleServerEvent({
    type: "task_finished",
    run_id: "run-1",
    task_id: "call-research",
    parent_tool_call_id: "call-research",
    status: "completed",
    summary: "done",
    depth: 1,
    timestamp: 5,
  });

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  const item = state.messages.get(activityId!)?.activity?.items.find((it) => it.id === "call-research");
  expect(item?.taskStatus).toBe("completed");
  expect(item?.progress).toBe("done");
});
