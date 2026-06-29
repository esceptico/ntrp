import { expect, test } from "bun:test";
import { groupSummary, operationLabel, stepSources } from "@/features/chat/lib/operationLabel";
import type { ActivityItem } from "@/stores";

function item(over: Partial<ActivityItem> = {}): ActivityItem {
  return { id: "x", kind: "tool", target: "", ...over } as ActivityItem;
}

test("known tools get corpus-specific labels + category icons", () => {
  expect(operationLabel(item({ kind: "read_file" }))).toMatchObject({ verb: "Read", iconKey: "file" });
  expect(operationLabel(item({ kind: "bash" }))).toMatchObject({ verb: "Ran", iconKey: "terminal" });
  expect(operationLabel(item({ kind: "web_search" }))).toMatchObject({ verb: "Searched the web", iconKey: "globe" });
  expect(operationLabel(item({ kind: "web_fetch" }))).toMatchObject({ verb: "Fetched a page", iconKey: "globe" });
  expect(operationLabel(item({ kind: "emails" }))).toMatchObject({ verb: "Searched email", iconKey: "mail" });
  expect(operationLabel(item({ kind: "slack_search" }))).toMatchObject({ verb: "Searched Slack", iconKey: "slack" });
  expect(operationLabel(item({ kind: "slack_dms" }))).toMatchObject({ verb: "Listed Slack DMs", iconKey: "slack" });
  expect(operationLabel(item({ kind: "calendar" }))).toMatchObject({ verb: "Checked the calendar", iconKey: "calendar" });
  expect(operationLabel(item({ kind: "search_transcripts" }))).toMatchObject({ verb: "Searched transcripts", iconKey: "history" });
  expect(operationLabel(item({ kind: "memory_search" }))).toMatchObject({ verb: "Searched memory", iconKey: "brain" });
  expect(operationLabel(item({ kind: "load_tools" }))).toMatchObject({ verb: "Loaded tools", iconKey: "wrench" });
});

test("the corpus, not just the action, is in the label (search tools are distinguishable)", () => {
  const verbs = ["emails", "slack_search", "web_search", "search_transcripts", "memory_search"].map(
    (kind) => operationLabel(item({ kind })).verb,
  );
  // No two search tools share a label — the user can tell what was searched.
  expect(new Set(verbs).size).toBe(verbs.length);
});

test("unknown tools fall back to a humanized display_name + a category/dot icon", () => {
  // camelCase display_name is humanized (split + title-case, acronyms preserved).
  expect(operationLabel(item({ kind: "list_automations", displayName: "ListAutomations" })).verb).toBe(
    "List Automations",
  );
  expect(operationLabel(item({ kind: "slack_dms_x", displayName: "SlackDMs" })).verb).toBe("Slack DMs");
  // Truly unknown → humanized kind + the dot glyph (a real icon, never a bare dot).
  expect(operationLabel(item({ kind: "custom_thing" }))).toMatchObject({ verb: "Custom thing", iconKey: "dot" });
  // Category prefix still gives an icon even with no curated entry.
  expect(operationLabel(item({ kind: "slack_reactions" })).iconKey).toBe("slack");
});

test("short heuristic tokens don't bleed into longer words", () => {
  expect(operationLabel(item({ kind: "preview" })).verb).toBe("Preview");
  expect(operationLabel(item({ kind: "category" })).verb).toBe("Category");
  expect(operationLabel(item({ kind: "view_file" })).verb).toBe("Read");
});

test("detail comes from args, preferring path-like keys; partial JSON is safe", () => {
  expect(operationLabel(item({ kind: "read_file", args: '{"path":"ntrp/core/agent.py"}' })).detail).toBe(
    "ntrp/core/agent.py",
  );
  expect(operationLabel(item({ kind: "read_file", args: '{"path":' })).detail).toBeNull();
  expect(operationLabel(item({ kind: "read_file" })).detail).toBeNull();
});

test("groupSummary pluralizes with the tool's noun, else falls back to a count", () => {
  expect(groupSummary([item({ kind: "read_file" }), item({ kind: "read_file" }), item({ kind: "read_file" })])).toMatchObject({
    verb: "Read 3 files",
    iconKey: "file",
  });
  expect(groupSummary([item({ kind: "web_search" }), item({ kind: "web_search" })]).verb).toBe("Searched 2 searches");
  // No noun → "{label} · {n}".
  expect(groupSummary([item({ kind: "slack_dms" }), item({ kind: "slack_dms" })]).verb).toBe("Listed Slack DMs · 2");
});

test("stepSources extracts deduped hostnames from url/urls args", () => {
  expect(stepSources(item({ kind: "web_fetch", args: '{"url":"https://www.github.com/x"}' }))).toEqual(["github.com"]);
  expect(stepSources(item({ kind: "read_file", args: '{"path":"a.ts"}' }))).toEqual([]);
});
