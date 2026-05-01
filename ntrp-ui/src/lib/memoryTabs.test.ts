import { expect, test } from "bun:test";
import { memoryTabLabels } from "./memoryTabs.js";

test("uses compact memory tab labels for narrow dialogs", () => {
  const labels = memoryTabLabels(68);

  expect(labels.overview).toBe("1");
  expect(labels.events).toBe("8");
});

test("uses readable memory tab labels when there is room", () => {
  const labels = memoryTabLabels(100);

  expect(labels.overview).toBe("Home");
  expect(labels.observations).toBe("Pat");
});
