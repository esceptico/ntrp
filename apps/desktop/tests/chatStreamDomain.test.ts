import { expect, test } from "bun:test";
import {
  clearReplayBlock,
  createInitialChatStreamState,
  reduceEventCursor,
  reduceReplayGap,
  reduceStreamConnecting,
  reduceStreamDisconnected,
  runCancelledEffect,
} from "../src/store/chat-stream.ts";

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
