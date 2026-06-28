import { expect, test } from "bun:test";
import { awaitingFirstRunOutput } from "@/lib/runIndicators";

test("thinking indicator waits only after a visible user turn", () => {
  expect(awaitingFirstRunOutput(false, [{ role: "user" }])).toBe(false);
  expect(awaitingFirstRunOutput(true, [{ role: "user" }])).toBe(true);
  expect(awaitingFirstRunOutput(true, [{ role: "user", isMeta: true }])).toBe(false);
  expect(awaitingFirstRunOutput(true, [{ role: "reasoning" }])).toBe(false);
  expect(awaitingFirstRunOutput(true, [])).toBe(false);
});

test("thinking indicator stays visible through pre-answer activity", () => {
  expect(
    awaitingFirstRunOutput(true, [
      { role: "user" },
      { role: "reasoning" },
      { role: "activity" },
    ]),
  ).toBe(true);
  expect(awaitingFirstRunOutput(true, [{ role: "user" }, { role: "assistant" }])).toBe(false);
});
