import { expect, test } from "bun:test";
import { historyMessagesToUi } from "../src/actions.js";
import type { HistoryMessage } from "../src/api.js";

test("keeps one loaded activity group across reasoning-only history messages", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "check it", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tools-1",
      tool_calls: [{ id: "tool-1", name: "ReadFile", arguments: '{"path":"a"}' }],
    },
    {
      role: "assistant",
      content: "",
      id: "assistant-reasoning-1",
      reasoning_content: "thinking",
    },
    {
      role: "assistant",
      content: "",
      id: "assistant-tools-2",
      tool_calls: [{ id: "tool-2", name: "ReadFile", arguments: '{"path":"b"}' }],
    },
  ];

  const items = historyMessagesToUi(messages, null);
  const activityItems = items.filter((item) => item.role === "activity");

  expect(activityItems).toHaveLength(1);
  expect(activityItems[0].activity?.items.map((item) => item.id)).toEqual([
    "tool-1",
    "tool-2",
  ]);
});
