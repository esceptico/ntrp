import { expect, test } from "bun:test";
import { groupConsecutiveCalls } from "@/features/chat/lib/trace";
import type { ActivityItem } from "@/stores";

function tool(id: string, kind: string, over: Partial<ActivityItem> = {}): ActivityItem {
  return { id, kind, target: kind, depth: 0, ...over } as ActivityItem;
}

test("collapses a run of >= 3 same-kind leaf calls into one group", () => {
  const rows = groupConsecutiveCalls([
    tool("a", "read"),
    tool("b", "read"),
    tool("c", "read"),
    tool("d", "read"),
  ]);
  expect(rows).toHaveLength(1);
  expect(rows[0].type).toBe("group");
  if (rows[0].type === "group") expect(rows[0].items).toHaveLength(4);
});

test("runs shorter than the threshold stay individual rows", () => {
  const rows = groupConsecutiveCalls([tool("a", "read"), tool("b", "read")]);
  expect(rows.map((r) => r.type)).toEqual(["item", "item"]);
});

test("only consecutive same-kind calls group; different kinds break the run", () => {
  const rows = groupConsecutiveCalls([
    tool("a", "read"),
    tool("b", "read"),
    tool("c", "bash"),
    tool("d", "read"),
    tool("e", "read"),
    tool("f", "read"),
  ]);
  // read,read (run 2 < 3) → two items; bash → item; read×3 → group.
  expect(rows.map((r) => r.type)).toEqual(["item", "item", "item", "group"]);
  if (rows[3].type === "group") expect(rows[3].items.map((i) => i.id)).toEqual(["d", "e", "f"]);
});

test("a different depth breaks the run (parent never folds in with siblings)", () => {
  const rows = groupConsecutiveCalls([
    tool("p", "read", { depth: 0 }),
    tool("c", "read", { depth: 1, parentToolId: "p" }),
    tool("q", "read", { depth: 0 }),
  ]);
  // No run of 3 at one depth → all individual.
  expect(rows.every((r) => r.type === "item")).toBe(true);
});

test("agents never group even when adjacent and same kind", () => {
  const rows = groupConsecutiveCalls([
    tool("a", "research", { semanticKind: "agent" }),
    tool("b", "research", { semanticKind: "agent" }),
    tool("c", "research", { semanticKind: "agent" }),
  ]);
  expect(rows.every((r) => r.type === "item")).toBe(true);
});
