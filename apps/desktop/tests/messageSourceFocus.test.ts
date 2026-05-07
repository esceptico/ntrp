import { expect, test } from "bun:test";
import {
  firstMessageIdInSourceFocus,
  messageInSourceFocus,
  resolveMessageSourceFocus,
  type MessageSourceFocus,
} from "../src/lib/messageSourceFocus.js";

const focus: MessageSourceFocus = {
  sessionId: "session-1",
  messageStart: 2,
  messageEnd: 5,
  nonce: 1,
};

test("matches messages inside the focused source range", () => {
  expect(messageInSourceFocus({ sourceIndex: 2 }, focus, "session-1")).toBe(true);
  expect(messageInSourceFocus({ sourceIndex: 4 }, focus, "session-1")).toBe(true);
  expect(messageInSourceFocus({ sourceIndex: 5 }, focus, "session-1")).toBe(false);
  expect(messageInSourceFocus({ sourceIndex: 3 }, focus, "other-session")).toBe(false);
  expect(messageInSourceFocus({}, focus, "session-1")).toBe(false);
});

test("finds the first loaded message inside the focused range", () => {
  const messages = new Map([
    ["a", { sourceIndex: 1 }],
    ["b", { sourceIndex: 3 }],
    ["c", { sourceIndex: 4 }],
  ]);

  expect(firstMessageIdInSourceFocus(["a", "b", "c"], messages, focus, "session-1")).toBe("b");
  expect(firstMessageIdInSourceFocus(["a", "b", "c"], messages, focus, "other-session")).toBeNull();
});

test("resolves stable message ids to a loaded source range", () => {
  const idFocus: MessageSourceFocus = {
    sessionId: "session-1",
    messageStartId: "msg-2",
    messageEndId: "msg-4",
    nonce: 1,
  };
  const messages = new Map([
    ["a", { sourceIndex: 1, sourceMessageId: "msg-1" }],
    ["b", { sourceIndex: 2, sourceMessageId: "msg-2" }],
    ["c", { sourceIndex: 3, sourceMessageId: "msg-3" }],
    ["d", { sourceIndex: 4, sourceMessageId: "msg-4" }],
  ]);

  const resolved = resolveMessageSourceFocus(["a", "b", "c", "d"], messages, idFocus, "session-1");

  expect(resolved).toEqual({
    ...idFocus,
    messageStart: 2,
    messageEnd: 5,
  });
  expect(messageInSourceFocus(messages.get("c"), resolved, "session-1")).toBe(true);
});

test("keeps unresolved id focus when target messages are not loaded", () => {
  const idFocus: MessageSourceFocus = {
    sessionId: "session-1",
    messageStartId: "msg-9",
    messageEndId: "msg-10",
    nonce: 1,
  };
  const messages = new Map([["a", { sourceIndex: 1, sourceMessageId: "msg-1" }]]);

  expect(resolveMessageSourceFocus(["a"], messages, idFocus, "session-1")).toEqual(idFocus);
});
