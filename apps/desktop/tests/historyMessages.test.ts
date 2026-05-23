import { expect, test } from "bun:test";
import { historyMessagesToUi } from "../src/actions/history.ts";
import type { HistoryMessage } from "../src/api.js";
import { turnLayout } from "../src/lib/turnLayout.js";

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

test("keeps one loaded activity group across hidden meta user messages", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "check it", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tools-1",
      tool_calls: [{ id: "tool-1", name: "ReadFile", arguments: '{"path":"a"}' }],
    },
    { role: "user", content: "hidden wakeup", id: "meta-user-1", is_meta: true },
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

test("rehydrates update_todos tool calls as task list messages", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "build todo list", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-todos",
      tool_calls: [
        {
          id: "call-todos",
          name: "update_todos",
          arguments: JSON.stringify({
            explanation: "Track rollout",
            items: [
              { content: "Research prior art", status: "completed" },
              { content: "Implement server tool", status: "in_progress" },
              { content: "Polish desktop UI", status: "pending" },
            ],
          }),
        },
      ],
    },
    { role: "tool", content: "Todo list updated.", id: "tool-result-1", tool_call_id: "call-todos" },
  ];

  const items = historyMessagesToUi(messages, null);

  expect(items.map((item) => item.role)).toEqual(["user", "todo"]);
  expect(items[1].id).toBe("assistant-todos-todo");
  expect(items[1].todo?.items.map((item) => item.content)).toEqual([
    "Research prior art",
    "Implement server tool",
    "Polish desktop UI",
  ]);
});

test("keeps regular activity separate from persisted todo calls", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "check it", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tools",
      tool_calls: [
        {
          id: "call-todos",
          name: "update_todos",
          arguments: JSON.stringify({
            items: [{ content: "Read files", status: "in_progress" }],
          }),
        },
        { id: "tool-1", name: "ReadFile", arguments: '{"path":"a"}' },
      ],
    },
    { role: "tool", content: "Todo list updated.", id: "todo-result", tool_call_id: "call-todos" },
    { role: "tool", content: "file text", id: "tool-result", tool_call_id: "tool-1" },
  ];

  const items = historyMessagesToUi(messages, null);

  expect(items.map((item) => item.role)).toEqual(["user", "todo", "activity"]);
  expect(items[2].activity?.items.map((item) => item.id)).toEqual(["tool-1"]);
});

test("keeps persisted goal meta turns visually hidden", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "Continue", id: "goal:goal-1:1", is_meta: true },
    { role: "assistant", content: "Working on it.", id: "assistant-1" },
  ];

  const items = historyMessagesToUi(messages, null);

  expect(items.map((item) => [item.role, item.content])).toEqual([
    ["user", "Continue"],
    ["assistant", "Working on it."],
  ]);
  expect(items[0].isMeta).toBe(true);
});

test("preserves persisted switch-back order when assistant text is between tool groups", () => {
  const messages: HistoryMessage[] = [
    {
      role: "user",
      content: "/goal read slack",
      id: "goal-user",
      seq: 1,
    },
    {
      role: "assistant",
      content: "",
      id: "load-tools-assistant",
      seq: 2,
      tool_calls: [{ id: "load-tools", name: "load_tools", arguments: '{"group":"slack"}' }],
    },
    {
      role: "tool",
      content: "Loaded slack tools",
      id: "load-tools-result",
      seq: 3,
      tool_call_id: "load-tools",
    },
    {
      role: "assistant",
      content: "I’ll read the Slack thread, then inspect ~/src/ntrp.",
      id: "progress-assistant",
      seq: 4,
      tool_calls: [{ id: "slack-thread", name: "slack_thread", arguments: '{"message_id":"C:1"}' }],
    },
    {
      role: "tool",
      content: "thread text",
      id: "slack-thread-result",
      seq: 5,
      tool_call_id: "slack-thread",
    },
  ];

  const items = historyMessagesToUi(messages, null);
  const children = items.slice(1).map((item) => ({ id: item.id, role: item.role }));
  const layout = turnLayout({ children, isDone: true });

  expect(children.map((item) => item.role)).toEqual(["activity", "assistant", "activity"]);
  expect(layout.workIds).toEqual(["load-tools-assistant-activity"]);
  expect(layout.afterWorkIds).toEqual(["progress-assistant", "progress-assistant-activity"]);
});

test("reopens newest trailing history activity for active runs", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "keep checking", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"date"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-reasoning-1",
      reasoning_content: "thinking",
    },
  ];

  const items = historyMessagesToUi(messages, "run-active");
  const activity = items.find((item) => item.role === "activity");

  expect(activity?.activity).toMatchObject({ done: false, label: "Calling" });
});

test("does not reopen non-newest history page activity for active runs", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "older work", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"date"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
  ];

  const items = historyMessagesToUi(messages, "run-active", { isNewestPage: false });
  const activity = items.find((item) => item.role === "activity");

  expect(activity?.activity).toMatchObject({
    done: true,
    label: "Called",
  });
});

test("does not reopen active history activity before visible final assistant", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "older work", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"date"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    { role: "assistant", content: "done", id: "assistant-final" },
  ];

  const items = historyMessagesToUi(messages, "run-active");
  const activity = items.find((item) => item.role === "activity");

  expect(activity?.activity).toMatchObject({
    done: true,
    label: "Called",
  });
});

test("reopens newest trailing history activity across hidden meta user messages", () => {
  const messages: HistoryMessage[] = [
    { role: "user", content: "keep checking", id: "user-1" },
    {
      role: "assistant",
      content: "",
      id: "assistant-tool-1",
      tool_calls: [{ id: "tool-1", name: "Bash", arguments: '{"command":"date"}' }],
    },
    { role: "tool", content: "ok", id: "tool-result-1", tool_call_id: "tool-1" },
    { role: "user", content: "hidden wakeup", id: "meta-user-1", is_meta: true },
  ];

  const items = historyMessagesToUi(messages, "run-active");
  const activity = items.find((item) => item.role === "activity");

  expect(activity?.activity).toMatchObject({ done: false, label: "Calling" });
});
