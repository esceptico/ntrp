import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useId,
  useRef,
  type CSSProperties,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
  type Ref,
} from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SPRING_LAYOUT, SPRING_TAP, MOTION } from "@/lib/tokens/motion";
import { useProximityHover, useRegisterProximityItem } from "@/hooks/useProximityHover";

type Size = "sm" | "md" | "lg";

const SIZES = {
  sm: { pad: 4, h: 32, font: 12, gap: 2, padX: 14 },
  md: { pad: 5, h: 40, font: 13, gap: 3, padX: 18 },
  lg: { pad: 6, h: 48, font: 14, gap: 4, padX: 22 },
} as const;

// The pill reads better slightly larger than the button it highlights.
const PILL_GROW = 2;

interface SegmentedContextValue {
  value: string;
  onChange: (value: string) => void;
  size: Size;
  layoutId: string;
  reduced: boolean;
  registerItem: (index: number, el: HTMLElement | null) => void;
}

const SegmentedContext = createContext<SegmentedContextValue | null>(null);

interface SegmentedControlProps {
  value: string;
  onChange: (value: string) => void;
  /** SegmentedControlItem children, composed directly (icon + label, icon-only, …). */
  children: ReactNode;
  size?: Size;
  /** Accessible name for the group — maps to aria-label on the tablist. */
  label?: string;
  className?: string;
  ref?: Ref<HTMLDivElement>;
}

/**
 * Compound segmented control. Compose options as <SegmentedControlItem> children
 * so each segment can carry an icon, a label, or both (icon-only via aria-label) —
 * the caller owns the content. Colors come from the --gt-* tokens (light + dark);
 * the active pill slides between segments via a shared layout animation.
 *
 * Arrow-key navigation reads the rendered `[role="tab"]` buttons from the DOM, so
 * items can be any direct children (including a `.map(...)`).
 *
 * A faint hover ghost (FF "fluid hover") springs between segments under the
 * pointer, sitting behind the selected pill. It's additive: items self-register
 * their measured rect via a `__index` the provider injects with `Children.map`,
 * so consumers don't change. Skipped under reduced-motion.
 */
export function SegmentedControl({
  value,
  onChange,
  children,
  size = "md",
  label,
  className,
  ref,
}: SegmentedControlProps) {
  const sz = SIZES[size];
  const layoutId = useId();
  const reduced = !!useReducedMotion();

  const containerRef = useRef<HTMLDivElement | null>(null);
  const { activeIndex, itemRects, handlers, registerItem } = useProximityHover(containerRef, {
    axis: "x",
  });

  const setRefs = useCallback(
    (node: HTMLDivElement | null) => {
      containerRef.current = node;
      if (typeof ref === "function") ref(node);
      else if (ref) (ref as { current: HTMLDivElement | null }).current = node;
    },
    [ref],
  );

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const tabs = Array.from(
      e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    );
    if (tabs.length === 0) return;
    const idx = tabs.findIndex((t) => t.dataset.value === value);
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    const btn = tabs[next];
    btn.focus();
    const v = btn.dataset.value;
    if (v && v !== value) onChange(v);
  };

  const trackStyle: CSSProperties = {
    position: "relative",
    display: "inline-flex",
    // Buttons stretch to the pill's vertical bounds: the track's vertical
    // padding doubles as the pill inset, so the layoutId indicator inside
    // the active button needs no measurement.
    alignItems: "stretch",
    gap: sz.gap,
    height: sz.h,
    padding: `${Math.max(2, sz.pad - PILL_GROW)}px ${sz.pad}px`,
    borderRadius: 999,
    background: "var(--gt-track-bg)",
    border: "1px solid var(--gt-track-border)",
    boxShadow: "var(--gt-track-shadow)",
  };

  const ctx: SegmentedContextValue = { value, onChange, size, layoutId, reduced, registerItem };
  const hoverRect = activeIndex != null ? itemRects[activeIndex] : null;

  return (
    <div
      ref={setRefs}
      role="tablist"
      aria-label={label}
      className={["segmented-control", className].filter(Boolean).join(" ")}
      style={trackStyle}
      onKeyDown={onKeyDown}
      onMouseMove={handlers.onMouseMove}
      onMouseEnter={handlers.onMouseEnter}
      onMouseLeave={handlers.onMouseLeave}
    >
      <SegmentedContext.Provider value={ctx}>
        <AnimatePresence>
          {!reduced && hoverRect && (
            <motion.span
              key="segmented-hover"
              aria-hidden
              initial={{
                opacity: 0,
                left: hoverRect.left,
                top: hoverRect.top,
                width: hoverRect.width,
                height: hoverRect.height,
              }}
              animate={{
                opacity: 1,
                left: hoverRect.left,
                top: hoverRect.top,
                width: hoverRect.width,
                height: hoverRect.height,
              }}
              exit={{ opacity: 0, transition: { duration: MOTION.fast } }}
              transition={{ ...SPRING_TAP, opacity: { duration: MOTION.fast } }}
              style={{
                position: "absolute",
                zIndex: 0,
                borderRadius: 999,
                background: "var(--gt-hover-bg)",
                pointerEvents: "none",
              }}
            />
          )}
        </AnimatePresence>
        {Children.map(children, (child, i) =>
          isValidElement(child)
            ? cloneElement(child as ReactElement<{ __index?: number }>, { __index: i })
            : child,
        )}
      </SegmentedContext.Provider>
    </div>
  );
}

