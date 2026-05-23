import { beforeEach, expect, test } from "bun:test";
import {
  eventStreamUrl,
  forgetEventSeqForSession,
  handleIncomingServerEvent,
  handleReplayServerEvent,
  handleServerEvent,
  lastEventSeqForSession,
  resetEventSeqStateForTest,
  resetReplayGapReloadStateForTest,
  resetStreamStateForTest,
} from "../src/hooks/useEvents.ts";
import { cancelSubagent, loadHistory, sendMessage, stopRun } from "../src/actions/index.ts";
import {
  isActiveBackgroundAgent,
  latestTodoListFromMessages,
  RIGHT_PANEL_BODY_WIDTH,
} from "../src/components/AgentRightSidebar.tsx";
import { visibleMessageIds } from "../src/lib/messageVisibility.ts";
import { getState, setState } from "../src/store/index.ts";
import { createBackgroundAgentsDomainState } from "../src/store/background-agent-domain.ts";
import type { HistoryMessage } from "../src/api.ts";

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
    skipApprovals: false,
    pendingApprovals: [],
    queuedMessages: [],
    backgroundAgents: createBackgroundAgentsDomainState(),
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
  expect(state.messages.get(state.order[1])?.activity?.items[0]?.target).toBe("read app");
});

test("live goal meta run shows subtle nudge marker", () => {
  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "goal-run-1",
    session_id: "session-1",
    is_meta_run: true,
    meta_client_id: "goal:goal-1:1",
  });

  const state = getState();
  expect(state.order).toEqual(["goal-nudge-goal-run-1", "meta-user-goal-run-1"]);
  expect(state.messages.get("goal-nudge-goal-run-1")?.role).toBe("status");
  expect(state.messages.get("goal-nudge-goal-run-1")?.content).toBe("Goal nudge");
  expect(state.messages.get("meta-user-goal-run-1")?.isMeta).toBe(true);
});

test("non-goal meta run stays visually hidden", () => {
  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "loop-run-1",
    session_id: "session-1",
    is_meta_run: true,
    meta_client_id: "loop:loop-1:1",
  });

  const state = getState();
  expect(state.order).toEqual(["meta-user-loop-run-1"]);
});

test("live tool target matches persisted history formatting without description", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-live-target", session_id: "target-session" });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-live-target",
    tool_call_name: "ReadFile",
  });
  handleServerEvent({
    type: "TOOL_CALL_ARGS",
    tool_call_id: "tool-live-target",
    delta: "{\"path\":\"a\"}",
  });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-live-target" });

  const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  expect(getState().messages.get(activityId!)?.activity?.items[0]?.target).toBe('ReadFile(path="a")');
});

test("todo update stays hidden in chat but available to sidebar", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-todos", session_id: "todo-session" });
  handleServerEvent({
    type: "todo_updated",
    run_id: "run-todos",
    tool_call_id: "call-todos",
    explanation: "Track rollout",
    items: [
      { content: "Research prior art", status: "completed" },
      { content: "Implement server tool", status: "in_progress" },
      { content: "Polish desktop UI", status: "pending" },
    ],
  });

  const state = getState();
  const message = state.messages.get("todo-run-todos");
  const visibleIds = visibleMessageIds({
    ids: state.order,
    roles: state.order.map((id) => state.messages.get(id)?.role ?? null),
    contents: state.order.map((id) => state.messages.get(id)?.content ?? ""),
  });
  const sidebarTodo = latestTodoListFromMessages(state.order, state.messages);

  expect(state.order).toEqual(["todo-run-todos"]);
  expect(visibleIds).toEqual([]);
  expect(message?.role).toBe("todo");
  expect(message?.todo?.explanation).toBe("Track rollout");
  expect(sidebarTodo?.items.map((item) => item.status)).toEqual([
    "completed",
    "in_progress",
    "pending",
  ]);
});

test("right sidebar derives the latest todo list from transcript state", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-todos-1", session_id: "todo-session" });
  handleServerEvent({
    type: "todo_updated",
    run_id: "run-todos-1",
    items: [{ content: "Old task", status: "completed" }],
  });
  handleServerEvent({ type: "RUN_FINISHED", run_id: "run-todos-1" });
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-todos-2", session_id: "todo-session" });
  handleServerEvent({
    type: "todo_updated",
    run_id: "run-todos-2",
    items: [{ content: "Current task", status: "in_progress" }],
  });

  const state = getState();
  const todo = latestTodoListFromMessages(state.order, state.messages);

  expect(todo?.items).toEqual([{ content: "Current task", status: "in_progress" }]);
});

test("right sidebar body is wider than the old 256px panel", () => {
  expect(RIGHT_PANEL_BODY_WIDTH).toBe(304);
});

test("update_todos tool stream stays out of activity trace", () => {
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "call-todos",
    tool_call_name: "update_todos",
  });
  handleServerEvent({
    type: "TOOL_CALL_ARGS",
    tool_call_id: "call-todos",
    delta: "{\"items\":[]}",
  });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "call-todos" });
  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    tool_call_id: "call-todos",
    name: "update_todos",
    content: "Todo list updated.",
  });

  expect(getState().order).toEqual([]);
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

