import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import type { TodoListItem } from "../src/api.ts";
import {
  clearTodoOverride,
  loadTodoOverride,
  nextTodoStatus,
  saveTodoOverride,
  todoSignature,
} from "../src/lib/todoOverride.ts";

// Minimal localStorage shim (bun test has no DOM).
beforeEach(() => {
  const store = new Map<string, string>();
  (globalThis as { localStorage?: Storage }).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
    key: () => null,
    length: 0,
  } as Storage;
});
afterEach(() => {
  delete (globalThis as { localStorage?: Storage }).localStorage;
});

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

describe("todo override persistence", () => {
  it("round-trips while the agent list is unchanged", () => {
    const sig = todoSignature(agent);
    const edited: TodoListItem[] = [...agent, { content: "c", status: "pending" }];
    saveTodoOverride("s1", sig, edited);
    expect(loadTodoOverride("s1", sig)).toEqual(edited);
  });

  it("is superseded once the agent emits a different list", () => {
    const sig = todoSignature(agent);
    saveTodoOverride("s1", sig, [...agent, { content: "c", status: "pending" }]);
    const newAgentSig = todoSignature([...agent, { content: "agent-added", status: "pending" }]);
    expect(loadTodoOverride("s1", newAgentSig)).toBeNull();
  });

  it("clears", () => {
    const sig = todoSignature(agent);
    saveTodoOverride("s1", sig, agent);
    clearTodoOverride("s1");
    expect(loadTodoOverride("s1", sig)).toBeNull();
  });

  it("is scoped per session", () => {
    const sig = todoSignature(agent);
    saveTodoOverride("s1", sig, [{ content: "only-s1", status: "pending" }]);
    expect(loadTodoOverride("s2", sig)).toBeNull();
  });
});
