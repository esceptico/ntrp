import { expect, test } from "bun:test";
import { formatLoopCountdown } from "../src/lib/loops.js";

test("formats loop countdown", () => {
  expect(formatLoopCountdown(1_060_000, 1_000_000)).toBe("1m");
  expect(formatLoopCountdown(1_001_000, 1_000_000)).toBe("<1m");
  expect(formatLoopCountdown(1_000_000 + 90 * 60_000, 1_000_000)).toBe("1h 30m");
  expect(formatLoopCountdown(1_000_000 + 25 * 60 * 60_000, 1_000_000)).toBe("1d");
});
