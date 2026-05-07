import { expect, test } from "bun:test";
import { visibleMessageIds } from "../src/lib/messageVisibility.js";

test("keeps reasoning visible by default", () => {
  expect(visibleMessageIds({
    ids: ["user-1", "reasoning-1", "activity-1", "assistant-1"],
    roles: ["user", "reasoning", "activity", "assistant"],
    showReasoning: true,
  })).toEqual(["user-1", "reasoning-1", "activity-1", "assistant-1"]);
});

test("hides reasoning without hiding tool activity", () => {
  expect(visibleMessageIds({
    ids: ["user-1", "reasoning-1", "activity-1", "assistant-1"],
    roles: ["user", "reasoning", "activity", "assistant"],
    showReasoning: false,
  })).toEqual(["user-1", "activity-1", "assistant-1"]);
});