test("replace loadHistory preserves event cursor for reconnect after canonical reload", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const config = { serverUrl: "http://localhost:6877", apiKey: "" };
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
    setState({ config, currentSessionId: "reload-session" });
    handleServerEvent({
      type: "TEXT_MESSAGE_CONTENT",
      message_id: "assistant-reload",
      delta: "accepted",
      session_id: "reload-session",
      seq: 31,
    });

    await loadHistory("reload-session");

    expect(lastEventSeqForSession("reload-session")).toBe(31);
    expect(eventStreamUrl(config, "reload-session")).toBe(
      "http://localhost:6877/chat/events/reload-session?stream=true&after_seq=31",
    );
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
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

test("rebuilds persisted transcript without replay animation marker", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const originalDocument = (globalThis as typeof globalThis & { document?: unknown }).document;
  const documentElement = { dataset: {} as Record<string, string> };
  (globalThis as typeof globalThis & { document?: unknown }).document = { documentElement };

  try {
    const messages: HistoryMessage[] = [
      { role: "user", content: "inspect", id: "user-1" },
      {
        role: "assistant",
        content: "checking",
        id: "assistant-1",
        tool_calls: [{ id: "tool-1", name: "ReadFile", arguments: "{\"path\":\"a\"}" }],
      },
      { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    ];

    (globalThis as typeof globalThis & { window?: unknown }).window = {
      ntrpDesktop: {
        api: {
          request: async () => ({
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: { messages, active_run_id: null },
            text: "",
          }),
        },
      },
      setTimeout,
      clearTimeout,
    };

    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "history-no-animation",
    });

    await loadHistory("history-no-animation");

    expect(documentElement.dataset.streamReplaying).toBeUndefined();
    expect(getState().order).toEqual(["user-1", "assistant-1", "assistant-1-activity"]);
    expect([...getState().messages.values()].every((message) => message.suppressEntryMotion)).toBe(true);
    expect(getState().messages.get("assistant-1-activity")?.activity?.items[0].result).toBe("ok");
    expect(getState().messages.get("assistant-1-activity")?.activity?.items[0].target).toBe('ReadFile(path="a")');
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
    (globalThis as typeof globalThis & { document?: unknown }).document = originalDocument;
  }
});

test("replay-created transcript messages suppress entry motion structurally", () => {
  setState({ currentSessionId: "session-1" });

  handleReplayServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-replay",
    delta: "replayed",
    session_id: "session-1",
    timestamp: 1,
  });
  handleReplayServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-replay",
    tool_call_name: "ReadFile",
    description: "ReadFile(path=\"a\")",
    session_id: "session-1",
    timestamp: 2,
  });

  const state = getState();
  expect(state.messages.get("assistant-replay")?.suppressEntryMotion).toBe(true);
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  expect(state.messages.get(activityId!)?.suppressEntryMotion).toBe(true);
});

test("live tool calls move from ongoing to executed on result", () => {
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-running",
    tool_call_name: "ReadFile",
    description: "ReadFile(path=\"a\")",
    timestamp: 1,
  });

  const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  expect(getState().messages.get(activityId!)?.activity?.items[0]?.status).toBe("ongoing");

  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    tool_call_id: "tool-running",
    name: "ReadFile",
    content: "ok",
    timestamp: 2,
  });

  expect(getState().messages.get(activityId!)?.activity?.items[0]?.status).toBe("executed");
});

test("active history hydrates old calls as executed and new tail as ongoing", async () => {
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
            messages: [
              { role: "user", content: "research", id: "user-1" },
              {
                role: "assistant",
                content: "",
                id: "assistant-old-tools",
                tool_calls: [
                  { id: "old-tool-1", name: "SlackSearch", arguments: "{}" },
                  { id: "old-tool-2", name: "SearchText", arguments: "{}" },
                ],
              },
            ],
            active_run_id: "run-active",
            runtime: {
              session_id: "active-trace-status-session",
              latest_event_seq: 10,
              checkpoint_seq: 10,
              active_run: { run_id: "run-active", status: "running" },
              pending_approvals: [],
              queued_messages: [],
            },
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
      currentSessionId: "active-trace-status-session",
    });

    await loadHistory("active-trace-status-session");
    const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
    expect(getState().messages.get(activityId!)?.activity?.items.map((item) => item.status)).toEqual([
      "executed",
      "executed",
    ]);

    handleServerEvent({
      type: "TOOL_CALL_START",
      session_id: "active-trace-status-session",
      seq: 11,
      tool_call_id: "live-tool",
      tool_call_name: "ReadFile",
      description: "ReadFile(path=\"b\")",
    });

    expect(getState().messages.get(activityId!)?.activity?.items.map((item) => item.status)).toEqual([
      "executed",
      "executed",
      "ongoing",
    ]);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("subagent compaction updates the agent row without global compaction UI", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1" });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "call-research",
    tool_call_name: "research",
    kind: "agent",
    description: "research(task='trace replay')",
  });

  handleServerEvent({
    type: "compaction_started",
    run_id: "run-1",
    scope: "agent",
    parent_tool_call_id: "call-research",
  });

  const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  const item = getState().messages.get(activityId!)?.activity?.items[0];
  expect(getState().compacting).toBe(false);
  expect(item?.progress).toBe("compacting");
  expect(item?.status).toBe("ongoing");

  handleServerEvent({
    type: "compaction_finished",
    run_id: "run-1",
    scope: "agent",
    parent_tool_call_id: "call-research",
    messages_before: 42,
    messages_after: 9,
  });

  const updated = getState().messages.get(activityId!)?.activity?.items[0];
  expect(getState().compacting).toBe(false);
  expect(updated?.progress).toBe("compacted 42 -> 9 messages");
});

