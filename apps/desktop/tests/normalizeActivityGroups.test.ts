import { expect, test } from "bun:test";
import { normalizeActivityGroups } from "../src/store/session-cache.ts";
import type { ActivityItem, UiMessage } from "../src/store/types.ts";

function activityItem(id: string): ActivityItem {
  return { id, kind: "bash", target: id, status: "executed" };
}

function activity(id: string, itemIds: string[]): UiMessage {
  return {
    id,
    role: "activity",
    content: "",
    activity: { items: itemIds.map(activityItem), label: "Called", done: true },
  };
}

function user(id: string): UiMessage {
  return { id, role: "user", content: "hi" };
}

// Regression: during an active run the projection could list one activity id
// twice in `order` (a stale cached copy beside the freshly projected one),
// separated by a visible boundary so the positional collapse missed it. That
// surfaced two children with the same React key. The id must appear once and
// the group's items must not be doubled.
test("normalizeActivityGroups collapses a duplicated activity id into one render key", () => {
  const messages = new Map<string, UiMessage>([
    ["msg-x-activity", activity("msg-x-activity", ["t1", "t2"])],
    ["user-1", user("user-1")],
  ]);
  const order = ["msg-x-activity", "user-1", "msg-x-activity"];

  const out = normalizeActivityGroups(messages, order, "msg-x-activity");

  expect(out.order.filter((id) => id === "msg-x-activity")).toHaveLength(1);
  expect(new Set(out.order).size).toBe(out.order.length);
  expect(out.messages.get("msg-x-activity")?.activity?.items.map((i) => i.id)).toEqual([
    "t1",
    "t2",
  ]);
});

// Distinct, consecutive activity groups still collapse into one (existing
// behavior — a run's tool calls span several assistant messages).
test("normalizeActivityGroups still merges distinct consecutive activities", () => {
  const messages = new Map<string, UiMessage>([
    ["a1", activity("a1", ["t1"])],
    ["a2", activity("a2", ["t2"])],
  ]);
  const order = ["a1", "a2"];

  const out = normalizeActivityGroups(messages, order, "a1");

  expect(out.order).toEqual(["a1"]);
  expect(out.messages.get("a1")?.activity?.items.map((i) => i.id)).toEqual(["t1", "t2"]);
  expect(out.activeActivityId).toBe("a1");
});
