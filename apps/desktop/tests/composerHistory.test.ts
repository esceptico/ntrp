import { expect, test } from "bun:test";
import { recallHistory, type HistoryState } from "@/features/chat/lib/composerHistory";

const sent = ["first", "second", "third"];

function fresh(draft: string): HistoryState {
  return { historyIndex: null, draft, stashedDraft: "" };
}

test("ArrowUp from fresh stashes the draft and shows the newest message", () => {
  const r = recallHistory(fresh("in progress"), "up", sent);
  expect(r.value).toBe("third");
  expect(r.historyIndex).toBe(2);
  expect(r.stashedDraft).toBe("in progress");
});

test("repeated ArrowUp walks toward older messages and clamps at the oldest", () => {
  const step1 = recallHistory(fresh("draft"), "up", sent);
  const step2 = recallHistory({ ...step1, draft: step1.value }, "up", sent);
  expect(step2.value).toBe("second");
  expect(step2.historyIndex).toBe(1);
  expect(step2.stashedDraft).toBe("draft");

  const step3 = recallHistory({ ...step2, draft: step2.value }, "up", sent);
  expect(step3.value).toBe("first");
  expect(step3.historyIndex).toBe(0);

  // Already at the oldest — clamp (no-op), draft preserved.
  const clamp = recallHistory({ ...step3, draft: step3.value }, "up", sent);
  expect(clamp.value).toBe("first");
  expect(clamp.historyIndex).toBe(0);
  expect(clamp.stashedDraft).toBe("draft");
});

test("ArrowDown walks toward newer messages", () => {
  // Sitting on the oldest with a stash from earlier.
  const state: HistoryState = { historyIndex: 0, draft: "first", stashedDraft: "draft" };
  const r = recallHistory(state, "down", sent);
  expect(r.value).toBe("second");
  expect(r.historyIndex).toBe(1);
  expect(r.stashedDraft).toBe("draft");
});

test("ArrowDown past the newest restores the stash and exits history mode", () => {
  const state: HistoryState = { historyIndex: 2, draft: "third", stashedDraft: "my draft" };
  const r = recallHistory(state, "down", sent);
  expect(r.value).toBe("my draft");
  expect(r.historyIndex).toBeNull();
  expect(r.stashedDraft).toBe("my draft");
});

test("ArrowDown when not in history mode is a no-op", () => {
  const r = recallHistory(fresh("draft"), "down", sent);
  expect(r.value).toBe("draft");
  expect(r.historyIndex).toBeNull();
});

test("empty history is a no-op in both directions", () => {
  const up = recallHistory(fresh("draft"), "up", []);
  expect(up.value).toBe("draft");
  expect(up.historyIndex).toBeNull();

  const down = recallHistory({ historyIndex: 0, draft: "x", stashedDraft: "d" }, "down", []);
  expect(down.value).toBe("x");
  expect(down.historyIndex).toBe(0);
});