test("subagent compaction buffers until the agent row exists", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1" });
  handleServerEvent({
    type: "compaction_started",
    run_id: "run-1",
    scope: "agent",
    parent_tool_call_id: "call-research",
  });

  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "call-research",
    tool_call_name: "research",
    kind: "agent",
    description: "research(task='trace replay')",
  });

  const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  const item = getState().messages.get(activityId!)?.activity?.items[0];
  expect(getState().compacting).toBe(false);
  expect(item?.progress).toBe("compacting");
  expect(item?.status).toBe("ongoing");
});

test("run compaction finish clears spinner without storing replayable toast state", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1" });
  handleServerEvent({ type: "compaction_started", run_id: "run-1" });

  expect(getState().compacting).toBe(true);

  handleServerEvent({
    type: "compaction_finished",
    run_id: "run-1",
    messages_before: 42,
    messages_after: 9,
  });

  expect(getState().compacting).toBe(false);
});

test("replayed run compaction does not toggle global compaction UI", () => {
  setState({ currentSessionId: "session-1", compacting: false });
  handleReplayServerEvent({
    type: "compaction_started",
    run_id: "run-1",
    session_id: "session-1",
  });
  expect(getState().compacting).toBe(false);

  setState({ compacting: true });
  handleReplayServerEvent({
    type: "compaction_finished",
    run_id: "run-1",
    session_id: "session-1",
    messages_before: 42,
    messages_after: 9,
  });
  expect(getState().compacting).toBe(true);
});

test("cancelled subagent lifecycle marks row executed", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1" });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "call-research",
    tool_call_name: "research",
    kind: "agent",
  });
  handleServerEvent({
    type: "task_finished",
    run_id: "run-1",
    task_id: "call-research",
    parent_tool_call_id: "call-research",
    status: "cancelled",
    summary: "partial summary ready",
  });

  const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  const item = getState().messages.get(activityId!)?.activity?.items[0];
  expect(item?.status).toBe("executed");
  expect(item?.taskStatus).toBe("cancelled");
  expect(item?.runId).toBe("run-1");
  expect(item?.progress).toBe("partial summary ready");
});

test("task lifecycle buffers only the canonical activity row id", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1" });
  handleServerEvent({
    type: "task_started",
    run_id: "run-1",
    task_id: "task-internal",
    parent_tool_call_id: "call-research",
    name: "Research Event Systems",
    summary: "event systems",
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "task-internal",
    tool_call_name: "ReadFile",
    description: "ReadFile(path=\"a\")",
  });

  let activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  let items = getState().messages.get(activityId!)?.activity?.items ?? [];
  expect(items.find((item) => item.id === "task-internal")?.taskStatus).toBeUndefined();

  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "call-research",
    tool_call_name: "research",
    kind: "agent",
    description: "research(task='event systems')",
  });

  activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  items = getState().messages.get(activityId!)?.activity?.items ?? [];
  const agent = items.find((item) => item.id === "call-research");
  expect(agent?.taskStatus).toBe("running");
  expect(agent?.displayName).toBe("Research Event Systems");
});

test("live deltas render during active stream", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-live", session_id: "session-live", timestamp: 1 });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    message_id: "assistant-live",
    delta: "live",
    session_id: "session-live",
    timestamp: 2,
  });

  expect(getState().running).toBe(true);
  expect(getState().messages.get("assistant-live")?.content).toBe("live");
});

test("tool lifecycle updates remain in call order", async () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-tools", session_id: "session-tools", timestamp: 1 });
  handleServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-1", tool_call_name: "ReadFile", timestamp: 2 });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-1", timestamp: 3 });
  handleServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-2", tool_call_name: "ListFiles", timestamp: 4 });
  handleServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-2", timestamp: 5 });
  handleServerEvent({
    type: "TOOL_CALL_RESULT",
    tool_call_id: "tool-1",
    name: "ReadFile",
    content: "first",
    timestamp: 6,
  });

  await new Promise((resolve) => setTimeout(resolve, 80));

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  const items = state.messages.get(activityId!)?.activity?.items ?? [];
  expect(items.map((item) => item.id)).toEqual(["tool-1", "tool-2"]);
  expect(items[0].result).toBe("first");
});

test("done terminal event finalizes running state once", () => {
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-done", session_id: "session-done", seq: 1, timestamp: 1 });
  handleServerEvent({
    type: "RUN_FINISHED",
    run_id: "run-done",
    session_id: "session-done",
    seq: 2,
    timestamp: 2,
    usage: { prompt: 3, completion: 4, cost: 0.01 },
    message_count: 5,
  });
  handleServerEvent({
    type: "RUN_FINISHED",
    run_id: "run-done",
    session_id: "session-done",
    seq: 2,
    timestamp: 3,
    usage: { prompt: 10, completion: 10, cost: 1 },
    message_count: 10,
  });

  const state = getState();
  expect(state.running).toBe(false);
  expect(state.currentRunId).toBeNull();
  expect(state.usage).toMatchObject({
    lastPrompt: 3,
    totalTokens: 7,
    totalCost: 0.01,
    messageCount: 5,
  });
});

