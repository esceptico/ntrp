import { expect, test } from "bun:test";
import { visibleMessageIds } from "../src/lib/messageVisibility.js";

test("hides reasoning without hiding tool activity", () => {
  expect(visibleMessageIds({
    ids: ["user-1", "reasoning-1", "activity-1", "assistant-1"],
    roles: ["user", "reasoning", "activity", "assistant"],
  })).toEqual(["user-1", "activity-1", "assistant-1"]);
});
