import { expect, test } from "bun:test";
import {
  factChatSourceFocus,
  factChatSourceSessionId,
  factSourceDetail,
  factSourceLabel,
  factSourceStatus,
  factSourceSummary,
} from "../src/lib/memoryProvenance.js";

test("formats fact source labels without inferring from refs", () => {
  expect(factSourceLabel({ source_type: "chat", source_ref: "session-123" })).toBe("Chat");
  expect(factSourceDetail({ source_type: "chat", source_ref: "session-123" })).toBe("session-123");
  expect(factSourceSummary({ source_type: "chat", source_ref: "session-123" })).toBe("Chat · session-123");
});

test("formats parsed chat segment refs as readable provenance", () => {
  const fact = {
    source_type: "chat",
    source_ref: "chat:session-123:4-9",
    source_ref_parts: {
      kind: "chat_segment",
      session_id: "session-123",
      message_start: 4,
      message_end: 9,
    },
  };

  expect(factSourceDetail(fact)).toBe("session-123 · messages 4-9");
  expect(factSourceSummary(fact)).toBe("Chat · session-123 · messages 4-9");
  expect(factChatSourceSessionId(fact)).toBe("session-123");
  expect(factChatSourceFocus(fact)).toEqual({
    sessionId: "session-123",
    messageStart: 4,
    messageEnd: 9,
  });
  expect(factSourceStatus(fact)).toEqual({ label: "Openable source", tone: "ok" });
});

test("does not expose a chat source action for unparsed refs", () => {
  const fact = { source_type: "chat", source_ref: "session-123" };

  expect(factChatSourceSessionId(fact)).toBeNull();
  expect(factChatSourceFocus(fact)).toBeNull();
  expect(factSourceStatus(fact)).toEqual({ label: "Source link unavailable", tone: "warn" });
  expect(factChatSourceSessionId({ source_type: "explicit", source_ref: null })).toBeNull();
});

test("omits empty source refs from summaries", () => {
  const fact = { source_type: "explicit", source_ref: null };

  expect(factSourceLabel(fact)).toBe("Explicit");
  expect(factSourceDetail(fact)).toBeNull();
  expect(factSourceSummary(fact)).toBe("Explicit");
  expect(factSourceStatus(fact)).toEqual({ label: "Manual entry", tone: "neutral" });
});

test("keeps unknown source types readable", () => {
  const fact = { source_type: "daily_sweep", source_ref: "note.md" };

  expect(factSourceLabel(fact)).toBe("Daily sweep");
  expect(factSourceStatus(fact)).toEqual({ label: "Source reference", tone: "neutral" });
});
