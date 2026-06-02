/** Coalesces a high-frequency event stream onto animation frames.
 *
 *  The SSE chat stream delivers one line per token/tool delta. Dispatching
 *  each line straight into the store produces one React commit per delta —
 *  a burst of N deltas in a frame becomes N renders. This batcher buffers
 *  events and flushes the whole batch once per frame, so the render cadence
 *  is decoupled from the network read cadence (React batches the setState
 *  calls inside the single rAF callback into one commit).
 *
 *  Dropping the buffer on dispose is safe: the stream cursor only advances
 *  when an event is applied, so anything buffered-but-unflushed is replayed
 *  on the next reconnect rather than lost.
 *
 *  CORRECTNESS over rAF: a browser/Electron window that is backgrounded,
 *  occluded, or minimized THROTTLES OR PAUSES requestAnimationFrame. If the
 *  flush only rode rAF, queued SSE events would pile up unrendered until the
 *  window was refocused or reloaded — the "I have to reload to see updates"
 *  bug. So each enqueue races a frame (smooth ~16ms cadence when visible)
 *  against a timeout fallback that still fires when rAF is paused; whichever
 *  runs first flushes and cancels the other.
 */
const FALLBACK_FLUSH_MS = 100;

export interface EventBatcher<T> {
  enqueue: (event: T) => void;
  dispose: () => void;
}

interface BatcherOptions {
  schedule?: (callback: () => void) => number;
  cancel?: (handle: number) => void;
  scheduleFallback?: (callback: () => void) => number;
  cancelFallback?: (handle: number) => void;
}

export function createAnimationFrameBatcher<T>(
  flush: (events: T[]) => void,
  options: BatcherOptions = {},
): EventBatcher<T> {
  const schedule = options.schedule ?? ((cb) => requestAnimationFrame(cb));
  const cancel = options.cancel ?? ((handle) => cancelAnimationFrame(handle));
  const scheduleFallback =
    options.scheduleFallback ?? ((cb) => setTimeout(cb, FALLBACK_FLUSH_MS) as unknown as number);
  const cancelFallback = options.cancelFallback ?? ((handle) => clearTimeout(handle));

  let queue: T[] = [];
  let frame: number | null = null;
  let fallback: number | null = null;

  const clearTimers = () => {
    if (frame !== null) {
      cancel(frame);
      frame = null;
    }
    if (fallback !== null) {
      cancelFallback(fallback);
      fallback = null;
    }
  };

  const run = () => {
    clearTimers();
    const batch = queue;
    queue = [];
    flush(batch);
  };

  return {
    enqueue(event) {
      queue.push(event);
      if (frame === null) frame = schedule(run);
      if (fallback === null) fallback = scheduleFallback(run);
    },
    dispose() {
      clearTimers();
      queue = [];
    },
  };
}
