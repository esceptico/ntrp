import { expect, test } from "bun:test";
import { memoryTabLabels } from "./memoryTabs.js";

test("uses compact memory tab labels for narrow dialogs", () => {
  const labels = memoryTabLabels(68);

  expect(labels.recall).toBe("1");
  expect(labels.facts).toBe("3");
  expect(labels.events).toBe("6");
});

test("uses readable memory tab labels when there is room", () => {
  const labels = memoryTabLabels(100);

  expect(labels.recall).toBe("Find");
  expect(labels.facts).toBe("Facts");
  expect(labels.observations).toBe("Pat");
});
