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

// "plain" = no animated indicator; the active state is the item's own static
// tint (matches the app's tint-only vertical menus, no out-of-place slide).
type Variant = "underline" | "pill" | "plain";
type Orientation = "horizontal" | "vertical";

interface TabsContextValue {
  value: string;
  onChange: (value: string) => void;
  orientation: Orientation;
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
 * `.t-tabs-indicator`'s CSS transition owns the tween, so the pill (or
 * underline) slides between the previous and next measured positions.
 * Offsets — not getBoundingClientRect — so a parent's open/close transform
 * never skews the measurement. Reduced motion is the stylesheet's
 * prefers-reduced-motion guard.
 */
export function Tabs({
  value,
  onChange,
  variant = "underline",
  orientation = "horizontal",
  indicatorClassName,
  className,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  variant?: Variant;
  orientation?: Orientation;
  indicatorClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const indicatorRef = useRef<HTMLSpanElement | null>(null);
  const mounted = useRef(false);

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
    if (animate) {
      write();
      return;
    }
    // Snap: suspend the transition, write, reflow, restore — otherwise first
    // paint and resize tween in from translate(0, 0) / width 0.
    const prev = el.style.transition;
    el.style.transition = "none";
    write();
    void el.offsetWidth;
    el.style.transition = prev;
  }, []);

  // No dep array on purpose: labels resize without `value` changing (count
  // suffixes), and a re-measure that lands on identical values is a no-op.
  useLayoutEffect(() => {
    moveTo(mounted.current);
    mounted.current = true;
  });

  useEffect(() => {
    const onResize = () => moveTo(false);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [moveTo]);

  return (
    <TabsContext.Provider value={{ value, onChange, orientation }}>
      <div
        ref={listRef}
        role="tablist"
        aria-orientation={orientation}
        className={clsx("relative flex", orientation === "vertical" && "flex-col", className)}
      >
        {variant !== "plain" && (
          <span
            ref={indicatorRef}
            aria-hidden="true"
            data-tab-indicator={variant}
            className={clsx(
              "t-tabs-indicator",
              variant === "pill" &&
                (indicatorClassName ??
                  "rounded-lg bg-surface-soft shadow-[inset_0_0_0_1px_var(--color-line-soft)]"),
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
  className,
  children,
}: {
  value: string;
  className?: string;
  children: ReactNode;
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
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      data-active={active ? "true" : undefined}
      data-tab-value={value}
      onClick={() => ctx.onChange(value)}
      onKeyDown={onKeyDown}
      className={clsx("group relative", className)}
    >
      {children}
    </button>
  );
}
