import {
  cloneElement,
  isValidElement,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import { DURATION_POPOVER, EASE_DECELERATE, EASE_OUT, MOTION } from "../../lib/tokens/motion";

type Side = "top" | "bottom" | "left" | "right";

const GAP = 6;
/** Open delay so the tip doesn't flash on every passing hover; hide is fast. */
const OPEN_DELAY_MS = 350;
const HIDE_DELAY_MS = 60;
/** Once any tooltip has just been open, the next one within this window opens
 *  instantly — no delay, no entrance animation. Moving across a toolbar then
 *  feels immediate instead of re-paying the 350ms intent delay every hover
 *  (Emil Kowalski's "skip the delay on subsequent hovers"). */
const INSTANT_GRACE_MS = 300;
let lastTooltipClosedAt = 0;

interface TooltipProps {
  label: ReactNode;
  /** A single focusable element. Handlers + ref are merged onto it directly —
   *  no wrapper, so the tooltip never perturbs the trigger's layout. */
  children: ReactElement;
  side?: Side;
  className?: string;
}

/**
 * Passive hover/focus hint — the animated replacement for bare `title=""`.
 * Clones its child to attach listeners and a measuring ref in place (no
 * wrapper span). Shares HoverPopover's house entrance and portal/re-measure
 * scaffolding. Give the child its own aria-label; the tooltip is supplementary.
 */
export function Tooltip({ label, children, side = "top", className }: TooltipProps) {
  const triggerRef = useRef<HTMLElement>(null);
  const showTimer = useRef<number | null>(null);
  const hideTimer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [instant, setInstant] = useState(false);
  const [coords, setCoords] = useState<Record<string, number> | null>(null);
  const tipId = useId();

  const clear = () => {
    if (showTimer.current !== null) window.clearTimeout(showTimer.current);
    if (hideTimer.current !== null) window.clearTimeout(hideTimer.current);
    showTimer.current = null;
    hideTimer.current = null;
  };
  const show = () => {
    clear();
    if (Date.now() - lastTooltipClosedAt < INSTANT_GRACE_MS) {
      setInstant(true);
      setOpen(true);
    } else {
      setInstant(false);
      showTimer.current = window.setTimeout(() => setOpen(true), OPEN_DELAY_MS);
    }
  };
  const hide = () => {
    clear();
    hideTimer.current = window.setTimeout(() => {
      setOpen(false);
      lastTooltipClosedAt = Date.now();
    }, HIDE_DELAY_MS);
  };

  // Cancel any pending show/hide on unmount — a stray hide timer would
  // otherwise fire later and stamp `lastTooltipClosedAt`, making the next
  // unrelated hover open with no delay.
  useLayoutEffect(() => clear, []);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const r = triggerRef.current!.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (side === "top") setCoords({ bottom: window.innerHeight - r.top + GAP, left: cx });
      else if (side === "bottom") setCoords({ top: r.bottom + GAP, left: cx });
      else if (side === "left") setCoords({ right: window.innerWidth - r.left + GAP, top: cy });
      else setCoords({ left: r.right + GAP, top: cy });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, side]);

  const axis = side === "left" || side === "right" ? "x" : "y";
  const sign = side === "top" || side === "left" ? 1 : -1;
  const center = side === "top" || side === "bottom" ? "translateX(-50%)" : "translateY(-50%)";
  const origin =
    side === "top"
      ? "bottom center"
      : side === "bottom"
        ? "top center"
        : side === "left"
          ? "center right"
          : "center left";

  // Merge our listeners + ref onto the child without a wrapper element.
  const childProps = children.props as Record<string, unknown>;
  const compose =
    (orig: unknown, ours: () => void) =>
    (e: unknown) => {
      if (typeof orig === "function") (orig as (ev: unknown) => void)(e);
      ours();
    };
  const setRef = (node: HTMLElement | null) => {
    triggerRef.current = node;
    const orig = (childProps as { ref?: unknown }).ref;
    if (typeof orig === "function") (orig as (n: HTMLElement | null) => void)(node);
    else if (orig && typeof orig === "object") (orig as { current: unknown }).current = node;
  };
  const trigger = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        ref: setRef,
        onMouseEnter: compose(childProps.onMouseEnter, show),
        onMouseLeave: compose(childProps.onMouseLeave, hide),
        onFocus: compose(childProps.onFocus, show),
        onBlur: compose(childProps.onBlur, hide),
        "aria-describedby": open ? tipId : childProps["aria-describedby"],
      })
    : children;

  return (
    <>
      {trigger}
      {createPortal(
        <AnimatePresence>
          {open && coords && (
            <motion.div
              id={tipId}
              role="tooltip"
              initial={{ opacity: 0, scale: 0.96, [axis]: sign * 3 }}
              animate={{ opacity: 1, scale: 1, [axis]: 0 }}
              exit={{ opacity: 0, scale: 0.96, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
              transition={
                instant ? { duration: 0 } : { duration: DURATION_POPOVER, ease: EASE_DECELERATE }
              }
              style={{
                position: "fixed",
                ...coords,
                zIndex: 70,
                transform: center,
                transformOrigin: origin,
              }}
              className={clsx(
                "surface-panel surface-popover pointer-events-none max-w-[min(18rem,80vw)] px-2 py-1 text-xs leading-snug text-ink",
                className,
              )}
            >
              {label}
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </>
  );
}