test("usage totals include cached input tokens", () => {
  const before = getState().usage.totalTokens;
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-cache", session_id: "session-cache", seq: 10, timestamp: 10 });
  handleServerEvent({
    type: "RUN_FINISHED",
    run_id: "run-cache",
    session_id: "session-cache",
    seq: 11,
    timestamp: 11,
    usage: { prompt: 3, completion: 4, cache_read: 5, cache_write: 6, cost: 0.01 },
    message_count: 2,
  });

  expect(getState().usage.totalTokens).toBe(before + 18);
  expect(getState().usage.lastPrompt).toBe(14);
});

test("live token usage updates context pressure without adding final totals", () => {
  const before = getState().usage.totalTokens;
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-live-usage", session_id: "session-live-usage", seq: 20, timestamp: 20 });
  handleServerEvent({
    type: "token_usage",
    run_id: "run-live-usage",
    session_id: "session-live-usage",
    seq: 21,
    timestamp: 21,
    usage: { prompt: 7, completion: 2, total: 14, cache_read: 3, cache_write: 2 },
    cost: 0.02,
    message_count: 9,
  });

  expect(getState().usage.lastPrompt).toBe(12);
  expect(getState().usage.messageCount).toBe(9);
  expect(getState().usage.totalTokens).toBe(before);
});

test("tool token usage updates live totals without changing context pressure", () => {
  const before = getState().usage.totalTokens;
  const costBefore = getState().usage.totalCost;
  const promptBefore = getState().usage.lastPrompt;
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-tool-usage", session_id: "session-tool-usage", seq: 24, timestamp: 24 });
  handleServerEvent({
    type: "token_usage",
    run_id: "run-tool-usage",
    session_id: "session-tool-usage",
    seq: 25,
    timestamp: 25,
    usage: { prompt: 7, completion: 2, total: 12, cache_read: 3, cache_write: 0 },
    cost: 0.02,
    scope: "tool",
  });

  expect(getState().usage.lastPrompt).toBe(promptBefore);
  expect(getState().usage.totalTokens).toBe(before + 12);
  expect(getState().usage.totalCost).toBe(costBefore + 0.02);
});

test("final cumulative usage does not overwrite context pressure", () => {
  const before = getState().usage.totalTokens;
  handleServerEvent({ type: "RUN_STARTED", run_id: "run-final-pressure", session_id: "session-final-pressure", seq: 30, timestamp: 30 });
  handleServerEvent({
    type: "token_usage",
    run_id: "run-final-pressure",
    session_id: "session-final-pressure",
    seq: 31,
    timestamp: 31,
    usage: { prompt: 100, completion: 10, total: 110 },
    message_count: 7,
  });
  handleServerEvent({
    type: "RUN_FINISHED",
    run_id: "run-final-pressure",
    session_id: "session-final-pressure",
    seq: 32,
    timestamp: 32,
    usage: { prompt: 5000, completion: 100, total: 5100, cost: 0.5 },
    context_input_tokens: 100,
    message_count: 7,
  });

  expect(getState().usage.lastPrompt).toBe(100);
  expect(getState().usage.messageCount).toBe(7);
  expect(getState().usage.totalTokens).toBe(before + 5100);
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

  expect(lastEventSeqForSession("reset-session")).toBe(3);
  expect(getState().activeActivityId).toBeNull();
  expect(getState().order).toEqual([]);
  expect(secondReload).toBeNull();

  releaseReload();
  await firstReload;
  await tailApply;

  expect(lastEventSeqForSession("reset-session")).toBe(4);
  expect(reloads).toEqual(["reset-session"]);
});

test("slow-consumer stream_reset schedules history reload", async () => {
  setState({ currentSessionId: "slow-reset-session" });
  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "run-slow-reset",
    session_id: "slow-reset-session",
    seq: 1,
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-slow-reset",
    tool_call_name: "ReadFile",
    session_id: "slow-reset-session",
    seq: 2,
  });

  const reloads: string[] = [];
  const resetReload = handleIncomingServerEvent(
    {
      type: "stream_reset",
      reason: "slow_consumer",
      session_id: "slow-reset-session",
      seq: 9,
    },
    async (sessionId) => {
      reloads.push(sessionId);
    },
  );
  await resetReload;

  expect(lastEventSeqForSession("slow-reset-session")).toBe(9);
  expect(getState().activeActivityId).toBeNull();
  expect(getState().order).toEqual([]);
  expect(reloads).toEqual(["slow-reset-session"]);
});

test("stream_reset can rewind an impossible future cursor", async () => {
  setState({ currentSessionId: "reset-future-session" });
  handleServerEvent({
    type: "thinking",
    status: "future",
    session_id: "reset-future-session",
    seq: 44,
  });

  const reload = handleIncomingServerEvent(
    {
      type: "stream_reset",
      reason: "replay_gap",
      session_id: "reset-future-session",
      seq: 1,
    },
    async () => undefined,
  );
  await reload;

  expect(lastEventSeqForSession("reset-future-session")).toBe(1);
});

