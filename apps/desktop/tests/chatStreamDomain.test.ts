import { expect, test } from "bun:test";
import {
  handleServerEvent,
  clearReplayBlock,
  createInitialChatStreamState,
  getChatStreamState,
  reduceEventCursor,
  reduceReplayGap,
  reduceStreamConnected,
  reduceStreamConnecting,
  reduceStreamDisconnected,
  reduceStreamReconnecting,
  runCancelledEffect,
} from "@/stores/chat-stream";
import { setState } from "@/stores/index";

test("stale event seq is ignored", () => {
  let state = createInitialChatStreamState();

  const first = reduceEventCursor(state, { session_id: "session-1", seq: 7 });
  expect(first.accepted).toBe(true);
  state = first.state;

  const duplicate = reduceEventCursor(state, { session_id: "session-1", seq: 7 });
  expect(duplicate.accepted).toBe(false);
  expect(duplicate.state.lastEventSeqBySession.get("session-1")).toBe(7);

  const stale = reduceEventCursor(state, { session_id: "session-1", seq: 6 });
  expect(stale.accepted).toBe(false);
  expect(stale.state.lastEventSeqBySession.get("session-1")).toBe(7);
});

test("replay gap blocks mutation until history reload finishes", () => {
  let state = createInitialChatStreamState();

  state = reduceReplayGap(state, "session-1");

  const blocked = reduceEventCursor(state, { session_id: "session-1", seq: 8 });
  expect(blocked.accepted).toBe(false);
  expect(blocked.state.lastEventSeqBySession.get("session-1")).toBeUndefined();

  state = clearReplayBlock(state, "session-1");
  const unblocked = reduceEventCursor(state, { session_id: "session-1", seq: 8 });
  expect(unblocked.accepted).toBe(true);
  expect(unblocked.state.lastEventSeqBySession.get("session-1")).toBe(8);
});

test("clear replay block is scoped to session id", () => {
  let state = createInitialChatStreamState();
  state = reduceReplayGap(state, "session-1");
  state = reduceReplayGap(state, "session-2");

  state = clearReplayBlock(state, "session-1");

  expect(state.replayGapBlockedSessions.has("session-1")).toBe(false);
  expect(state.replayGapBlockedSessions.has("session-2")).toBe(true);
});

test("reconnect keeps cursor but does not replay visual animations", () => {
  let state = createInitialChatStreamState();
  state = reduceEventCursor(state, { session_id: "session-1", seq: 12 }).state;
  state = {
    ...state,
    activeAssistantMessageId: "assistant-1",
    replayMutationTimer: setTimeout(() => undefined, 100),
    replayMutationActive: true,
  };

  state = reduceStreamDisconnected(state, "session-1");
  state = reduceStreamConnecting(state, "session-1");

  expect(state.lastEventSeqBySession.get("session-1")).toBe(12);
  expect(state.activeAssistantMessageId).toBeNull();
  expect(state.replayMutationTimer).toBeNull();
  expect(state.replayMutationActive).toBe(false);
  expect(state.connectionPhase).toBe("connecting");
});

test("transport diagnostics track reconnect cursor and keepalive seq", () => {
  let state = createInitialChatStreamState();

  state = reduceStreamConnecting(state, "session-1", 41);
  state = reduceEventCursor(state, {
    session_id: "session-1",
    type: "stream_keepalive",
    seq: 42,
    latest_seq: 99,
  }).state;

  expect(state.transportDiagnosticsBySession.get("session-1")).toMatchObject({
    connectionPhase: "connecting",
    connectAfterSeq: 41,
    lastSeq: 42,
    lastKeepaliveSeq: 99,
  });
});

