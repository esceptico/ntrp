import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Fact } from "../src/api";
import { SupportingFacts } from "../src/components/memory/ObservationsPane.js";

function fact(patch: Partial<Fact>): Fact {
  return {
    id: 1,
    text: "User prefers source-linked memory",
    source_type: "chat",
    source_ref: "chat:session-123:4-9",
    source_ref_parts: {
      kind: "chat_segment",
      session_id: "session-123",
      message_start: 4,
      message_end: 9,
    },
    created_at: "2026-05-07T00:00:00Z",
    happened_at: null,
    last_accessed_at: "2026-05-07T00:00:00Z",
    access_count: 0,
    consolidated_at: null,
    archived_at: null,
    kind: "preference",
    lifetime: "durable",
    salience: 1,
    confidence: 0.9,
    expires_at: null,
    pinned_at: null,
    valid_from: null,
    valid_until: null,
    superseded_by_fact_id: null,
    status: "active",
    ...patch,
  };
}

test("pattern supporting facts expose openable source links", () => {
  const html = renderToStaticMarkup(
    createElement(SupportingFacts, {
      facts: [fact({})],
      missing: [],
      onOpenFact: () => undefined,
      onOpenSource: () => undefined,
    }),
  );

  expect(html).toContain("Open source");
  expect(html).toContain("Chat · session-123 · messages 4-9");
});
