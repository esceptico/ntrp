import { expect, test } from "bun:test";
import { awaitingFirstRunOutput } from "../src/lib/runIndicators.ts";

test("thinking indicator waits only after a visible user turn", () => {
  expect(awaitingFirstRunOutput(false, { role: "user" })).toBe(false);
  expect(awaitingFirstRunOutput(true, { role: "user" })).toBe(true);
  expect(awaitingFirstRunOutput(true, { role: "user", isMeta: true })).toBe(false);
  expect(awaitingFirstRunOutput(true, { role: "reasoning" })).toBe(false);
  expect(awaitingFirstRunOutput(true, { role: "activity" })).toBe(false);
  expect(awaitingFirstRunOutput(true, null)).toBe(false);
});
