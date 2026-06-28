import { expect, test } from "bun:test";
import { operationLabel } from "@/features/chat/lib/operationLabel";
import type { ActivityItem } from "@/stores";

function item(over: Partial<ActivityItem>): ActivityItem {
  return { id: "x", kind: "tool", target: "", ...over } as ActivityItem;
}

test("maps common tool kinds to natural-language verbs", () => {
  expect(operationLabel(item({ kind: "read_file" })).verb).toBe("Read");
  expect(operationLabel(item({ kind: "bash" })).verb).toBe("Ran");
  expect(operationLabel(item({ kind: "grep" })).verb).toBe("Searched code");
  expect(operationLabel(item({ kind: "glob" })).verb).toBe("Listed files");
  expect(operationLabel(item({ kind: "web_search" })).verb).toBe("Searched the web");
  expect(operationLabel(item({ kind: "web_fetch" })).verb).toBe("Fetched");
  expect(operationLabel(item({ kind: "str_replace_editor" })).verb).toBe("Edited");
});

test("file-search kinds win over the generic web-search rule", () => {
  // `search_files` must read as a code search, not a web search.
  expect(operationLabel(item({ kind: "search_files" })).verb).toBe("Searched code");
});

test("pulls the operation object out of args, preferring path-like keys", () => {
  expect(operationLabel(item({ kind: "read", args: '{"path":"ntrp/core/agent.py"}' })).detail).toBe(
    "ntrp/core/agent.py",
  );
  expect(operationLabel(item({ kind: "web_search", args: '{"query":"opus 4.8"}' })).detail).toBe(
    "opus 4.8",
  );
});

test("partial/empty args yield no detail rather than throwing", () => {
  expect(operationLabel(item({ kind: "read", args: '{"path":' })).detail).toBeNull();
  expect(operationLabel(item({ kind: "read", args: "{}" })).detail).toBeNull();
  expect(operationLabel(item({ kind: "read" })).detail).toBeNull();
});

test("short verb tokens don't bleed into longer words", () => {
  // "view"/"cat"/"read" must not claim preview/category/overview.
  expect(operationLabel(item({ kind: "preview" })).verb).toBe("Preview");
  expect(operationLabel(item({ kind: "category" })).verb).toBe("Category");
  expect(operationLabel(item({ kind: "overview" })).verb).toBe("Overview");
  // …but snake_case tool names still resolve.
  expect(operationLabel(item({ kind: "view_file" })).verb).toBe("Read");
  expect(operationLabel(item({ kind: "open_file" })).verb).toBe("Read");
});

test("unknown kinds fall back to a title-cased displayName/kind", () => {
  expect(operationLabel(item({ kind: "custom_thing" })).verb).toBe("Custom thing");
  expect(operationLabel(item({ kind: "custom_thing", displayName: "Sync vault" })).verb).toBe(
    "Sync vault",
  );
});

test("truncates long details", () => {
  const long = "a/".repeat(60);
  const { detail } = operationLabel(item({ kind: "read", args: JSON.stringify({ path: long }) }));
  expect(detail).not.toBeNull();
  expect(detail!.length).toBeLessThanOrEqual(64);
  expect(detail!.endsWith("…")).toBe(true);
});
