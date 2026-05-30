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
 */
export interface EventBatcher<T> {
  enqueue: (event: T) => void;
  dispose: () => void;
}

interface BatcherOptions {
  schedule?: (callback: () => void) => number;
  cancel?: (handle: number) => void;
}

export function createAnimationFrameBatcher<T>(
  flush: (events: T[]) => void,
  options: BatcherOptions = {},
): EventBatcher<T> {
  const schedule = options.schedule ?? ((cb) => requestAnimationFrame(cb));
  const cancel = options.cancel ?? ((handle) => cancelAnimationFrame(handle));

  let queue: T[] = [];
  let handle: number | null = null;

  const run = () => {
    handle = null;
    const batch = queue;
    queue = [];
    flush(batch);
  };

  return {
    enqueue(event) {
      queue.push(event);
      if (handle === null) handle = schedule(run);
    },
    dispose() {
      if (handle !== null) {
        cancel(handle);
        handle = null;
      }
      queue = [];
    },
  };
}
