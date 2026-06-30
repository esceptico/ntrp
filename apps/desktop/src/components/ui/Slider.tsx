import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type Ref,
} from "react";
import { motion, useMotionValue, useTransform, animate, useReducedMotion } from "motion/react";
import clsx from "clsx";
import { SPRING_TAP } from "@/lib/tokens/motion";

const THUMB_REST = 16;
const THUMB_PRESS = 20;
const TRACK_HEIGHT = 6;

/**
 * Map a pointer's clientX to a stepped, clamped slider value. Pure so the
 * pointer-drag math is unit-testable without a layout engine: `rect` is the
 * track's bounding box, the thumb travels between the track edges.
 */
export function valueFromPosition(
  clientX: number,
  rect: { left: number; width: number },
  min: number,
  max: number,
  step: number,
): number {
  if (rect.width <= 0 || max <= min) return min;
  const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
  const raw = min + ratio * (max - min);
  const snapped = Math.round((raw - min) / step) * step + min;
  return Math.max(min, Math.min(max, snapped));
}

const clamp = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

interface SliderProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  /** Larger jump for PageUp / PageDown. Defaults to 10× step. */
  pageStep?: number;
  /** Render a small value readout next to the track. */
  formatValue?: (value: number) => string;
  className?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  ref?: Ref<HTMLDivElement>;
}

/**
 * Single-value horizontal slider — track, filled range, and a draggable thumb
 * that grows on press. Ported (minimal) from Fluid Functionalism: the fill
 * width and thumb position ride motion values on the hot path (no React state
 * per pointermove), and the grow/spring is gated on reduced motion. Pointer
 * drag, keyboard stepping, and ARIA are hand-rolled (no radix).
 */
