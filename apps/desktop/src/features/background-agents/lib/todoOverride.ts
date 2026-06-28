import type { TodoListItem, TodoStatus } from "@/api";

// Pure helpers for the editable todo list. Persistence is server-side (see
// get/set/clearTodoOverrideApi) so the agent sees manual edits on its next run.

export function todoSignature(items: TodoListItem[]): string {
  return JSON.stringify(items.map((item) => [item.content, item.status]));
}

const STATUS_CYCLE: TodoStatus[] = ["pending", "in_progress", "completed"];

export function nextTodoStatus(status: TodoStatus): TodoStatus {
  return STATUS_CYCLE[(STATUS_CYCLE.indexOf(status) + 1) % STATUS_CYCLE.length];
}
