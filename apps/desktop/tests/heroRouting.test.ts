import { expect, test } from "bun:test";
import { routeHeroInput } from "@/features/home/lib/heroRouting";

const ctx = {
  sessions: [{ session_id: "s1", name: "counsel requirements" }],
  slices: [{ key: "o-1a", title: "O-1A" }],
  automations: [{ task_id: "t1", name: "morning-digest" }],
  skills: [{ name: "research", description: "" }],
};

test("plain text routes to chat first", () => {
  const s = routeHeroInput("book flights", ctx);
  expect(s[0].kind).toBe("chat");
});

test("prefix matches surface slices, sessions, automations", () => {
  const s = routeHeroInput("o-1", ctx);
  expect(s.some((x) => x.kind === "slice" && x.ref === "o-1a")).toBe(true);
  const t = routeHeroInput("morning", ctx);
  expect(t.some((x) => x.kind === "automation" && x.ref === "t1")).toBe(true);
});

test("empty query still returns a chat suggestion with empty label", () => {
  const s = routeHeroInput("", ctx);
  expect(s.length).toBe(1);
  expect(s[0]).toEqual({ kind: "chat", label: "", ref: "" });
});

test("chat suggestion is always first even when other kinds match", () => {
  const s = routeHeroInput("research", ctx);
  expect(s[0].kind).toBe("chat");
  expect(s.some((x) => x.kind === "skill" && x.ref === "research")).toBe(true);
});

test("matches session names case-insensitively", () => {
  const s = routeHeroInput("COUNSEL", ctx);
  expect(s.some((x) => x.kind === "session" && x.ref === "s1")).toBe(true);
});

test("caps suggestions at 6", () => {
  const manySlices = Array.from({ length: 10 }, (_, i) => ({ key: `slice-${i}`, title: `Slice ${i}` }));
  const s = routeHeroInput("slice", { ...ctx, slices: manySlices });
  expect(s.length).toBeLessThanOrEqual(6);
});

test("no matches returns only the chat suggestion", () => {
  const s = routeHeroInput("zzz-nonexistent-zzz", ctx);
  expect(s).toEqual([{ kind: "chat", label: "zzz-nonexistent-zzz", ref: "" }]);
});
