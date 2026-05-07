import { expect, test } from "bun:test";
import { advancedMemoryTabsVisible } from "../src/lib/memoryTabs.js";

test("shows advanced tabs when the row is expanded", () => {
  expect(advancedMemoryTabsVisible("search", true)).toBe(true);
});

test("keeps advanced tabs visible for an active advanced pane", () => {
  expect(advancedMemoryTabsVisible("cleanup", false)).toBe(true);
});

test("collapses advanced tabs for primary panes", () => {
  expect(advancedMemoryTabsVisible("facts", false)).toBe(false);
});

