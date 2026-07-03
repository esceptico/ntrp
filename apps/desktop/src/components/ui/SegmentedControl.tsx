import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type FocusEvent,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
  type Ref,
} from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SPRING_LAYOUT, SPRING_TAP } from "@/lib/tokens/motion";
import { useProximityHover, useRegisterProximityItem, type ItemRect } from "@/hooks/useProximityHover";

type Size = "sm" | "md" | "lg";

const SIZES = {
  sm: { h: 28, padX: 10, font: 12 },
  md: { h: 33, padX: 12, font: 13 },
  lg: { h: 40, padX: 14, font: 14 },
} as const;

// FF's bg-active (overlay 7% light / 10% dark) — same fill as RadioGroup /
// CheckboxGroup so every FF-style selection control shares one language.
// The hover pill is this fill at 0.4 element-opacity, per FF tabs-subtle.
const SELECTED_FILL = "color-mix(in oklab, var(--color-ink) 7%, transparent)";

interface SegmentedContextValue {
  value: string;
  onChange: (value: string) => void;
  size: Size;
  hoveredIndex: number | null;
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

const rectPose = (r: ItemRect) => ({ left: r.left, top: r.top, width: r.width, height: r.height });

/**
 * FF "tabs-subtle", adapted to ntrp's compound value/onChange API. Trackless:
 * no capsule border — the selection reads through a quiet tinted pill that
 * springs between segments, and the fluid details carry the feel:
 *   - the hover pill GROWS OUT of the selected pill, and on pointer exit
 *     retreats back into it while fading;
 *   - the selected pill dims to 0.8 while another segment is hovered;
 *   - a focus-visible ring travels between segments (accent, not FF's
 *     hard-coded blue);
 *   - string labels reserve their semibold width with an invisible ghost so
 *     the weight shift never moves siblings.
 * Divergence from FF, kept deliberately: arrow keys select (automatic
 * activation) — the house pattern shared with Tabs/RadioGroup — where FF
 * only moves focus.
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
  const reduced = !!useReducedMotion();

  const containerRef = useRef<HTMLDivElement | null>(null);
  const mouseInsideRef = useRef(false);
  const { activeIndex: hoveredIndex, itemRects, handlers, registerItem, measureItems } =
    useProximityHover(containerRef, { axis: "x" });
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);

  // Child order == registration order (__index), so the selected rect is
  // just the value's position among the children.
  const values: string[] = [];
  Children.forEach(children, (child) => {
    if (isValidElement(child)) values.push((child.props as { value: string }).value);
  });
  const selectedIndex = values.indexOf(value);

  // Labels can change (e.g. count suffixes) without any register/unregister.
  useEffect(() => {
    measureItems();
  }, [measureItems, children]);

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

  const onFocus = (e: FocusEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const v = target.dataset.value;
    setFocusedIndex(v !== undefined && target.matches(":focus-visible") ? values.indexOf(v) : null);
  };
  const onBlur = (e: FocusEvent<HTMLDivElement>) => {
    if (containerRef.current?.contains(e.relatedTarget as Node)) return;
    setFocusedIndex(null);
  };

  const selectedRect = selectedIndex >= 0 ? itemRects[selectedIndex] : undefined;
  const hoverRect = hoveredIndex != null ? itemRects[hoveredIndex] : undefined;
  const isHoveringSelected = hoveredIndex === selectedIndex;
  const isHoveringOther = hoveredIndex != null && !isHoveringSelected;
  const focusRect = focusedIndex != null && focusedIndex >= 0 ? itemRects[focusedIndex] : undefined;

  const ctx: SegmentedContextValue = { value, onChange, size, hoveredIndex, registerItem };

  return (
    <div
      ref={setRefs}
      role="tablist"
      aria-label={label}
      className={["segmented-control relative inline-flex items-center gap-0.5 select-none", className]
        .filter(Boolean)
        .join(" ")}
      onKeyDown={onKeyDown}
      onFocus={onFocus}
      onBlur={onBlur}
      onMouseMove={(e) => {
        mouseInsideRef.current = true;
        handlers.onMouseMove(e);
      }}
      onMouseEnter={handlers.onMouseEnter}
      onMouseLeave={() => {
        mouseInsideRef.current = false;
        handlers.onMouseLeave();
      }}
    >
      {/* Selected pill — container-level so it can dim under a hover
          elsewhere and hand its rect to the hover pill's enter/exit. */}
      {selectedRect && (
        <motion.div
          aria-hidden
          className="absolute rounded-lg pointer-events-none"
          style={{ background: SELECTED_FILL }}
          initial={false}
          animate={{ ...rectPose(selectedRect), opacity: isHoveringOther ? 0.8 : 1 }}
          transition={
            reduced ? { duration: 0 } : { ...SPRING_LAYOUT, opacity: { duration: 0.08 } }
          }
        />
      )}
      {/* Hover pill — born from the selected pill, retreats into it when the
          pointer leaves the control (fade-only if it unmounts another way). */}
      <AnimatePresence>
        {!reduced && hoverRect && !isHoveringSelected && selectedRect && (
          <motion.div
            key="hover-pill"
            aria-hidden
            className="absolute rounded-lg pointer-events-none"
            style={{ background: SELECTED_FILL }}
            initial={{ ...rectPose(selectedRect), opacity: 0 }}
            animate={{ ...rectPose(hoverRect), opacity: 0.4 }}
            exit={
              !mouseInsideRef.current
                ? {
                    ...rectPose(selectedRect),
                    opacity: 0,
                    transition: { ...SPRING_LAYOUT, opacity: { duration: 0.06 } },
                  }
                : { opacity: 0, transition: { duration: 0.06 } }
            }
            transition={{ ...SPRING_TAP, opacity: { duration: 0.08 } }}
          />
        )}
      </AnimatePresence>
      {/* Traveling focus-visible ring — concentric +2px over the pill. */}
      <AnimatePresence>
        {focusRect && (
          <motion.div
            aria-hidden
            className="absolute z-20 rounded-[10px] border border-accent pointer-events-none"
            initial={false}
            animate={{
              left: focusRect.left - 2,
              top: focusRect.top - 2,
              width: focusRect.width + 4,
              height: focusRect.height + 4,
            }}
            exit={{ opacity: 0, transition: { duration: 0.06 } }}
            transition={
              reduced ? { duration: 0 } : { ...SPRING_TAP, opacity: { duration: 0.08 } }
            }
          />
        )}
      </AnimatePresence>
      <SegmentedContext.Provider value={ctx}>
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
   *  used to register its measured rect for the pills. */
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
  const selected = ctx.value === value;
  const active = selected || ctx.hoveredIndex === __index;
  const btnRef = useRef<HTMLButtonElement | null>(null);
  useRegisterProximityItem(ctx.registerItem, __index, btnRef);

  const buttonStyle: CSSProperties = {
    position: "relative",
    zIndex: 10,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    lineHeight: 1,
    height: sz.h,
    padding: `0 ${sz.padX}px`,
    fontSize: sz.font,
    color: active ? "var(--color-ink)" : "var(--color-muted)",
    background: "transparent",
    border: "none",
    borderRadius: 8,
    outline: "none",
    cursor: "pointer",
    appearance: "none",
    WebkitAppearance: "none",
    whiteSpace: "nowrap",
    transition: "color 80ms var(--ease-out-soft)",
    userSelect: "none",
  };

  return (
    <button
      ref={btnRef}
      id={id}
      type="button"
      role="tab"
      data-value={value}
      aria-selected={selected}
      aria-label={ariaLabel}
      tabIndex={selected ? 0 : -1}
      onClick={() => ctx.onChange(value)}
      style={buttonStyle}
    >
      {typeof children === "string" ? (
        // Invisible semibold ghost reserves the selected width so the weight
        // shift never nudges neighboring segments (FF's inline-grid trick).
        <span className="inline-grid">
          <span aria-hidden className="col-start-1 row-start-1 invisible font-semibold">
            {children}
          </span>
          <span
            className="col-start-1 row-start-1"
            style={{ fontWeight: selected ? 600 : 500 }}
          >
            {children}
          </span>
        </span>
      ) : (
        children
      )}
    </button>
  );
}

export default SegmentedControl;