test("stream_reset clears visible transient activity from the old projection", async () => {
  setState({ currentSessionId: "reset-delayed-session" });
  handleServerEvent({
    type: "RUN_STARTED",
    run_id: "run-reset-delayed",
    session_id: "reset-delayed-session",
    seq: 1,
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-immediate",
    tool_call_name: "ReadFile",
    session_id: "reset-delayed-session",
    seq: 2,
  });
  handleServerEvent({
    type: "TOOL_CALL_END",
    tool_call_id: "tool-immediate",
    session_id: "reset-delayed-session",
    seq: 3,
  });
  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-delayed",
    tool_call_name: "ListFiles",
    session_id: "reset-delayed-session",
    seq: 4,
  });
  handleServerEvent({
    type: "TOOL_CALL_END",
    tool_call_id: "tool-delayed",
    session_id: "reset-delayed-session",
    seq: 5,
  });

  const activityId = getState().activeActivityId;
  expect(activityId).toBeTruthy();

  const resetReload = handleIncomingServerEvent(
    {
      type: "stream_reset",
      reason: "replay_gap",
      session_id: "reset-delayed-session",
      seq: 6,
    },
    async () => undefined,
  );
  await resetReload;
  await new Promise((resolve) => setTimeout(resolve, 80));

  const items = getState().messages.get(activityId!)?.activity?.items ?? [];
  expect(items.map((item) => item.id)).toEqual([]);
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

  expect(lastEventSeqForSession("reset-session")).toBe(3);
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

  expect(lastEventSeqForSession("reset-session")).toBe(3);
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

