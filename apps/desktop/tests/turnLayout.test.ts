import { expect, test } from "bun:test";
import { turnLayout } from "../src/lib/turnLayout.js";

test("keeps active turns in stream order instead of hoisting streaming assistant text", () => {
  const layout = turnLayout({
    childIds: ["assistant-1", "activity-1", "assistant-2", "activity-2"],
    finalAssistantId: "assistant-2",
    isDone: false,
  });

  expect(layout).toEqual({
    directIds: ["assistant-1", "activity-1", "assistant-2", "activity-2"],
    workIds: [],
    finalAssistantId: "assistant-2",
  });
});

test("keeps completed turns split into work block plus final assistant", () => {
  const layout = turnLayout({
    childIds: ["assistant-1", "activity-1", "assistant-2"],
    finalAssistantId: "assistant-2",
    isDone: true,
  });

  expect(layout).toEqual({
    directIds: ["assistant-2"],
    workIds: ["assistant-1", "activity-1"],
    finalAssistantId: "assistant-2",
  });
});

test("keeps completed tool activity inline when work trace grouping is disabled", () => {
  const layout = turnLayout({
    childIds: ["activity-1", "assistant-1"],
    finalAssistantId: "assistant-1",
    isDone: true,
    showWorkTrace: false,
  });

  expect(layout).toEqual({
    directIds: ["activity-1", "assistant-1"],
    workIds: [],
    finalAssistantId: "assistant-1",
  });
});
