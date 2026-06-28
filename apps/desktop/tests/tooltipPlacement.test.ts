import { expect, test } from "bun:test";
import { calculateTooltipPlacement } from "@/components/ui/tooltipPlacement";

test("top tooltip near the right edge clamps inside the viewport", () => {
  const placement = calculateTooltipPlacement({
    preferredSide: "top",
    trigger: { top: 120, right: 398, bottom: 142, left: 376, width: 22, height: 22 },
    tooltip: { width: 120, height: 32 },
    viewport: { width: 400, height: 300 },
    gap: 6,
    safeMargin: 8,
  });

  expect(placement.side).toBe("top");
  expect(placement.left).toBe(272);
  expect(placement.left + 120).toBeLessThanOrEqual(392);
});

test("top tooltip flips below when there is no room above", () => {
  const placement = calculateTooltipPlacement({
    preferredSide: "top",
    trigger: { top: 10, right: 72, bottom: 32, left: 50, width: 22, height: 22 },
    tooltip: { width: 100, height: 32 },
    viewport: { width: 400, height: 300 },
    gap: 6,
    safeMargin: 8,
  });

  expect(placement.side).toBe("bottom");
  expect(placement.top).toBe(38);
});

test("right tooltip clamps vertically inside the viewport", () => {
  const placement = calculateTooltipPlacement({
    preferredSide: "right",
    trigger: { top: 278, right: 54, bottom: 300, left: 32, width: 22, height: 22 },
    tooltip: { width: 96, height: 56 },
    viewport: { width: 400, height: 320 },
    gap: 6,
    safeMargin: 8,
  });

  expect(placement.side).toBe("right");
  expect(placement.top).toBe(256);
  expect(placement.top + 56).toBeLessThanOrEqual(312);
});
