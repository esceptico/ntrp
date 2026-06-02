import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
} from "react";

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

export interface MutationState {
  busy: boolean;
  error: string | null;
  run: (fn: () => Promise<void>) => Promise<void>;
}

/** Shared busy/error state for save+delete handlers. */
export function useMutationState(): MutationState {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
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

/** Roving-index keyboard nav for a list of options. Pass `items.length`
 *  and either controlled `{index, setIndex}` or omit both to use internal
 *  state. Returns `{index, setIndex, onKeyDown}` — wire `onKeyDown` to the
 *  input/container that owns focus.
 *
 *  Handles ArrowUp/ArrowDown (clamped to [0, length-1]) and Enter
 *  (invokes `onEnter(index)`). Escape/Backspace are NOT handled — owners
 *  with drill-down or close semantics keep that logic. */
export function useListNav(
  length: number,
  onEnter: (index: number) => void,
  controlled?: { index: number; setIndex: (i: number) => void },
): {
  index: number;
  setIndex: (i: number) => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLElement>) => void;
} {
  const [internal, setInternal] = useState(0);
  const rawIndex = controlled ? controlled.index : internal;
  const setIndex = controlled ? controlled.setIndex : setInternal;
  const last = Math.max(0, length - 1);
  const index = Math.min(Math.max(rawIndex, 0), last);

  // Converge controlled state when it falls out of bounds (shorter list after
  // a filter change). Uncontrolled state can't drift past `last` because
  // setIndex calls below all clamp.
  useEffect(() => {
    if (rawIndex !== index) setIndex(index);
  }, [rawIndex, index, setIndex]);

  const enterRef = useRef(onEnter);
  enterRef.current = onEnter;

  const onKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLElement>) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setIndex(Math.min(index + 1, last));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setIndex(Math.max(index - 1, 0));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        enterRef.current(index);
      }
    },
    [index, last, setIndex],
  );

  return { index, setIndex, onKeyDown };
}

/** Calls `onClose` when a `mousedown` lands outside the element referenced
 *  by `ref`. No-op when `open` is false (keeps the listener off when it
 *  isn't needed). Used by popovers, dropdowns, and command pickers. */
export function useOutsideClick(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  onClose: () => void,
): void {
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, ref, onClose]);
}

/** Invokes `callback` once on mount, then on each `intervalMs` tick
 *  (skipped when the document is hidden), and again on every visibility
 *  transition back to "visible". The latest `callback` is captured in a
 *  ref so consumers don't need to memoize it.
 *
 *  Use for background data refresh that should pause when the user
 *  switches away from the window (saves API calls, respects user focus). */
export function useVisibilityPoll(
  callback: () => void | Promise<void>,
  intervalMs: number,
): void {
  const cbRef = useRef(callback);
  cbRef.current = callback;
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (!cancelled) void cbRef.current();
    };
    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, intervalMs);
    const onVis = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [intervalMs]);
}
