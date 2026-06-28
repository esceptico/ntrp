import { describe, expect, it } from "bun:test";
import type { TodoListItem } from "@/api";
import { nextTodoStatus, todoSignature } from "@/lib/todoOverride";

const agent: TodoListItem[] = [
  { content: "a", status: "completed" },
  { content: "b", status: "pending" },
];

describe("todoSignature", () => {
  it("is stable for content+status and changes when either changes", () => {
    expect(todoSignature(agent)).toBe(todoSignature([...agent]));
    expect(todoSignature(agent)).not.toBe(todoSignature([{ content: "a", status: "pending" }, agent[1]]));
    expect(todoSignature(agent)).not.toBe(todoSignature([agent[0]]));
  });
});

describe("nextTodoStatus", () => {
  it("cycles pending -> in_progress -> completed -> pending", () => {
    expect(nextTodoStatus("pending")).toBe("in_progress");
    expect(nextTodoStatus("in_progress")).toBe("completed");
    expect(nextTodoStatus("completed")).toBe("pending");
  });
});
