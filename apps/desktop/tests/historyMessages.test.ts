import { expect, test } from "bun:test";
import { historyMessagesToUi } from "../src/actions/history.ts";
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

test("keeps assistant content before tool activity when history row has both", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "send it", id: "user-1" },
    {
      role: "assistant",
      content: "I'll draft/send it to yourself.",
      id: "assistant-1",
      tool_calls: [{ id: "tool-1", name: "SendEmail", arguments: '{"account":"me"}' }],
    },
    { role: "tool", content: "sent", id: "tool-result-1", tool_call_id: "tool-1" },
  ];

  const items = historyMessagesToUi(messages, null);

  expect(items.map((item) => item.role)).toEqual(["user", "assistant", "activity"]);
  expect(items[1].content).toBe("I'll draft/send it to yourself.");
  expect(items[2].activity?.items[0].result).toBe("sent");
});

test("shows a subtle nudge marker for persisted goal meta turns", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "Continue", id: "goal:goal-1:1", is_meta: true },
    { role: "assistant", content: "Working on it.", id: "assistant-1" },
  ];

  const items = historyMessagesToUi(messages, null);

  expect(items.map((item) => [item.role, item.content])).toEqual([
    ["status", "Goal nudge"],
    ["user", "Continue"],
    ["assistant", "Working on it."],
  ]);
  expect(items[1].isMeta).toBe(true);
});