test("stream_reset keeps persisted history activity when history reload fails", async () => {
  setState({ currentSessionId: "reset-history-session" });
  const s = getState();
  s.setHistory([
    {
      id: "assistant-history-activity",
      role: "activity",
      sourceMessageId: "assistant-history",
      content: "",
      activity: {
        label: "Calling",
        done: false,
        items: [{ id: "history-tool", kind: "Bash", target: "Bash(command='date')" }],
      },
    },
  ]);
  s.setActiveActivityId("assistant-history-activity");

  const resetReload = handleIncomingServerEvent(
    {
      type: "stream_reset",
      reason: "replay_gap",
      session_id: "reset-history-session",
      seq: 3,
    },
    async () => {
      throw new Error("reload failed");
    },
  );
  await resetReload;

  expect(getState().order).toEqual(["assistant-history-activity"]);
  expect(getState().messages.get("assistant-history-activity")?.activity?.items).toMatchObject([
    { id: "history-tool" },
  ]);
  expect(getState().activeActivityId).toBeNull();
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
      { path: "/cancel", method: "POST", body: JSON.stringify({ run_id: "run-1" }), timeout: 60_000 },
    ]);
    expect(getState().running).toBe(false);
    expect(getState().currentRunId).toBeNull();
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("stopRun clears stopped session after switching sessions during cancel", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  let resolveCancel!: () => void;
  const cancelAccepted = new Promise<void>((resolve) => {
    resolveCancel = resolve;
  });
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => {
          await cancelAccepted;
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
      currentSessionId: "session-1",
      running: true,
      currentRunId: "run-1",
      activeRunSessionIds: new Set(["session-1", "session-2"]),
    });

    const stopPromise = stopRun();
    setState({
      currentSessionId: "session-2",
      running: true,
      currentRunId: "run-2",
    });
    resolveCancel();
    await stopPromise;

    expect(getState().running).toBe(true);
    expect(getState().currentRunId).toBe("run-2");
    expect(getState().activeRunSessionIds.has("session-1")).toBe(false);
    expect(getState().activeRunSessionIds.has("session-2")).toBe(true);
    expect(getState().terminalRunIds.has("run-1")).toBe(true);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("cancelSubagent failure after session switch does not mutate current session", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  let rejectCancel!: () => void;
  const cancelFailed = new Promise<never>((_resolve, reject) => {
    rejectCancel = () => reject(new Error("cancel failed"));
  });
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => cancelFailed,
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: null,
      sessionCache: new Map(),
      messages: new Map(),
      order: [],
    });
    const s = getState();
    s.setCurrentSession("session-old");
    setState({
      messages: new Map([
        [
          "activity-old",
          {
            id: "activity-old",
            role: "activity",
            content: "",
            activity: {
              label: "Calling",
              done: false,
              items: [
                {
                  id: "call-research",
                  kind: "research",
                  semanticKind: "agent",
                  target: "research",
                  runId: "run-1",
                  taskStatus: "running",
                  status: "ongoing",
                  progress: "running",
                },
              ],
            },
          },
        ],
      ]),
      order: ["activity-old"],
    });

    const cancelPromise = cancelSubagent("run-1", "call-research");
    expect(getState().messages.get("activity-old")?.activity?.items[0]?.progress).toBe("cancelling");
    s.setCurrentSession("session-new");
    getState().appendMessage({ id: "new-message", role: "assistant", content: "new" });
    rejectCancel();
    await cancelPromise;

    expect(getState().currentSessionId).toBe("session-new");
    expect(getState().order).toEqual(["new-message"]);
    expect([...getState().messages.values()].some((message) => message.role === "error")).toBe(false);
    const cachedItem = getState()
      .sessionCache.get("session-old")
      ?.messages.get("activity-old")
      ?.activity?.items[0];
    expect(cachedItem?.progress).toBe("running");
    expect(cachedItem?.cancelRequested).toBe(false);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("old-session send failure does not clear newer optimistic run", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  let rejectSend!: () => void;
  const sendFailed = new Promise<never>((_resolve, reject) => {
    rejectSend = () => reject(new Error("send failed"));
  });
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => sendFailed,
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "session-old",
      running: false,
      currentRunId: null,
      activeRunSessionIds: new Set(),
      messages: new Map(),
      order: [],
    });

    const sendPromise = sendMessage("old session send");
    getState().setCurrentSession("session-new");
    setState({
      currentSessionId: "session-new",
      running: true,
      currentRunId: null,
      activeRunSessionIds: new Set(["session-old", "session-new"]),
      messages: new Map([["new-message", { id: "new-message", role: "assistant", content: "new" }]]),
      order: ["new-message"],
    });
    rejectSend();
    await sendPromise;

    expect(getState().currentSessionId).toBe("session-new");
    expect(getState().running).toBe(true);
    expect(getState().currentRunId).toBeNull();
    expect(getState().activeRunSessionIds.has("session-old")).toBe(false);
    expect(getState().activeRunSessionIds.has("session-new")).toBe(true);
    expect(getState().order).toEqual(["new-message"]);
    expect(getState().messages.get("new-message")?.content).toBe("new");
    expect([...getState().messages.values()].some((message) => message.role === "error")).toBe(false);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("stopRun failure after session switch clears cached old-session stopping state", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  let rejectCancel!: () => void;
  const cancelFailed = new Promise<never>((_resolve, reject) => {
    rejectCancel = () => reject(new Error("cancel failed"));
  });
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => cancelFailed,
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: null,
      sessionCache: new Map(),
      running: false,
      currentRunId: null,
      stoppingRunId: null,
      messages: new Map(),
      order: [],
    });
    const s = getState();
    s.setCurrentSession("session-old");
    setState({
      running: true,
      currentRunId: "run-old",
      messages: new Map([["old-message", { id: "old-message", role: "assistant", content: "old" }]]),
      order: ["old-message"],
    });

    const stopPromise = stopRun();
    expect(getState().stoppingRunId).toBe("run-old");
    s.setCurrentSession("session-new");
    getState().appendMessage({ id: "new-message", role: "assistant", content: "new" });
    expect(getState().sessionCache.get("session-old")?.stoppingRunId).toBe("run-old");

    rejectCancel();
    await stopPromise;

    expect(getState().currentSessionId).toBe("session-new");
    expect(getState().stoppingRunId).toBeNull();
    expect(getState().order).toEqual(["new-message"]);
    expect(getState().messages.get("new-message")?.content).toBe("new");
    expect([...getState().messages.values()].some((message) => message.role === "error")).toBe(false);
    expect(getState().sessionCache.get("session-old")?.stoppingRunId).toBeNull();

    s.setCurrentSession("session-old");
    expect(getState().stoppingRunId).toBeNull();
    expect(getState().order).toEqual(["old-message"]);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("old-session edit revert failure does not mutate newer transcript", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  let rejectRevert!: () => void;
  const revertFailed = new Promise<never>((_resolve, reject) => {
    rejectRevert = () => reject(new Error("revert failed"));
  });
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => revertFailed,
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "session-old",
      editingId: "edit-old",
      messages: new Map([["edit-old", { id: "edit-old", role: "user", content: "old" }]]),
      order: ["edit-old"],
    });

    const sendPromise = sendMessage("edited old message");
    getState().setCurrentSession("session-new");
    setState({
      currentSessionId: "session-new",
      messages: new Map([["new-message", { id: "new-message", role: "assistant", content: "new" }]]),
      order: ["new-message"],
      editingId: null,
    });
    rejectRevert();
    await sendPromise;

    expect(getState().currentSessionId).toBe("session-new");
    expect(getState().order).toEqual(["new-message"]);
    expect(getState().messages.get("new-message")?.content).toBe("new");
    expect([...getState().messages.values()].some((message) => message.role === "error")).toBe(false);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("old-session edit revert success does not mutate newer transcript or post edit", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  let resolveRevert!: () => void;
  const revertSucceeded = new Promise((resolve) => {
    resolveRevert = () =>
      resolve({
        ok: true,
        status: 200,
        statusText: "OK",
        contentType: "application/json",
        data: {},
        text: "",
      });
  });
  let chatPostCount = 0;
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: { path: string }) => {
          if (request.path === "/session/revert") return revertSucceeded;
          if (request.path === "/chat/message") {
            chatPostCount += 1;
            return {
              ok: true,
              status: 200,
              statusText: "OK",
              contentType: "application/json",
              data: { run_id: "run-old" },
              text: "",
            };
          }
          throw new Error(`Unexpected path ${request.path}`);
        },
      },
    },
    setTimeout,
    clearTimeout,
  };

  try {
    setState({
      config: { serverUrl: "http://localhost:6877", apiKey: "" },
      currentSessionId: "session-old",
      editingId: "edit-old",
      messages: new Map([["edit-old", { id: "edit-old", role: "user", content: "old" }]]),
      order: ["edit-old"],
    });

    const sendPromise = sendMessage("edited old message");
    getState().setCurrentSession("session-new");
    setState({
      currentSessionId: "session-new",
      messages: new Map([["new-message", { id: "new-message", role: "assistant", content: "new" }]]),
      order: ["new-message"],
      editingId: null,
    });
    resolveRevert();
    await sendPromise;

    expect(getState().currentSessionId).toBe("session-new");
    expect(getState().order).toEqual(["new-message"]);
    expect(getState().messages.get("new-message")?.content).toBe("new");
    expect(chatPostCount).toBe(0);
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

test("run_cancelled resends pending queued messages through stream callback", () => {
  const resent: Array<{ text: string; images: unknown[] }> = [];
  setState({
    running: true,
    currentRunId: "run-cancel",
    queuedMessages: [
      {
        clientId: "queued-1",
        text: "retry one",
        images: [{ type: "input_image", image_url: "data:image/png;base64,a" }],
        status: "pending",
        enqueuedAt: 1,
      },
      {
        clientId: "queued-2",
        text: "skip failed",
        status: "failed",
        enqueuedAt: 2,
      },
    ],
  });

  handleIncomingServerEvent(
    { type: "run_cancelled", run_id: "run-cancel", timestamp: 3 },
    undefined,
    {
      resendQueuedMessage: (text, images) => {
        resent.push({ text, images: images ?? [] });
      },
    },
  );

  expect(resent).toEqual([
    {
      text: "retry one",
      images: [{ type: "input_image", image_url: "data:image/png;base64,a" }],
    },
  ]);
  expect(getState().queuedMessages).toEqual([]);
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

test("loadHistory reapplies local Auto to active runtime and hides stale approvals", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const requests: { path: string; method?: string; body?: string }[] = [];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (_config: unknown, request: { path: string; method?: string; body?: string }) => {
          requests.push(request);
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: request.path.startsWith("/session/history")
              ? {
                  messages: [],
                  active_run_id: "run-auto",
                  runtime: {
                    session_id: "auto-session",
                    latest_event_seq: 7,
                    checkpoint_seq: 7,
                    active_run: { run_id: "run-auto", status: "running" },
                    pending_approvals: [
                      {
                        tool_id: "tool-1",
                        tool_name: "Bash",
                        preview: "date",
                        diff: null,
                        status: "pending",
                      },
                    ],
                    queued_messages: [],
                  },
                }
              : { status: "ok", skip_approvals: true, auto_resolved: 1 },
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
      currentSessionId: "auto-session",
      skipApprovals: true,
      pendingApprovals: [],
    });

    await loadHistory("auto-session");

    expect(getState().pendingApprovals).toEqual([]);
    expect(
      requests.some(
        (request) =>
          request.path === "/sessions/auto-session/auto" &&
          request.method === "POST" &&
          request.body === JSON.stringify({ value: true }),
      ),
    ).toBe(true);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("loadHistory lets replayed tools continue the active trailing history group", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const messages: HistoryMessage[] = [
    { role: "user", content: "watch it", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"date"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-reasoning-1",
      reasoning_content: "thinking",
    },
  ];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: {
            messages,
            active_run_id: "run-active",
            runtime: {
              session_id: "active-history-session",
              latest_event_seq: 10,
              checkpoint_seq: 10,
              active_run: { run_id: "run-active", status: "running" },
              pending_approvals: [],
              queued_messages: [],
            },
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
      currentSessionId: "active-history-session",
    });

    await loadHistory("active-history-session");
    const loadedActivityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
    expect(getState().messages.get(loadedActivityId!)?.activity).toMatchObject({
      done: true,
      label: "Called",
    });
    handleServerEvent({
      type: "TOOL_CALL_START",
      session_id: "active-history-session",
      seq: 11,
      tool_call_id: "tool-2",
      tool_call_name: "Bash",
      description: "Bash(command='sleep 120')",
    });

    const state = getState();
    const activityIds = state.order.filter((id) => state.messages.get(id)?.role === "activity");
    expect(activityIds).toHaveLength(1);
    expect(state.messages.get(activityIds[0])?.activity).toMatchObject({
      done: false,
      label: "Calling",
    });
    expect(state.messages.get(activityIds[0])?.activity?.items.map((item) => item.id)).toEqual([
      "tool-1",
      "tool-2",
    ]);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("loadHistory lets replayed tools continue across trailing hidden meta user messages", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const messages: HistoryMessage[] = [
    { role: "user", content: "watch it", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"date"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    { role: "user", content: "hidden wakeup", id: "meta-user-1", is_meta: true },
  ];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: {
            messages,
            active_run_id: "run-active",
            runtime: {
              session_id: "active-hidden-meta-session",
              latest_event_seq: 10,
              checkpoint_seq: 10,
              active_run: { run_id: "run-active", status: "running" },
              pending_approvals: [],
              queued_messages: [],
            },
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
      currentSessionId: "active-hidden-meta-session",
    });

    await loadHistory("active-hidden-meta-session");
    const loadedActivityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
    expect(getState().messages.get(loadedActivityId!)?.activity).toMatchObject({
      done: true,
      label: "Called",
    });
    handleServerEvent({
      type: "TOOL_CALL_START",
      session_id: "active-hidden-meta-session",
      seq: 11,
      tool_call_id: "tool-2",
      tool_call_name: "Bash",
      description: "Bash(command='sleep 120')",
    });

    const state = getState();
    const activityIds = state.order.filter((id) => state.messages.get(id)?.role === "activity");
    expect(activityIds).toHaveLength(1);
    expect(state.messages.get(activityIds[0])?.activity).toMatchObject({
      done: false,
      label: "Calling",
    });
    expect(state.messages.get(activityIds[0])?.activity?.items.map((item) => item.id)).toEqual([
      "tool-1",
      "tool-2",
    ]);
  } finally {
    (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
  }
});

test("live tools keep appending after canonical reload merged hidden-split activity groups", async () => {
  const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;
  const messages: HistoryMessage[] = [
    { role: "user", content: "watch it", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"sleep 90"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-reasoning-1",
      reasoning_content: "thinking",
    },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-2",
      tool_calls: [{ id: "tool-2", name: "Bash", arguments: '{"command":"sleep 120"}' }],
    },
  ];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async () => ({
          ok: true,
          status: 200,
          statusText: "OK",
          contentType: "application/json",
          data: {
            messages,
            active_run_id: "run-active",
            runtime: {
              session_id: "active-reload-session",
              latest_event_seq: 20,
              checkpoint_seq: 20,
              active_run: { run_id: "run-active", status: "running" },
              pending_approvals: [],
              queued_messages: [],
            },
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
      currentSessionId: "active-reload-session",
    });

    await loadHistory("active-reload-session");
    handleServerEvent({
      type: "TOOL_CALL_START",
      session_id: "active-reload-session",
      seq: 21,
      tool_call_id: "tool-3",
      tool_call_name: "Bash",
      description: "Bash(command='sleep 60')",
    });

    const state = getState();
    const activityIds = state.order.filter((id) => state.messages.get(id)?.role === "activity");
    expect(activityIds).toHaveLength(1);
    expect(state.activeActivityId).toBe(activityIds[0]);
    expect(state.messages.get(activityIds[0])?.activity).toMatchObject({
      label: "Calling",
      done: false,
    });
    expect(state.messages.get(activityIds[0])?.activity?.items.map((item) => item.id)).toEqual([
      "tool-1",
      "tool-2",
      "tool-3",
    ]);
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

test("replay mode applies tool burst activity synchronously", () => {
  handleReplayServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1", timestamp: 1 });
  handleReplayServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-1", tool_call_name: "ReadFile", timestamp: 2 });
  handleReplayServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-1", timestamp: 3 });
  handleReplayServerEvent({ type: "TOOL_CALL_START", tool_call_id: "tool-2", tool_call_name: "ListFiles", timestamp: 4 });
  handleReplayServerEvent({ type: "TOOL_CALL_END", tool_call_id: "tool-2", timestamp: 5 });

  const state = getState();
  const activityId = state.order.find((id) => state.messages.get(id)?.role === "activity");
  const items = state.messages.get(activityId!)?.activity?.items ?? [];
  expect(items.map((item) => item.id)).toEqual(["tool-1", "tool-2"]);
});

test("replay mode marks transcript mutations as non-live motion", async () => {
  const originalDocument = (globalThis as typeof globalThis & { document?: unknown }).document;
  const documentElement = { dataset: {} as Record<string, string> };
  (globalThis as typeof globalThis & { document?: unknown }).document = { documentElement };

  try {
    handleReplayServerEvent({ type: "RUN_STARTED", run_id: "run-1", session_id: "session-1", timestamp: 1 });

    expect(documentElement.dataset.streamReplaying).toBe("true");
    expect(getState().streamReplaying).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(documentElement.dataset.streamReplaying).toBe("true");
    expect(getState().streamReplaying).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(documentElement.dataset.streamReplaying).toBeUndefined();
    expect(getState().streamReplaying).toBe(false);
  } finally {
    (globalThis as typeof globalThis & { document?: unknown }).document = originalDocument;
  }
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
    name: "Research Event Systems",
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
  expect(item?.displayName).toBe("Research Event Systems");
  expect(item?.progress).toBe("done");
});

test("task lifecycle updates subagent row by parent tool call id", () => {
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
    task_id: "task-internal",
    parent_tool_call_id: "call-research",
    name: "Research",
    summary: "event systems",
    depth: 1,
    timestamp: 4,
  });

  const activityId = getState().order.find((id) => getState().messages.get(id)?.role === "activity");
  let item = getState().messages.get(activityId!)?.activity?.items.find((it) => it.id === "call-research");
  expect(item?.status).toBe("ongoing");
  expect(item?.taskStatus).toBe("running");

  handleServerEvent({
    type: "task_finished",
    run_id: "run-1",
    task_id: "task-internal",
    parent_tool_call_id: "call-research",
    status: "completed",
    summary: "done",
    depth: 1,
    timestamp: 5,
  });

  item = getState().messages.get(activityId!)?.activity?.items.find((it) => it.id === "call-research");
  expect(item?.status).toBe("executed");
  expect(item?.taskStatus).toBe("completed");
});

test("background task event updates background agents without transcript noise", () => {
  setState({ currentSessionId: "session-1" });

  handleServerEvent({
    type: "background_task",
    session_id: "session-1",
    task_id: "bg-1",
    command: "research event systems",
    status: "completed",
    detail: "done",
    timestamp: 10,
  });

  const state = getState();
  expect(state.order).toEqual([]);
  expect(state.backgroundAgents.rows["session-1:bg-1"]).toMatchObject({
    taskId: "bg-1",
    sessionId: "session-1",
    command: "research event systems",
    status: "completed",
    detail: "done",
  });
});

test("background snapshot does not complete missing running tasks", () => {
  const s = getState();
  s.upsertBackgroundAgent({
    taskId: "bg-1",
    sessionId: "session-1",
    command: "research",
    status: "running",
    updatedAt: 1,
  });

  s.setBackgroundAgentsForSession("session-1", []);

  expect(getState().backgroundAgents.rows["session-1:bg-1"].status).toBe("running");
});

test("right sidebar active background agents excludes terminal statuses", () => {
  expect(
    isActiveBackgroundAgent({
      taskId: "bg-1",
      sessionId: "session-1",
      command: "research",
      status: "completed",
      createdAt: 1,
      updatedAt: 2,
    }),
  ).toBe(false);
  expect(
    isActiveBackgroundAgent({
      taskId: "bg-2",
      sessionId: "session-1",
      command: "research",
      status: "running",
      createdAt: 1,
      updatedAt: 2,
    }),
  ).toBe(true);
});
