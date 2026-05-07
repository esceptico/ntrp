import { expect, test } from "bun:test";
import { factSourceDetail, factSourceLabel, factSourceSummary } from "../src/lib/memoryProvenance.js";

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
});

test("omits empty source refs from summaries", () => {
  expect(factSourceLabel({ source_type: "explicit", source_ref: null })).toBe("Explicit");
  expect(factSourceDetail({ source_type: "explicit", source_ref: null })).toBeNull();
  expect(factSourceSummary({ source_type: "explicit", source_ref: null })).toBe("Explicit");
});

test("keeps unknown source types readable", () => {
  expect(factSourceLabel({ source_type: "daily_sweep", source_ref: "note.md" })).toBe("Daily sweep");
});
