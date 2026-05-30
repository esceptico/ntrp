/** Detects a silently-stalled SSE stream and triggers a reconnect.
 *
 *  The server sends a keepalive every few seconds, so a healthy connection
 *  bumps the watchdog at least that often. A half-open TCP stream (peer gone
 *  but no FIN) delivers neither events nor keepalives yet never errors — the
 *  read just hangs until the OS gives up, which presents as a frozen UI that
 *  only a manual reload fixes. The watchdog notices the silence and forces a
 *  reconnect; the stream cursor makes reconnect lossless.
 */
export interface StallWatchdog {
  /** Call on every received event or keepalive — proof the stream is alive. */
  bump: () => void;
  dispose: () => void;
}

interface WatchdogOptions {
  /** Silence past this many ms is treated as a stall. */
  stallMs: number;
  /** How often to check for silence. */
  checkMs: number;
  onStall: () => void;
  now?: () => number;
  setInterval?: (callback: () => void, ms: number) => number;
  clearInterval?: (handle: number) => void;
}

export function createStallWatchdog(options: WatchdogOptions): StallWatchdog {
  const now = options.now ?? (() => Date.now());
  const schedule =
    options.setInterval ?? ((cb, ms) => globalThis.setInterval(cb, ms) as unknown as number);
  const clear = options.clearInterval ?? ((handle) => globalThis.clearInterval(handle));

  let lastSeen = now();
  const handle = schedule(() => {
    if (now() - lastSeen >= options.stallMs) {
      // Reset before firing so a single stall doesn't retrigger every tick
      // while the reconnect is in flight.
      lastSeen = now();
      options.onStall();
    }
  }, options.checkMs);

  return {
    bump() {
      lastSeen = now();
    },
    dispose() {
      clear(handle);
    },
  };
}
