import { expect, test } from "bun:test";
import { MEMORY_TABS, memoryTabLabels } from "../src/lib/memoryTabs.js";

test("memory modal exposes explicit knowledge surfaces", () => {
  expect(MEMORY_TABS.map((tab) => tab.id)).toEqual(["overview", "library", "review", "activation"]);
});

test("memory tab labels stay short enough for modal navigation", () => {
  expect(memoryTabLabels().map((tab) => tab.label)).toEqual(["Overview", "Library", "Review", "Activation"]);

  for (const tab of memoryTabLabels()) {
    expect(tab.label.length).toBeLessThanOrEqual(10);
  }
});
