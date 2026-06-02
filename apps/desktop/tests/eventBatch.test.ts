import { expect, test } from "bun:test";
import { createAnimationFrameBatcher } from "../src/lib/eventBatch.ts";

function manualScheduler() {
  let pending: (() => void) | null = null;
  return {
    schedule: (cb: () => void) => {
      pending = cb;
      return 1;
    },
    cancel: () => {
      pending = null;
    },
    tick: () => {
      const cb = pending;
      pending = null;
      cb?.();
    },
    hasPending: () => pending !== null,
  };
}

test("flushes all events enqueued within a frame in one batch, in order", () => {
  const flushes: number[][] = [];
  const s = manualScheduler();
  const batcher = createAnimationFrameBatcher<number>((events) => flushes.push(events), {
    schedule: s.schedule,
    cancel: s.cancel,
  });

  batcher.enqueue(1);
  batcher.enqueue(2);
  batcher.enqueue(3);
  expect(flushes).toEqual([]); // nothing flushed until the frame fires

  s.tick();
  expect(flushes).toEqual([[1, 2, 3]]);
});

test("schedules a single frame per burst, then re-arms on the next enqueue", () => {
  const flushes: number[][] = [];
  const s = manualScheduler();
  const batcher = createAnimationFrameBatcher<number>((events) => flushes.push(events), {
    schedule: s.schedule,
    cancel: s.cancel,
  });

  batcher.enqueue(1);
  batcher.enqueue(2);
  s.tick();
  batcher.enqueue(3);
  s.tick();

  expect(flushes).toEqual([[1, 2], [3]]);
});

test("fallback timer flushes when rAF never fires (backgrounded window)", () => {
  // Simulates a backgrounded/occluded window where requestAnimationFrame is
  // paused: the frame scheduler is captured but never ticked. The timeout
  // fallback must still flush so SSE events render without a manual reload.
  const flushes: number[][] = [];
  const frame = manualScheduler();
  const timer = manualScheduler();
  const batcher = createAnimationFrameBatcher<number>((events) => flushes.push(events), {
    schedule: frame.schedule,
    cancel: frame.cancel,
    scheduleFallback: timer.schedule,
    cancelFallback: timer.cancel,
  });

  batcher.enqueue(1);
  batcher.enqueue(2);
  expect(flushes).toEqual([]);

  timer.tick(); // rAF never fired; fallback fires
  expect(flushes).toEqual([[1, 2]]);
  expect(frame.hasPending()).toBe(false); // frame cancelled to avoid double-flush
});

test("frame and fallback never double-flush the same batch", () => {
  const flushes: number[][] = [];
  const frame = manualScheduler();
  const timer = manualScheduler();
  const batcher = createAnimationFrameBatcher<number>((events) => flushes.push(events), {
    schedule: frame.schedule,
    cancel: frame.cancel,
    scheduleFallback: timer.schedule,
    cancelFallback: timer.cancel,
  });

  batcher.enqueue(1);
  frame.tick(); // frame wins
  expect(flushes).toEqual([[1]]);
  expect(timer.hasPending()).toBe(false); // fallback cancelled

  timer.tick(); // stale tick is a no-op
  expect(flushes).toEqual([[1]]);
});

test("dispose cancels the pending frame and drops the buffer (no flush)", () => {
  const flushes: number[][] = [];
  const s = manualScheduler();
  const batcher = createAnimationFrameBatcher<number>((events) => flushes.push(events), {
    schedule: s.schedule,
    cancel: s.cancel,
  });

  batcher.enqueue(1);
  batcher.dispose();
  expect(s.hasPending()).toBe(false);
  s.tick();
  expect(flushes).toEqual([]);
});
