import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  type ReactNode,
} from "react";
import clsx from "clsx";

// The one tabs primitive:
//   "underline" — sliding 2px bar under the active tab (modal header tabs).
//   "segmented" — transitions.dev capsule: tinted track + elevated pill that
//                 slides between segments; items get size/color styling.
//   "plain"     — no animated indicator; the active state is the item's own
//                 static tint (the app's tint-only vertical menus).
type Variant = "underline" | "plain" | "segmented";
type Orientation = "horizontal" | "vertical";
type Size = "sm" | "md" | "lg";

// Literal class strings so Tailwind sees them.
const ITEM_SIZE: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-[33px] px-3 text-[13px]",
  lg: "h-10 px-3.5 text-sm",
};

interface TabsContextValue {
  value: string;
  onChange: (value: string) => void;
  orientation: Orientation;
  variant: Variant;
  size: Size;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("<Tab> must be used inside <Tabs>");
  return ctx;
}

/**
 * transitions.dev "tabs sliding": one persistent indicator element per
 * tablist. JS writes the active tab's measured offsets/size inline and
 * `.t-tabs-indicator`'s CSS transition owns the tween, so the indicator
 * slides between the previous and next measured positions. Offsets — not
 * getBoundingClientRect — so a parent's open/close transform never skews the
 * measurement. Reduced motion is the stylesheet's prefers-reduced-motion
 * guard.
 */
export function Tabs({
  value,
  onChange,
  variant = "underline",
  orientation = "horizontal",
  size = "md",
  label,
  indicatorClassName,
  className,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  variant?: Variant;
  orientation?: Orientation;
  /** Segment sizing for variant="segmented" items. */
  size?: Size;
  /** Accessible name for the group — maps to aria-label on the tablist. */
  label?: string;
  indicatorClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const indicatorRef = useRef<HTMLSpanElement | null>(null);

  const moveTo = useCallback((animate: boolean) => {
    const el = indicatorRef.current;
    if (!el) return;
    const tab = listRef.current?.querySelector<HTMLElement>('[role="tab"][data-active]');
    const write = () => {
      if (!tab) {
        el.style.width = "0px";
        el.style.height = "0px";
        return;
      }
      const underline = el.dataset.tabIndicator === "underline";
      // Underline reproduces the old static geometry: 2px bar, 1px below the
      // tab's bottom edge (-bottom-px).
      const y = underline ? tab.offsetTop + tab.offsetHeight - 1 : tab.offsetTop;
      el.style.transform = `translate(${tab.offsetLeft}px, ${y}px)`;
      el.style.width = `${tab.offsetWidth}px`;
      el.style.height = underline ? "2px" : `${tab.offsetHeight}px`;
    };
    // A fresh element — first paint, or React recreated the span and dropped
    // our inline styles — must never tween from the stylesheet's 0×0
    // defaults (reads as the pill growing out of the track corner).
    const fresh = !el.style.width || el.style.width === "0px";
    if (animate && !fresh) {
      write();
      return;
    }
    // Snap: suspend the transition, write, reflow, restore.
    const prev = el.style.transition;
    el.style.transition = "none";
    write();
    void el.offsetWidth;
    el.style.transition = prev;
  }, []);

  // No dep array on purpose: labels resize without `value` changing (count
  // suffixes), and a re-measure that lands on identical values is a no-op.
  useLayoutEffect(() => {
    moveTo(true);
  });

  useEffect(() => {
    const onResize = () => moveTo(false);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [moveTo]);

  const segmented = variant === "segmented";
  return (
    <TabsContext.Provider value={{ value, onChange, orientation, variant, size }}>
      <div
        ref={listRef}
        role="tablist"
        aria-label={label}
        aria-orientation={orientation}
        className={clsx(
          "relative flex",
          orientation === "vertical" && "flex-col",
          segmented &&
            "segmented-control inline-flex items-center gap-[3px] rounded-full p-[3px] bg-[color-mix(in_oklab,var(--color-ink)_6%,transparent)]",
          className,
        )}
      >
        {variant !== "plain" && (
          <span
            ref={indicatorRef}
            aria-hidden="true"
            data-tab-indicator={variant}
            className={clsx(
              "t-tabs-indicator",
              segmented &&
                (indicatorClassName ?? "rounded-full bg-surface-3 shadow-[var(--shadow-2)]"),
              variant === "underline" && "rounded-full bg-ink",
            )}
          />
        )}
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function Tab({
  value,
  id,
  "aria-label": ariaLabel,
  className,
  children,
}: {
  value: string;
  id?: string;
  /** Accessible name for icon-only tabs. */
  "aria-label"?: string;
  className?: string;
  children?: ReactNode;
}) {
  const ctx = useTabsContext();
  const active = ctx.value === value;

  // APG tabs pattern: arrow keys (orientation-aware) + Home/End move between
  // tabs with automatic activation; roving tabindex keeps only the selected
  // tab in the Tab sequence.
  const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    const horizontal = ctx.orientation === "horizontal";
    const nextKey = horizontal ? "ArrowRight" : "ArrowDown";
    const prevKey = horizontal ? "ArrowLeft" : "ArrowUp";
    if (![nextKey, prevKey, "Home", "End"].includes(e.key)) return;
    const tablist = e.currentTarget.closest('[role="tablist"]');
    if (!tablist) return;
    const tabs = Array.from(
      tablist.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])'),
    );
    const idx = tabs.indexOf(e.currentTarget);
    if (idx === -1) return;
    e.preventDefault();
    const next =
      e.key === "Home" ? 0
      : e.key === "End" ? tabs.length - 1
      : e.key === nextKey ? (idx + 1) % tabs.length
      : (idx - 1 + tabs.length) % tabs.length;
    const target = tabs[next];
    target.focus();
    const nextValue = target.getAttribute("data-tab-value");
    if (nextValue !== null) ctx.onChange(nextValue);
  };

  return (
    <button
      type="button"
      role="tab"
      id={id}
      aria-label={ariaLabel}
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      data-active={active ? "true" : undefined}
      data-tab-value={value}
      onClick={() => ctx.onChange(value)}
      onKeyDown={onKeyDown}
      className={clsx(
        "group relative",
        ctx.variant === "segmented" &&
          clsx(
            "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full font-medium",
            "text-muted hover:text-ink data-[active]:text-ink",
            "[transition:color_var(--tabs-dur)_var(--tabs-ease)]",
            "outline-none focus-visible:ring-2 focus-visible:ring-accent",
            ITEM_SIZE[ctx.size],
          ),
        className,
      )}
    >
      {children}
    </button>
  );
}
