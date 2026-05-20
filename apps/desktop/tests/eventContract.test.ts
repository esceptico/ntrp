import { beforeEach, expect, test } from "bun:test";
import {
  handleServerEvent,
  lastEventSeqForSession,
  resetEventSeqStateForTest,
  resetReplayGapReloadStateForTest,
  resetStreamStateForTest,
} from "../src/hooks/useEvents.js";
import { getState, setState } from "../src/store/index.js";

beforeEach(() => {
  resetStreamStateForTest();
  resetEventSeqStateForTest();
  resetReplayGapReloadStateForTest();
  setState({
    currentSessionId: "sess-1",
    messages: new Map(),
    order: [],
    activeActivityId: null,
    running: false,
    currentRunId: null,
    error: null,
  });
});

test("desktop applies terminal event once by sequence", () => {
  handleServerEvent({ type: "RUN_STARTED", session_id: "sess-1", run_id: "run-1", seq: 1 });
  handleServerEvent({ type: "RUN_FINISHED", session_id: "sess-1", run_id: "run-1", seq: 2 });
  handleServerEvent({ type: "RUN_FINISHED", session_id: "sess-1", run_id: "run-1", seq: 2 });

  const state = getState();
  expect(state.running).toBe(false);
  expect(state.currentRunId).toBeNull();
  expect(lastEventSeqForSession("sess-1")).toBe(2);
});

test("desktop ignores stale run error for an older run", () => {
  setState({ running: true, currentRunId: "run-new", activeRunSessionIds: new Set(["sess-1"]) });
  handleServerEvent({
    type: "RUN_ERROR",
    session_id: "sess-1",
    run_id: "run-old",
    message: "old failure",
    seq: 11,
  });

  const state = getState();
  expect(state.running).toBe(true);
  expect(state.currentRunId).toBe("run-new");
  expect(state.order).toEqual([]);
});

test("desktop ignores stale run finish for an older run", () => {
  setState({ running: true, currentRunId: "run-new", activeRunSessionIds: new Set(["sess-1"]) });
  handleServerEvent({ type: "RUN_FINISHED", session_id: "sess-1", run_id: "run-old", seq: 11 });

  const state = getState();
  expect(state.running).toBe(true);
  expect(state.currentRunId).toBe("run-new");
});

test("desktop preserves ordered text under sequenced content events", () => {
  handleServerEvent({ type: "RUN_STARTED", session_id: "sess-1", run_id: "run-1", seq: 1 });
  handleServerEvent({ type: "TEXT_MESSAGE_START", session_id: "sess-1", message_id: "text-1", seq: 2 });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    session_id: "sess-1",
    message_id: "text-1",
    delta: "a",
    seq: 3,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    session_id: "sess-1",
    message_id: "text-1",
    delta: "b",
    seq: 4,
  });

  expect(getState().messages.get("text-1")?.content).toBe("ab");
});

test("desktop advances cursor on typed keepalive without mutating transcript", () => {
  handleServerEvent({
    type: "stream_keepalive",
    session_id: "sess-1",
    seq: 42,
    latest_seq: 42,
  });

  expect(lastEventSeqForSession("sess-1")).toBe(42);
  expect(getState().order).toEqual([]);
});

test("desktop reconciles assistant content on text end", () => {
  handleServerEvent({ type: "RUN_STARTED", session_id: "sess-1", run_id: "run-1", seq: 1 });
  handleServerEvent({ type: "TEXT_MESSAGE_START", session_id: "sess-1", message_id: "text-1", seq: 2 });
  handleServerEvent({
    type: "TEXT_MESSAGE_CONTENT",
    session_id: "sess-1",
    message_id: "text-1",
    delta: "helo",
    seq: 3,
  });
  handleServerEvent({
    type: "TEXT_MESSAGE_END",
    session_id: "sess-1",
    message_id: "text-1",
    content: "hello",
    seq: 4,
  });

  expect(getState().messages.get("text-1")?.content).toBe("hello");
  expect(lastEventSeqForSession("sess-1")).toBe(4);
});