test("transient stream closures show reconnecting during backoff instead of disconnected", () => {
  let state = createInitialChatStreamState();
  state = reduceStreamConnected(state, "session-1");

  state = reduceStreamReconnecting(state, "session-1", "eof");

  expect(state.connectionPhase).toBe("reconnecting");
  expect(state.transportDiagnosticsBySession.get("session-1")).toMatchObject({
    connectionPhase: "reconnecting",
    lastClosedReason: "eof",
  });
});

test("stream connection binds transient projection state to the target session", () => {
  let state = createInitialChatStreamState();

  state = reduceStreamConnecting(state, "session-1");
  expect(state.projectionSessionId).toBe("session-1");

  state = {
    ...state,
    activeAssistantMessageId: "assistant-1",
    pendingToolCalls: new Map([
      [
        "tool-1",
        {
          name: "ReadFile",
          description: "",
          argsBuffer: "{}",
          depth: 0,
          parentId: null,
          semanticKind: "tool",
          startSeq: 10,
        },
      ],
    ]),
  };

  state = reduceStreamConnecting(state, "session-2");

  expect(state.projectionSessionId).toBe("session-2");
  expect(state.activeAssistantMessageId).toBeNull();
  expect(state.pendingToolCalls.size).toBe(0);
});

test("disconnect rewinds cursor for a half-applied tool call", () => {
  let state = createInitialChatStreamState();
  state = reduceEventCursor(state, { session_id: "session-1", seq: 12 }).state;
  state = {
    ...state,
    sessionId: "session-1",
    pendingToolCalls: new Map([
      [
        "tool-1",
        {
          name: "ReadFile",
          description: "",
          argsBuffer: "{}",
          depth: 0,
          parentId: null,
          semanticKind: "tool",
          startSeq: 10,
        },
      ],
    ]),
  };

  state = reduceStreamDisconnected(state, "session-1");

  expect(state.lastEventSeqBySession.get("session-1")).toBe(9);
  expect(state.pendingToolCalls.size).toBe(0);
});

test("disconnect rewinds cursor for delayed activity item render", () => {
  let state = createInitialChatStreamState();
  state = reduceEventCursor(state, { session_id: "session-1", seq: 12 }).state;
  state = {
    ...state,
    sessionId: "session-1",
    pendingActivityReplaySeqs: new Map([["tool-1", 10]]),
  };

  state = reduceStreamDisconnected(state, "session-1");

  expect(state.lastEventSeqBySession.get("session-1")).toBe(9);
  expect(state.pendingActivityReplaySeqs.size).toBe(0);
});

test("visible first tool item does not leave cursor rewind marker", () => {
  setState({
    currentSessionId: "session-1",
    messages: new Map(),
    order: [],
    activeActivityId: null,
    running: false,
    currentRunId: null,
  });

  handleServerEvent({
    type: "TOOL_CALL_START",
    tool_call_id: "tool-1",
    tool_call_name: "ReadFile",
    session_id: "session-1",
    seq: 10,
  });
  handleServerEvent({
    type: "TOOL_CALL_END",
    tool_call_id: "tool-1",
    session_id: "session-1",
    seq: 11,
  });

  const stream = getChatStreamState();
  expect(getChatStreamState().lastEventSeqBySession.get("session-1")).toBe(11);
  expect(stream.pendingActivityReplaySeqs.size).toBe(0);
});

test("run cancellation exposes pending queued messages as resend effects", () => {
  const effect = runCancelledEffect([
    {
      clientId: "pending-1",
      text: "retry me",
      images: [{ type: "input_image", image_url: "data:image/png;base64,a" }],
      status: "pending",
      enqueuedAt: 1,
    },
    {
      clientId: "failed-1",
      text: "do not retry",
      status: "failed",
      enqueuedAt: 2,
    },
  ]);

  expect(effect).toEqual({
    type: "resend_queued_messages",
    messages: [
      {
        clientId: "pending-1",
        text: "retry me",
        images: [{ type: "input_image", image_url: "data:image/png;base64,a" }],
        status: "pending",
        enqueuedAt: 1,
      },
    ],
  });
});
