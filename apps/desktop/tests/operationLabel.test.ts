import { expect, test } from "bun:test";
import { operationLabel, stepSources } from "@/features/chat/lib/operationLabel";
import type { ActivityItem } from "@/stores";

function item(over: Partial<ActivityItem>): ActivityItem {
  return { id: "x", kind: "tool", target: "", ...over } as ActivityItem;
}

test("maps common tool kinds to natural-language verbs + icons", () => {
  expect(operationLabel(item({ kind: "read_file" }))).toMatchObject({ verb: "Read", iconKey: "file" });
  expect(operationLabel(item({ kind: "bash" }))).toMatchObject({ verb: "Ran", iconKey: "terminal" });
  expect(operationLabel(item({ kind: "grep" }))).toMatchObject({ verb: "Searched code", iconKey: "search" });
  expect(operationLabel(item({ kind: "glob" }))).toMatchObject({ verb: "Listed files", iconKey: "folder" });
  expect(operationLabel(item({ kind: "web_search" }))).toMatchObject({ verb: "Searched the web", iconKey: "search" });
  expect(operationLabel(item({ kind: "web_fetch" }))).toMatchObject({ verb: "Fetched", iconKey: "globe" });
  expect(operationLabel(item({ kind: "str_replace_editor" }))).toMatchObject({ verb: "Edited", iconKey: "edit" });
});

test("unknown kinds get no icon (fall back to a timeline dot)", () => {
  expect(operationLabel(item({ kind: "custom_thing" })).iconKey).toBeNull();
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

test("stepSources extracts deduped hostnames from url/urls args", () => {
  expect(stepSources(item({ kind: "web_fetch", args: '{"url":"https://www.github.com/willccbb/verifiers"}' }))).toEqual([
    "github.com",
  ]);
  expect(stepSources(item({ kind: "fetch", args: '{"urls":["https://a.com/x","http://a.com/y","https://b.io"]}' }))).toEqual([
    "a.com",
    "b.io",
  ]);
  expect(stepSources(item({ kind: "read", args: '{"path":"a.ts"}' }))).toEqual([]);
  expect(stepSources(item({ kind: "web_fetch" }))).toEqual([]);
});

test("truncates long details", () => {
  const long = "a/".repeat(60);
  const { detail } = operationLabel(item({ kind: "read", args: JSON.stringify({ path: long }) }));
  expect(detail).not.toBeNull();
  expect(detail!.length).toBeLessThanOrEqual(64);
  expect(detail!.endsWith("…")).toBe(true);
});