interface SegmentedControlItemProps {
  value: string;
  /** Segment content — text, an icon, or both (icon-only: pass `aria-label`). */
  children?: ReactNode;
  id?: string;
  "aria-label"?: string;
  /** Injected by SegmentedControl via Children.map — the segment's DOM index,
   *  used to register its measured rect for the proximity hover. */
  __index?: number;
}

export function SegmentedControlItem({
  value,
  children,
  id,
  "aria-label": ariaLabel,
  __index = 0,
}: SegmentedControlItemProps) {
  const ctx = useContext(SegmentedContext);
  if (!ctx) throw new Error("SegmentedControlItem must be used within SegmentedControl");
  const sz = SIZES[ctx.size];
  const active = ctx.value === value;
  const btnRef = useRef<HTMLButtonElement | null>(null);
  useRegisterProximityItem(ctx.registerItem, __index, btnRef);

  return (
    <button
      ref={btnRef}
      id={id}
      type="button"
      role="tab"
      data-value={value}
      aria-selected={active}
      aria-label={ariaLabel}
      tabIndex={active ? 0 : -1}
      onClick={() => ctx.onChange(value)}
      style={{
        position: "relative",
        isolation: "isolate",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        lineHeight: 1,
        padding: `0 ${sz.padX}px`,
        fontSize: sz.font,
        fontWeight: active ? 600 : 500,
        color: active ? "var(--gt-fg)" : "var(--gt-fg-muted)",
        background: "transparent",
        border: "none",
        borderRadius: 999,
        cursor: "pointer",
        appearance: "none",
        WebkitAppearance: "none",
        whiteSpace: "nowrap",
        transition: "color var(--duration-trace) var(--ease-out-soft)",
        userSelect: "none",
      }}
    >
      {active && (
        <motion.span
          aria-hidden
          layoutId={`${ctx.layoutId}-pill`}
          className="segmented-control-pill"
          transition={ctx.reduced ? { layout: { duration: 0 } } : { layout: SPRING_LAYOUT }}
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: -PILL_GROW,
            right: -PILL_GROW,
            zIndex: -1,
            borderRadius: 999,
            background: "var(--gt-pill-bg)",
            border: "1px solid var(--gt-pill-border)",
            boxShadow: "var(--gt-pill-shadow)",
            pointerEvents: "none",
          }}
        />
      )}
      {children}
    </button>
  );
}

export default SegmentedControl;
