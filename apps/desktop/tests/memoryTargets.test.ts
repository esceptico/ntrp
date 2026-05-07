import { expect, test } from "bun:test";
import {
  memoryTargetId,
  memoryTargetItem,
  nextMemoryTarget,
  selectedMemoryItem,
  upsertById,
} from "../src/lib/memoryTargets.js";

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

test("uses a loaded record when available and falls back to the numeric id", () => {
  const records = new Map([[12, { id: 12, text: "loaded" }]]);

  expect(memoryTargetItem(records, 12)).toEqual({ id: 12, text: "loaded" });
  expect(memoryTargetItem(records, 34)).toBe(34);
});

test("upserts target item at the top without duplicates", () => {
  expect(upsertById([{ id: 1 }, { id: 2 }], { id: 2 })).toEqual([{ id: 2 }, { id: 1 }]);
});

test("keeps selected detail when a refreshed list does not include the target", () => {
  const refreshed = [{ id: 1, text: "visible list item" }];
  const detail = { id: 2, text: "selected supporting fact" };

  expect(selectedMemoryItem(refreshed, 2, detail)).toEqual(detail);
  expect(selectedMemoryItem(refreshed, 1, detail)).toEqual(refreshed[0]);
  expect(selectedMemoryItem(refreshed, null, detail)).toBeNull();
});
