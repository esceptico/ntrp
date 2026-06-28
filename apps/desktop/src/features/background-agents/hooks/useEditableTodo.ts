import { useEffect, useMemo, useRef, useState } from "react";
import { clearTodoOverrideApi, getTodoOverrideApi, setTodoOverrideApi } from "@/api/chat";
import type { TodoListItem, TodoStatus } from "@/api/types";
import { nextTodoStatus, todoSignature } from "@/features/background-agents/lib/todoOverride";
import { useStore, type TodoListState } from "@/stores";

export interface EditableTodo {
  key: string;
  content: string;
  status: TodoStatus;
}

// Todos carry no server id, so mint a stable key per item — editing text then
// doesn't remount the row (no flash) and deleting animates the right row.
let todoKeySeq = 0;
const withTodoKeys = (items: TodoListItem[]): EditableTodo[] =>
  items.map((item) => ({ key: `todo-${todoKeySeq++}`, content: item.content, status: item.status }));

// Editable todo list. Agent-produced todos are the base; the user's manual
// edits persist server-side (so the agent sees them on its next run) and last
// until the agent emits a different list, which supersedes them.
export function useEditableTodo(sessionId: string | null, todo: TodoListState) {
  const config = useStore((s) => s.config);
  const agentItems = todo.items;
  const agentSig = useMemo(() => todoSignature(agentItems), [agentItems]);
  const [items, setItems] = useState<EditableTodo[]>(() => withTodoKeys(agentItems));
  const [edited, setEdited] = useState(false);
  const lastSig = useRef(agentSig);

  // Load any persisted override on mount (the section remounts per session).
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void getTodoOverrideApi(config, sessionId)
      .then((override) => {
        if (!cancelled && override) {
          setItems(withTodoKeys(override.items));
          setEdited(true);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessionId, config]);

  // The agent emitted a new list — it supersedes the manual edit (the server
  // already cleared the override when update_todos ran).
  useEffect(() => {
    if (lastSig.current === agentSig) return;
    lastSig.current = agentSig;
    setItems(withTodoKeys(agentItems));
    setEdited(false);
  }, [agentSig, agentItems]);

  const commit = (next: EditableTodo[]) => {
    setItems(next);
    setEdited(true);
    if (sessionId) {
      void setTodoOverrideApi(
        config,
        sessionId,
        next.map(({ content, status }) => ({ content, status })),
      ).catch(() => {});
    }
  };

  return {
    items,
    edited,
    add: (content: string) => commit([...items, { key: `todo-${todoKeySeq++}`, content, status: "pending" }]),
    edit: (key: string, content: string) =>
      commit(items.map((item) => (item.key === key ? { ...item, content } : item))),
    remove: (key: string) => commit(items.filter((item) => item.key !== key)),
    cycle: (key: string) =>
      commit(items.map((item) => (item.key === key ? { ...item, status: nextTodoStatus(item.status) } : item))),
    reset: () => {
      setItems(withTodoKeys(agentItems));
      setEdited(false);
      if (sessionId) void clearTodoOverrideApi(config, sessionId).catch(() => {});
    },
  };
}
