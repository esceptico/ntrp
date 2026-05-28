import { expect, test } from "bun:test";
import { MEMORY_TABS, memoryTabLabels } from "./memoryTabs.js";

test("uses compact memory tab labels for narrow dialogs", () => {
  const labels = memoryTabLabels(68);

  expect(labels.today).toBe("1");
  expect(labels.graph).toBe("2");
  expect(labels.skills).toBe("3");
  expect(labels.search).toBe("4");
});

test("uses readable memory tab labels when there is room", () => {
  const labels = memoryTabLabels(100);

  expect(labels.today).toBe("Today");
  expect(labels.graph).toBe("Graph");
  expect(labels.skills).toBe("Skills");
  expect(labels.search).toBe("Search");
});

test("memory tabs expose the spec surfaces", () => {
  expect(MEMORY_TABS).toEqual(["today", "graph", "skills", "search"]);
});
