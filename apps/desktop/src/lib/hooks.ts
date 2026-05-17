import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

/** Returns `[flag, fire]`. `fire()` flips the flag true and schedules
 *  it back to false after `durationMs`. The pending timeout is cleared
 *  if the component unmounts (or `fire()` is called again) so the flag
 *  never updates after unmount — fixing the classic "setCopied(false)
 *  after the button is gone" warning. */
export function useTimeoutFlag(durationMs: number): readonly [boolean, () => void] {
  const [flag, setFlag] = useState(false);
  const timerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    [],
  );
  const fire = useCallback(() => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    setFlag(true);
    timerRef.current = window.setTimeout(() => {
      setFlag(false);
      timerRef.current = null;
    }, durationMs);
  }, [durationMs]);
  return [flag, fire] as const;
}

/** Fire `onEscape` while `active` is true. Replaces the boilerplate
 *  useEffect + addEventListener("keydown") + Escape branch that every
 *  modal/popover/picker would otherwise hand-roll. The callback is held
 *  in a ref so callers don't need to memoize it. */
export function useEscapeKey(onEscape: () => void, active = true): void {
  const ref = useRef(onEscape);
  useEffect(() => {
    ref.current = onEscape;
  }, [onEscape]);
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") ref.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);
}

/** Tracks whether the component is still mounted. Use to gate state updates
 *  that follow an `await` whose resolution could outlive the component
 *  (typical case: a delete handler whose `onDeleted` callback unmounts the
 *  detail pane before our `finally` runs). */
export function useMountedRef(): RefObject<boolean> {
  const ref = useRef(true);
  useEffect(
    () => () => {
      ref.current = false;
    },
    [],
  );
  return ref;
}

export interface MutationState {
  busy: boolean;
  error: string | null;
  run: (fn: () => Promise<void>) => Promise<void>;
}

/** Shared busy/error state for save+delete handlers. setBusy/setError calls
 *  are guarded by the mounted ref so post-unmount updates don't warn. */
export function useMutationState(mounted: RefObject<boolean>): MutationState {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    if (mounted.current) {
      setBusy(true);
      setError(null);
    }
    try {
      await fn();
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return { busy, error, run };
}

/** Forces a re-render every `intervalMs` ms. Use to refresh relative-time
 *  labels ("2m ago") without each consumer wiring its own timer. */
export function useTimeTicker(intervalMs = 30_000): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}
