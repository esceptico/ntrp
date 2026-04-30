import { expect, test } from "bun:test";
import { truncateText } from "./utils.js";

test("truncateText handles zero and negative widths", () => {
  expect(truncateText("abcdef", 0)).toBe("");
  expect(truncateText("abcdef", -1)).toBe("");
});

test("truncateText truncates narrow positive widths", () => {
  expect(truncateText("abcdef", 2)).toBe("..");
  expect(truncateText("abcdef", 4)).toBe("a...");
});