export function Slider({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
  pageStep,
  formatValue,
  className,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledby,
  ref,
}: SliderProps) {
  const reduced = !!useReducedMotion();
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Hot-path: 0..1 fill fraction drives both the fill width and thumb offset.
  const fraction = useMotionValue(max > min ? clamp((value - min) / (max - min), 0, 1) : 0);
  const fillWidth = useTransform(fraction, (f) => `${f * 100}%`);
  const thumbLeft = useTransform(fraction, (f) => `${f * 100}%`);
  const thumbSize = useMotionValue(THUMB_REST);

  // Keep the motion fraction in sync with controlled value changes (keyboard,
  // programmatic) — but never fight an in-progress drag.
  useLayoutEffect(() => {
    if (dragging.current) return;
    fraction.set(max > min ? clamp((value - min) / (max - min), 0, 1) : 0);
  }, [value, min, max, fraction]);

  const setFromPointer = useCallback(
    (clientX: number) => {
      const rect = trackRef.current?.getBoundingClientRect();
      if (!rect) return;
      const next = valueFromPosition(clientX, rect, min, max, step);
      // Update the fill/thumb immediately (no React state on the hot path),
      // then notify. The controlled value re-render confirms it.
      fraction.set(max > min ? clamp((next - min) / (max - min), 0, 1) : 0);
      if (next !== value) onChange(next);
    },
    [min, max, step, value, onChange, fraction],
  );

  const grow = useCallback(
    (pressed: boolean) => {
      const target = pressed ? THUMB_PRESS : THUMB_REST;
      if (reduced) thumbSize.set(target);
      else animate(thumbSize, target, SPRING_TAP);
    },
    [reduced, thumbSize],
  );

  const onPointerDown = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
      e.preventDefault();
      dragging.current = true;
      grow(true);
      e.currentTarget.setPointerCapture(e.pointerId);
      setFromPointer(e.clientX);
    },
    [disabled, grow, setFromPointer],
  );

  const onPointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (!dragging.current) return;
      setFromPointer(e.clientX);
    },
    [setFromPointer],
  );

  const endDrag = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    grow(false);
  }, [grow]);

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (disabled) return;
      const big = pageStep ?? step * 10;
      let next: number | null = null;
      switch (e.key) {
        case "ArrowRight":
        case "ArrowUp":
          next = value + step;
          break;
        case "ArrowLeft":
        case "ArrowDown":
          next = value - step;
          break;
        case "PageUp":
          next = value + big;
          break;
        case "PageDown":
          next = value - big;
          break;
        case "Home":
          next = min;
          break;
        case "End":
          next = max;
          break;
        default:
          return;
      }
      e.preventDefault();
      const clamped = clamp(next, min, max);
      if (clamped !== value) onChange(clamped);
    },
    [disabled, pageStep, step, value, min, max, onChange],
  );

  // Press-grow follows keyboard focus too (focus-visible only).
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (focused && !dragging.current) grow(true);
    else if (!focused && !dragging.current) grow(false);
  }, [focused, grow]);

  const readout = formatValue ? formatValue(value) : null;

  return (
    <div
      ref={ref}
      className={clsx("flex items-center gap-3 select-none", disabled && "opacity-50", className)}
    >
      <div
        ref={trackRef}
        className="relative h-5 flex-1 cursor-ew-resize touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {/* Track */}
        <div
          className="absolute inset-x-0 top-1/2 -translate-y-1/2 rounded-full bg-surface-soft"
          style={{
            height: TRACK_HEIGHT,
            boxShadow: "inset 0 0 0 1px var(--color-line)",
          }}
        >
          {/* Filled range */}
          <motion.div
            className="absolute inset-y-0 left-0 rounded-full bg-accent"
            style={{ width: fillWidth }}
          />
        </div>

        {/* Thumb — the focusable, ARIA-bearing control */}
        <motion.div
          role="slider"
          tabIndex={disabled ? -1 : 0}
          aria-orientation="horizontal"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledby}
          aria-disabled={disabled || undefined}
          onKeyDown={onKeyDown}
          onFocus={(e) => setFocused(e.currentTarget.matches(":focus-visible"))}
          onBlur={() => setFocused(false)}
          className="absolute top-1/2 rounded-full bg-surface-1 shadow-[0_1px_3px_rgba(0,0,0,0.18)] outline-none focus-visible:ring-2 focus-visible:ring-accent"
          style={{
            left: thumbLeft,
            width: thumbSize,
            height: thumbSize,
            x: "-50%",
            y: "-50%",
            border: "1px solid var(--color-line-strong)",
            transition: reduced ? "none" : undefined,
          }}
        />
      </div>

      {readout !== null && (
        <span className="min-w-[3ch] text-right text-[13px] tabular-nums text-ink-soft">
          {readout}
        </span>
      )}
    </div>
  );
}

// ─── Range (two-thumb) ──────────────────────────────────────────────────────

interface RangeSliderProps {
  /** [low, high] — kept ordered (low ≤ high) by the component. */
  value: [number, number];
  onChange: (value: [number, number]) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  /** Formats each end for the readout, e.g. minutes → "HH:MM". */
  formatValue?: (value: number) => string;
  className?: string;
  "aria-label"?: string;
  ref?: Ref<HTMLDivElement>;
}

/** Clamp `value` to [low, high], keeping the two ends ordered. */
export function orderRange(
  thumb: 0 | 1,
  next: number,
  [low, high]: [number, number],
  min: number,
  max: number,
): [number, number] {
  const v = clamp(next, min, max);
  return thumb === 0 ? [Math.min(v, high), high] : [low, Math.max(v, low)];
}

/**
 * Two-thumb range slider — same track/thumb/`valueFromPosition` as {@link Slider},
 * with the fill drawn BETWEEN the thumbs. Pointer grabs the nearer thumb; each
 * thumb is its own `role="slider"` (Arrow/Page/Home/End), bounded by the other so
 * they can't cross. Position is controlled (no per-move React-free hot path —
 * a settings range slider isn't dragged continuously like a primary control).
 */
