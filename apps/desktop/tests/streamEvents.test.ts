import { beforeEach, expect, test } from "bun:test";
import { handleServerEvent, resetStreamStateForTest } from "../src/hooks/useEvents.js";
import { getState, setState } from "../src/store.js";

beforeEach(() => {
  resetStreamStateForTest();
  setState({
    messages: new Map(),
    order: [],
    activeActivityId: null,
    running: false,
    currentRunId: null,
    error: null,
  });
});

test("continues assistant content by message id after late tool activity", () => {
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
  expect(roles).toEqual(["activity", "assistant"]);
});
