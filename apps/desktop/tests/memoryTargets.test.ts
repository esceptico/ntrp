import { expect, test } from "bun:test";
import { memoryTargetId, nextMemoryTarget, upsertById } from "../src/lib/memoryTargets.js";

test("increments target nonce even for the same item", () => {
  const first = nextMemoryTarget(null, { id: 7, text: "one" });
  const second = nextMemoryTarget(first, { id: 7, text: "one" });

  expect(first.nonce).toBe(1);
  expect(second.nonce).toBe(2);
});

test("extracts target ids from object and numeric targets", () => {
  expect(memoryTargetId(nextMemoryTarget(null, { id: 12 }))).toBe(12);
  expect(memoryTargetId(nextMemoryTarget(null, 34))).toBe(34);
  expect(memoryTargetId(null)).toBeNull();
});

test("upserts target item at the top without duplicates", () => {
  expect(upsertById([{ id: 1 }, { id: 2 }], { id: 2 })).toEqual([{ id: 2 }, { id: 1 }]);
});

