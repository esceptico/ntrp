import { expect, test } from "bun:test";
import { sliderVariant } from "@/features/settings/components/Field";

test("sliderVariant: small discrete ranges use pips, large ones use a scrubber", () => {
  // ≤16 pips → pips (clicking a pip is exact)
  expect(sliderVariant(1, 16, 1)).toBe("pips"); // 16 steps — Agent depth
  expect(sliderVariant(0, 4, 1)).toBe("pips"); // 5 steps
  // >16 pips → scrubber
  expect(sliderVariant(1, 17, 1)).toBe("scrubber"); // 17 steps — just past the breakpoint
  expect(sliderVariant(0, 100, 1)).toBe("scrubber"); // percent fields
  expect(sliderVariant(256, 8000, 64)).toBe("scrubber"); // token counts
  expect(sliderVariant(10, 1000, 10)).toBe("scrubber"); // max messages
});

test("sliderVariant handles a degenerate single-value range", () => {
  expect(sliderVariant(1, 1, 1)).toBe("pips"); // one pip, no crash
});