export function RangeSlider({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled = false,
  formatValue,
  className,
  "aria-label": ariaLabel,
  ref,
}: RangeSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<0 | 1 | null>(null);
  const [low, high] = value;
  const pct = (v: number) => (max > min ? clamp((v - min) / (max - min), 0, 1) * 100 : 0);

  const move = (thumb: 0 | 1, next: number) => {
    const ordered = orderRange(thumb, next, value, min, max);
    if (ordered[0] !== low || ordered[1] !== high) onChange(ordered);
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return;
    e.preventDefault();
    const v = valueFromPosition(e.clientX, rect, min, max, step);
    // Grab the nearer thumb; tie goes to the one the pointer is past.
    const thumb: 0 | 1 = Math.abs(v - low) < Math.abs(v - high) || v < low ? 0 : 1;
    dragging.current = thumb;
    e.currentTarget.setPointerCapture(e.pointerId);
    move(thumb, v);
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (dragging.current === null) return;
    const rect = trackRef.current?.getBoundingClientRect();
    if (rect) move(dragging.current, valueFromPosition(e.clientX, rect, min, max, step));
  };

  const endDrag = () => {
    dragging.current = null;
  };

  const onThumbKey = (thumb: 0 | 1) => (e: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    const cur = thumb === 0 ? low : high;
    const big = step * 10;
    let next: number | null = null;
    switch (e.key) {
      case "ArrowRight":
      case "ArrowUp": next = cur + step; break;
      case "ArrowLeft":
      case "ArrowDown": next = cur - step; break;
      case "PageUp": next = cur + big; break;
      case "PageDown": next = cur - big; break;
      case "Home": next = min; break;
      case "End": next = max; break;
      default: return;
    }
    e.preventDefault();
    move(thumb, next);
  };

  return (
    <div
      ref={ref}
      className={clsx("flex items-center gap-3 select-none", disabled && "opacity-50", className)}
    >
      <div
        ref={trackRef}
        className="relative h-5 flex-1 cursor-ew-resize touch-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          className="absolute inset-x-0 top-1/2 -translate-y-1/2 rounded-full bg-surface-soft"
          style={{ height: TRACK_HEIGHT, boxShadow: "inset 0 0 0 1px var(--color-line)" }}
        >
          {/* Fill BETWEEN the thumbs. */}
          <div
            className="absolute inset-y-0 rounded-full bg-accent"
            style={{ left: `${pct(low)}%`, right: `${100 - pct(high)}%` }}
          />
        </div>
        {([low, high] as const).map((v, i) => {
          const thumb = i as 0 | 1;
          return (
            <div
              key={thumb}
              role="slider"
              tabIndex={disabled ? -1 : 0}
              aria-orientation="horizontal"
              aria-valuemin={thumb === 0 ? min : low}
              aria-valuemax={thumb === 0 ? high : max}
              aria-valuenow={v}
              aria-valuetext={formatValue ? formatValue(v) : undefined}
              aria-label={ariaLabel ? `${ariaLabel} ${thumb === 0 ? "start" : "end"}` : undefined}
              aria-disabled={disabled || undefined}
              onKeyDown={onThumbKey(thumb)}
              className="absolute top-1/2 rounded-full bg-surface-1 shadow-[0_1px_3px_rgba(0,0,0,0.18)] outline-none focus-visible:ring-2 focus-visible:ring-accent"
              style={{
                left: `${pct(v)}%`,
                width: THUMB_REST,
                height: THUMB_REST,
                transform: "translate(-50%,-50%)",
                border: "1px solid var(--color-line-strong)",
              }}
            />
          );
        })}
      </div>

      {formatValue && (
        <span className="whitespace-nowrap text-[13px] tabular-nums text-ink-soft">
          {formatValue(low)}–{formatValue(high)}
        </span>
      )}
    </div>
  );
}

export default Slider;
