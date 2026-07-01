import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type Ref } from "react";
import { motion, useMotionValue, animate, useReducedMotion } from "motion/react";
import clsx from "clsx";
import { SPRING_LAYOUT } from "@/lib/tokens/motion";

interface SwitchControlProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  size?: "sm" | "md";
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
  ref?: Ref<HTMLButtonElement>;
}

// Track/knob geometry per size. `pill` = hover width bump; `pressW`/`pressH` =
// the press squish (wider + shorter). Ported from Fluid Functionalism's Switch:
// the knob pill-extends on hover, squishes on press, is spring-animated, and can
// be dragged across to toggle (with a dead-zone). The themed track stays CSS.
const SIZES = {
  sm: { w: 30, h: 18, knob: 14, offset: 2, pill: 2, pressW: 3, pressH: 3 },
  md: { w: 36, h: 22, knob: 18, offset: 2, pill: 2, pressW: 4, pressH: 4 },
} as const;

export function SwitchControl({
  checked,
  onChange,
  size = "md",
  disabled = false,
  className,
  "aria-label": ariaLabel,
  ref,
}: SwitchControlProps) {
  const sz = SIZES[size];
  const travel = sz.w - sz.knob - sz.offset * 2;
  const knobTop = (sz.h - 2 - sz.knob) / 2; // center the knob inside the 1px-bordered track
  const reduced = !!useReducedMotion();
  const spring = reduced ? { duration: 0 } : SPRING_LAYOUT;

  const [hovered, setHovered] = useState(false);
  const [pressed, setPressed] = useState(false);
  const hasMounted = useRef(false);
  const dragging = useRef(false);
  const didDrag = useRef(false);
  const start = useRef<{ clientX: number; originX: number } | null>(null);
  const motionX = useMotionValue(checked ? sz.offset + travel : sz.offset);

  useEffect(() => {
    hasMounted.current = true;
  }, []);

  // Knob shape: press wins over hover. When checked, anchor the (possibly wider)
  // knob to the right edge so it never overflows the track.
  const thumbWidth = pressed ? sz.knob + sz.pressW : hovered ? sz.knob + sz.pill : sz.knob;
  const thumbHeight = pressed ? sz.knob - sz.pressH : sz.knob;
  const thumbY = pressed ? knobTop + sz.pressH / 2 : knobTop;
  const thumbX = checked ? sz.offset + travel - (thumbWidth - sz.knob) : sz.offset;

  // Settle the resting x on hover/press/checked change — never while dragging.
  useEffect(() => {
    if (dragging.current) return;
    if (!hasMounted.current) motionX.set(thumbX);
    else animate(motionX, thumbX, spring);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thumbX]);

  const dragMax = sz.w - sz.offset - (sz.knob + sz.pressW);

  const onPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    if (disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
    setPressed(true);
    dragging.current = false;
    didDrag.current = false;
    start.current = { clientX: e.clientX, originX: motionX.get() };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: PointerEvent<HTMLButtonElement>) => {
    if (!start.current) return;
    const delta = e.clientX - start.current.clientX;
    if (!dragging.current) {
      if (Math.abs(delta) < 2) return; // dead-zone: distinguish a drag from a tap
      dragging.current = true;
    }
    motionX.jump(Math.max(sz.offset, Math.min(dragMax, start.current.originX + delta)));
  };

  const endPointer = () => {
    if (!start.current) return;
    setPressed(false);
    if (dragging.current) {
      didDrag.current = true; // suppress the click that follows a drag
      dragging.current = false;
      const next = motionX.get() > (sz.offset + dragMax) / 2;
      if (next !== checked) onChange(next);
      else animate(motionX, thumbX, spring); // snap back to the resting position
      requestAnimationFrame(() => {
        didDrag.current = false;
      });
    }
    start.current = null;
  };

  return (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") setHovered(true);
      }}
      onPointerLeave={() => setHovered(false)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPointer}
      onPointerCancel={endPointer}
      onClick={() => {
        if (disabled || didDrag.current) return;
        onChange(!checked);
      }}
      className={clsx("switch-control", checked && "switch-control-on", className)}
      style={{ "--gs-track-w": `${sz.w}px`, "--gs-track-h": `${sz.h}px` } as CSSProperties}
    >
      <motion.span
        aria-hidden
        className="switch-control-knob"
        initial={false}
        style={{ x: motionX, top: 0, left: 0 }}
        animate={{ y: thumbY, width: thumbWidth, height: thumbHeight }}
        transition={hasMounted.current ? spring : { duration: 0 }}
      />
    </button>
  );
}

export default SwitchControl;
