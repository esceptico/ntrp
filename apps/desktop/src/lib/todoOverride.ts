import type { TodoListItem, TodoStatus } from "../api";

// Manual todo edits, persisted per session in localStorage. Todos are otherwise
// derived from the agent's latest update_todos call; an override layers the
// user's curation on top. It's keyed to the agent list it was made against
// (`base`), so the next agent update (a different signature) supersedes it
// rather than fighting it.

const key = (sessionId: string) => `ntrp:todo-override:${sessionId}`;

interface StoredOverride {
  base: string;
  items: TodoListItem[];
}

export function todoSignature(items: TodoListItem[]): string {
  return JSON.stringify(items.map((item) => [item.content, item.status]));
}

/** The user's edited list, but only while it still matches the agent list it
 *  was based on. Returns null once the agent has moved on (its update wins). */
export function loadTodoOverride(sessionId: string, agentSignature: string): TodoListItem[] | null {
  try {
    const raw = localStorage.getItem(key(sessionId));
    if (!raw) return null;
    const stored = JSON.parse(raw) as StoredOverride;
    return stored.base === agentSignature ? stored.items : null;
  } catch {
    return null;
  }
}

export function saveTodoOverride(sessionId: string, base: string, items: TodoListItem[]): void {
  try {
    localStorage.setItem(key(sessionId), JSON.stringify({ base, items } satisfies StoredOverride));
  } catch {
    /* localStorage unavailable — edits just won't persist */
  }
}

export function clearTodoOverride(sessionId: string): void {
  try {
    localStorage.removeItem(key(sessionId));
  } catch {
    /* ignore */
  }
}

const STATUS_CYCLE: TodoStatus[] = ["pending", "in_progress", "completed"];

export function nextTodoStatus(status: TodoStatus): TodoStatus {
  return STATUS_CYCLE[(STATUS_CYCLE.indexOf(status) + 1) % STATUS_CYCLE.length];
}
