import { useEffect, useRef, useState, type RefObject } from "react";

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
