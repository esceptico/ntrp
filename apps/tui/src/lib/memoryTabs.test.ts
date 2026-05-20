import { expect, test } from "bun:test";
import { MEMORY_TABS, memoryTabLabels } from "./memoryTabs.js";

test("uses compact memory tab labels for narrow dialogs", () => {
  const labels = memoryTabLabels(68);

  expect(labels.overview).toBe("1");
  expect(labels.library).toBe("2");
  expect(labels.review).toBe("3");
  expect(labels.activation).toBe("4");
});

test("uses readable memory tab labels when there is room", () => {
  const labels = memoryTabLabels(100);

  expect(labels.overview).toBe("View");
  expect(labels.library).toBe("Types");
  expect(labels.review).toBe("Review");
  expect(labels.activation).toBe("Use");
});

test("memory tabs expose explicit knowledge surfaces", () => {
  expect(MEMORY_TABS).toEqual(["overview", "library", "review", "activation"]);
});
