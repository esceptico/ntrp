import { expect, test } from "bun:test";
import { createStallWatchdog } from "../src/lib/streamWatchdog.ts";

function harness(stallMs: number, checkMs: number) {
  let nowMs = 0;
  let tick: (() => void) | null = null;
  const stalls: number[] = [];
  const watchdog = createStallWatchdog({
    stallMs,
    checkMs,
    onStall: () => stalls.push(nowMs),
    now: () => nowMs,
    setInterval: (cb) => {
      tick = cb;
      return 1;
    },
    clearInterval: () => {
      tick = null;
    },
  });
  return {
    watchdog,
    stalls,
    advance: (ms: number) => {
      nowMs += ms;
    },
    check: () => tick?.(),
    active: () => tick !== null,
  };
}

test("fires onStall after silence exceeds the threshold", () => {
  const h = harness(15_000, 5_000);
  h.advance(5_000);
  h.check();
  expect(h.stalls.length).toBe(0); // 5s < 15s
  h.advance(11_000); // 16s total silence
  h.check();
  expect(h.stalls.length).toBe(1);
});

test("bump resets the silence clock so a live stream never stalls", () => {
  const h = harness(15_000, 5_000);
  for (let i = 0; i < 5; i++) {
    h.advance(5_000); // keepalive cadence
    h.watchdog.bump();
    h.check();
  }
  expect(h.stalls.length).toBe(0);
});

test("dispose stops checking", () => {
  const h = harness(15_000, 5_000);
  h.watchdog.dispose();
  expect(h.active()).toBe(false);
  h.advance(60_000);
  h.check();
  expect(h.stalls.length).toBe(0);
});
